"""The simulations' health probes (v3.3): one cached HTTP probe per registry entry, refreshed every 30 s."""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass

import httpx

PROBE_EVERY_S = 30
PROBE_TIMEOUT_S = 5.0


@dataclass(frozen=True)
class HealthState:
    status: str                # healthy | unreachable | unknown
    latency_ms: int | None = None
    checked_at: float | None = None


class Prober:
    def __init__(self, registry, transport: httpx.AsyncBaseTransport | None = None, clock=time.time) -> None:
        self.registry = registry
        self.transport = transport
        self.clock = clock
        self.states: dict[str, HealthState] = {sid: HealthState("unknown") for sid in registry.simulations}

    def url(self, sim) -> str:
        host = os.environ.get("PANEL_PROBE_HOST") or sim.health.service  # dev runs outside compose
        return f"http://{host}:{sim.health.port}{sim.health.path}"

    async def check(self, sim_id: str) -> HealthState:
        sim = self.registry.simulation(sim_id)
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=PROBE_TIMEOUT_S) as client:
                resp = await client.get(self.url(sim))
            ok = resp.status_code == 200
        except httpx.HTTPError:
            ok = False
        state = HealthState("healthy" if ok else "unreachable",
                            int((time.perf_counter() - start) * 1000) if ok else None, self.clock())
        self.states[sim_id] = state
        return state

    async def run(self) -> None:
        while True:
            for sim_id in list(self.states):
                await self.check(sim_id)
            await asyncio.sleep(PROBE_EVERY_S)
