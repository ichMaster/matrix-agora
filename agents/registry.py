"""The simulation registry (v3.3): simulations.toml at the repo root.

Both the agents (to resolve their connection settings) and the panel (to resolve every name a request
carries) read it. Lookups return None for anything not listed — the only way outside input becomes a name.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

REGISTRY_PATH = Path("simulations.toml")
KINDS = ("matrix-chat",)
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")


class RegistryError(RuntimeError):
    """A malformed registry."""


@dataclass(frozen=True)
class Health:
    service: str
    port: int
    path: str


@dataclass(frozen=True)
class Simulation:
    id: str
    kind: str
    title: str
    description: str
    services: tuple[str, ...]
    agents: tuple[str, ...]
    health: Health
    endpoints: dict[str, str]


def _names(value, what: str, sim_id: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or not all(isinstance(v, str) and NAME.match(v) for v in value):
        raise RegistryError(f"{sim_id}: '{what}' must be a non-empty list of names")
    if len(set(value)) != len(value):
        raise RegistryError(f"{sim_id}: duplicate in '{what}'")
    return tuple(value)


def parse_registry(text: str) -> dict[str, Simulation]:
    data = tomllib.loads(text)
    sims: dict[str, Simulation] = {}
    seen_agents: dict[str, str] = {}
    for sim_id, raw in data.items():
        if not NAME.match(sim_id) or not isinstance(raw, dict):
            raise RegistryError(f"bad simulation id {sim_id!r}")
        for key in ("kind", "title", "services", "agents", "health", "endpoints"):
            if key not in raw:
                raise RegistryError(f"{sim_id}: missing '{key}'")
        if raw["kind"] not in KINDS:
            raise RegistryError(f"{sim_id}: unknown kind {raw['kind']!r}")
        services = _names(raw["services"], "services", sim_id)
        agents = _names(raw["agents"], "agents", sim_id)
        for name in agents:
            if name in seen_agents:
                raise RegistryError(f"agent {name!r} is in both {seen_agents[name]!r} and {sim_id!r}")
            seen_agents[name] = sim_id
        h = raw["health"]
        if h.get("service") not in services or not isinstance(h.get("port"), int) or not str(h.get("path", "")).startswith("/"):
            raise RegistryError(f"{sim_id}: health needs one of its services, a port and a path")
        endpoints = raw["endpoints"]
        if not {"homeserver", "room"} <= set(endpoints) or not all(isinstance(v, str) for v in endpoints.values()):
            raise RegistryError(f"{sim_id}: endpoints need 'homeserver' and 'room' env names")
        sims[sim_id] = Simulation(sim_id, raw["kind"], str(raw["title"]), str(raw.get("description", "")),
                                  services, agents, Health(h["service"], h["port"], h["path"]), dict(endpoints))
    if not sims:
        raise RegistryError("the registry is empty")
    return sims


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, Simulation]:
    try:
        return parse_registry(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RegistryError(f"registry not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise RegistryError(f"{path}: {exc}") from exc


def simulation_of(registry: dict[str, Simulation], agent: str) -> Simulation | None:
    return next((s for s in registry.values() if agent in s.agents), None)
