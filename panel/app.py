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
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from panel.actions import ActionError, ComposeRunner, Supervisor
from panel.docker_read import DockerReader
from panel.health import Prober
from panel.host import host_metrics
from panel.memory import local_today, memory_view, usage_view
from panel.registry import Registry

MIN_TOKEN_LEN = 24
STATIC_DIR = Path(__file__).parent / "static"
# The page makes no outside requests — and the browser is told to refuse any (v3.3 adoption notes).
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                               "img-src 'self' data:; connect-src 'self'; font-src 'self'; frame-ancestors 'none'; "
                               "base-uri 'none'; form-action 'self'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}
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
               os_release: Path = Path("/host/os-release"), background: bool = True,
               supervisor: Supervisor | None = None) -> FastAPI:
    token = token if token is not None else os.environ.get("PANEL_TOKEN", "")
    if len(token) < MIN_TOKEN_LEN:
        raise RuntimeError(f"PANEL_TOKEN must be set (at least {MIN_TOKEN_LEN} characters) — refusing to start")
    expected = f"Bearer {token}".encode()
    reg = registry or Registry()
    dock = docker_reader or DockerReader(project=os.environ.get("COMPOSE_PROJECT", "server"))
    probe = prober or Prober(reg)
    stack = os.environ.get("STACK_DIR")
    sup = supervisor or Supervisor(dock, ComposeRunner(os.environ.get("COMPOSE_PROJECT", "server"),
                                                       f"{stack}/server/docker-compose.yml" if stack else None),
                                   state_dir)

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
                response = JSONResponse({"detail": "unauthorized"}, status_code=401,
                                        headers={"WWW-Authenticate": "Bearer"})
                response.headers.update(SECURITY_HEADERS)
                return response
            origin = request.headers.get("origin")
            if request.method not in ("GET", "HEAD") and origin and urlsplit(origin).netloc != request.headers.get("host"):
                # actions are same-origin only: a page elsewhere can't drive them even with a stolen token
                response = JSONResponse({"detail": "cross-origin action refused"}, status_code=403)
                response.headers.update(SECURITY_HEADERS)
                return response
        response = await call_next(request)
        response.headers.update(SECURITY_HEADERS)
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        return response

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

    def run(fn, *args) -> dict:
        try:
            return fn(*args)
        except ActionError as exc:
            raise HTTPException(exc.status, exc.detail) from exc

    # ── actions (v3.4): POST only, token-gated, same-origin, names only through the registry ──
    @app.post("/api/agents/{name}/forget")
    def agent_forget(name: str) -> dict:
        found = reg.agent(name)
        if found is None:
            raise HTTPException(404, "not found")
        return run(sup.forget, found.name)

    @app.post("/api/agents/{name}/{action}")
    def agent_action(name: str, action: str) -> dict:
        found = reg.agent(name)
        if found is None or action not in ("start", "stop", "restart"):
            raise HTTPException(404, "not found")
        return run(sup.act, found.container, action)

    @app.post("/api/simulations/{sim_id}/services/{service}/{action}")
    def service_action(sim_id: str, service: str, action: str) -> dict:
        svc = reg.service(sim_id, service)
        if svc is None or action not in ("start", "stop", "restart"):
            raise HTTPException(404, "not found")
        return run(sup.act, svc, action)

    # the page: served without the token (it holds no data); everything it shows comes from /api/*
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app
