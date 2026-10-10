"""What the panel may name: simulations from simulations.toml and the agents they list.

Every id a request carries goes through these lookups; anything not listed is None → 404. Nothing from a
request ever reaches a path, an argv or the docker API without passing here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from agents.registry import REGISTRY_PATH, Simulation, load_registry
from agents.roster import RosterError, load_member

log = logging.getLogger("panel.registry")


@dataclass(frozen=True)
class Agent:
    name: str           # the localpart: ada
    display: str        # Ada
    role: str           # editor, 32, Lviv
    simulation: str     # agora
    container: str      # the compose service: ada
    pronoun: str = "they"  # from the TOML's [panel] — never guessed from a name
    type: str = "persona"  # v4.1: the card follows the type's capabilities
    engine: str = "gemini"
    capabilities: frozenset[str] = frozenset()
    natal: str = ""  # v4.2: the natal file (the mood view computes the biorhythms from its birth date)


class Registry:
    def __init__(self, path: Path = REGISTRY_PATH, agents_dir: Path = Path("agents")) -> None:
        self.simulations: dict[str, Simulation] = load_registry(path)
        self.agents: dict[str, Agent] = {}
        for sim in self.simulations.values():
            for name in sim.agents:
                try:  # the same parser the agents use (agents/roster.py)
                    m = load_member(agents_dir / f"{name}.toml")
                except RosterError as exc:  # a broken TOML greys out its card, never the panel
                    log.error("agent %s: %s", name, exc)
                    self.agents[name] = Agent(name, name.title(), "", sim.id, name, type="unknown", engine="")
                    continue
                panel = m.panel
                self.agents[name] = Agent(name, str(panel.get("name", name.title())), str(panel.get("role", "")),
                                          sim.id, name, str(panel.get("pronoun", "they")), m.type, m.engine,
                                          m.capabilities, m.natal)

    def simulation(self, sim_id: str) -> Simulation | None:
        return self.simulations.get(sim_id)

    def agent(self, name: str) -> Agent | None:
        return self.agents.get(name)

    def service(self, sim_id: str, service: str) -> str | None:
        sim = self.simulations.get(sim_id)
        return service if sim and service in sim.services else None
