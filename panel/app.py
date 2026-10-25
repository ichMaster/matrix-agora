"""The panel's API and page (v3.3: read-only).

Run on the server as the `panel` service: `uvicorn --factory panel.app:create_app --host 0.0.0.0 --port 8090`.
Every /api/* request needs `Authorization: Bearer <PANEL_TOKEN>` — checked before routing, so even an unknown
path answers 401 without it. No route mutates anything (the actions are v3.4).
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
import logging
import os
import time
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from agents.facts import remove_fact, set_pin
from panel.actions import ActionError, ComposeRunner, Supervisor
from panel.docker_read import DockerReader
from panel.files import (
    MAX_UPLOAD,
    FilesError,
    delete_file,
    file_for_download,
    list_files,
    read_text,
    write_file,
)
from panel.health import Prober
from panel.host import host_metrics
from panel.memory import local_today, memory_view, usage_view
from panel.registry import Registry
from panel.settings import SettingsError, save_settings, settings_view

MIN_TOKEN_LEN = 24
LOG_FORMAT = "%(asctime)s %(name)s %(levelname)s %(message)s"


def panel_logging() -> logging.Logger:
    """The panel's own events (actions, probe failures) to the console at INFO — `docker logs panel`.

    Uvicorn configures only its own loggers, so without this every action event is dropped (v3.4 review #1).
    A handler on the `panel` logger, not the root: no side effects on uvicorn or tests.
    """
    log = logging.getLogger("panel")
    if not any(getattr(h, "_panel", False) for h in log.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        handler._panel = True
        log.addHandler(handler)
    log.setLevel(logging.INFO)
    return log
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
            "container": agent.container, "pronoun": agent.pronoun, "type": agent.type, "engine": agent.engine,
            "capabilities": sorted(agent.capabilities)}


def create_app(token: str | None = None, registry: Registry | None = None, docker_reader: DockerReader | None = None,
               prober: Prober | None = None, state_dir: Path = Path("state"), proc: Path = Path("/proc"),
               os_release: Path = Path("/host/os-release"), background: bool = True,
               supervisor: Supervisor | None = None, files_dir: Path = Path("/claude-workspace")) -> FastAPI:
    token = token if token is not None else os.environ.get("PANEL_TOKEN", "")
    if len(token) < MIN_TOKEN_LEN:
        raise RuntimeError(f"PANEL_TOKEN must be set (at least {MIN_TOKEN_LEN} characters) — refusing to start")
    expected = f"Bearer {token}".encode()
    panel_logging()
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
        natal = Path(found.natal) if found.natal else None  # the registry's own paths, never request data
        theses = Path(found.memories) if found.memories and "pastlife" in found.capabilities else None
        return memory_view(state_dir, found.name, local_today(), natal, "mood" in found.capabilities, theses,
                           "nudge" in found.capabilities, found.engine == "claude-sdk", "news" in found.capabilities,
                           "digest" in found.capabilities, "facts" in found.capabilities, "recall" in found.capabilities)

    # ── v5.8: a person's facts about the owner — re-pin or delete one; the id resolves only inside her own folder ──
    def facts_folder(name: str) -> Path:
        found = reg.agent(name)
        if found is None or "facts" not in found.capabilities:
            raise HTTPException(404, "not found")
        return state_dir / f"{found.name}.facts"

    @app.post("/api/agents/{name}/facts/update")
    def facts_update(name: str) -> dict:
        """AGORA-116 — «Update now»: a request she sees within her idle watcher's tick (≤ 30 s) — her facts from the
        talk so far, without waiting for the session's end. Written atomically, private (0600)."""
        folder = facts_folder(name)
        path = folder.parent / f"{folder.name.removesuffix('.facts')}.facts.request"
        tmp = path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, json.dumps({"requested_ms": int(time.time() * 1000)}).encode())
        finally:
            os.close(fd)
        os.replace(tmp, path)
        return {"requested": True}

    @app.put("/api/agents/{name}/facts/{fact_id}")
    async def fact_pin(name: str, fact_id: str, request: Request) -> dict:
        folder = facts_folder(name)
        try:
            body = await request.json()
        except ValueError:
            body = None
        pin = body.get("pin") if isinstance(body, dict) else None
        if isinstance(pin, bool) or pin not in (0, 1, 2):
            raise HTTPException(422, "pin must be 0, 1 or 2")
        if not set_pin(folder, fact_id, pin):
            raise HTTPException(404, "not found")
        return {"id": fact_id, "pin": pin}

    @app.delete("/api/agents/{name}/facts/{fact_id}")
    def fact_delete(name: str, fact_id: str) -> dict:
        if not remove_fact(facts_folder(name), fact_id):
            raise HTTPException(404, "not found")
        return {"id": fact_id, "deleted": True}

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

    # ── settings (v4.7), under their service: a simulation's on its card, an agent's own in its drawer ──
    def sim_scope(sim_id: str):
        sim = reg.simulation(sim_id)
        if sim is None:
            raise HTTPException(404, "not found")
        return "services", sim.id, sim.kind, [reg.agents[n] for n in sim.agents if n in reg.agents]

    def agent_scope(name: str):
        found = reg.agent(name)
        if found is None:
            raise HTTPException(404, "not found")
        return "agents", found.name, None, [found]

    async def settings_save(request: Request, scope) -> dict:
        try:
            body = await request.json()
        except ValueError as exc:
            raise HTTPException(422, "a JSON object is expected") from exc
        part, owner, kind, agents = scope
        try:
            return await asyncio.to_thread(save_settings, state_dir, part, owner, kind, agents, body,
                                           lambda c: dock.container(c).state, lambda c: sup.act(c, "restart"))
        except SettingsError as exc:
            raise HTTPException(exc.status, exc.detail) from exc

    @app.get("/api/simulations/{sim_id}/settings")
    def sim_settings_get(sim_id: str) -> dict:
        return settings_view(state_dir, *sim_scope(sim_id))

    @app.put("/api/simulations/{sim_id}/settings")
    async def sim_settings_put(sim_id: str, request: Request) -> dict:
        return await settings_save(request, sim_scope(sim_id))

    @app.get("/api/agents/{name}/settings")
    def agent_settings_get(name: str) -> dict:
        return settings_view(state_dir, *agent_scope(name))

    @app.put("/api/agents/{name}/settings")
    async def agent_settings_put(name: str, request: Request) -> dict:
        return await settings_save(request, agent_scope(name))

    # ── Claude's files (v4.7): his folder only, every path through files.safe_path ──
    def files_root(name: str) -> Path:
        found = reg.agent(name)
        if found is None or found.engine != "claude-sdk":
            raise HTTPException(404, "not found")
        return files_dir

    def files_call(fn, *args):
        try:
            return fn(*args)
        except FilesError as exc:
            raise HTTPException(exc.status, exc.detail) from exc

    @app.get("/api/agents/{name}/files")
    def files_list(name: str) -> dict:
        return {"files": list_files(files_root(name))}

    @app.get("/api/agents/{name}/files/{path:path}")
    def files_read(name: str, path: str, download: int = 0):
        root = files_root(name)
        if download:
            target = files_call(file_for_download, root, path)
            return FileResponse(target, filename=target.name, media_type="application/octet-stream")
        return files_call(read_text, root, path)

    @app.put("/api/agents/{name}/files/{path:path}")
    async def files_upload(name: str, path: str, request: Request, overwrite: int = 0) -> dict:
        root = files_root(name)
        data = bytearray()
        async for chunk in request.stream():
            data += chunk
            if len(data) > MAX_UPLOAD:
                raise HTTPException(413, "larger than 5 MB")
        return files_call(write_file, root, path, bytes(data), bool(overwrite))

    @app.delete("/api/agents/{name}/files/{path:path}")
    def files_delete(name: str, path: str) -> dict:
        return files_call(delete_file, files_root(name), path)

    # the page: served without the token (it holds no data); everything it shows comes from /api/*
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app
