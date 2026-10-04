"""The panel's API and page (v3.3: read-only).

Run on the server as the `panel` service: `uvicorn --factory panel.app:create_app --host 0.0.0.0 --port 8090`.
Every /api/* request needs `Authorization: Bearer <PANEL_TOKEN>` — checked before routing, so even an unknown
path answers 401 without it. No route mutates anything (the actions are v3.4).
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from panel.docker_read import DockerReader
from panel.health import Prober
from panel.host import host_metrics
from panel.memory import local_today, memory_view, usage_view
from panel.registry import Registry

MIN_TOKEN_LEN = 24
TAIL_MAX = 500
USAGE_DAYS_MAX = 31


def clamp_tail(tail: int) -> int:
    return max(1, min(TAIL_MAX, tail))


def _sim_view(sim) -> dict:
    return {"id": sim.id, "kind": sim.kind, "title": sim.title, "description": sim.description,
            "services": list(sim.services), "agents": list(sim.agents)}


def _agent_view(agent) -> dict:
    return {"name": agent.name, "display": agent.display, "role": agent.role, "simulation": agent.simulation,
            "container": agent.container}


def create_app(token: str | None = None, registry: Registry | None = None, docker_reader: DockerReader | None = None,
               prober: Prober | None = None, state_dir: Path = Path("state"), proc: Path = Path("/proc"),
               os_release: Path = Path("/host/os-release"), background: bool = True) -> FastAPI:
    token = token if token is not None else os.environ.get("PANEL_TOKEN", "")
    if len(token) < MIN_TOKEN_LEN:
        raise RuntimeError(f"PANEL_TOKEN must be set (at least {MIN_TOKEN_LEN} characters) — refusing to start")
    expected = f"Bearer {token}".encode()
    reg = registry or Registry()
    dock = docker_reader or DockerReader(project=os.environ.get("COMPOSE_PROJECT", "server"))
    probe = prober or Prober(reg)

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        task = asyncio.create_task(probe.run()) if background else None
        yield
        if task:
            task.cancel()

    app = FastAPI(title="Agora panel", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.registry = reg

    def state_readable() -> bool:
        return os.access(state_dir, os.R_OK | os.X_OK)

    def health_view(sim_id: str) -> dict:
        h = probe.states.get(sim_id)
        return {"status": h.status, "latency_ms": h.latency_ms, "checked_at": h.checked_at}

    def container_view(service: str) -> dict:
        c = dock.container(service)
        return {"state": c.state, "uptime_s": c.uptime_s, "image": c.image, "started_at": c.started_at,
                "exit_code": c.exit_code}

    @app.middleware("http")
    async def owner_token(request: Request, call_next):
        if request.url.path.startswith("/api"):
            given = request.headers.get("authorization", "").encode()
            if not hmac.compare_digest(given, expected):
                return JSONResponse({"detail": "unauthorized"}, status_code=401,
                                    headers={"WWW-Authenticate": "Bearer"})
        return await call_next(request)

    @app.get("/api/simulations")
    def simulations() -> list[dict]:
        return [_sim_view(s) for s in reg.simulations.values()]

    @app.get("/api/health")
    def health(request: Request) -> dict:
        docker_ok = dock.available()
        sims = {sid: probe.states[sid].status for sid in reg.simulations}
        memory_ok = state_readable()
        if any(s == "unreachable" for s in sims.values()):
            status = "matrix"
        elif not docker_ok:
            status = "docker"
        elif not memory_ok:
            status = "memory"
        else:
            status = "ok"
        host = host_metrics(proc, state_dir, os_release)
        host["address"] = request.url.hostname
        host["containers_running"] = dock.running_count() if docker_ok else None
        return {"status": status, "docker": docker_ok, "memory": memory_ok, "simulations": sims, "host": host}

    @app.get("/api/simulations/{sim_id}")
    def simulation(sim_id: str) -> dict:
        sim = reg.simulation(sim_id)
        if sim is None:
            raise HTTPException(404, "not found")
        view = _sim_view(sim)
        view["health"] = health_view(sim_id)
        view["service_states"] = {svc: container_view(svc) for svc in sim.services}
        return view

    @app.get("/api/simulations/{sim_id}/logs")
    def simulation_logs(sim_id: str, service: str, tail: int = 200) -> dict:
        svc = reg.service(sim_id, service)
        if svc is None:
            raise HTTPException(404, "not found")
        lines = dock.logs(svc, clamp_tail(tail))
        return {"available": lines is not None, "lines": lines or []}

    @app.get("/api/agents")
    def agents() -> list[dict]:
        return [_agent_view(a) for a in reg.agents.values()]

    @app.get("/api/agents/{name}")
    def agent(name: str) -> dict:
        found = reg.agent(name)
        if found is None:
            raise HTTPException(404, "not found")
        view = _agent_view(found)
        view["container_state"] = container_view(found.container)
        return view

    @app.get("/api/agents/{name}/memory")
    def agent_memory(name: str) -> dict:
        found = reg.agent(name)
        if found is None:
            raise HTTPException(404, "not found")
        return memory_view(state_dir, found.name, local_today())

    @app.get("/api/usage")
    def usage(days: int = 7, agent: str | None = None) -> dict:
        if agent is not None and reg.agent(agent) is None:
            raise HTTPException(404, "not found")
        return usage_view(state_dir, max(1, min(USAGE_DAYS_MAX, days)), local_today(), agent)

    @app.get("/api/agents/{name}/logs")
    def agent_logs(name: str, tail: int = 200) -> dict:
        found = reg.agent(name)
        if found is None:
            raise HTTPException(404, "not found")
        lines = dock.logs(found.container, clamp_tail(tail))
        return {"available": lines is not None, "lines": lines or []}

    return app
