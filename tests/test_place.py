"""v5.27 — where a person is (`agents/place.py`): her TOML's places, her life story's moves and nights at the
telescope, her place at a moment, the night she is awake (pure; made-up stories only)."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from agents.life import LifeError, parse_life
from agents.nudge import parse_hours
from agents.place import (
    PlaceError,
    awake_at,
    check_story,
    home_place,
    next_block,
    night_on,
    parse_places,
    place_at,
)
from agents.world import now_line, season

STORY = """# Життя

Народження: 2002-12-02 20:40, Донецьк
Смерть: 2089-08-12

## 2024–2025 · Львів

Купол над Львовом.

## 2026–2029 · Атакама

Нове життя в Чилі.

### Ночі на телескопі
- 2026-11-10 – 2026-11-17
- 2026-12-08 – 2026-12-11

### Місця
- 2026-11-09 19:30 · paranal
- 2026-11-07 21:00 · road
- 2026-11-09 08:30 · santiago
- 2026-11-18 18:00 · santiago

### Події
- 2026-11-07 12:00 · surprise · Подзвонили з Единбурга.

### Відкриті ниточки
- Іспанська.
"""
PLACES = {
    "night": "paranal",
    "road": {"name": "у дорозі до Чилі", "name_en": "on the road to Chile", "tz": "Europe/Kyiv"},
    "santiago": {"name": "Сантьяго, Чилі", "name_en": "Santiago, Chile", "tz": "America/Santiago",
                 "lat": -33.45, "lon": -70.66},
    "paranal": {"name": "гора Параналь, Чилі", "name_en": "Paranal, Chile", "tz": "America/Santiago",
                "lat": -24.63, "lon": -70.4},
    "lviv": {"name": "Львів, Україна", "name_en": "Lviv, Ukraine", "tz": "Europe/Kyiv", "lat": 49.84, "lon": 24.03,
             "news": True},
}
HOME = home_place("Львів, Україна", "Europe/Kyiv")
SCL = ZoneInfo("America/Santiago")


def ms(y, mo, d, h, mi, tz):
    return int(datetime(y, mo, d, h, mi, tzinfo=ZoneInfo(tz)).timestamp() * 1000)


@pytest.fixture
def world():
    story = parse_life(STORY)
    places, night = parse_places(PLACES, "kira.toml")
    check_story(story, places, night, "kira.toml")
    return story, places, night


def test_the_story_keeps_moves_and_nights_out_of_the_body(world):
    story, _, _ = world
    chapter = story.chapters[-1]
    assert [m.place for m in chapter.moves] == ["road", "santiago", "paranal", "santiago"]   # sorted by time
    assert chapter.nights == ((date(2026, 11, 10), date(2026, 11, 17)), (date(2026, 12, 8), date(2026, 12, 11)))
    assert "Місця" not in chapter.body and "Ночі на телескопі" not in chapter.body and "2026-11-10" not in chapter.body
    assert "Відкриті ниточки" in chapter.body and "Подзвонили" not in chapter.body
    assert len(chapter.events) == 1


@pytest.mark.parametrize("line", ["- 2026-11-09 · paranal", "- 2026-11-09 25:00 · paranal", "- 2031-01-01 10:00 · x"])
def test_a_bad_move_refuses(line):
    with pytest.raises(LifeError):
        parse_life(STORY.replace("- 2026-11-09 19:30 · paranal", line))


@pytest.mark.parametrize("line", ["- 2026-11-17 – 2026-11-10", "- 2026-11-10", "- 2030-01-01 – 2030-01-02"])
def test_a_bad_nights_line_refuses(line):
    with pytest.raises(LifeError):
        parse_life(STORY.replace("- 2026-11-10 – 2026-11-17", line))


def test_the_places_are_checked():
    with pytest.raises(PlaceError):
        parse_places({"x": {"name": "X", "name_en": "X", "tz": "Mars/Olympus"}}, "t")
    with pytest.raises(PlaceError):
        parse_places({"x": {"name": "X", "name_en": "X", "tz": "UTC", "lat": 1.0}}, "t")
    with pytest.raises(PlaceError):
        parse_places({"night": "nowhere", "x": {"name": "X", "name_en": "X", "tz": "UTC"}}, "t")
    with pytest.raises(PlaceError):
        parse_places({"x": {"name": "X", "tz": "UTC"}}, "t")
    assert parse_places(None, "t") == ({}, None)
    story = parse_life(STORY)
    with pytest.raises(PlaceError):          # a move to a place the TOML lacks
        check_story(story, {k: v for k, v in parse_places(PLACES, "t")[0].items() if k != "road"}, "paranal", "t")
    with pytest.raises(PlaceError):          # nights with no night place
        check_story(story, parse_places(PLACES, "t")[0], None, "t")


def test_her_place_at_a_moment(world):
    story, places, night = world

    def at(*when):
        return place_at(story, places, night, HOME, ms(*when)).key

    assert at(2026, 11, 7, 20, 59, "Europe/Kyiv") == "home"                 # before any move
    assert at(2026, 11, 7, 21, 0, "Europe/Kyiv") == "road"
    assert at(2026, 11, 9, 8, 29, "America/Santiago") == "road"             # a move's time is its place's zone
    assert at(2026, 11, 9, 8, 30, "America/Santiago") == "santiago"
    assert at(2026, 11, 9, 19, 30, "America/Santiago") == "paranal"
    assert at(2026, 11, 10, 12, 0, "America/Santiago") == "paranal"         # the block from its first noon
    assert at(2026, 11, 18, 11, 59, "America/Santiago") == "paranal"        # to noon after the last night
    assert at(2026, 11, 18, 12, 0, "America/Santiago") == "paranal"         # then the latest move: still the mountain
    assert at(2026, 11, 18, 18, 0, "America/Santiago") == "santiago"
    assert at(2026, 12, 8, 12, 0, "America/Santiago") == "paranal"          # the next block, with no move
    assert at(2026, 12, 12, 12, 0, "America/Santiago") == "santiago"        # back after it


def test_with_no_places_she_is_home():
    assert place_at(parse_life(STORY), {}, None, HOME, ms(2026, 11, 20, 12, 0, "UTC")) is HOME
    assert HOME.tz == "Europe/Kyiv" and HOME.news and not HOME.south


def test_nights_and_the_next_block(world):
    story, _, _ = world
    assert night_on(story, date(2026, 11, 10)) and night_on(story, date(2026, 11, 17))
    assert not night_on(story, date(2026, 11, 18)) and not night_on(story, date(2026, 11, 9))
    assert next_block(story, date(2026, 11, 20)) == (date(2026, 12, 8), date(2026, 12, 11))
    assert next_block(story, date(2026, 11, 1), within_days=5) is None
    assert next_block(story, date(2026, 12, 20)) is None


def test_awake_on_a_normal_day_and_on_the_nights(world):
    story, _, _ = world
    day, night = parse_hours("08-01"), parse_hours("14-07")

    def awake(d, h):
        return awake_at(datetime(2026, 11, d, h, 0, tzinfo=SCL), story, day, night)

    assert awake(5, 8) and awake(5, 23) and awake(6, 0) and not awake(5, 3)        # a normal day: 08-01
    assert awake(10, 9) and awake(10, 23) and awake(11, 3)                         # the first night: the day too
    assert not awake(11, 9) and not awake(11, 13) and awake(11, 14)                # the morning after: asleep
    assert awake(18, 6) and not awake(18, 8) and awake(18, 14)                     # after the last night: up at 14
    assert awake(18, 20) and not awake(19, 3)                                      # a normal evening, a normal night
    assert awake_at(datetime(2026, 11, 5, 3, 0, tzinfo=SCL), story, None, night)             # no hours: always


def test_the_world_line_with_two_clocks_and_the_southern_spring():
    here = datetime(2026, 11, 9, 20, 15, tzinfo=ZoneInfo("America/Santiago"))
    home = here.astimezone(ZoneInfo("Europe/Kyiv"))
    line = now_line(here, "Сантьяго, Чилі", home, south=True)
    assert line.startswith("Місце: Сантьяго, Чилі. Зараз понеділок, 9 листопада 2026 року, 20:15, вечір, весна.")
    assert line.endswith("У Львові, де Ich, зараз 01:15 — там уже вівторок.")
    noon = datetime(2026, 11, 9, 12, 0, tzinfo=ZoneInfo("America/Santiago"))
    assert now_line(noon, "Сантьяго", noon.astimezone(ZoneInfo("Europe/Kyiv")), True).endswith(
        "У Львові, де Ich, зараз 17:00.")
    at_home = datetime(2026, 11, 9, 20, 15, tzinfo=ZoneInfo("Europe/Kyiv"))
    assert "У Львові" not in now_line(at_home, "Львів, Україна") and "осінь" in now_line(at_home, "Львів")
    assert [season(m, south=True) for m in (1, 4, 7, 10)] == ["літо", "осінь", "зима", "весна"]


def test_the_agent_follows_her_place(tmp_path, monkeypatch, world, caplog):
    import dataclasses
    import logging

    from tests.test_archive import kira

    caplog.set_level(logging.INFO)
    story, places, night = world
    agent = kira(tmp_path, monkeypatch)
    agent.cfg = dataclasses.replace(agent.cfg, life=story, places=places, night_place=night)
    agent.clock = lambda: ms(2026, 11, 7, 18, 0, "Europe/Kyiv")
    assert agent.tz == "Europe/Kyiv" and agent.place.key == "home"
    at_home = agent.prompt_layers()["world"]
    assert at_home.startswith("Місце: Львів, Україна.") and "У Львові" not in at_home
    agent.clock = lambda: ms(2026, 11, 9, 22, 0, "America/Santiago")
    assert agent.tz == "America/Santiago" and agent.location == places["paranal"].name
    world_line = agent.prompt_layers()["world"]
    assert "22:00, вечір, весна." in world_line and "У Львові, де Ich, зараз 03:00 — там уже вівторок." in world_line
    assert "place: home → paranal" in caplog.text
    agent.cfg = dataclasses.replace(agent.cfg, places=None)          # no places: home, as before v5.27
    agent._place_cache = None
    assert agent.tz == "Europe/Kyiv" and "У Львові" not in agent.prompt_layers()["world"]
