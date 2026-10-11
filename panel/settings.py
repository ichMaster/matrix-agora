"""The panel's settings (v4.7): the schema with its overrides and every agent's effective values, and a save that
restarts exactly the agents a change concerns.

Names resolve only through the schema (`agents.settings`), values only through its `validate`; the only thing from a
request that reaches the docker API is a registry agent's container name. The overrides file is written atomically,
0600; each agent's `state/<name>.settings.json` is read-only here and degrades to `null` when unreadable.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from agents.settings import BY_NAME, OVERRIDES_FILE, SCHEMA, concerns, load_overrides, save_json, validate

log = logging.getLogger("panel.settings")
_SAVE_LOCK = threading.Lock()  # one save at a time: no lost update, no shared temp file (v4.7 review #5)

GROUPS = (("turns", "Room & turns"), ("personas", "Personas"), ("memory", "Memory"), ("cat", "Кіт"),
          ("claude", "Клод"), ("gemini", "Gemini"))


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


def settings_view(state_dir: Path, agents: Iterable[Any]) -> dict:
    """The schema, grouped, with each setting's override, the agents it concerns and their effective values."""
    agents = list(agents)
    overrides = load_overrides(state_dir / OVERRIDES_FILE)
    effective = {a.name: _effective(state_dir, a.name) for a in agents}
    rows = []
    for s in SCHEMA:
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
    return {"groups": [{"id": g, "title": t} for g, t in GROUPS], "settings": rows}


def save_settings(state_dir: Path, agents: Iterable[Any], body: Any, state_of: Callable[[str], str],
                  restart: Callable[[str], dict]) -> dict:
    """Validate `{"set": {name: value}, "reset": [names]}`, write the overrides, restart the concerned agents that
    run (a stopped one is skipped, never started). Nothing is written when anything is invalid; saves run one at a
    time."""
    with _SAVE_LOCK:
        return _save(state_dir, agents, body, state_of, restart)


def _save(state_dir: Path, agents: Iterable[Any], body: Any, state_of: Callable[[str], str],
          restart: Callable[[str], dict]) -> dict:
    if not isinstance(body, dict):
        raise SettingsError(422, "a JSON object is expected")
    to_set, to_reset = body.get("set") or {}, body.get("reset") or []
    if not isinstance(to_set, dict) or not isinstance(to_reset, list):
        raise SettingsError(422, "`set` is an object, `reset` a list")
    errors, clean = {}, {}
    for name, raw in to_set.items():
        value, why = validate(str(name), raw)
        if value is None:
            errors[str(name)] = why
        else:
            clean[str(name)] = value
    for name in to_reset:
        if str(name) not in BY_NAME:
            errors[str(name)] = "unknown setting"
    if errors:
        raise SettingsError(422, {"invalid": errors})
    overrides = load_overrides(state_dir / OVERRIDES_FILE)
    changed = []
    for name, value in clean.items():
        if overrides.get(name) != value:
            overrides[name] = value
            changed.append(name)
    for name in map(str, to_reset):
        if name in overrides:
            del overrides[name]
            changed.append(name)
    if not changed:
        return {"saved": [], "restarted": [], "skipped": []}
    save_json(state_dir / OVERRIDES_FILE, {k: v for k, v in overrides.items() if k in BY_NAME})
    log.info("settings saved: %s", ", ".join(sorted(changed)))
    agents = list(agents)
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
