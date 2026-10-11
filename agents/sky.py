"""Today's sky (the owner, 2026-10-11) — the astrological positions of the Sun, the Moon and the planets and the
day's aspects between them (conjunctions, oppositions, trines, squares, sextiles), asked of Gemini with Google
Search once a day, for the cat's horoscope: his reading and his talk name only these, never invented transits.

As Lumi's web lookup (core/weblookup.py): one grounded, date-anchored call on the same `GEMINI_API_KEY`. Astrology,
not astronomy — the signs of the tropical zodiac as horoscopes give them (the owner: the astronomical and the
astrological positions need not coincide). The day's line is kept in `state/<name>.sky.json` (the day and the
line — world data, no room text), so a restart makes no second call. Pure but for the file I/O.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import date
from pathlib import Path

log = logging.getLogger("agent.sky")

SKY_MAX_TOKENS = 800
SKY_MAX_CHARS = 1500
WEEKDAYS = ("понеділок", "вівторок", "середа", "четвер", "п'ятниця", "субота", "неділя")
MONTHS_GEN = ("січня", "лютого", "березня", "квітня", "травня", "червня", "липня", "серпня", "вересня", "жовтня",
              "листопада", "грудня")
BODIES = ("Сонце", "Місяць", "Меркурій", "Венера", "Марс", "Юпітер", "Сатурн", "Уран", "Нептун", "Плутон")


def sky_query(day: date) -> str:
    """The date-anchored question: the day's astrological positions and aspects (the owner: trines, oppositions
    and the rest), as two short lines."""
    when = f"{day.day} {MONTHS_GEN[day.month - 1]} {day.year} ({WEEKDAYS[day.weekday()]}, {day.isoformat()})"
    return (
        f"Сьогодні {when}. Які сьогодні астрологічні положення планет у знаках зодіаку (тропічний зодіак, як у "
        f"гороскопах, не астрономічні сузір'я): {', '.join(BODIES)} — знак і градус кожного; які з них "
        "ретроградні; фаза Місяця? І які головні аспекти дня між ними — з'єднання, опозиції, тригони, квадрати, "
        "секстилі (точні або з невеликим орбісом)? Перевір за ефемеридами й астрологічними календарями в інтернеті. "
        "Відповідай українською, без вступу й пояснень, двома рядками у форматі: «Положення: Сонце — Терези 18°; "
        "Місяць — Скорпіон 2° (молодик); Венера — Скорпіон 7° ℞; …» і «Аспекти: Сонце тригон Юпітер; Марс "
        "опозиція Сатурн; …». Нічого не вигадуй."
    )


def clean_sky(text: str | None) -> str | None:
    """The answer as one bounded line (positions, then aspects), or None when it does not read like the day's sky
    (no Sun, no Moon)."""
    line = re.sub(r"\s+", " ", (text or "").replace("**", "")).strip().strip("«»\"")
    if "Сонце" not in line or "Місяць" not in line:
        return None
    if len(line) > SKY_MAX_CHARS:
        line = line[:SKY_MAX_CHARS].rsplit(";", 1)[0]
    return line


def load_sky(path: Path, day: str) -> str | None:
    """The day's line from the file, or None (another day, missing, corrupt)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("day") != day or not isinstance(data.get("sky"), str):
        return None
    return data["sky"] or None


def save_sky(path: Path, day: str, line: str) -> None:
    """Atomic, private from birth (0600); a failure is logged by its type — the line is kept in memory anyway."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, json.dumps({"day": day, "sky": line}, ensure_ascii=False).encode("utf-8"))
        finally:
            os.close(fd)
        os.replace(tmp, path)
    except OSError as exc:
        log.error("sky not saved (%s)", type(exc).__name__)
