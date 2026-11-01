"""v5.20 — Кіра's layered memory of the private chat (ROADMAP §v5.20, ARCHITECTURE §Memory).

On top of her private prompt stay the last `HISTORY_N` messages word for word. Below them, summaries of the open talk
older than that window: by the hour for the last `TALK_HOUR_DAYS` days, by local four-hour blocks (00, 04, 08, 12, 16,
20) up to `TALK_4H_DAYS`, by the week (Monday 00:00) after that. Gemini 3.1 Pro writes each one once, from the lines
open to it; the rows live in her archive's `talk` table and are never rewritten. The closed talk is never summarized
for Gemini: it stays in the archive, counted per period.

Everything here is pure — plain data and an injected clock; the agent reads the archive and calls Gemini.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

LEVELS = ("hour", "4h", "week")
DAY_MS = 86_400_000
HOUR_MS = 3_600_000


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def period_of(level: str, ts_ms: int, tz: str) -> tuple[int, int]:
    """The local period of `level` that holds `ts_ms`: (start_ms, end_ms). An hour is an hour of the clock; a block and
    a week start and end at local wall-clock times, so on a DST day they have their true length."""
    zone = ZoneInfo(tz)
    t = datetime.fromtimestamp(ts_ms / 1000, zone)
    if level == "hour":
        start = (ts_ms // HOUR_MS) * HOUR_MS  # Kyiv's offsets are whole hours
        return start, start + HOUR_MS
    if level == "4h":
        first = datetime(t.year, t.month, t.day, t.hour - t.hour % 4, tzinfo=zone)
        nxt = first.replace(tzinfo=None) + timedelta(hours=4)
        return _ms(first), _ms(datetime(nxt.year, nxt.month, nxt.day, nxt.hour, tzinfo=zone))
    if level == "week":
        monday = (t - timedelta(days=t.weekday())).date()
        after = monday + timedelta(days=7)
        return (_ms(datetime(monday.year, monday.month, monday.day, tzinfo=zone)),
                _ms(datetime(after.year, after.month, after.day, tzinfo=zone)))
    raise ValueError(f"unknown level {level!r}")


def periods_due(now_ms: int, tz: str, open_times: list[int], held: set[tuple[str, int]], hour_days: int,
                fourh_days: int) -> list[tuple[str, int, int]]:
    """The periods to summarize, oldest first, as (level, start_ms, end_ms): each holds at least one line open to
    Gemini (`open_times`), is over, and is not `held` ((level, start_ms) already written).
    - `hour`: starting within the last `hour_days` days;
    - `4h`: ended before the hours' band, and not wholly before the blocks' band (`fourh_days`);
    - `week`: ended before the blocks' band."""
    hour_cut, fourh_cut = now_ms - hour_days * DAY_MS, now_ms - fourh_days * DAY_MS
    due: dict[tuple[str, int], int] = {}
    for ts in open_times:
        for level in LEVELS:
            start, end = period_of(level, ts, tz)
            if (level, start) in held or (level, start) in due or end > now_ms:
                continue
            if (level == "hour" and start >= hour_cut) or (level == "4h" and fourh_cut < end <= hour_cut) or (
                    level == "week" and end <= fourh_cut):
                due[(level, start)] = end
    return sorted(((lv, s, e) for (lv, s), e in due.items()), key=lambda p: (p[1], LEVELS.index(p[0])))
