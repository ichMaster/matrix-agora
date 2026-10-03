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


def season(month: int) -> str:
    return {12: "зима", 1: "зима", 2: "зима", 3: "весна", 4: "весна", 5: "весна",
            6: "літо", 7: "літо", 8: "літо"}.get(month, "осінь")


def now_line(now: datetime, location: str) -> str:
    return (
        f"Місце: {location}. Зараз {WEEKDAYS[now.weekday()]}, {now.day} {MONTHS_GEN[now.month - 1]} "
        f"{now.year} року, {now:%H:%M}, {part_of_day(now.hour)}, {season(now.month)}."
    )


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
