"""Where a person is (v5.27; the owner, 2026-11-07: Кіра moves to Chile) — her place sets her clock, her season, her
weather, her photos' city and whether the city's news touches her life.

The places are her TOML's (`[places.<key>]`: `name`, `name_en`, `tz`, `lat`, `lon`, `news`; `[places] night`, the
place of her nights at the telescope); her moves and her blocks of nights are her life story's (`agents/life.py`).
Her place at a moment: within a block of nights (from the first night's noon to noon after the last, in the night
place's zone) the night place; else her latest move at or before it (its time read in its own place's zone); else
the default — `LOCATION` and `TIMEZONE`, as every person had before. Everything here is pure; the clock is the
caller's.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from agents.life import LifeStory, Move

LVIV = (49.84, 24.03)
NOON = 12


class PlaceError(ValueError):
    """A malformed place in the TOML, or a story naming a place it lacks."""


@dataclass(frozen=True)
class Place:
    key: str
    name: str        # Ukrainian, her world line: «Сантьяго, Чилі»
    name_en: str     # English, her photos' city: «Santiago, Chile»
    tz: str          # an IANA zone
    lat: float | None = None
    lon: float | None = None
    news: bool = False  # Lviv's news may touch her life here (v5.11's feed is Lviv's)

    @property
    def south(self) -> bool:
        return self.lat is not None and self.lat < 0


def home_place(location: str, tz: str) -> Place:
    """The default: `LOCATION` in `TIMEZONE`, with Lviv's coordinates and news — every person before v5.27."""
    return Place("home", location, "Lviv, Ukraine", tz, LVIV[0], LVIV[1], True)


def parse_places(data: object, source: str) -> tuple[dict[str, Place], str | None]:
    """The TOML's `[places]` table: (key → Place, the night place's key). Missing: ({}, None)."""
    if data is None:
        return {}, None
    if not isinstance(data, dict):
        raise PlaceError(f"{source}: [places] is not a table")
    night = data.get("night")
    places: dict[str, Place] = {}
    for key, spec in data.items():
        if key == "night":
            continue
        if not isinstance(spec, dict):
            raise PlaceError(f"{source}: [places.{key}] is not a table")
        name, name_en, tz = (str(spec.get(k, "")).strip() for k in ("name", "name_en", "tz"))
        if not name or not name_en or not tz:
            raise PlaceError(f"{source}: [places.{key}] needs 'name', 'name_en' and 'tz'")
        try:
            ZoneInfo(tz)
        except (ZoneInfoNotFoundError, ValueError):
            raise PlaceError(f"{source}: [places.{key}] has an unknown zone {tz!r}") from None
        lat, lon = spec.get("lat"), spec.get("lon")
        if (lat is None) != (lon is None) or any(
                v is not None and (isinstance(v, bool) or not isinstance(v, int | float)) for v in (lat, lon)):
            raise PlaceError(f"{source}: [places.{key}] needs both 'lat' and 'lon' as numbers, or neither")
        places[key] = Place(key, name, name_en, tz, None if lat is None else float(lat),
                            None if lon is None else float(lon), bool(spec.get("news", False)))
    if night is not None and str(night) not in places:
        raise PlaceError(f"{source}: [places] night {night!r} is not a place")
    return places, None if night is None else str(night)


def moves_of(story: LifeStory | None) -> list[Move]:
    return [m for c in story.chapters for m in c.moves] if story else []


def nights_of(story: LifeStory | None) -> list[tuple[date, date]]:
    return sorted(b for c in story.chapters for b in c.nights) if story else []


def check_story(story: LifeStory | None, places: dict[str, Place], night: str | None, source: str) -> None:
    """Every move names a place of the TOML, and blocks of nights need a night place."""
    for m in moves_of(story):
        if m.place not in places:
            raise PlaceError(f"{source}: the move of {m.date} names an unknown place {m.place!r}")
    if nights_of(story) and night is None:
        raise PlaceError(f"{source}: the story has nights at the telescope but [places] has no 'night'")


def _ms(day: date, hour: int, minute: int, tz: str) -> int:
    return int(datetime(day.year, day.month, day.day, hour, minute, tzinfo=ZoneInfo(tz)).timestamp() * 1000)


def move_ms(move: Move, places: dict[str, Place]) -> int:
    return _ms(move.date, int(move.time[:2]), int(move.time[3:]), places[move.place].tz)


def place_at(story: LifeStory | None, places: dict[str, Place], night: str | None, default: Place,
             now_ms: int) -> Place:
    """Her place at `now_ms`: a block's night place, else the latest move, else `default` (always, with no places)."""
    if not places:
        return default
    if night is not None:
        tz = places[night].tz
        for first, last in nights_of(story):
            if _ms(first, NOON, 0, tz) <= now_ms < _ms(last + timedelta(days=1), NOON, 0, tz):
                return places[night]
    latest = None
    for m in moves_of(story):
        at = move_ms(m, places)
        if at <= now_ms and (latest is None or at >= latest[0]):
            latest = (at, m)
    return places[latest[1].place] if latest else default


def night_on(story: LifeStory | None, day: date) -> bool:
    """Whether the night that begins on the evening of `day` is a night at the telescope."""
    return any(first <= day <= last for first, last in nights_of(story))


def next_block(story: LifeStory | None, day: date, within_days: int = 30) -> tuple[date, date] | None:
    """The next block of nights that begins after `day` and within `within_days`."""
    later = [b for b in nights_of(story) if day < b[0] <= day + timedelta(days=within_days)]
    return later[0] if later else None


def awake_at(now: datetime, story: LifeStory | None, hours: tuple[int, int] | None,
             night_hours: tuple[int, int]) -> bool:
    """Whether she is awake at her local `now`. No `hours` — always (every person before v5.27). The night of a
    block: awake from `night_hours`' start that evening to its end the next morning, and asleep from that end to the
    start; any other time by `hours`."""
    from agents.nudge import in_hours

    if hours is None:
        return True
    start, end = night_hours
    today, yesterday = now.date(), now.date() - timedelta(days=1)
    if (now.hour >= start and night_on(story, today)) or (now.hour < end and night_on(story, yesterday)):
        return True
    if night_on(story, yesterday) and end <= now.hour < start:
        return False  # the morning after a night: she sleeps
    return in_hours(now.hour, hours)


def nights_line(now: datetime, story: LifeStory | None) -> str:
    """Her nights at the telescope in her world line (pure): on the night shift now, tonight, or the next block
    within 30 days, as a person says it; "" with none."""
    from agents.world import MONTHS_GEN

    if now.hour < 7 and night_on(story, now.date() - timedelta(days=1)):
        return "Ти зараз на нічній зміні біля телескопа."
    if night_on(story, now.date()):
        return "Сьогодні в тебе ніч на телескопі."
    block = next_block(story, now.date())
    if block is None:
        return ""
    first, last = block
    since = f"{first.day}" if first.month == last.month else f"{first.day} {MONTHS_GEN[first.month - 1]}"
    return f"Наступні ночі на телескопі — з {since} по {last.day} {MONTHS_GEN[last.month - 1]}."
