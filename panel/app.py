"""The panel's API and page (v3.3: read-only).

Run on the server as the `panel` service: `uvicorn --factory panel.app:create_app --host 0.0.0.0 --port 8090`.
Every /api/* request needs `Authorization: Bearer <PANEL_TOKEN>` — checked before routing, so even an unknown
path answers 401 without it. No route mutates anything (the actions are v3.4).
"""

from __future__ import annotations

import hmac
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from panel.registry import Registry

MIN_TOKEN_LEN = 24


def _sim_view(sim) -> dict:
    return {"id": sim.id, "kind": sim.kind, "title": sim.title, "description": sim.description,
            "services": list(sim.services), "agents": list(sim.agents)}


def _agent_view(agent) -> dict:
    return {"name": agent.name, "display": agent.display, "role": agent.role, "simulation": agent.simulation,
            "container": agent.container}


def create_app(token: str | None = None, registry: Registry | None = None) -> FastAPI:
    token = token if token is not None else os.environ.get("PANEL_TOKEN", "")
    if len(token) < MIN_TOKEN_LEN:
        raise RuntimeError(f"PANEL_TOKEN must be set (at least {MIN_TOKEN_LEN} characters) — refusing to start")
    expected = f"Bearer {token}".encode()
    reg = registry or Registry()
    app = FastAPI(title="Agora panel", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.registry = reg

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

    @app.get("/api/simulations/{sim_id}")
    def simulation(sim_id: str) -> dict:
        sim = reg.simulation(sim_id)
        if sim is None:
            raise HTTPException(404, "not found")
        return _sim_view(sim)

    @app.get("/api/agents")
    def agents() -> list[dict]:
        return [_agent_view(a) for a in reg.agents.values()]

    @app.get("/api/agents/{name}")
    def agent(name: str) -> dict:
        found = reg.agent(name)
        if found is None:
            raise HTTPException(404, "not found")
        return _agent_view(found)

    return app
