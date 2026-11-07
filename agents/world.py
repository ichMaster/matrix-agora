"""Place, calendar and time in Ukrainian — from tables in code, never the
system locale; the clock is injected (ARCHITECTURE §World awareness)."""

from __future__ import annotations

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


def history_times(stamps: list[int], now: datetime, tz: str, gap_ms: int = HISTORY_GAP_MS) -> dict[int, str]:
    """Her private history's time lines (the owner, 2026-11-01: Gemini's history held Wednesday's talk right before
    Sunday's, so «I'm off to Kyiv» read as tonight's): index → the line shown before that history line — the first
    line's when, and after a pause of at least `gap_ms` how long it was and when the next line came («— через 3 дні,
    сьогодні ввечері: —»). As a person remembers it (`ago`), never a date or an hour. Pure."""
    out: dict[int, str] = {}
    for i, ts in enumerate(stamps):
        when = ago(local_now(ts, tz), now)
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


def last_talk_line(then: datetime, now: datetime) -> str:
    return f"Востаннє ви говорили {relative_when(then, now)}."


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
