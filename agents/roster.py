"""The roster (v4.1): the members of a simulation, read from the registry and their TOMLs.

Pure loading — no network, no env. The agents (who is in the room, who may be answered, how they are addressed)
and the panel (what each card shows) read the same file through this one parser. Every image ships the same
TOMLs, so every agent sees the same roster: shared input, never shared state.
Run `python -m agents.roster` to list the agents of every simulation (scripts/run-agent.sh uses it).
"""

from __future__ import annotations

import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from agents.registry import REGISTRY_PATH, RegistryError, load_registry

AGENTS_DIR = Path("agents")

# the type sets the default capabilities; later phases add creature / assistant / bridge
CAPABILITIES = ("canon", "life", "summary", "chronicle", "plans", "today", "world")
TYPES: dict[str, frozenset[str]] = {
    "persona": frozenset(CAPABILITIES),
}
ENGINES = ("gemini",)
MODES = ("ranked", "ambient", "mention-only")


class RosterError(RuntimeError):
    """A malformed agent TOML or roster."""


@dataclass(frozen=True)
class Member:
    localpart: str            # ada — the TOML's file name and the compose service
    user_id: str              # @ada:agora.lan
    name: str                 # Ада — how the room sees them
    name_forms: tuple[str, ...]  # lowercase forms that address them («ада», «адо», …)
    type: str = "persona"
    engine: str = "gemini"
    capabilities: frozenset[str] = TYPES["persona"]
    mode: str = "ranked"
    weight: float = 1.0
    panel: dict = field(default_factory=dict, compare=False, hash=False)  # [panel] — never part of a prompt

    def can(self, capability: str) -> bool:
        return capability in self.capabilities


def parse_member(localpart: str, data: dict, source: str = "<toml>") -> Member:
    """One agent TOML (already parsed) → a Member; anything malformed is a clear error."""
    for key in ("name", "user_id"):
        if not str(data.get(key, "")).strip():
            raise RosterError(f"{source}: missing '{key}'")
    kind = str(data.get("type", "persona"))
    if kind not in TYPES:
        raise RosterError(f"{source}: unknown type {kind!r} (known: {', '.join(TYPES)})")
    engine = str(data.get("engine", "gemini"))
    if engine not in ENGINES:
        raise RosterError(f"{source}: unknown engine {engine!r} (known: {', '.join(ENGINES)})")
    caps = set(TYPES[kind])
    overrides = data.get("capabilities", {})
    if not isinstance(overrides, dict):
        raise RosterError(f"{source}: [capabilities] must be a table")
    for cap, on in overrides.items():
        if cap not in CAPABILITIES or not isinstance(on, bool):
            raise RosterError(f"{source}: bad capability {cap!r} (true/false of: {', '.join(CAPABILITIES)})")
        (caps.add if on else caps.discard)(cap)
    turns = data.get("turns", {})
    if not isinstance(turns, dict):
        raise RosterError(f"{source}: [turns] must be a table")
    mode = str(turns.get("mode", "ranked"))
    if mode not in MODES:
        raise RosterError(f"{source}: unknown turn mode {mode!r} (known: {', '.join(MODES)})")
    weight = turns.get("weight", 1.0)
    if isinstance(weight, bool) or not isinstance(weight, int | float) or weight <= 0:
        raise RosterError(f"{source}: [turns] weight must be a positive number")
    name = str(data["name"]).strip()
    forms = data.get("name_forms", [name.lower()])
    if not isinstance(forms, list) or not forms or not all(isinstance(f, str) and f.strip() for f in forms):
        raise RosterError(f"{source}: 'name_forms' must be a non-empty list of strings")
    panel = data.get("panel", {})
    return Member(
        localpart=localpart, user_id=str(data["user_id"]).strip(), name=name,
        name_forms=tuple(f.strip().lower() for f in forms), type=kind, engine=engine,
        capabilities=frozenset(caps), mode=mode, weight=float(weight),
        panel=dict(panel) if isinstance(panel, dict) else {},
    )


def load_member(path: Path) -> Member:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RosterError(f"agent config not found: {path}") from exc
    except (OSError, UnicodeDecodeError) as exc:  # a directory, no permission, not UTF-8 (code review #5)
        raise RosterError(f"{path}: unreadable ({type(exc).__name__})") from exc
    except tomllib.TOMLDecodeError as exc:
        raise RosterError(f"{path}: {exc}") from exc
    return parse_member(path.stem, data, str(path))


def load_roster(sim_id: str, registry_path: Path = REGISTRY_PATH, agents_dir: Path = AGENTS_DIR) -> dict[str, Member]:
    """The simulation's members, in registry order: its `agents` list, then each listed TOML."""
    try:
        sim = load_registry(registry_path).get(sim_id)
    except RegistryError as exc:
        raise RosterError(str(exc)) from exc
    if sim is None:
        raise RosterError(f"unknown simulation {sim_id!r}")
    return {name: load_member(agents_dir / f"{name}.toml") for name in sim.agents}


def main() -> None:
    """Print every registry agent's localpart, one per line."""
    try:
        sims = load_registry(REGISTRY_PATH)
    except RegistryError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc
    for sim in sims.values():
        for name in sim.agents:
            print(name)


if __name__ == "__main__":
    main()
