"""Place, calendar and time in Ukrainian — from tables in code, never the
system locale; the clock is injected (ARCHITECTURE §World awareness)."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

WEEKDAYS = ["понеділок", "вівторок", "середа", "четвер", "п'ятниця", "субота", "неділя"]
MONTHS_GEN = ["січня", "лютого", "березня", "квітня", "травня", "червня",
              "липня", "серпня", "вересня", "жовтня", "листопада", "грудня"]
MONTHS_NOM = ["січень", "лютий", "березень", "квітень", "травень", "червень",
              "липень", "серпень", "вересень", "жовтень", "листопад", "грудень"]
PART_ADVERB = {"ранок": "вранці", "день": "вдень", "вечір": "ввечері", "ніч": "вночі"}


def local_now(clock_ms: int, tz: str) -> datetime:
    return datetime.fromtimestamp(clock_ms / 1000, ZoneInfo(tz))


def part_of_day(hour: int) -> str:
    if 5 <= hour < 12:
        return "ранок"
    if 12 <= hour < 17:
        return "день"
    if 17 <= hour < 23:
        return "вечір"
    return "ніч"


def season(month: int, south: bool = False) -> str:
    """The season of `month`; v5.27: in the southern hemisphere the other half of the year (November is spring)."""
    if south:
        month = (month + 5) % 12 + 1
    return {12: "зима", 1: "зима", 2: "зима", 3: "весна", 4: "весна", 5: "весна",
            6: "літо", 7: "літо", 8: "літо"}.get(month, "осінь")


def now_line(now: datetime, location: str, home: datetime | None = None, south: bool = False) -> str:
    """Her place and moment; v5.27: away from Lviv (`home`, Lviv's moment, when her zone is another) Lviv's time
    too, with its weekday when Lviv's date is another."""
    line = (
        f"Місце: {location}. Зараз {WEEKDAYS[now.weekday()]}, {now.day} {MONTHS_GEN[now.month - 1]} "
        f"{now.year} року, {now:%H:%M}, {part_of_day(now.hour)}, {season(now.month, south)}."
    )
    if home is not None:
        line += f" У Львові, де Ich, зараз {home:%H:%M}"
        if home.date() != now.date():
            line += f" — там {'уже' if home.date() > now.date() else 'ще'} {WEEKDAYS[home.weekday()]}"
        line += "."
    return line


def _days_word(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "день"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "дні"
    return "днів"


def relative_when(then: datetime, now: datetime) -> str:
    diff = (now.date() - then.date()).days
    adverb = PART_ADVERB[part_of_day(then.hour)]
    if diff <= 0:
        return f"сьогодні {adverb}"
    if diff == 1:
        return f"вчора {adverb}"
    if diff == 2:
        return f"позавчора {adverb}"
    if diff < 7:
        return f"{diff} {_days_word(diff)} тому"
    return f"{then.day} {MONTHS_GEN[then.month - 1]}"


HISTORY_GAP_MS = 3 * 3600 * 1000   # a pause this long in her private history gets a time line (the owner, 2026-11-01)


def _hours_word(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "годину"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "години"
    return "годин"


def span(pause_ms: int) -> str:
    """How long a pause was, as a person says it: hours under a day, then days."""
    hours = max(1, pause_ms // 3_600_000)
    if hours < 24:
        return f"{hours} {_hours_word(hours)}"
    days = hours // 24
    return f"{days} {_days_word(days)}"


def history_times(stamps: list[int], now: datetime, tz: str, gap_ms: int = HISTORY_GAP_MS,
                  stamped: bool = False) -> dict[int, str]:
    """Her private history's time lines (the owner, 2026-11-01: Gemini's history held Wednesday's talk right before
    Sunday's, so «I'm off to Kyiv» read as tonight's): index → the line shown before that history line — the first
    line's when, and after a pause of at least `gap_ms` how long it was and when the next line came («— через 3 дні,
    сьогодні ввечері: —»). As a person remembers it (`ago`), never a date or an hour. Pure. v9.1 (AGORA-277/278):
    `stamped` — its age and its date (`stamp`): «— 6 годин тому (сьогодні, 08:15): —»."""
    out: dict[int, str] = {}
    for i, ts in enumerate(stamps):
        when = stamp(local_now(ts, tz), now) if stamped else ago(local_now(ts, tz), now)
        if i == 0:
            out[i] = f"— {when}: —"
        elif ts - stamps[i - 1] >= gap_ms:
            out[i] = f"— через {span(ts - stamps[i - 1])}, {when}: —"
    return out


def ago(then: datetime, now: datetime) -> str:
    """When a remembered line was, as a person remembers it — never a date or an hour (the owner, 2026-10-26: «26
    жовтня» gives her away). The nearest band wins; the week starts on Monday."""
    d, today = then.date(), now.date()
    diff = (today - d).days
    if diff <= 0:
        return f"сьогодні {PART_ADVERB[part_of_day(then.hour)]}"
    if diff == 1:
        return "вчора"
    if diff == 2:
        return "позавчора"
    monday = today - timedelta(days=today.weekday())
    if d >= monday:
        return "цього тижня"
    if d >= monday - timedelta(days=7):
        return "минулого тижня"
    months = (today.year - d.year) * 12 + today.month - d.month
    if months == 0:
        return "цього місяця"
    if months == 1:
        return "минулого місяця"
    return "якось"


def last_talk_line(then: datetime, now: datetime, stamped: bool = False) -> str:
    """«Востаннє ви говорили …»; v9.1: `stamped` — its age and its date."""
    return f"Востаннє ви говорили {stamp(then, now) if stamped else relative_when(then, now)}."


def day_label(d: date, today: date) -> str:
    base = f"{WEEKDAYS[d.weekday()]}, {d.day} {MONTHS_GEN[d.month - 1]}"
    if d.year != today.year:
        base += f" {d.year}"
    diff = (today - d).days
    if diff == 1:
        return f"вчора, {base}"
    if diff == 2:
        return f"позавчора, {base}"
    return base


def week_label(monday: date) -> str:
    sunday = monday + timedelta(days=6)
    if monday.month == sunday.month:
        return f"тиждень {monday.day}–{sunday.day} {MONTHS_GEN[monday.month - 1]}"
    return (f"тиждень {monday.day} {MONTHS_GEN[monday.month - 1]} – "
            f"{sunday.day} {MONTHS_GEN[sunday.month - 1]}")


def month_label(year: int, month: int) -> str:
    return f"{MONTHS_NOM[month - 1]} {year}"


def year_label(year: int) -> str:
    return f"{year} рік"


# --- v9.1 (AGORA-277): a time on every memory and every plan — its age and its date ------------------------------
# The owner, 2026-11-18: «всі спогади мають мати мітку часу щоб було відомо що відбулось 6 год тому а що 12 а що вчора
# а що місяць тому. Давати їй дати але гвоорити вона має як зараз не з датами»; «всі плани теж мали б мати мітку
# часу». The age first, as a person says it, then the date in brackets. `fine` (the prompt's tail and history, read
# anew each call): minutes and hours within a day; not `fine` (the cached start): the day is the smallest unit, so the
# text changes only when the date does (v7.5's cache is rebuilt no more often than before).
WEEKDAY_ON = ("у понеділок", "у вівторок", "у середу", "у четвер", "у п'ятницю", "у суботу", "у неділю")
_UNITS = {  # the accusative after «тому» and «через»: 1 · 2–4 · 5+
    "minute": ("хвилину", "хвилини", "хвилин"),
    "hour": ("годину", "години", "годин"),
    "day": ("день", "дні", "днів"),
    "week": ("тиждень", "тижні", "тижнів"),
    "month": ("місяць", "місяці", "місяців"),
    "year": ("рік", "роки", "років"),
}


def _count(n: int, unit: str) -> str:
    """«годину», «2 години», «5 годин» — one alone says no number."""
    one, few, many = _UNITS[unit]
    if n == 1:
        return one
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} {one}"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f"{n} {few}"
    return f"{n} {many}"


def _date(d: date, today: date) -> str:
    """«17.11»; the year only when it is not this one: «18.11.2025»."""
    return f"{d.day:02d}.{d.month:02d}" + (f".{d.year}" if d.year != today.year else "")


def _months_between(earlier: date, later: date) -> int:
    """Whole calendar months from `earlier` to `later` (0 when less than one)."""
    months = (later.year - earlier.year) * 12 + later.month - earlier.month
    return months - 1 if later.day < earlier.day else months


def _past_days(d: date, today: date) -> str:
    """The age of a day before today, as a person says it: 3 дні тому, тиждень тому, місяць тому, рік тому."""
    diff = (today - d).days
    if diff == 1:
        return "вчора"
    if diff == 2:
        return "позавчора"
    if diff < 7:
        return f"{_count(diff, 'day')} тому"
    months = _months_between(d, today)
    if months < 1:
        return f"{_count(diff // 7, 'week')} тому"
    if months < 12:
        return f"{_count(months, 'month')} тому"
    return f"{_count(months // 12, 'year')} тому"


def _ahead_days(d: date, today: date) -> str:
    diff = (d - today).days
    if diff == 1:
        return "завтра"
    if diff == 2:
        return "післязавтра"
    if diff < 7:
        return WEEKDAY_ON[d.weekday()]
    months = _months_between(today, d)
    if months < 1:
        return f"через {_count(diff, 'day')}"
    if months < 12:
        return f"через {_count(months, 'month')}"
    return f"через {_count(months // 12, 'year')}"


def stamp(then: datetime, now: datetime, fine: bool = True, hour: bool | None = None) -> str:
    """A memory's or a plan's time (pure): its age, then its date in brackets — «6 годин тому (сьогодні, 08:15)»,
    «вчора ввечері (17.11, 21:40)», «5 днів тому (13.11)», «місяць тому (18.10)», «через 3 години (17:00)», «завтра
    (19.11)». `fine` False: the day is the smallest unit («сьогодні (18.11)», «вчора (17.11)»), the same text all day.
    `hour`: show the hour — by default, when `fine`, within today and yesterday (and tomorrow ahead); `then` is taken in `now`'s
    zone, so the age is counted in her local calendar days."""
    then = then.astimezone(now.tzinfo)
    today, d = now.date(), then.date()
    diff = (today - d).days
    at = f"{then:%H:%M}"
    show_hour = hour if hour is not None else fine and -1 <= diff <= 1
    if fine and then <= now:
        secs = (now - then).total_seconds()
        if secs < 60:
            return f"щойно ({at})"
        if secs < 3600:
            return f"{_count(int(secs // 60), 'minute')} тому ({at})"
        if secs < 86400:
            return f"{_count(int(secs // 3600), 'hour')} тому ({'сьогодні' if diff == 0 else 'вчора'}, {at})"
    if fine and then > now:
        secs = (then - now).total_seconds()
        if secs < 60:
            return f"зараз ({at})"
        if secs < 3600:
            return f"через {_count(max(1, int(secs // 60)), 'minute')} ({at})"
        if diff == 0:
            return f"через {_count(int(secs // 3600), 'hour')} ({at})"
    if diff == 0:
        word = "сьогодні"
    elif diff > 0:
        word = _past_days(d, today)
        if fine and diff in (1, 2):
            word += f" {PART_ADVERB[part_of_day(then.hour)]}"
    else:
        word = _ahead_days(d, today)
    shown = _date(d, today) + (f", {at}" if show_hour else "")
    return f"{word} ({shown})"


def _range(first: date, last: date, today: date) -> str:
    """«10–16.11», «27.10–02.11», a year's when not this one."""
    if first.month == last.month and first.year == last.year:
        return f"{first.day:02d}–{_date(last, today)}"
    return f"{_date(first, today)}–{_date(last, today)}"


def span_stamp(start: datetime, end: datetime, now: datetime, fine: bool = False) -> str:
    """A period's time (pure), `end` exclusive, in `now`'s zone: a year, a month, a week from Monday, a day — each by
    its age and its dates («тиждень тому (10–16.11)», «місяць тому (жовтень 2026)», «вчора (17.11)») — or hours
    («сьогодні, 08:00–09:00 (18.11)»; `fine`: «3 години тому (11:00–12:00)», its age from its end)."""
    start, end = start.astimezone(now.tzinfo), end.astimezone(now.tzinfo)
    today, first = now.date(), start.date()
    midnight = start.time() == end.time() == datetime.min.time()
    if midnight and first.month == 1 and first.day == 1 and end.date() == date(first.year + 1, 1, 1):
        n = today.year - first.year
        return f"{'цього року' if n == 0 else _count(n, 'year') + ' тому'} ({first.year})"
    if midnight and first.day == 1 and end.date() == date(first.year + first.month // 12, first.month % 12 + 1, 1):
        n = (today.year - first.year) * 12 + today.month - first.month
        name = f"{MONTHS_NOM[first.month - 1]} {first.year}"
        return f"{'цього місяця' if n == 0 else _count(n, 'month') + ' тому'} ({name})"
    if midnight and (end.date() - first).days == 7 and first.weekday() == 0:
        n = ((today - timedelta(days=today.weekday())) - first).days // 7
        word = "цього тижня" if n == 0 else f"{_count(n, 'week')} тому" if n > 0 else "наступного тижня"
        return f"{word} ({_range(first, first + timedelta(days=6), today)})"
    if midnight and (end.date() - first).days == 1:
        return stamp(start, now, fine=False, hour=False)
    hours = f"{start:%H:%M}–{end:%H:%M}"
    if fine and end <= now and (now - end).total_seconds() < 86400:
        return f"{stamp(end, now, fine=True).split(' (')[0]} ({hours})"
    word = stamp(start, now, fine=False, hour=False).split(" (")[0]
    return f"{word}, {hours} ({_date(first, today)})"


_DATE_ISO = re.compile(r"(?<![\d.\-])\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])(?![\d\-])")
_DATE_DOTS = re.compile(r"(?<![\d.:,])(0?[1-9]|[12]\d|3[01])\.(0[1-9]|1[0-2])(?:\.(?:\d{4}|\d{2}))?(?![\d:]|\.\d)")
_DATE_WORDS = re.compile(r"(?<!\d)(0?[1-9]|[12]\d|3[01])(?:-?(?:го|ого|е))?\s+(" + "|".join(MONTHS_GEN) + r")(?!\w)",
                         re.IGNORECASE)


def says_date(text: str) -> int:
    """How many dates an answer names (pure; v9.1, the owner: she speaks without dates) — «17.11», «17.11.2026», «17
    листопада», «2026-11-17». Not an hour («14:20», «17.30»), a count («17 разів»), a year alone or a decimal («3.5»)."""
    text = text or ""
    n = len(_DATE_ISO.findall(text))
    text = _DATE_ISO.sub(" ", text)
    n += len(_DATE_DOTS.findall(text))
    text = _DATE_DOTS.sub(" ", text)
    return n + len(_DATE_WORDS.findall(text))


def with_time_lines(lines: list[tuple[str, str]], times: list[int], now: datetime, tz: str,
                    gap_ms: int = HISTORY_GAP_MS) -> list[tuple[str, str]]:
    """v9.1 (AGORA-278) — a history with its stamped time lines (`history_times`) as nameless entries before the lines
    they mark: her own Agora prompt's, so she knows what was said hours ago. Pure; the lines unchanged and in order;
    `times` must align with `lines`, else the lines as they are."""
    if len(times) != len(lines):
        return list(lines)
    marks = history_times(times, now, tz, gap_ms, stamped=True)
    out: list[tuple[str, str]] = []
    for i, line in enumerate(lines):
        if i in marks:
            out.append(("", marks[i]))
        out.append(line)
    return out


def day_age(d: date, today: date) -> str:
    """v9.1 (AGORA-279) — a day's age from dates alone (pure): «сьогодні», «вчора», «3 дні тому», «місяць тому»;
    ahead «завтра», «у неділю». The cached start's labels, so they change only with the date."""
    if d == today:
        return "сьогодні"
    return _past_days(d, today) if d < today else _ahead_days(d, today)


def _noon(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 12, tzinfo=ZoneInfo("UTC"))


def _midnight(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=ZoneInfo("UTC"))


def layer_age(kind: str, key, today: date) -> str:
    """v9.1 (AGORA-279) — how long ago a memory's layer was, by dates alone: a day «3 дні тому», a week «тиждень тому»,
    a month «місяць тому», a year «рік тому» (pure; «цього тижня», «цього місяця», «цього року» for the current)."""
    if kind == "day":
        return day_age(key, today)
    if kind == "week":
        first = key
        after = first + timedelta(days=7)
    elif kind == "month":
        first = date(*key, 1)
        after = date(key[0] + key[1] // 12, key[1] % 12 + 1, 1)
    else:
        first, after = date(key, 1, 1), date(key + 1, 1, 1)
    return span_stamp(_midnight(first), _midnight(after), _noon(today)).split(" (")[0]
