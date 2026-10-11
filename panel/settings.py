"""The panel's settings (v4.7), under their service (the owner, 2026-10-11): a simulation's settings on its card, an
agent's own in its drawer.

A **scope** is `("services", <simulation id>, <its kind>)` — the service settings of that simulation kind, for the
simulation's agents — or `("agents", <agent>, None)` — the agent's own settings that concern it. A view shows the
scope's settings with their override and every concerned agent's effective value; a save validates `{set, reset}`
against the scope, writes `state/settings.json` (`services.<sim>` or `agents.<agent>`) and restarts the running
concerned agents. Names resolve only through the schema (`agents.settings`), values only through its `validate`; the
only thing from a request that reaches the docker API is a registry agent's container name. Saves run one at a time.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from agents.settings import (
    AGENT_GROUPS,
    BY_NAME,
    OVERRIDES_FILE,
    SCHEMA,
    SERVICE_GROUPS,
    concerns,
    in_scope,
    load_overrides,
    save_json,
    validate,
)

log = logging.getLogger("panel.settings")
_SAVE_LOCK = threading.Lock()  # one save at a time: no lost update, no shared temp file (v4.7 review #5)


class SettingsError(Exception):
    def __init__(self, status: int, detail: Any) -> None:
        super().__init__(str(detail))
        self.status = status
        self.detail = detail


def _effective(state_dir: Path, agent: str) -> dict | None:
    try:
        data = json.loads((state_dir / f"{agent}.settings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _rows(agents: list[Any], sim_kind: str | None) -> list:
    """The scope's settings: of this service kind, or the agent settings — each concerning at least one agent."""
    return [s for s in SCHEMA if in_scope(s, sim_kind) and any(concerns(s, a) for a in agents)]


def settings_view(state_dir: Path, part: str, owner: str, sim_kind: str | None, agents: Iterable[Any]) -> dict:
    """One scope's settings, grouped, with the override and every concerned agent's effective value."""
    agents = list(agents)
    overrides = load_overrides(state_dir / OVERRIDES_FILE)[part].get(owner, {})
    effective = {a.name: _effective(state_dir, a.name) for a in agents}
    rows = []
    for s in _rows(agents, sim_kind):
        concerned = [a.name for a in agents if concerns(s, a)]
        per_agent = {}
        for name in concerned:
            entry = (effective[name] or {}).get(s.name) if effective[name] is not None else None
            per_agent[name] = ({"value": str(entry.get("value", "")), "source": str(entry.get("source", ""))}
                               if isinstance(entry, dict) else None)
        rows.append({"name": s.name, "kind": s.kind, "default": s.default, "unit": s.unit,
                     "description": s.description, "group": s.group, "scope": s.scope, "low": s.low,
                     "high": s.high, "choices": list(s.choices), "override": overrides.get(s.name),
                     "agents": concerned, "effective": per_agent})
    groups = SERVICE_GROUPS if sim_kind is not None else AGENT_GROUPS
    return {"scope": part, "owner": owner, "groups": [{"id": g, "title": t} for g, t in groups], "settings": rows}


def save_settings(state_dir: Path, part: str, owner: str, sim_kind: str | None, agents: Iterable[Any], body: Any,
                  state_of: Callable[[str], str], restart: Callable[[str], dict]) -> dict:
    """Validate `{"set": {name: value}, "reset": [names]}` against the scope, write the overrides, restart the
    running concerned agents (a stopped one is skipped, never started). Nothing is written when anything is
    invalid; saves run one at a time."""
    with _SAVE_LOCK:
        return _save(state_dir, part, owner, sim_kind, list(agents), body, state_of, restart)


def _save(state_dir: Path, part: str, owner: str, sim_kind: str | None, agents: list[Any], body: Any,
          state_of: Callable[[str], str], restart: Callable[[str], dict]) -> dict:
    if not isinstance(body, dict):
        raise SettingsError(422, "a JSON object is expected")
    to_set, to_reset = body.get("set") or {}, body.get("reset") or []
    if not isinstance(to_set, dict) or not isinstance(to_reset, list):
        raise SettingsError(422, "`set` is an object, `reset` a list")
    allowed = {s.name for s in _rows(agents, sim_kind)}
    errors, clean = {}, {}
    for name, raw in to_set.items():
        if str(name) not in allowed:
            errors[str(name)] = "not a setting here" if str(name) in BY_NAME else "unknown setting"
            continue
        value, why = validate(str(name), raw)
        if value is None:
            errors[str(name)] = why
        else:
            clean[str(name)] = value
    for name in to_reset:
        if str(name) not in allowed:
            errors[str(name)] = "not a setting here" if str(name) in BY_NAME else "unknown setting"
    if errors:
        raise SettingsError(422, {"invalid": errors})
    overrides = load_overrides(state_dir / OVERRIDES_FILE)
    mine = overrides[part].setdefault(owner, {})
    changed = []
    for name, value in clean.items():
        if mine.get(name) != value:
            mine[name] = value
            changed.append(name)
    for name in map(str, to_reset):
        if name in mine:
            del mine[name]
            changed.append(name)
    if not changed:
        return {"saved": [], "restarted": [], "skipped": []}
    overrides[part] = {k: v for k, v in overrides[part].items() if v}
    save_json(state_dir / OVERRIDES_FILE, overrides)
    log.info("settings saved (%s %s): %s", part, owner, ", ".join(sorted(changed)))
    concerned = [a for a in agents if any(concerns(BY_NAME[n], a) for n in changed)]
    restarted, skipped = [], []
    for a in concerned:
        state = state_of(a.container)
        if state not in ("running", "restarting"):
            skipped.append({"agent": a.name, "why": "docker unreachable" if state == "unknown" else "not running"})
            continue
        try:
            restart(a.container)
            restarted.append(a.name)
        except Exception as exc:  # noqa: BLE001 — one failed restart never hides the others
            skipped.append({"agent": a.name, "why": getattr(exc, "detail", type(exc).__name__)})
    return {"saved": sorted(changed), "restarted": restarted, "skipped": skipped}
