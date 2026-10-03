"""The chronicle: day memories, week/month/year digests, the today block and
the layered memory selection (ARCHITECTURE §Memory). Pure helpers only.

Nothing lived is deleted; nothing past is rewritten. Memories follow the life
story (new concrete details, never copied); plans drift from it, and the
memories resolve the drift.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from agents.world import MONTHS_GEN, WEEKDAYS, day_label, month_label, part_of_day, week_label, year_label

WORD_RE = re.compile(r"[\w'ʼ’]+", re.UNICODE)
TAG_RE = re.compile(r"\s*<!--\s*mutation:\s*\w+\s*-->")


# --- the verbatim guard -------------------------------------------------------
def _words(text: str) -> list[str]:
    return [w.lower() for w in WORD_RE.findall(text)]


def shares_span(text: str, source: str, n: int = 8) -> bool:
    """True when `text` copies `n` or more consecutive words of `source`."""
    a, b = _words(text), _words(source)
    if len(a) < n or len(b) < n:
        return False
    grams = {tuple(b[i:i + n]) for i in range(len(b) - n + 1)}
    return any(tuple(a[i:i + n]) in grams for i in range(len(a) - n + 1))


def visible_deviations(plan: str) -> str:
    """For generators only: hidden mutation tags become a visible marker."""
    return TAG_RE.sub(" [відхилення]", plan)


# --- what is due --------------------------------------------------------------
def monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def month_end(y: int, m: int) -> date:
    first_next = date(y + (m == 12), m % 12 + 1, 1)
    return first_next - timedelta(days=1)


def days_due(today: date, first_run: date, existing: set[date], max_back: int) -> list[date]:
    start = max(first_run, today - timedelta(days=max_back))
    return [start + timedelta(days=i) for i in range((today - start).days)
            if start + timedelta(days=i) not in existing]


def weeks_due(today: date, first_run: date, existing: set[date], day_files: set[date],
              lookback: int = 8) -> list[date]:
    out = []
    m = monday_of(today) - timedelta(days=7)
    for _ in range(lookback):
        sunday = m + timedelta(days=6)
        if sunday >= first_run and m not in existing and any(m <= d <= sunday for d in day_files):
            out.append(m)
        m -= timedelta(days=7)
    return sorted(out)


def months_due(today: date, first_run: date, existing: set[tuple[int, int]], day_files: set[date],
               lookback: int = 13) -> list[tuple[int, int]]:
    out = []
    y, m = today.year, today.month
    for _ in range(lookback):
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
        if month_end(y, m) >= first_run and (y, m) not in existing and \
                any(d.year == y and d.month == m for d in day_files):
            out.append((y, m))
    return sorted(out)


def years_due(today: date, first_run: date, existing: set[int], month_files: set[tuple[int, int]]) -> list[int]:
    return [y for y in range(first_run.year, today.year)
            if y not in existing and any(my == y for my, _ in month_files)]


# --- the layered selection for the prompt --------------------------------------
def select_layers(today: date, n_days: int, n_weeks: int, n_months: int,
                  days: set[date], weeks: set[date], months: set[tuple[int, int]], years: set[int]):
    """Nested windows, coarsest and oldest first, no gaps: all years before the
    months window, the last `n_months` complete months before the weeks window,
    the last `n_weeks` complete weeks before the days window, the last `n_days`
    days. Returns [(kind, key)] in prompt order, only for existing files."""
    days_start = today - timedelta(days=n_days)
    week_keys = []
    m = monday_of(today) - timedelta(days=7)
    while len(week_keys) < n_weeks:
        if m < days_start:
            week_keys.append(m)
        m -= timedelta(days=7)
    weeks_start = min(week_keys) if week_keys else days_start
    month_keys = []
    y, mo = today.year, today.month
    while len(month_keys) < n_months:
        y, mo = (y - 1, 12) if mo == 1 else (y, mo - 1)
        if date(y, mo, 1) < weeks_start:
            month_keys.append((y, mo))
    months_start = date(*min(month_keys), 1) if month_keys else weeks_start
    out = [("year", y) for y in sorted(years) if date(y, 12, 31) < months_start]
    out += [("month", k) for k in sorted(month_keys) if k in months]
    out += [("week", k) for k in sorted(week_keys) if k in weeks]
    out += [("day", days_start + timedelta(days=i)) for i in range(n_days)
            if days_start + timedelta(days=i) in days]
    return out


def layer_label(kind: str, key, today: date) -> str:
    if kind == "day":
        return day_label(key, today)
    if kind == "week":
        return week_label(key)
    if kind == "month":
        return month_label(*key)
    return year_label(key)


# --- generator requests -------------------------------------------------------
RULES = (
    "Пиши від першої особи, українською, живо і конкретно. Опис твого життя — лише рамка: не переказуй і "
    "не копіюй його речень, а додай нові деталі саме цього дня — що саме, де, з ким, погода, дрібні "
    "відчуття. Усе, що стосується Ich чи інших людей з Агори, бери лише з журналу розмов — нічого за них "
    "не вигадуй. Вигадувати можна тільки власне життя і місто."
)


def day_memory_request(name: str, canon: str, day: date, chapter_body: str,
                       previous: list[tuple[str, str]], journal: str | None, plan: str | None,
                       today_block: str | None, max_words: int) -> tuple[str, str]:
    parts = [f"Твоє життя зараз:\n{chapter_body}"]
    if previous:
        parts.append("Твої спогади попередніх днів:\n" + "\n".join(f"{lb}: {tx}" for lb, tx in previous))
    if plan:
        parts.append(f"Твій план на той день:\n{visible_deviations(plan)}")
    if today_block:
        parts.append(f"Як минав той день (твої нотатки протягом дня):\n{today_block}")
    parts.append(f"Журнал розмов в Агорі за той день:\n{journal}" if journal
                 else "Того дня розмов в Агорі не було.")
    label = f"{WEEKDAYS[day.weekday()]}, {day.day} {MONTHS_GEN[day.month - 1]} {day.year}"
    parts.append(
        f"Напиши свій спогад про цей день ({label}), не більше {max_words} слів. {RULES} Пункти плану з "
        "позначкою [відхилення], найімовірніше, не здійснились — якщо природно, розкажи, що завадило "
        "(«хотілося…, але…»). Не повторюй заняття попередніх днів без потреби. Лише сам спогад, без вступу."
    )
    return f"{canon}\n\nТи — {name}.", "\n\n".join(parts)


def digest_request(kind: str, name: str, canon: str, label: str, sources: list[tuple[str, str]],
                   plan: str | None, max_words: int) -> tuple[str, str]:
    what = {"week": "тиждень", "month": "місяць", "year": "рік"}[kind]
    parts = ["Твої спогади за цей період:\n" + "\n\n".join(f"{lb}: {tx}" for lb, tx in sources)]
    if plan:
        parts.append(f"Що ти планував(-ла) на цей {what}:\n{visible_deviations(plan)}")
    parts.append(
        f"Стисни це в спогад про {what} ({label}), не більше {max_words} слів: що було головним — настрої, "
        "люди, поворотні моменти, що задумувалось і що вийшло насправді, що лишилося незавершеним. "
        "Від першої особи, своїми словами, не копіюючи речень. Лише сам спогад, без вступу."
    )
    return f"{canon}\n\nТи — {name}.", "\n\n".join(parts)


def today_request(name: str, canon: str, now: datetime, chapter_body: str, plan: str | None,
                  journal: str | None, previous: str | None, max_words: int) -> tuple[str, str]:
    parts = [f"Твоє життя зараз:\n{chapter_body}"]
    if plan:
        parts.append(f"Твій план на сьогодні:\n{visible_deviations(plan)}")
    if journal:
        parts.append(f"Розмови в Агорі сьогодні:\n{journal}")
    if previous:
        parts.append(f"Твоя попередня нотатка про сьогодні:\n{previous}")
    parts.append(
        f"Зараз {now:%H:%M} ({part_of_day(now.hour)}). Напиши дві короткі частини, разом не більше "
        f"{max_words} слів:\nСьогодні вже: <що вже було сьогодні — так, як воно справді йде у твоєму "
        "житті; пункти з позначкою [відхилення] не позначай зробленими>\nЩе сьогодні: <що ще попереду "
        f"за планом>\n{RULES}"
    )
    return f"{canon}\n\nТи — {name}.", "\n\n".join(parts)
