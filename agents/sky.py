"""Today's sky (the owner, 2026-10-11) — the real positions of the Sun, the Moon and the planets in the tropical
zodiac, for the cat's horoscope: his reading and his talk name only these, never invented transits.

Computed by PyEphem (analytic theories, no data files, no network) for a given moment; the agent passes local noon
of the day. A planet is retrograde when its ecliptic longitude decreases over the next day. Pure.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, tzinfo
from zoneinfo import ZoneInfo

import ephem

SIGNS = ("Овен", "Телець", "Близнюки", "Рак", "Лев", "Діва", "Терези", "Скорпіон", "Стрілець", "Козеріг",
         "Водолій", "Риби")
SIGNS_IN = ("в Овні", "в Тельці", "в Близнюках", "в Раку", "в Леві", "в Діві", "в Терезах", "у Скорпіоні",
            "у Стрільці", "в Козерозі", "у Водолії", "в Рибах")
BODIES = (("Сонце", "Sun"), ("Місяць", "Moon"), ("Меркурій", "Mercury"), ("Венера", "Venus"), ("Марс", "Mars"),
          ("Юпітер", "Jupiter"), ("Сатурн", "Saturn"), ("Уран", "Uranus"), ("Нептун", "Neptune"),
          ("Плутон", "Pluto"))
# the Moon's phase by its elongation from the Sun (degrees, the start of each eighth)
PHASES = ((0, "молодик"), (22.5, "молодий місяць росте"), (67.5, "перша чверть"), (112.5, "місяць росте до повні"),
          (157.5, "повня"), (202.5, "місяць спадає після повні"), (247.5, "остання чверть"),
          (292.5, "старий місяць спадає"), (337.5, "молодик"))


@dataclass(frozen=True)
class Placement:
    body: str        # Ukrainian name, «Венера»
    longitude: float  # tropical ecliptic longitude of date, 0–360
    retrograde: bool

    @property
    def sign(self) -> str:
        return SIGNS[int(self.longitude // 30) % 12]

    @property
    def degree(self) -> int:
        return int(self.longitude % 30)


def _longitude(attr: str, when: ephem.Date) -> float:
    body = getattr(ephem, attr)()
    body.compute(when, epoch=when)  # the equinox of date: the tropical zodiac
    return math.degrees(float(ephem.Ecliptic(body, epoch=when).lon)) % 360


def _ephem_date(moment: datetime) -> ephem.Date:
    return ephem.Date(moment.astimezone(UTC).replace(tzinfo=None))


def placements(moment: datetime) -> list[Placement]:
    """Every body's sign and degree at `moment` (an aware datetime), with retrograde motion for the planets."""
    when = _ephem_date(moment)
    out = []
    for name, attr in BODIES:
        lon = _longitude(attr, when)
        retro = False
        if attr not in ("Sun", "Moon"):
            step = (_longitude(attr, ephem.Date(when + 1)) - lon + 540) % 360 - 180
            retro = step < 0
        out.append(Placement(name, lon, retro))
    return out


def moon_phase(sky: list[Placement]) -> str:
    sun = next(p for p in sky if p.body == "Сонце")
    moon = next(p for p in sky if p.body == "Місяць")
    elongation = (moon.longitude - sun.longitude) % 360
    return [label for start, label in PHASES if elongation >= start][-1]


def format_sky(sky: list[Placement]) -> str:
    """«Сонце в Терезах 18°; Місяць в Терезах 26° (молодик); …; Венера у Скорпіоні 7° (ретроградна); …»."""
    parts = []
    for p in sky:
        text = f"{p.body} {SIGNS_IN[SIGNS.index(p.sign)]} {p.degree}°"
        if p.body == "Місяць":
            text += f" ({moon_phase(sky)})"
        if p.retrograde:
            text += " (ретроградна)" if p.body == "Венера" else " (ретроградний)"
        parts.append(text)
    return "; ".join(parts)


def noon(day: date, tz: tzinfo) -> datetime:
    """Local noon of `day` — the moment a day's sky is read at."""
    return datetime.combine(day, time(12, 0), tzinfo=tz)


def sky_line(day: date, tz: str | tzinfo) -> str:
    """The day's sky at local noon in `tz` (a zone name, as `TIMEZONE`, or a tzinfo)."""
    return format_sky(placements(noon(day, ZoneInfo(tz) if isinstance(tz, str) else tz)))
