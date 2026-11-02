"""v5.20 — Кіра's layered memory of the private chat (ROADMAP §v5.20, §v5.23, ARCHITECTURE §Memory).

On top of her private prompt stays her last day of talk word for word (v5.23: the window by time). Below it, summaries
of the open talk older than that window — v5.23 (the owner, 2026-11-02: «далі за попередні 2 доби по годині і потім
4 дні підсумок дня а решта вже РАГ»): by the hour for the last `TALK_HOUR_DAYS` (3) days, by the local day up to
`TALK_DAY_DAYS` (7), and nothing older (her recall brings it back). Gemini 3.1 Pro writes each one once, from the
lines open to it; the rows live in her archive's `talk` table and are never rewritten — v5.20's four-hour blocks and
weeks stay there, never written again and never shown. The closed talk is never summarized
for Gemini: it is counted per period (v5.21: its text is emptied after a day, and nothing reopens it — the re-check
went).

Everything here is pure — plain data and an injected clock; the agent reads the archive and calls Gemini.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from agents.world import PART_ADVERB, ago, part_of_day

LEVELS = ("hour", "day")  # v5.23; the older rows' `4h` and `week` are kept, never due or shown
DAY_MS = 86_400_000
HOUR_MS = 3_600_000


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def period_of(level: str, ts_ms: int, tz: str) -> tuple[int, int]:
    """The local period of `level` that holds `ts_ms`: (start_ms, end_ms). An hour is an hour of the clock; a day
    (v5.23) starts and ends at local midnight, so a DST day has its true length."""
    if level == "hour":
        start = (ts_ms // HOUR_MS) * HOUR_MS  # Kyiv's offsets are whole hours
        return start, start + HOUR_MS
    if level == "day":
        zone = ZoneInfo(tz)
        day = datetime.fromtimestamp(ts_ms / 1000, zone).date()
        after = day + timedelta(days=1)
        return (_ms(datetime(day.year, day.month, day.day, tzinfo=zone)),
                _ms(datetime(after.year, after.month, after.day, tzinfo=zone)))
    raise ValueError(f"unknown level {level!r}")


def periods_due(now_ms: int, tz: str, open_times: list[int], held: set[tuple[str, int]], hour_days: int,
                day_days: int) -> list[tuple[str, int, int]]:
    """The periods to summarize, oldest first, as (level, start_ms, end_ms): each holds at least one line open to
    Gemini (`open_times`), is over, and is not `held` ((level, start_ms) already written).
    - `hour`: starting within the last `hour_days` days;
    - `day` (v5.23): ended before the hours' band and within the last `day_days` days;
    - nothing older (v5.23: her recall brings it back)."""
    hour_cut, day_cut = now_ms - hour_days * DAY_MS, now_ms - day_days * DAY_MS
    due: dict[tuple[str, int], int] = {}
    for ts in open_times:
        for level in LEVELS:
            start, end = period_of(level, ts, tz)
            if (level, start) in held or (level, start) in due or end > now_ms:
                continue
            if (level == "hour" and start >= hour_cut) or (level == "day" and day_cut < end <= hour_cut):
                due[(level, start)] = end
    return sorted(((lv, s, e) for (lv, s), e in due.items()), key=lambda p: (p[1], LEVELS.index(p[0])))


SPAN = {"hour": "цієї години", "day": "цього дня"}
# v5.23: a day is written from its hours when they cover it, else from v5.20's four-hour blocks (the first backfill's
# days, whose hours were never written: a whole day's lines named what she is twice and left the day empty), else
# from its lines
FINER = {"day": ("hour", "4h")}
TALK_SPLIT_MIN = 4   # a blocked part this small is left out, never halved again
TALK_CALLS_MAX = 12  # a period's calls, halvings included
TALK_FAILS_MAX = 3   # code review v5.20 #2: a period whose call keeps failing, unblocked at the prompt stage, is
                     # then written empty — else, always the oldest due, it stalls every later one
TALK_CHECK_MS = 30_000  # how often the idle watcher looks for a period due: a backfill of 60 takes half an hour


def iso_hour(ts_ms: int, tz: str) -> str:
    """A period's start for the log: the local ISO hour, never a text."""
    return datetime.fromtimestamp(ts_ms / 1000, ZoneInfo(tz)).strftime("%Y-%m-%dT%H:00")


def talk_request(level: str, name: str, canon: str, items: list[tuple[str, str]], max_words: int,
                 from_summaries: bool) -> tuple[str, str]:
    """(system instruction, contents) for a period's summary: her own memory of the talk alone with Ich, first person,
    from the lines (speaker, text) or, when they cover the period, the finer summaries — never a date, an hour or a
    word of when it was, which her prompt adds as she remembers it (`talk_section`)."""
    system = (f"{canon}\n\nТи — {name}. Запиши для себе коротку пам'ять про вашу розмову наодинці з Ich {SPAN[level]} — "
              f"від першої особи, мовою розмови, не більше {max_words} слів: про що говорили, що вирішили, що Ich "
              "розповів про себе, що ви одне одному пообіцяли, що ти відчувала. Тільки те, що є нижче, нічого не "
              "вигадуй. Без дат, без годин і без слів про те, коли це було (вчора, сьогодні, вранці).")
    if from_summaries:
        return system, "Що ти пам'ятаєш про ці години, по черзі:\n" + "\n".join(f"- {text}" for _, text in items)
    return system, "Розмова:\n" + "\n".join(f"{who}: {text}" for who, text in items)


def covered(times: list[int], rows: list) -> bool:
    """Whether every open line's time falls in one of the finer rows' periods (an empty row counts: it was blocked)."""
    return bool(rows) and all(any(r.start_ms <= t < r.end_ms for r in rows) for t in times)


TALK_TITLE = "Що було між вами раніше (твоя пам'ять, а не те, що кажуть зараз):"
TALK_PROMPT_WORDS = 4000  # her prompt's summaries at most: past it the oldest go first


WEEKDAY_ON = ("у понеділок", "у вівторок", "у середу", "у четвер", "у п'ятницю", "у суботу", "у неділю")


def _label(row, now: datetime, tz: str) -> str:
    """When a period was, as a person remembers it, never a date or an hour (the owner, 2026-10-26: «26 жовтня» gives
    her away): today, yesterday and the day before by `ago`; a day of the last week by its weekday (v5.23, the owner,
    2026-11-03: «став дати або мітки днів» — `ago` would call them all «цього тижня» or «минулого тижня»); older by
    `ago`. An hour adds its part of the day («у п'ятницю ввечері», «позавчора вранці»)."""
    then = datetime.fromtimestamp(row.start_ms / 1000, ZoneInfo(tz))
    diff = (now.date() - then.date()).days
    when = WEEKDAY_ON[then.weekday()] if 2 < diff < 7 else ago(then, now)
    if row.level == "day" or when.startswith("сьогодні"):
        return when
    part = PART_ADVERB[part_of_day(then.hour)]
    return f"{when} {part}" if when in ("вчора", "позавчора") or 2 < diff < 7 else f"{when}, {part}"


def talk_section(rows: list, before_ms: int, now: datetime, tz: str, words_budget: int = TALK_PROMPT_WORDS,
                 day_days: int = 7) -> str | None:
    """Her private prompt's summaries (pure): v5.23 — only the `hour` and `day` rows, those ended within the last
    `day_days` days (nothing older: her recall brings it back), each period at the coarsest level written for it — an
    hour is left out when a day with text covers its start (an empty one hides nothing) — only those that began
    before `before_ms` (the first line of Gemini's history window), oldest first, an empty one skipped, labelled as
    she remembers it; past `words_budget` words the oldest go first. None when nothing is left."""
    cut = int(now.timestamp() * 1000) - day_days * DAY_MS
    kept = [r for r in rows if r.level in LEVELS and r.end_ms > cut]
    shown = [r for r in kept if r.text and r.start_ms < before_ms and not (r.level == "hour" and any(
        o.text and o.level == "day" and o.start_ms <= r.start_ms < o.end_ms for o in kept))]  # (review v5.20 #3)
    shown.sort(key=lambda r: r.start_ms)
    lines = [f"- {_label(r, now, tz)}: {r.text}" for r in shown]
    while lines and sum(len(x.split()) for x in lines) > words_budget:
        lines.pop(0)
    return TALK_TITLE + "\n" + "\n".join(lines) if lines else None
