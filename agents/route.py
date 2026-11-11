"""The route of Кіра's private answer (pure, an injected clock) — v5.21 (the owner, 2026-11-02): no judge, two modes.

`mode` says how the next answer is made: `gemini`, or `backup` — for `FALLBACK_WINDOW_S` after a block, for
`FALLBACK_LOCK_S` after more than `FALLBACK_HOUR_MAX` blocks in the last 60 minutes, or by hand (`/backup`) until
`/gemini`, which ends either and empties the hour's count. After the window his next message goes straight to Gemini.
`state/<name>.route.json` keeps the pin (`auto` or `backup`), the last hour's block times, the window's end and today's
answers — never a text. (v5.14's day cap, the window's end by the judge's rating, the pin `gemini` and the judge's and
the probe's counts went in v5.21; a file that still has them loads with them ignored.)
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

PINS = ("auto", "backup")
HOUR_MS = 3_600_000


@dataclass(frozen=True)
class Route:
    pin: str = "auto"
    pinned_at_ms: int | None = None
    blocks: tuple[int, ...] = ()            # the last hour's block times (ms)
    window_until_ms: int | None = None      # an opened window's end; None: no window
    day: str = ""                           # her local day the answers count
    answers: dict = field(default_factory=lambda: {"gemini": 0, "backup": 0})


def day_bounds(now_ms: int, tz: str) -> tuple[str, int, int]:
    """Her local day of `now_ms`: (ISO date, its start, its end) in ms — a DST day is 23 or 25 hours long."""
    zone = ZoneInfo(tz)
    now = datetime.fromtimestamp(now_ms / 1000, zone)
    start = datetime(now.year, now.month, now.day, tzinfo=zone)
    nxt = start.date() + timedelta(days=1)
    end = datetime(nxt.year, nxt.month, nxt.day, tzinfo=zone)
    return start.date().isoformat(), int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def _int(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def load_route(path: Path) -> Route:
    """The saved route; missing or corrupt → `auto`, nothing open. A file from before v5.21 loads with the pin `gemini`
    as `auto` and its day cap's and the judge's and the probe's fields ignored."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Route()
    if not isinstance(data, dict):
        return Route()
    answers = data.get("answers") if isinstance(data.get("answers"), dict) else {}
    blocks = data.get("blocks") if isinstance(data.get("blocks"), list) else []
    pin = data.get("pin") if data.get("pin") in PINS else "auto"
    return Route(pin=pin, pinned_at_ms=_int(data.get("pinned_at_ms")) if pin != "auto" else None,
                 blocks=tuple(t for t in (_int(b) for b in blocks) if t is not None),
                 window_until_ms=_int(data.get("window_until_ms")),
                 day=str(data.get("day") or ""),
                 answers={k: _int(answers.get(k)) or 0 for k in ("gemini", "backup")})


def save_route(path: Path, route: Route) -> None:
    """Atomic, private from birth (0600) — a pin, times and counts, never a text."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, json.dumps({"pin": route.pin, "pinned_at_ms": route.pinned_at_ms, "blocks": list(route.blocks),
                                 "window_until_ms": route.window_until_ms, "day": route.day,
                                 "answers": route.answers}).encode())
    finally:
        os.close(fd)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def _hhmm(ms: int, tz: str) -> str:
    return datetime.fromtimestamp(ms / 1000, ZoneInfo(tz)).strftime("%H:%M")


# --- v5.21: the modes, the outcomes, the backup's mark and `/status` ---------------------------------------------------
MODES = ("gemini", "backup")
BACKUP_MARK_RE = re.compile(r"^⚙️ backup(?: до \d{2}:\d{2}| · вручну)?\n")  # every form, on a line of its own


def mode(route: Route, now_ms: int) -> str:
    """v5.21 — how the next answer is made: `backup` by hand (the pin `backup`) or while a window is ahead, `gemini`
    otherwise — after the window his next message goes straight to Gemini."""
    if route.pin == "backup":
        return "backup"
    return "backup" if route.window_until_ms is not None and now_ms < route.window_until_ms else "gemini"


def step(route: Route, now_ms: int, outcome: str, window_s: int, hour_max: int, lock_s: int, day: str) -> Route:
    """v5.21 — the route after an outcome: `block` (a Gemini block or a caught refusal: the backup for `window_s`, or for
    `lock_s` once more than `hour_max` blocks fell in the last 60 minutes; by hand, neither counted nor windowed),
    `gemini` / `backup` (who answered, counted for her day), `pin:gemini` (the owner: back to Gemini now — the window
    ends and the hour's count is emptied), `pin:backup` (the backup until `/gemini`) or `clear` (v5.24, AGORA-212: the
    scan made her prompt pass — the window ends, the hour's count and a pin stay). Only the last hour's blocks are
    kept."""
    answers = dict(route.answers) if route.day == day else {"gemini": 0, "backup": 0}
    r = replace(route, day=day, answers=answers, blocks=tuple(t for t in route.blocks if t > now_ms - HOUR_MS))
    if outcome == "block":
        if r.pin == "backup":
            return r
        blocks = (*r.blocks, now_ms)
        until = now_ms + (lock_s if len(blocks) > hour_max else window_s) * 1000
        ahead = r.window_until_ms if r.window_until_ms is not None and r.window_until_ms > now_ms else 0
        return replace(r, blocks=blocks, window_until_ms=max(ahead, until))
    if outcome in ("gemini", "backup"):
        r = replace(r, answers={**answers, outcome: answers.get(outcome, 0) + 1})
        if outcome == "gemini" and r.window_until_ms is not None and now_ms >= r.window_until_ms:
            r = replace(r, window_until_ms=None)
        return r
    if outcome == "clear":
        return replace(r, window_until_ms=None)
    if outcome == "pin:gemini":
        return replace(r, pin="auto", pinned_at_ms=None, window_until_ms=None, blocks=())
    if outcome == "pin:backup":
        return replace(r, pin="backup", pinned_at_ms=now_ms)
    return r


def backup_mark(route: Route, now_ms: int, tz: str) -> str:
    """v5.21 — the line above her words through the backup (the owner: «просто додай туди годину до якої він
    включений»): «⚙️ backup до HH:MM», the window's end in her `TIMEZONE`, or «⚙️ backup · вручну» by hand."""
    if route.pin == "backup":
        return "⚙️ backup · вручну"
    if route.window_until_ms is not None and route.window_until_ms > now_ms:
        return f"⚙️ backup до {_hhmm(route.window_until_ms, tz)}"
    return "⚙️ backup"


def route_status(route: Route, now_ms: int, tz: str, hour_max: int, blocked: int, answers: dict,
                 main: str = "gemini", label: str | None = None) -> str:
    """v5.21 — `/status`: the mode and its end, the blocks of the last hour out of `hour_max`, her `blocked` private
    lines, today's answers through Gemini and through the backup. One service block, never a text of the talk. v7.3:
    `main` names the main model's command (`claude` on Claude); the stored mode stays `gemini`, the main model.
    v7.4: `label` names the model itself (a companion's chosen one), `main` stays the command."""
    label = label or main
    if route.pin == "backup":
        where = f"backup вручну (повернути: /{main})"
    elif mode(route, now_ms) == "backup":
        where = f"backup до {_hhmm(route.window_until_ms, tz)} (повернути зараз: /{main})"
    else:
        where = label
    hour = sum(1 for t in route.blocks if t > now_ms - HOUR_MS)
    return (f"⚙️ Маршрут — {where}\n"
            f"Блоків за останню годину: {hour} з {hour_max} (більше — backup на годину)\n"
            f"Приватний чат: закритих рядків {blocked}\n"
            f"Сьогодні відповіла: через {label} {answers.get('gemini', 0)}, через backup {answers.get('backup', 0)}")


def day_counts(records: list[dict], day: str, now_ms: int) -> tuple[dict, int, int]:
    """Her private answers of `day` from her usage lines: ({gemini, backup} answered, blocks in the last hour, blocks
    today) — a block or a refusal is the line's `blocked` (v5.13), the backup's engine `novelai` (v5.14)."""
    answers, hour, today = {"gemini": 0, "backup": 0}, 0, 0
    for r in records:
        ts = str(r.get("ts", ""))
        if not ts.startswith(day) or r.get("kind") not in ("private", "private_nudge"):
            continue
        if r.get("blocked"):
            today += 1
            try:
                hour += datetime.fromisoformat(ts).timestamp() * 1000 >= now_ms - HOUR_MS
            except ValueError:
                pass
        elif r.get("ok"):
            answers["backup" if r.get("engine") == "novelai" else "gemini"] += 1
    return answers, hour, today
