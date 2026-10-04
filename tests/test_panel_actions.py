import threading

import pytest
from docker.errors import DockerException
from fastapi.testclient import TestClient

from panel.actions import STOP_TIMEOUT_S, ActionError, ComposeRunner, Supervisor
from panel.app import create_app
from panel.docker_read import DockerReader, classify
from panel.health import Prober
from panel.registry import Registry

TOKEN = "t" * 32
AUTH = {"Authorization": f"Bearer {TOKEN}"}


class Container:
    def __init__(self, service, status="running"):
        self.service, self.status = service, status
        self.attrs = {"State": {"ExitCode": 0, "StartedAt": "2026-10-04T10:00:00Z"}}
        self.image = type("I", (), {"tags": []})()
        self.stopped_with = None

    def stop(self, timeout):
        self.stopped_with = timeout
        self.status = "exited"


class Docker:
    def __init__(self, *containers, up=True):
        self.by = {c.service: c for c in containers}
        self.containers = self
        self.up = up

    def ping(self):
        if not self.up:
            raise DockerException("down")
        return True

    def list(self, all=False, filters=None):
        if not self.up:
            raise DockerException("down")
        svc = (filters or {}).get("label", ["", "x=?"])[1].split("=", 1)[1]
        return [self.by[svc]] if svc in self.by else []


class Compose:
    """Records `up` calls; brings the container into existence like compose would."""

    def __init__(self, docker):
        self.docker, self.calls = docker, []

    def up(self, service):
        self.calls.append(service)
        self.docker.by[service] = Container(service, "running")


def make(*containers, up=True, state_dir=None):
    docker = Docker(*containers, up=up)
    reader = DockerReader(client_factory=lambda: docker)
    compose = Compose(docker)
    return Supervisor(reader, compose, state_dir) if state_dir else Supervisor(reader, compose), docker, compose


# --- the supervisor ---
def test_start_creates_a_missing_container_through_compose():
    sup, _, compose = make()
    assert sup.act("bruno", "start") == {"ok": True, "state": "running"}
    assert compose.calls == ["bruno"]


def test_stop_waits_for_the_summary_then_restart_brings_it_back():
    ada = Container("ada")
    sup, _, compose = make(ada)
    assert sup.act("ada", "stop") == {"ok": True, "state": "stopped"}
    assert ada.stopped_with == STOP_TIMEOUT_S == 30  # SIGTERM → summary → SIGKILL after 30 s
    assert sup.act("ada", "restart")["state"] == "running" and compose.calls == ["ada"]


def test_refusals():
    sup, _, _ = make()
    with pytest.raises(ActionError) as e:
        sup.act("bruno", "stop")
    assert e.value.status == 409  # no container to stop
    with pytest.raises(ActionError) as e:
        sup.act("ada", "explode")
    assert e.value.status == 404
    down, _, _ = make(Container("ada"), up=False)
    with pytest.raises(ActionError) as e:
        down.act("ada", "stop")
    assert e.value.status == 503


def test_one_action_at_a_time_per_target():
    gate, release = threading.Event(), threading.Event()
    ada = Container("ada")

    def slow_stop(timeout):
        gate.set()
        release.wait(5)
        ada.status = "exited"
    ada.stop = slow_stop
    sup, _, _ = make(ada)
    worker = threading.Thread(target=sup.act, args=("ada", "stop"))
    worker.start()
    gate.wait(5)
    with pytest.raises(ActionError) as e:
        sup.act("ada", "restart")
    assert e.value.status == 409 and sup.busy() == {"ada"}
    release.set()
    worker.join(5)
    assert sup.busy() == set()


def test_compose_runner_argv_and_missing_config(tmp_path, monkeypatch):
    with pytest.raises(ActionError) as e:
        ComposeRunner("server", None).up("ada")
    assert e.value.status == 503
    f = tmp_path / "docker-compose.yml"
    f.write_text("services: {}\n")
    seen = {}
    monkeypatch.setattr("panel.actions.subprocess.run", lambda argv, **kw: seen.setdefault("argv", argv))
    ComposeRunner("server", str(f)).up("bruno")
    assert seen["argv"] == ["docker", "compose", "-p", "server", "-f", str(f), "up", "-d", "--no-deps", "bruno"]


def test_restarting_is_its_own_state():
    assert classify("restarting", 0) == "restarting"  # v3.3 review #5


# --- the routes ---
@pytest.fixture
def client():
    def _client(*containers, up=True):
        sup, _, compose = make(*containers, up=up)
        reg = Registry()
        app = create_app(token=TOKEN, registry=reg, docker_reader=sup.reader, prober=Prober(reg), supervisor=sup,
                         background=False)
        return TestClient(app), compose
    return _client


def test_action_routes_resolve_through_the_registry(client):
    c, compose = client(Container("homeserver"), Container("ada"))
    assert c.post("/api/agents/ada/stop", headers=AUTH).json() == {"ok": True, "state": "stopped"}
    assert c.post("/api/agents/bruno/start", headers=AUTH).json()["state"] == "running"
    assert c.post("/api/simulations/agora/services/homeserver/restart", headers=AUTH).json()["ok"]
    assert compose.calls == ["bruno", "homeserver"]
    for path in ("/api/agents/carol/stop", "/api/agents/ada/explode", "/api/simulations/agora/services/ada/stop",
                 "/api/simulations/nowhere/services/homeserver/stop"):
        assert c.post(path, headers=AUTH).status_code == 404, path
    # a traversal attempt matches no action route at all (the static files allow GET only)
    assert c.post("/api/simulations/agora/services/..%2Fetc/stop", headers=AUTH).status_code in (404, 405)
    assert compose.calls == ["bruno", "homeserver"]  # nothing else ran


def test_actions_need_the_token_post_and_the_same_origin(client):
    c, _ = client(Container("ada"))
    assert c.post("/api/agents/ada/stop").status_code == 401
    assert c.get("/api/agents/ada/stop", headers=AUTH).status_code in (404, 405)
    evil = c.post("/api/agents/ada/stop", headers={**AUTH, "Origin": "http://evil.example"})
    assert evil.status_code == 403
    same = c.post("/api/agents/ada/stop", headers={**AUTH, "Origin": "http://testserver"})
    assert same.status_code == 200


def test_docker_down_is_503_not_a_crash(client):
    c, _ = client(Container("ada"), up=False)
    assert c.post("/api/agents/ada/stop", headers=AUTH).status_code == 503


# --- forget (AGORA-040) ---
@pytest.fixture
def state(tmp_path):
    s = tmp_path / "state"
    for rel in ("ada.memory.md", "ada.days/2026-10-03.md", "ada.plans/2026-10-04.md", "ada.today.md", "bruno.memory.md"):
        (s / rel).parent.mkdir(parents=True, exist_ok=True)
        (s / rel).write_text("x\n")
    return s


def files(s):
    return sorted(str(p.relative_to(s)) for p in s.rglob("*") if p.is_file())


@pytest.mark.parametrize("status,allowed", [("exited", True), ("running", False), ("restarting", False)])
def test_forget_only_for_a_stopped_agent(state, status, allowed):
    sup, _, _ = make(Container("ada", status), state_dir=state)
    before = files(state)
    if allowed:
        assert sup.forget("ada") == {"ok": True, "forgotten": True}
        assert files(state) == [f for f in before if f != "ada.memory.md"]  # only the summary, nothing else
    else:
        with pytest.raises(ActionError) as e:
            sup.forget("ada")
        assert e.value.status == 409 and files(state) == before


def test_forget_with_no_container_or_no_summary_and_docker_down(state):
    sup, _, _ = make(state_dir=state)          # bruno has no container: allowed
    assert sup.forget("bruno")["forgotten"] is True
    assert sup.forget("bruno") == {"ok": True, "forgotten": False}  # nothing left to forget — not an error
    down, _, _ = make(Container("ada", "exited"), up=False, state_dir=state)
    with pytest.raises(ActionError) as e:
        down.forget("ada")                     # state unknown → refuse
    assert e.value.status == 409 and (state / "ada.memory.md").exists()


def test_the_forget_route(state):
    sup, _, _ = make(Container("ada", "exited"), Container("bruno"), state_dir=state)
    reg = Registry()
    c = TestClient(create_app(token=TOKEN, registry=reg, docker_reader=sup.reader, prober=Prober(reg), supervisor=sup,
                              state_dir=state, background=False))
    assert c.post("/api/agents/ada/forget").status_code == 401
    assert c.post("/api/agents/ada/forget", headers={**AUTH, "Origin": "http://evil.example"}).status_code == 403
    assert c.post("/api/agents/bruno/forget", headers=AUTH).status_code == 409   # bruno is running
    assert c.post("/api/agents/carol/forget", headers=AUTH).status_code == 404
    assert c.post("/api/agents/ada/forget", headers=AUTH).json() == {"ok": True, "forgotten": True}
    assert not (state / "ada.memory.md").exists() and (state / "bruno.memory.md").exists()



# --- v3.4 review #1: the action events reach the panel's log ---
def test_actions_are_logged_by_the_panel(caplog):
    import logging

    from panel.app import panel_logging
    log = panel_logging()
    assert log.level == logging.INFO and any(getattr(h, "_panel", False) for h in log.handlers)
    panel_logging()
    assert sum(getattr(h, "_panel", False) for h in log.handlers) == 1  # idempotent
    sup, _, _ = make(Container("ada"))
    with caplog.at_level(logging.INFO, logger="panel.actions"):
        sup.act("ada", "stop")
    assert any(r.name == "panel.actions" and "action stop ada" in r.getMessage() for r in caplog.records)



def test_a_failed_compose_up_logs_why(tmp_path, monkeypatch, caplog):
    import logging
    import subprocess
    f = tmp_path / "docker-compose.yml"
    f.write_text("services: {}\n")

    def fail(argv, **kw):
        raise subprocess.CalledProcessError(1, argv, stderr=b"pulling...\nno such service: brunoo\n")
    monkeypatch.setattr("panel.actions.subprocess.run", fail)
    with caplog.at_level(logging.WARNING, logger="panel.actions"), pytest.raises(ActionError) as e:
        ComposeRunner("server", str(f)).up("bruno")
    assert e.value.status == 502
    assert any("no such service: brunoo" in r.getMessage() for r in caplog.records)  # code review #2
