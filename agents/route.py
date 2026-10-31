"""v5.14 — the route of Кіра's private answer: Gemini, or the backup's window after a block (pure, an injected clock).

`state` says how the next answer is made: `gemini`; `window` (the backup alone, for `FALLBACK_WINDOW_S` after a block,
or to her day's end once `FALLBACK_DAY_MAX` blocks fell in her local day); `window_end` (the first message after the
window: Gemini and the backup start together — Gemini's answer wins and closes the window, a block opens the next).
A pin from a Telegram command overrides the rules, the day cap included, until `/auto`: pinned `backup` is a window with
no end, pinned `gemini` is Gemini's state where a block still goes to the backup but opens no window. v5.15.3 (the
owner, v5.14 review #5): a block under a pin is kept apart and never counts toward the day cap, so `/auto` after a
pinned evening does not send the rest of the day to the backup.
`state/<name>.route.json` keeps the pin, the block times (those under a pin apart too), the window's end, today's
answers and (v5.15) today's ratings by the judge — never a text.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

PINS = ("auto", "gemini", "backup")
STATES = ("gemini", "window", "window_end")
OUTCOMES = ("block", "gemini", "backup", "rated", "flagged")  # and `pin:<auto|gemini|backup>`
HOUR_MS = 3_600_000


@dataclass(frozen=True)
class Route:
    pin: str = "auto"
    pinned_at_ms: int | None = None
    blocks: tuple[int, ...] = ()            # the block times (ms) of her day and the last hour
    window_until_ms: int | None = None      # an opened window's end; None: no window
    day: str = ""                           # her local day the answers count
    answers: dict = field(default_factory=lambda: {"gemini": 0, "backup": 0})
    judged: dict = field(default_factory=lambda: {"rated": 0, "flagged": 0})  # v5.15: today's lines the judge rated
    pinned_blocks: tuple[int, ...] = ()     # v5.15.3: the block times under a pin — in `blocks`, not in the day cap
    probed: dict = field(default_factory=lambda: {"calls": 0, "closed": 0})  # v5.16: today's probe calls, parts closed


def day_bounds(now_ms: int, tz: str) -> tuple[str, int, int]:
    """Her local day of `now_ms`: (ISO date, its start, its end) in ms — a DST day is 23 or 25 hours long."""
    zone = ZoneInfo(tz)
    now = datetime.fromtimestamp(now_ms / 1000, zone)
    start = datetime(now.year, now.month, now.day, tzinfo=zone)
    nxt = start.date() + timedelta(days=1)
    end = datetime(nxt.year, nxt.month, nxt.day, tzinfo=zone)
    return start.date().isoformat(), int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def state(route: Route, now_ms: int) -> str:
    """How the next answer is made: `gemini`, `window` or `window_end`."""
    if route.pin == "gemini":
        return "gemini"
    if route.pin == "backup":
        return "window"
    if route.window_until_ms is None:
        return "gemini"
    return "window" if now_ms < route.window_until_ms else "window_end"


def blocks_since(route: Route, since_ms: int) -> int:
    return sum(1 for t in route.blocks if t >= since_ms)


def capped_since(route: Route, since_ms: int) -> int:
    """The blocks that count toward the day cap: those under `auto` (v5.15.3)."""
    return blocks_since(route, since_ms) - sum(1 for t in route.pinned_blocks if t >= since_ms)


def after(route: Route, now_ms: int, outcome: str, window_s: int, day_max: int, day: str, day_start_ms: int,
          day_end_ms: int, rated: int = 0, flagged: int = 0, calls: int = 0, closed: int = 0) -> Route:
    """The route after an outcome: `block` (Gemini blocked or refused), `gemini` / `backup` (who answered), `rated`
    (v5.15: the judge rated `rated` lines, `flagged` of them flagged), `flagged` (v5.15: at the window's end the judge
    kept the backup on — the next window, no block, not counted toward the day cap), `probed` (v5.16: Gemini was asked
    `calls` times about a blocked prompt's parts, `closed` of them closed), or `pin:<auto|gemini|backup>` (a
    command)."""
    answers = dict(route.answers) if route.day == day else {"gemini": 0, "backup": 0}
    judged = dict(route.judged) if route.day == day else {"rated": 0, "flagged": 0}
    probed = dict(route.probed) if route.day == day else {"calls": 0, "closed": 0}
    keep_from = min(day_start_ms, now_ms - HOUR_MS)
    r = replace(route, day=day, answers=answers, judged=judged, probed=probed,
                blocks=tuple(t for t in route.blocks if t >= keep_from),
                pinned_blocks=tuple(t for t in route.pinned_blocks if t >= keep_from))
    if outcome == "block":
        r = replace(r, blocks=(*r.blocks, now_ms))
        if r.pin != "auto":  # never counted toward the day cap (v5.15.3)
            r = replace(r, pinned_blocks=(*r.pinned_blocks, now_ms))
        if r.pin == "auto":  # pinned `gemini` opens no window; pinned `backup` never asks Gemini
            until = day_end_ms if capped_since(r, day_start_ms) >= day_max else now_ms + window_s * 1000
            r = replace(r, window_until_ms=max(r.window_until_ms or 0, until))
    elif outcome in ("gemini", "backup"):
        r = replace(r, answers={**answers, outcome: answers.get(outcome, 0) + 1})
        if outcome == "gemini" and r.pin == "auto" and r.window_until_ms is not None and now_ms >= r.window_until_ms:
            r = replace(r, window_until_ms=None)  # the talk is Gemini's again
    elif outcome == "flagged":
        if r.pin == "auto":
            r = replace(r, window_until_ms=max(r.window_until_ms or 0, now_ms + window_s * 1000))
    elif outcome == "rated":
        r = replace(r, judged={"rated": judged.get("rated", 0) + max(int(rated), 0),
                               "flagged": judged.get("flagged", 0) + max(int(flagged), 0)})
    elif outcome == "probed":
        r = replace(r, probed={"calls": probed.get("calls", 0) + max(int(calls), 0),
                               "closed": probed.get("closed", 0) + max(int(closed), 0)})
    elif outcome.startswith("pin:") and outcome[4:] in PINS:
        pin = outcome[4:]
        r = replace(r, pin=pin, pinned_at_ms=None if pin == "auto" else now_ms)
    return r


def _int(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def load_route(path: Path) -> Route:
    """The saved route; missing or corrupt → `auto`, nothing open."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Route()
    if not isinstance(data, dict):
        return Route()
    answers = data.get("answers") if isinstance(data.get("answers"), dict) else {}
    judged = data.get("judged") if isinstance(data.get("judged"), dict) else {}
    blocks = data.get("blocks") if isinstance(data.get("blocks"), list) else []
    pinned = data.get("pinned_blocks") if isinstance(data.get("pinned_blocks"), list) else []
    probed = data.get("probed") if isinstance(data.get("probed"), dict) else {}
    return Route(pin=data.get("pin") if data.get("pin") in PINS else "auto",
                 pinned_at_ms=_int(data.get("pinned_at_ms")),
                 blocks=tuple(t for t in (_int(b) for b in blocks) if t is not None),
                 window_until_ms=_int(data.get("window_until_ms")),
                 day=str(data.get("day") or ""),
                 answers={k: _int(answers.get(k)) or 0 for k in ("gemini", "backup")},
                 judged={k: _int(judged.get(k)) or 0 for k in ("rated", "flagged")},
                 pinned_blocks=tuple(t for t in (_int(b) for b in pinned) if t is not None),
                 probed={k: _int(probed.get(k)) or 0 for k in ("calls", "closed")})


def save_route(path: Path, route: Route) -> None:
    """Atomic, private from birth (0600) — a pin, times and counts, never a text."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, json.dumps({"pin": route.pin, "pinned_at_ms": route.pinned_at_ms, "blocks": list(route.blocks),
                                 "window_until_ms": route.window_until_ms, "day": route.day,
                                 "answers": route.answers, "judged": route.judged,
                                 "pinned_blocks": list(route.pinned_blocks), "probed": route.probed}).encode())
    finally:
        os.close(fd)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


PIN_NAMES = {"auto": "auto", "gemini": "gemini", "backup": "backup"}  # the commands' own words


def _hhmm(ms: int, tz: str) -> str:
    return datetime.fromtimestamp(ms / 1000, ZoneInfo(tz)).strftime("%H:%M")


def status_text(route: Route, now_ms: int, tz: str, day_max: int, waiting: int, censored: int,
                answers: dict, blocks_hour: int, blocks_today: int, judged: dict | None = None) -> str:
    """`/status`: the route, auto or pinned since when (lifted by `/auto`); the blocks in the last hour and today, out
    of the cap; the lines of her private chat waiting for the judge and censored; today's answers by Gemini and by the
    backup. The counts are the whole day's (the owner's live test: from her usage lines, not only since the route's
    file began). v5.15: the judge's line — today's lines rated and flagged (`judged`, the route's counts of her day)
    and those still waiting, or «вимкнено» (None). v5.15.3: today's blocks under a pin, named as outside the cap.
    One service line block, never a text of the talk."""
    start = day_bounds(now_ms, tz)[1]
    pinned = sum(1 for t in route.pinned_blocks if t >= start)
    if route.pin != "auto":
        since = f"закріплено о {_hhmm(route.pinned_at_ms, tz)}; " if route.pinned_at_ms else "закріплено; "
        where = f"{PIN_NAMES[route.pin]} ({since}скасувати: /auto)"
    elif state(route, now_ms) == "window":
        where = f"auto: backup до {_hhmm(route.window_until_ms, tz)}"
    elif state(route, now_ms) == "window_end":
        where = "auto: вікно backup скінчилось — наступне повідомлення вирішить"
    else:
        where = "auto: gemini"
    return (f"⚙️ Маршрут — {where}\n"
            f"Блоків: за годину {blocks_hour}, сьогодні {blocks_today} з {day_max}"
            + (f" (під закріпленням {pinned} — не в ліміті)" if pinned else "") + "\n"
            f"Приватний чат: чекають на суддю {waiting}, цензуровані {censored}\n"
            f"Сьогодні відповіла: через gemini {answers.get('gemini', 0)}, через backup {answers.get('backup', 0)}\n"
            + ("Суддя: вимкнено" if judged is None else
               f"Суддя: оцінено сьогодні {judged.get('rated', 0)}, позначено {judged.get('flagged', 0)}, "
               f"чекають {waiting}"))


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
