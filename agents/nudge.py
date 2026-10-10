"""The cat starts conversations (v4.3): when a nudge is due, what kind it is, and its small state file.

He is the only agent that ever posts without a trigger — the path runs only with the `nudge` capability. After a
quiet stretch in the daytime he drops one line tied to the recent talk: a past-life fragment, a Linux line, or the
day's horoscope as a metaphor. `state/<name>.nudge.json` keeps the last attempt, the day and the day's count (no
texts), so a restart neither re-nudges at once nor exceeds the cap. Everything but the file I/O is pure.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

NUDGE_KINDS = ("memory", "command", "horoscope")
# the rule and the material of a nudge (the prompt; never a claim about anyone in the room)
NUDGE_RULE = ("Ти сам починаєш розмову: один короткий рядок, що пов'язує це з тим, про що недавно говорили. "
              "Не вітайся і не питай, чи є хтось.")
COMMAND_MATERIAL = "Кинь один рядок команди Linux чи скрипту — лише як текст, — що пасує до розмови."
HOROSCOPE_MATERIAL = "Перекажи свій сьогоднішній гороскоп метафорою про останню розмову."


@dataclass
class NudgeState:
    last_ms: int | None  # the last attempt (sent or silent), wall-clock ms
    day: str             # the local day the count belongs to
    count: int           # nudges sent that day
    sent_ms: int | None = None  # the last nudge actually sent (the panel's "last nudge")


def parse_hours(spec: str) -> tuple[int, int]:
    """`"09-22"` → (9, 22): the local hours a nudge may go out, start inclusive, end exclusive; a start after the
    end wraps past midnight (`"09-03"`: from 09:00 to 03:00 the next night)."""
    try:
        start, end = (int(x) for x in str(spec).split("-", 1))
    except ValueError as exc:
        raise ValueError(f"CAT_NUDGE_HOURS must look like 09-22, got {spec!r}") from exc
    if not (0 <= start <= 23 and 0 <= end <= 24 and start != end):
        raise ValueError(f"CAT_NUDGE_HOURS must be two different hours, 0-23 and 0-24, got {spec!r}")
    return start, end


def in_hours(hour: int, hours: tuple[int, int]) -> bool:
    start, end = hours
    return start <= hour < end if start < end else hour >= start or hour < end


def nudge_due(now_ms: int, local_now: datetime, last_room_ms: int | None, last_nudge_ms: int | None,
              nudges_today: int, idle_ms: int, per_day: int, hours: tuple[int, int]) -> bool:
    """All of: daytime (`hours`, local), under the day's cap, the room quiet for `idle_ms` (its last message, purrs
    included — an empty room counts as quiet), and the last attempt at least `idle_ms` ago."""
    if not in_hours(local_now.hour, hours):
        return False
    if nudges_today >= per_day:
        return False
    if last_room_ms is not None and now_ms - last_room_ms < idle_ms:
        return False
    return last_nudge_ms is None or now_ms - last_nudge_ms >= idle_ms


def nudge_kind(day: str, n: int) -> str:
    """The day's n-th nudge: memory, command or horoscope — a deterministic draw over the day and the number."""
    from agents.turns import uniform  # local: turns imports config, which imports the roster

    return NUDGE_KINDS[min(int(uniform(f"{day}:{n}", "nudge") * len(NUDGE_KINDS)), len(NUDGE_KINDS) - 1)]


def load_nudge_state(path: Path, day: str) -> NudgeState:
    """The state for `day`: a missing or corrupt file is a fresh state; another day keeps the last attempt (the gap
    holds across midnight) and starts the count at 0."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        last, sent = data.get("last_ms"), data.get("sent_ms")
        last = int(last) if last is not None else None
        sent = int(sent) if sent is not None else None
        stored_day, count = str(data["day"]), int(data["count"])
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return NudgeState(None, day, 0)
    return NudgeState(last, day, count if stored_day == day else 0, sent)


def save_nudge_state(path: Path, state: NudgeState) -> None:
    """Atomic, private from birth (0600) — times and a count, never a text."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, json.dumps({"last_ms": state.last_ms, "day": state.day, "count": state.count,
                                 "sent_ms": state.sent_ms}).encode())
    finally:
        os.close(fd)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
