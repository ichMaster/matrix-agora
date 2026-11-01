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

from agents.world import PART_ADVERB, ago, part_of_day

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


SPAN = {"hour": "цієї години", "4h": "цих кількох годин", "week": "цього тижня"}
FINER = {"4h": "hour", "week": "4h"}  # a block is written from its hours, a week from its blocks, when they cover it
TALK_SPLIT_MIN = 4   # a blocked part this small is left out, never halved again
TALK_CALLS_MAX = 12  # a period's calls, halvings included
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


def _label(row, now: datetime, tz: str) -> str:
    """When a period was, as a person remembers it (`ago`), with the part of the day for an hour or a block — never a
    date or an hour."""
    then = datetime.fromtimestamp(row.start_ms / 1000, ZoneInfo(tz))
    when = ago(then, now)
    if row.level == "week" or when.startswith("сьогодні"):
        return when
    part = PART_ADVERB[part_of_day(then.hour)]
    return f"{when} {part}" if when in ("вчора", "позавчора") else f"{when}, {part}"


def talk_section(rows: list, before_ms: int, now: datetime, tz: str, words_budget: int = TALK_PROMPT_WORDS) -> str | None:
    """Her private prompt's summaries (pure): each period shown at the coarsest level written for it — a row is left
    out when a coarser row covers its start — only those that began before `before_ms` (the first line of Gemini's
    history window), oldest first, an empty one skipped, labelled as she remembers it; past `words_budget` words the
    oldest go first. None when nothing is left."""
    coarser = {"hour": ("4h", "week"), "4h": ("week",), "week": ()}
    shown = [r for r in rows if r.text and r.start_ms < before_ms and not any(
        o.level in coarser[r.level] and o.start_ms <= r.start_ms < o.end_ms for o in rows)]
    shown.sort(key=lambda r: r.start_ms)
    lines = [f"- {_label(r, now, tz)}: {r.text}" for r in shown]
    while lines and sum(len(x.split()) for x in lines) > words_budget:
        lines.pop(0)
    return TALK_TITLE + "\n" + "\n".join(lines) if lines else None


RECHECK_GROUP = 20  # the re-check's group: halved down to the lines that block


async def sift(items: list[tuple[str, str]], blocked, group: int = RECHECK_GROUP) -> tuple[set[str], int]:
    """The re-check (2026-11-02, made a command): (the ids that stay closed, the calls made). `items` are (id, line)
    in order; `blocked(text)` says whether Gemini blocks those lines at the prompt stage (True), passes them (False)
    or failed (None). Each group of `group` that blocks is halved down to the lines that block; a set whose halves both
    pass blocks only together and stays closed whole; a failed call keeps its lines closed."""
    calls = 0

    async def closed_of(part: list[tuple[str, str]]) -> list[str]:
        nonlocal calls
        calls += 1
        verdict = await blocked("\n".join(line for _, line in part))
        if verdict is False:
            return []
        if verdict is None or len(part) == 1:
            return [i for i, _ in part]
        half = len(part) // 2
        first, second = await closed_of(part[:half]), await closed_of(part[half:])
        return first + second if first or second else [i for i, _ in part]

    closed: set[str] = set()
    for n in range(0, len(items), group):
        closed.update(await closed_of(items[n:n + group]))
    return closed, calls


def main(argv: list[str] | None = None) -> int:
    """`python -m agents.talk recheck [--agent kira] [--since YYYY-MM-DD] [--until YYYY-MM-DD]`, in her container while
    she is stopped: her `censored` private lines of the local days go to Gemini again (`GeminiClient.probe`); what
    passes is marked `clean`. `waiting` and `reopened` stay. Counts only, never a text; the calls are usage lines of
    the kind `probe`."""
    import argparse
    import asyncio
    import json
    import os
    import time
    from datetime import date
    from pathlib import Path

    from agents.archive import Archive
    from agents.llm import GeminiClient
    from agents.usage import usage_line
    from agents.world import local_now

    parser = argparse.ArgumentParser(prog="python -m agents.talk")
    sub = parser.add_subparsers(dest="cmd", required=True)
    recheck = sub.add_parser("recheck", help="her censored private lines sent to Gemini again; what passes reopens")
    recheck.add_argument("--agent", default="kira")
    recheck.add_argument("--since", type=date.fromisoformat, default=None)
    recheck.add_argument("--until", type=date.fromisoformat, default=None)
    args = parser.parse_args(argv)
    tz = os.environ.get("TIMEZONE", "Europe/Kyiv")
    state = Path("state")
    usage_file = state / f"{args.agent}.usage.jsonl"

    def sink(kind, model, meta, ok, blocked=None):  # counted under the agent, like any other call of hers
        line = usage_line(local_now(int(time.time() * 1000), tz).isoformat(timespec="seconds"), args.agent, kind,
                          model, meta, ok, blocked)
        fd = os.open(usage_file, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, (json.dumps(line, ensure_ascii=False) + "\n").encode())
        finally:
            os.close(fd)

    def edge(day: date | None, default: int) -> int:
        return _ms(datetime(day.year, day.month, day.day, tzinfo=ZoneInfo(tz))) if day else default

    start, end = edge(args.since, 0), edge(args.until + timedelta(days=1) if args.until else None, 2 ** 62)
    archive = Archive(state / f"{args.agent}.archive.db")
    try:
        rows = archive.db.execute("SELECT key, speaker, text FROM lines WHERE place = 'private' AND mark = 'censored' "
                                  "AND ts_ms >= ? AND ts_ms < ? ORDER BY ts_ms, id", (start, end)).fetchall()
        items = [(key, f"{speaker}: {text}") for key, speaker, text in rows]
        client = GeminiClient(sink=sink)

        async def blocked(text: str) -> bool | None:
            for attempt in range(3):  # a transient failure is tried again before its lines stay closed
                verdict = await client.probe(text, None)
                if verdict is not None:
                    return verdict
                await asyncio.sleep(5 * (attempt + 1))
            return None

        closed, calls = asyncio.run(sift(items, blocked))
        reopened = archive.mark([k for k, _ in items if k not in closed], "clean")
    finally:
        archive.close()
    print(f"recheck: {len(items)} censored · reopened {reopened} · still closed {len(closed)} · calls {calls}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
