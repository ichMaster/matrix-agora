"""The mood of the day (v4.2) — Lumi's horoscope service, ported (lumi/core/mood.py + lumi/core/biorhythm.py, MIT).

Once per local day the agent asks the model for a vivid, honest reading from its fixed **natal chart** + today's
date + the day's computed **biorhythms**, ending in a short **resolution** (mood, energy, what it is drawn to, what
it avoids, tone). The full reading is appended to `state/<name>.mood.log`; only the resolution enters the prompt as
«Настрій дня». As in Lumi, the transits are the model's own — no astronomy engine — so the sky colors the day, it is
not checked against an ephemeris. Not ported: the hormonal cycle, the face themes, recent thoughts.
Everything here is pure; the agent owns the clock, the call and the file.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date

# The mood call's system line (Lumi's, with the persona's name and pronouns made neutral).
MOOD_SYSTEM = (
    "Ти — вдумливий, ЧЕСНИЙ астролог. Нижче — натальна карта ({name}). СПЕРШУ дай РОЗГОРНУТИЙ "
    "гороскоп-настрій на вказану дату — КІЛЬКА абзаців про ключові транзити дня й як вони фарбують "
    "день (енергія, почуття, спілкування, творчість); не пропускай цю частину. Будь ОБ'ЄКТИВНИМ — не "
    "роби день штучно позитивним: транзити бувають і важкі. Якщо день низький, напружений, втомливий, "
    "замкнений чи похмурий — так і скажи (втома, роздратування, смуток, нетерплячість, потреба тиші), так "
    "само щиро, як і світлі дні. А ВЖЕ ПОТІМ, у самому кінці — окремий рядок «РЕЗОЛЮЦІЯ:» і одним абзацом "
    "(~5 речень) ОПИШИ СТАН на сьогодні: настрій, енергію, до чого тягне, чого уникає, який тон. Тільки "
    "ОПИС стану — БЕЗ порад, рекомендацій чи вказівок (жодних «варто», «спробуй», «тягни», «бери», "
    "«дозволь собі»): не що РОБИТИ, а ЯКИЙ це стан. Резолюція має відображати справжній характер дня "
    "(хай навіть складний чи тьмяний), а не підбадьорювати. Лише про настрій і тон — не про знання чи вміння."
)
MOOD_MAX_TOKENS = 2000  # several paragraphs, then the resolution — a reading cut by the cap is not kept (review #8)

# The mood log's per-reading header: "===== 2026-10-10 =====" on its own line.
_MOOD_LOG_HEADER_RE = re.compile(r"(?m)^===== (\d{4}-\d{2}-\d{2}) =====[ \t]*$")


@dataclass(frozen=True)
class MoodState:
    """One local day's mood: the full `reading` (logged) + the `resolution` (in the prompt)."""

    date: str        # the local date key, e.g. "2026-10-10"
    resolution: str
    reading: str


def mood_request(name: str, natal: str, date_str: str, biorhythms: str | None = None) -> tuple[str, str]:
    """(system, contents) for the daily mood call — the natal chart, the date and the computed biorhythms."""
    content = f"Натальна карта:\n{natal}\n\nДата: {date_str}."
    if biorhythms:
        content += (
            f"\n\nБіоритми (ТОЧНО обчислені цикли): {biorhythms}."
            "\n\nІНТЕГРУЙ ці обчислені ритми в саме читання настрою РАЗОМ із транзитами — не окремим блоком "
            "і не списком, а вплетеними в загальну картину дня; де щось суперечить транзитам, примири в "
            "одному настрої. Нехай вони фарбують енергію, чутливість і тон, і нехай це відіб'ється в РЕЗОЛЮЦІЇ."
        )
    return MOOD_SYSTEM.format(name=name), content


def log_block(day: str, reading: str) -> str:
    """One append-only block of the mood log."""
    return f"\n\n===== {day} =====\n{reading.strip()}\n"


def reading_from_log(log_text: str, day: str) -> str | None:
    """The LAST full reading logged for `day`, or None — reused across restarts instead of a new call."""
    headers = list(_MOOD_LOG_HEADER_RE.finditer(log_text or ""))
    for i in range(len(headers) - 1, -1, -1):
        if headers[i].group(1) == day:
            end = headers[i + 1].start() if i + 1 < len(headers) else len(log_text)
            reading = log_text[headers[i].end():end].strip()
            return reading or None
    return None


# A line that *starts* with the marker, Markdown and all: «РЕЗОЛЮЦІЯ: …», «**РЕЗОЛЮЦІЯ:** …», «### Резолюція» (review #6)
_RESOLUTION_RE = re.compile(r"^[\s*#_>•·—-]*резолюц\w*[\s*_#]*:?[\s*_#]*(.*)$", re.IGNORECASE)


def split_resolution(reading: str) -> str:
    """The RESOLUTION — the text after the last line that starts with «резолюція» (inline or below it), Markdown
    stripped; the last paragraph otherwise. A mention of the resolution inside the reading is no marker."""
    lines = reading.splitlines()
    for i in range(len(lines) - 1, -1, -1):
        m = _RESOLUTION_RE.match(lines[i])
        if m:
            after_colon = m.group(1).strip().strip("*_#").strip()
            below = "\n".join(lines[i + 1:]).strip().lstrip("-—*#:•· \n").strip()
            parts = [p for p in (after_colon, below) if p]
            if parts:
                return "\n".join(parts).strip()
    paragraphs = [p.strip() for p in reading.split("\n\n") if p.strip()]
    return paragraphs[-1] if paragraphs else reading.strip()


# --- biorhythms: three exact sine cycles from the birth date -------------------------------------------------------
PERIODS: dict[str, int] = {"physical": 23, "emotional": 28, "intellectual": 33}
_UA = {"physical": "фізичний", "emotional": "емоційний", "intellectual": "інтелектуальний"}
# "Народження: DD.MM.YYYY, …" in the natal file → the birth date
_BIRTH_RE = re.compile(r"Народження:\s*(\d{1,2})\.(\d{1,2})\.(\d{4})")


@dataclass(frozen=True)
class Cycle:
    name: str    # physical | emotional | intellectual
    value: float  # sin(2π·d/period), −1…+1
    label: str   # high | low | rising | falling | critical


def _label(value: float, value_next: float) -> str:
    """`critical` at/around a zero crossing, else high / low / rising / falling."""
    if value == 0.0 or (value > 0) != (value_next > 0):
        return "critical"
    if value >= 0.7:
        return "high"
    if value <= -0.7:
        return "low"
    return "rising" if value_next > value else "falling"


def biorhythms(birth: date, today: date) -> tuple[Cycle, Cycle, Cycle]:
    """The three cycles for `today`, exact and deterministic from `birth`."""
    d = (today - birth).days
    out = []
    for name, period in PERIODS.items():
        value = math.sin(2 * math.pi * d / period)
        value_next = math.sin(2 * math.pi * (d + 1) / period)
        out.append(Cycle(name, value, _label(value, value_next)))
    return tuple(out)


def parse_birth_date(natal_text: str) -> date | None:
    m = _BIRTH_RE.search(natal_text or "")
    if not m:
        return None
    day, month, year = (int(g) for g in m.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def format_biorhythms(cycles) -> str:
    """e.g. `фізичний +0.82 (high) · емоційний −0.61 (low) · інтелектуальний +0.10 (rising)`."""
    return " · ".join(f"{_UA[c.name]} {c.value:+.2f} ({c.label})" for c in cycles)
