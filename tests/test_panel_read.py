import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest
from docker.errors import DockerException
from fastapi.testclient import TestClient

from panel.app import create_app
from panel.docker_read import DockerReader, classify, parse_log_line
from panel.health import HealthState, Prober
from panel.host import host_metrics, parse_loadavg, parse_meminfo, parse_os_release, parse_uptime
from panel.registry import Registry

NOW = datetime(2026, 10, 4, 12, 0, 0, tzinfo=UTC)
TOKEN = "t" * 32
AUTH = {"Authorization": f"Bearer {TOKEN}"}


class FakeContainer:
    def __init__(self, service, status="running", exit_code=0, started="2026-10-04T10:00:00.123456789Z",
                 logs=b"", tags=("ghcr.io/ichmaster/matrix-agora-agent:latest",)):
        self.service, self.status, self._logs = service, status, logs
        self.attrs = {"State": {"ExitCode": exit_code, "StartedAt": started}}
        self.image = SimpleNamespace(tags=list(tags))
        self.tail_asked = None

    def logs(self, tail, stdout, stderr):
        self.tail_asked = tail
        return self._logs


class FakeClient:
    def __init__(self, containers):
        self.by_service = {c.service: c for c in containers}
        self.containers = self

    def ping(self):
        return True

    def list(self, all=False, filters=None):
        labels = (filters or {}).get("label", [])
        if labels:
            service = labels[1].split("=", 1)[1]
            assert labels[0] == "com.docker.compose.project=server"  # found by compose labels, never by name
            return [self.by_service[service]] if service in self.by_service else []
        return [c for c in self.by_service.values() if c.status == "running"]


def broken():
    raise DockerException("socket gone")


OUR_LOG = (b"2026-10-04 13:26:02,101 agent INFO ada: session restored (device X)\n"
           b"2026-10-04 13:52:40,500 agent WARNING sync failed: homeserver unreachable; retry in 10s\n")
HS_LOG = b"\x1b[2m2026-10-04T10:26:02.123Z\x1b[0m  INFO conduwuit::router: Listening on 0.0.0.0:8008\n"


def reader(*containers):
    return DockerReader(client_factory=lambda: FakeClient(containers), clock=lambda: NOW)


# --- docker ---
@pytest.mark.parametrize("status,code,want", [("running", 0, "running"), ("exited", 0, "stopped"),
                                              ("exited", 143, "stopped"), ("exited", 137, "stopped"),
                                              ("exited", 1, "crashed"), ("dead", 0, "crashed"),
                                              ("created", 0, "stopped")])
def test_container_states(status, code, want):
    assert classify(status, code) == want


def test_container_info_uptime_image_missing_and_unreachable():
    r = reader(FakeContainer("ada"), FakeContainer("bruno", status="exited", exit_code=0))
    ada = r.container("ada")
    assert (ada.state, ada.uptime_s, ada.image) == ("running", 7200, "matrix-agora-agent")
    assert r.container("bruno").state == "stopped" and r.container("bruno").uptime_s is None
    assert r.container("usage-report").state == "missing"
    assert DockerReader(client_factory=broken).container("ada").state == "unknown"
    assert DockerReader(client_factory=broken).available() is False
    assert r.running_count() == 1


def test_log_tails_parse_both_formats_oldest_first():
    c = FakeContainer("homeserver", logs=HS_LOG + OUR_LOG)
    lines = reader(c).logs("homeserver", 200)
    assert c.tail_asked == 200
    assert lines[0] == {"time": "10:26:02", "source": "conduwuit::router", "level": "INFO",
                        "message": "Listening on 0.0.0.0:8008"}  # ANSI stripped
    assert lines[1]["source"] == "agent" and lines[2]["level"] == "WARNING"
    assert reader().logs("ada", 10) is None and DockerReader(client_factory=broken).logs("ada", 10) is None
    assert parse_log_line("plain text") == {"time": "", "source": "", "level": "", "message": "plain text"}


# --- the probe ---
def test_the_probe_reports_healthy_unreachable_and_latency():
    reg = Registry()

    def run(handler):
        p = Prober(reg, transport=httpx.MockTransport(handler), clock=lambda: 1000.0)
        return asyncio.run(p.check("agora")), p

    ok, p = run(lambda req: httpx.Response(200, json={"versions": []}))
    assert ok.status == "healthy" and ok.latency_ms is not None and ok.checked_at == 1000.0
    assert p.url(reg.simulation("agora")) == "http://homeserver:8008/_matrix/client/versions"
    assert run(lambda req: httpx.Response(502)).__getitem__(0).status == "unreachable"

    def refuse(req):
        raise httpx.ConnectError("refused")
    down, _ = run(refuse)
    assert (down.status, down.latency_ms) == ("unreachable", None)


# --- host ---
MEMINFO = "MemTotal:        8000000 kB\nMemFree:  100 kB\nMemAvailable:    6000000 kB\n"


def test_host_parsers_and_degrade(tmp_path):
    assert parse_uptime("140400.55 280000.10\n") == 140400
    assert parse_meminfo(MEMINFO) == (8000000 * 1024, 2000000 * 1024)
    assert parse_loadavg("0.12 0.20 0.18 1/234 5678\n") == (0.12, 0.20, 0.18)
    assert parse_os_release('NAME="Ubuntu"\nPRETTY_NAME="Ubuntu 22.04.5 LTS"\n') == "Ubuntu 22.04.5 LTS"
    proc = tmp_path / "proc"
    proc.mkdir()
    (proc / "uptime").write_text("100.0 1.0")
    (proc / "meminfo").write_text(MEMINFO)  # loadavg missing → None, never an exception
    m = host_metrics(proc, tmp_path, tmp_path / "missing-os-release")
    assert m["uptime_s"] == 100 and m["memory"]["used"] == 2000000 * 1024
    assert m["load"] is None and m["os"] is None and m["disk"]["total"] > 0


# --- the API ---
@pytest.fixture
def make(tmp_path):
    def _make(docker_reader, health="healthy", state_ok=True):
        prober = Prober(Registry())
        prober.states["agora"] = HealthState(health, 42 if health == "healthy" else None, 1.0)
        state = tmp_path / "state"
        state.mkdir(exist_ok=True)
        state.chmod(0o700 if state_ok else 0o000)
        app = create_app(token=TOKEN, docker_reader=docker_reader, prober=prober, state_dir=state,
                         proc=tmp_path, os_release=tmp_path / "x", background=False)
        return TestClient(app)
    yield _make
    (tmp_path / "state").chmod(0o700)


def test_simulation_and_agent_views(make):
    c = make(reader(FakeContainer("homeserver", tags=("forgejo.ellis.link/continuwuation/continuwuity@sha256:abc",)),
                    FakeContainer("ada"), FakeContainer("bruno", status="exited")))
    sim = c.get("/api/simulations/agora", headers=AUTH).json()
    assert sim["health"]["status"] == "healthy" and sim["health"]["latency_ms"] == 42
    assert sim["service_states"]["homeserver"]["state"] == "running"
    ada = c.get("/api/agents/ada", headers=AUTH).json()
    assert ada["container_state"]["state"] == "running" and ada["container_state"]["uptime_s"] == 7200
    assert c.get("/api/agents/bruno", headers=AUTH).json()["container_state"]["state"] == "stopped"


def test_log_routes_clamp_and_refuse_unknown_services(make):
    hs = FakeContainer("homeserver", logs=HS_LOG)
    c = make(reader(hs, FakeContainer("ada", logs=OUR_LOG)))
    body = c.get("/api/simulations/agora/logs?service=homeserver&tail=99999", headers=AUTH).json()
    assert body["available"] and hs.tail_asked == 500
    c.get("/api/simulations/agora/logs?service=homeserver&tail=-5", headers=AUTH)
    assert hs.tail_asked == 1
    assert c.get("/api/simulations/agora/logs?service=ada", headers=AUTH).status_code == 404  # an agent, not a service
    assert c.get("/api/simulations/agora/logs?service=../../etc", headers=AUTH).status_code == 404
    assert len(c.get("/api/agents/ada/logs", headers=AUTH).json()["lines"]) == 2
    assert c.get("/api/agents/bruno/logs", headers=AUTH).json() == {"available": False, "lines": []}


@pytest.mark.parametrize("docker_ok,health,state_ok,want", [
    (True, "healthy", True, "ok"), (True, "unreachable", True, "matrix"), (False, "healthy", True, "docker"),
    (True, "healthy", False, "memory"), (False, "unreachable", False, "matrix")])
def test_the_global_status(make, docker_ok, health, state_ok, want):
    c = make(reader(FakeContainer("ada")) if docker_ok else DockerReader(client_factory=broken),
             health=health, state_ok=state_ok)
    body = c.get("/api/health", headers=AUTH).json()
    assert body["status"] == want and body["docker"] is docker_ok
    assert body["host"]["address"] == "testserver"
    assert body["host"]["containers_running"] == (1 if docker_ok else None)


def test_an_unexpected_error_is_unreachable_and_the_loop_survives(monkeypatch):
    reg = Registry()

    def boom(req):
        raise ValueError("malformed")
    p = Prober(reg, transport=httpx.MockTransport(boom), clock=lambda: 5.0)
    assert asyncio.run(p.check("agora")).status == "unreachable"  # not an exception (code review #2)

    calls = {"n": 0}

    async def flaky(sim_id):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("bug")
        p.states[sim_id] = HealthState("healthy", 1, 6.0)

    sleeps = {"n": 0}

    async def fake_sleep(_):
        sleeps["n"] += 1
        if sleeps["n"] == 2:
            raise asyncio.CancelledError

    monkeypatch.setattr(p, "check", flaky)
    monkeypatch.setattr("panel.health.asyncio.sleep", fake_sleep)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(p.run())
    assert calls["n"] == 2 and p.states["agora"].status == "healthy"  # the crash did not end the loop
