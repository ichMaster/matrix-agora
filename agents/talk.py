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

from agents.memory import HUMAN_MEMORY
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
    - `hour`: starting within the last `hour_days` days, or earlier in a day not yet past the band (code review v5.23
      #3: else an hour not written in the band — a downtime, an outage — waits in neither level until its day passes);
    - `day` (v5.23): ended before the hours' band and within the last `day_days` days;
    - nothing older (v5.23: her recall brings it back).
    v5.27: a `day` that overlaps a `day` already written by more than two hours (one written in another zone, before
    a move) is held — a DST day's neighbour overlaps it by an hour at most."""
    hour_cut, day_cut = now_ms - hour_days * DAY_MS, now_ms - day_days * DAY_MS
    held_days = [s for lv, s in held if lv == "day"]
    due: dict[tuple[str, int], int] = {}
    for ts in open_times:
        for level in LEVELS:
            start, end = period_of(level, ts, tz)
            if (level, start) in held or (level, start) in due or end > now_ms:
                continue
            if level == "day" and any(min(end, s + DAY_MS) - max(start, s) > 2 * HOUR_MS for s in held_days):
                continue  # v5.27: a day of another zone is written over it — a move never doubles a day
            if (level == "hour" and (start >= hour_cut or period_of("day", start, tz)[1] > hour_cut)) or (
                    level == "day" and day_cut < end <= hour_cut):
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


# v5.24 (the owner, 2026-11-04: «коли робиться підсумок то треба давати промпт який би просив згладити сцени близкості
# і коли підсумок готовий то треба робити валідацію чи він не блочить»; «якщо він блочить то знову корекція через
# промпт і так 3 рази і кожен раз все строгіше промпт, на 3й раз взагалі промпт має бути забрати всі сцени
# близкості»; «якщо третя генерація теж не проходить валідацію то взагалі не робити самаризацію»): how a summary tells
# of their closeness — gently the first time, stricter the second, not at all the third; when the third still blocks,
# no summary. On 11-04 at 09:00 an hour's summary blocked her prompt the hour it came in, while its own lines, word for
# word, had passed. The summaries written before stay as they are (the owner: «не треба міняти вже згенеровані»).
TALK_GENTLE = (
    ("Близькість між вами згадуй м'яко і загально — тепло, ніжність, що ви були разом, — без подробиць тіла, дотиків і "
     "дій, без відвертих слів, без сили, болю чи влади одного над одним."),
    ("Близькість між вами — лише одним-двома загальними словами («були разом», «обіймалися»): жодних подробиць тіла, "
     "дотиків, дій чи бажань, жодної сили чи влади, жодних фото чи відео одне одного. Головне — про що говорили, що "
     "вирішили і що ти відчувала."),
    ("Прибери всі сцени близькості повністю: ані слова про близькість, ліжко, ковдру, роздягання, тіло, дотики, "
     "поцілунки, пристрасть, бажання, фантазії, фото чи відео одне одного, силу чи контроль. Пиши лише про інше: про що "
     "говорили, події дня, плани, справи, людей. Якщо, крім близькості, нічого не було — одне речення: ви говорили "
     "наодинці, і тобі було тепло."),
)


def iso_hour(ts_ms: int, tz: str) -> str:
    """A period's start for the log: the local ISO hour, never a text."""
    return datetime.fromtimestamp(ts_ms / 1000, ZoneInfo(tz)).strftime("%Y-%m-%dT%H:00")


def talk_request(level: str, name: str, canon: str, items: list[tuple[str, str]], max_words: int,
                 from_summaries: bool, strict: int = 0) -> tuple[str, str]:
    """(system instruction, contents) for a period's summary: her own memory of the talk alone with Ich, first person,
    from the lines (speaker, text) or, when they cover the period, the finer summaries — never a date, an hour or a
    word of when it was, which her prompt adds as she remembers it (`talk_section`); their closeness told as
    `TALK_GENTLE[strict]` says (v5.24: 0 the first time, each rewrite one step stricter)."""
    system = (f"{canon}\n\nТи — {name}. Запиши для себе коротку пам'ять про вашу розмову наодинці з Ich {SPAN[level]} — "
              f"від першої особи, мовою розмови, не більше {max_words} слів: про що говорили, що вирішили, що Ich "
              "розповів про себе, що ви одне одному пообіцяли, що ти відчувала. Тільки те, що є нижче, нічого не "
              "вигадуй. Без дат, без годин і без слів про те, коли це було (вчора, сьогодні, вранці).\n\n"
              f"{TALK_GENTLE[min(max(strict, 0), len(TALK_GENTLE) - 1)]}\n\n"
              f"{HUMAN_MEMORY}")  # v5.23 (the owner): a human's own memory
    if from_summaries:
        return system, "Що ти пам'ятаєш про ці години, по черзі:\n" + "\n".join(f"- {text}" for _, text in items)
    return system, "Розмова:\n" + "\n".join(f"{who}: {text}" for who, text in items)


def covered(times: list[int], rows: list) -> bool:
    """Whether every open line's time falls in one of the finer rows' periods (an empty row counts: it was blocked)."""
    return bool(rows) and all(any(r.start_ms <= t < r.end_ms for r in rows) for t in times)


TALK_TITLE = "Що було між вами раніше (твоя пам'ять, а не те, що кажуть зараз):"
TALK_PROMPT_WORDS = 4000  # her prompt's summaries at most: past it the oldest go first


def talk_check_request(canon: str, text: str) -> tuple[str, str]:
    """(system instruction, contents) for the check of a summary written (v5.24): her canon, as her private prompt has
    it, and the summary as that prompt shows it — so what is checked is the summary alone."""
    return canon, f"{TALK_TITLE}\n- {text}"


WEEKDAY_ON = ("у понеділок", "у вівторок", "у середу", "у четвер", "у п'ятницю", "у суботу", "у неділю")


def _label(row, now: datetime, tz: str) -> str:
    """When a period was, as a person remembers it, never a date or an hour (the owner, 2026-10-26: «26 жовтня» gives
    her away): today, yesterday and the day before by `ago`; a day of the last week by its weekday (v5.23, the owner,
    2026-11-03: «став дати або мітки днів» — `ago` would call them all «цього тижня» or «минулого тижня»); older by
    `ago`. An hour adds its part of the day («у п'ятницю ввечері», «позавчора вранці»)."""
    then = datetime.fromtimestamp(row.start_ms / 1000, ZoneInfo(tz))
    diff = (now.date() - then.date()).days
    when = WEEKDAY_ON[then.weekday()] if 2 < diff < 7 else ago(then, now)
    if row.level in ("day", "gist_day") or when.startswith("сьогодні"):  # v7.6: a day's gist is a day
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


# --- v7.6 (AGORA-261): her talk in short — one line a day, one line a week (`MEMORY_MODE = lumi`) -----------------
# The owner, 2026-11-12: «також в Люмі меньше підсумків розмов в промпті»; «підсумки в промпті стають рядками на
# сесію, день і тиждень; -- сесія немає сенсу так як рестарт дуже рідко». A day's gist is written once from that day's
# summaries (its `day` row, else its hours, else v5.20's blocks — they cover every open line of the day, which her
# running digest may not: lines still in her window at midnight), a week's once from its days' gists; both are
# `talk` rows of their own levels, never rewritten and never shown in `layered` mode.
GIST_LEVELS = ("gist_day", "gist_week")
GIST_DAYS = 7
GIST_WEEKS = 4
GIST_WORDS = 30
GIST_TITLE = "Що було між вами раніше — коротко (твоя пам'ять, а не те, що кажуть зараз):"
GIST_SOURCES = ("day", "hour", "4h")  # a day's summaries, the coarsest first
GIST_SPAN = {"gist_day": "того дня", "gist_week": "того тижня"}
WEEKS_AGO = {1: "минулого тижня", 2: "два тижні тому", 3: "три тижні тому", 4: "чотири тижні тому"}


def week_of(ts_ms: int, tz: str) -> tuple[int, int]:
    """The local week (Monday 00:00 to the next Monday 00:00) that holds `ts_ms`."""
    zone = ZoneInfo(tz)
    day = datetime.fromtimestamp(ts_ms / 1000, zone).date()
    monday = day - timedelta(days=day.weekday())
    after = monday + timedelta(days=7)
    return (_ms(datetime(monday.year, monday.month, monday.day, tzinfo=zone)),
            _ms(datetime(after.year, after.month, after.day, tzinfo=zone)))


def _bands(now_ms: int, tz: str, gist_days: int, gist_weeks: int) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """The days shown (the last `gist_days` before today) and the weeks shown (the last `gist_weeks` that are over and
    began before the days shown, so no day falls between them), each oldest first."""
    today = period_of("day", now_ms, tz)[0]
    days, start = [], today
    for _ in range(max(gist_days, 0)):
        start = period_of("day", start - HOUR_MS, tz)[0]
        days.append((start, period_of("day", start, tz)[1]))
    band = days[-1][0] if days else today
    weeks, monday = [], week_of(now_ms, tz)[0]
    while len(weeks) < max(gist_weeks, 0):
        w_start, w_end = week_of(monday - HOUR_MS, tz)
        monday = w_start
        if w_start < band:
            weeks.append((w_start, w_end))
    return days[::-1], weeks[::-1]


def _overlaps(row, start: int, end: int) -> bool:
    return row.start_ms < end and row.end_ms > start


def gist_items(level: str, start: int, end: int, rows: list, tz: str) -> list[str]:
    """What a gist is written from (pure): a day's — its summaries of the coarsest level that has text; a week's —
    its days' gists, each with its weekday."""
    if level == "gist_day":
        for source in GIST_SOURCES:
            texts = [r.text for r in sorted(rows, key=lambda r: r.start_ms)
                     if r.level == source and r.text and start <= r.start_ms < end]
            if texts:
                return texts
        return []
    return [f"{WEEKDAY_ON[datetime.fromtimestamp(r.start_ms / 1000, ZoneInfo(tz)).weekday()]}: {r.text}"
            for r in sorted(rows, key=lambda r: r.start_ms) if r.level == "gist_day" and r.text
            and start <= r.start_ms < end]


def gists_due(now_ms: int, tz: str, rows: list, pending: list[tuple[str, int, int]], gist_days: int = GIST_DAYS,
              gist_weeks: int = GIST_WEEKS) -> list[tuple[str, int, int]]:
    """The gists to write, oldest first, as (level, start_ms, end_ms) (pure):
    - a day of the days shown, or of the weeks shown (a week is written from its days' gists), that has a summary
      with text, none of whose periods is still `pending`, and no gist yet;
    - a week shown that is over, has no gist yet, and whose every day with a summary has its gist."""
    held = {(r.level, r.start_ms) for r in rows if r.level in GIST_LEVELS}
    days, weeks = _bands(now_ms, tz, gist_days, gist_weeks)
    every_day = sorted({d for w_start, w_end in weeks for d in _days_of(w_start, w_end, tz)} | set(days))
    due = []
    for start, end in every_day:
        if ("gist_day", start) in held or not gist_items("gist_day", start, end, rows, tz):
            continue
        if any(s < end and e > start for _, s, e in pending):
            continue
        due.append(("gist_day", start, end))
    waiting = {s for _, s, _ in due}
    for start, end in weeks:
        if ("gist_week", start) in held or end > now_ms:
            continue
        days_with_talk = [s for s, e in _days_of(start, end, tz) if gist_items("gist_day", s, e, rows, tz)]
        if not days_with_talk or any(s in waiting or ("gist_day", s) not in held for s in days_with_talk):
            continue
        due.append(("gist_week", start, end))
    return sorted(due, key=lambda g: (g[1], GIST_LEVELS.index(g[0])))


def _days_of(start: int, end: int, tz: str) -> list[tuple[int, int]]:
    out, s = [], start
    while s < end:
        e = period_of("day", s, tz)[1]
        out.append((s, e))
        s = e
    return out


def week_label(start_ms: int, now: datetime, tz: str) -> str:
    """A week as a person remembers it: «минулого тижня», «два тижні тому», … — never a date."""
    then = datetime.fromtimestamp(start_ms / 1000, ZoneInfo(tz)).date()
    monday = now.date() - timedelta(days=now.weekday())
    n = max(1, (monday - then).days // 7)
    return WEEKS_AGO.get(n, f"{n} тижнів тому")


def gist_section(rows: list, now: datetime, tz: str, gist_days: int = GIST_DAYS,
                 gist_weeks: int = GIST_WEEKS) -> str | None:
    """Her private prompt's talk in `lumi` mode (pure): a line for each week shown, then for each day shown, oldest
    first, each labelled as she remembers it, an empty one skipped; no hour's text. None when nothing is left."""
    now_ms = int(now.timestamp() * 1000)
    days, weeks = _bands(now_ms, tz, gist_days, gist_weeks)
    by = {(r.level, r.start_ms): r for r in rows if r.level in GIST_LEVELS and r.text}
    lines = [f"- {week_label(s, now, tz)}: {by[('gist_week', s)].text}" for s, _ in weeks if ("gist_week", s) in by]
    lines += [f"- {_label(by[('gist_day', s)], now, tz)}: {by[('gist_day', s)].text}" for s, _ in days
              if ("gist_day", s) in by]
    return GIST_TITLE + "\n" + "\n".join(lines) if lines else None


def gist_request(level: str, name: str, canon: str, items: list[str], max_words: int,
                 strict: int = 0) -> tuple[str, str]:
    """(system instruction, contents) for a gist: one sentence of her own memory of their talk alone with Ich that day
    or that week, at most `max_words` words, from her summaries of it — never a date or an hour; their closeness told
    as `TALK_GENTLE[strict]` says."""
    system = (f"{canon}\n\nТи — {name}. Запиши для себе одним реченням, не більше {max_words} слів, пам'ять про вашу "
              f"розмову наодинці з Ich {GIST_SPAN[level]} — від першої особи, мовою розмови: головне, про що говорили "
              "і що ти відчувала. Тільки з того, що нижче, нічого не вигадуй. Без дат, без днів тижня і без годин.\n\n"
              f"{TALK_GENTLE[min(max(strict, 0), len(TALK_GENTLE) - 1)]}\n\n"
              f"{HUMAN_MEMORY}")
    head = "Що ти пам'ятаєш про той день, по черзі:" if level == "gist_day" else "Що ти пам'ятаєш про дні того тижня:"
    return system, head + "\n" + "\n".join(f"- {x}" for x in items)

