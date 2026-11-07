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


def test_her_weather_photos_and_news_follow_her_place(tmp_path, monkeypatch, world):
    """AGORA-215 — away, the weather is her place's (none on the road), her photos are set there in its season, and
    Lviv's news no longer touches her life."""
    import asyncio
    import dataclasses
    from urllib.parse import parse_qs, urlparse

    from agents.events import parse_day
    from agents.photo import moment_line
    from agents.weather import fetch_weather
    from tests.test_archive import kira
    from tests.test_weather import DAY, answer

    story, places, night = world
    seen = []

    async def fetch(url):
        seen.append(parse_qs(urlparse(url).query))
        return answer()

    line = asyncio.run(fetch_weather(DAY, fetch=fetch, place=places["paranal"]))
    assert line.startswith("гора Параналь: дощ, від +3 до +9 °C")
    assert (seen[0]["latitude"], seen[0]["longitude"], seen[0]["timezone"]) == (["-24.63"], ["-70.4"],
                                                                              ["America/Santiago"])

    agent = kira(tmp_path, monkeypatch)
    agent.cfg = dataclasses.replace(agent.cfg, life=story, places=places, night_place=night,
                                    capabilities=agent.cfg.capabilities | {"mood"})
    calls = []

    async def weather(day, tz, place=None):
        calls.append((day, tz, place and place.key))
        return f"{place.name if place else 'Львів'}: ясно"
    agent.weather_fetch = weather
    agent.clock = lambda: ms(2026, 11, 8, 10, 0, "Europe/Kyiv")             # on the road: no weather, no call
    assert asyncio.run(agent.ensure_weather(local_now_of(agent))) is None and calls == []
    agent.clock = lambda: ms(2026, 11, 10, 15, 0, "America/Santiago")
    assert asyncio.run(agent.ensure_weather(local_now_of(agent))) == "гора Параналь, Чилі: ясно"
    assert calls == [(date(2026, 11, 10), "America/Santiago", "paranal")]
    moment = agent._moment()
    assert moment.city == "Paranal, Chile" and moment.south and moment.weather == "гора Параналь, Чилі: ясно"
    assert "afternoon in spring, around 15:00, in Paranal, Chile" in moment_line(moment)

    woven = []

    def source(name):
        async def items(now):
            woven.append(name)
            return []
        return items
    agent.ensure_citynews, agent.ensure_worldnews = source("lviv"), source("world")
    agent.city_news_p, agent.city_news_max = 1.0, 2
    asyncio.run(agent._weave_news(local_now_of(agent), parse_day("")))
    assert woven == ["world"]                                               # Chile: the world's news, not Lviv's
    agent.clock = lambda: ms(2026, 11, 6, 15, 0, "Europe/Kyiv")             # at home, before she left
    agent._place_cache = None
    asyncio.run(agent._weave_news(local_now_of(agent), parse_day("")))
    assert woven == ["world", "lviv"] and agent._moment().city == "Lviv"


def test_away_from_lviv_her_news_is_the_worlds(tmp_path, monkeypatch, world):
    """The owner, 2026-11-07: «поміняй джерела новин на міжнародні» — away from a place with `news`, her reading has no
    Zaxid.net and the news woven into her life is the Guardian's `world` section, fetched at most every three hours
    (an empty answer tried again in an hour), never «you were there»."""
    import asyncio
    import dataclasses

    from agents.citynews import WAYS, news_ask, pick_way
    from agents.citynews import Item as CityItem
    from agents.events import parse_day
    from agents.reading import Item
    from tests.test_archive import kira

    assert {pick_way(lambda x=x: x, world=True) for x in (0.0, 0.3, 0.6, 0.999)} == set(WAYS) - {"there"}
    assert "Сьогодні в новинах (The Guardian): «Flood»" in news_ask(CityItem("Flood", "https://x", "", "x"), "heard",
                                                                    "The Guardian")
    story, places, night = world
    agent = kira(tmp_path, monkeypatch)
    agent.cfg = dataclasses.replace(agent.cfg, life=story, places=places, night_place=night,
                                    capabilities=agent.cfg.capabilities | {"events"})
    agent.clock = lambda: ms(2026, 11, 20, 12, 0, "America/Santiago")
    asked, answer = [], [Item("guardian", "world/1", "Flood in Spain", "Rivers rose", "https://g/1", "2026-11-20")]

    async def guardian(sections, day):
        asked.append(sections)
        return list(answer)
    agent.reading_sources.guardian = guardian
    now = local_now_of(agent)
    items = asyncio.run(agent.ensure_worldnews(now))
    assert asked == [["world"]] and [(i.title, i.link, i.published) for i in items] == [
        ("Flood in Spain", "https://g/1", "2026-11-20T00:00:00+00:00")]
    assert asyncio.run(agent.ensure_worldnews(now)) == items and len(asked) == 1     # kept for three hours
    agent.clock = lambda: ms(2026, 11, 20, 15, 1, "America/Santiago")
    answer[:] = [Item("guardian", "world/2", "Storm", "", "https://g/2", "2026-11-20")]
    assert [i.link for i in asyncio.run(agent.ensure_worldnews(local_now_of(agent)))] == ["https://g/1", "https://g/2"]
    agent._worldnews, answer[:] = ("", 0, []), []
    assert asyncio.run(agent.ensure_worldnews(local_now_of(agent))) == [] and len(asked) == 3
    assert asyncio.run(agent.ensure_worldnews(local_now_of(agent))) == [] and len(asked) == 3  # tried again in an hour

    asks = []

    async def write_event(way, now, news=None):
        asks.append((way, news))
        return "Я прочитала про повінь."
    agent._write_event = write_event
    agent._worldnews = ("2026-11-20", agent.clock(), [CityItem("Storm", "https://g/2", "", "2026-11-20T00:00:00+00:00")])
    agent.city_news_p, agent.city_news_max, agent.rng = 1.0, 2, lambda: 0.0
    asyncio.run(agent._weave_news(local_now_of(agent), parse_day("")))
    assert asks and asks[0][0] != "there" and "(The Guardian): «Storm»" in asks[0][1]

    async def lviv(now):
        raise AssertionError("no Lviv feed away from Lviv")

    async def nothing(sections, day):
        return []
    agent.ensure_citynews, agent.reading_sources.guardian = lviv, nothing
    asyncio.run(agent._reading_tick(local_now_of(agent)))                 # her reading never asks Zaxid.net here



def local_now_of(agent):
    from agents.world import local_now

    return local_now(agent.clock(), agent.tz)


@pytest.mark.parametrize("when, due", [
    ((2026, 11, 20, 6, 0), False),     # his 11:00, her 06:00: she sleeps
    ((2026, 11, 20, 9, 0), True),      # his 14:00, her 09:00: both awake
    ((2026, 11, 20, 21, 0), False),    # his 02:00: he sleeps
    ((2026, 11, 12, 4, 0), True),      # a night at the telescope: his 09:00, her 04:00 — the morning they share
    ((2026, 11, 12, 10, 0), False),    # the morning after a night: she sleeps
])
def test_she_writes_first_only_when_both_are_awake(tmp_path, monkeypatch, world, when, due):
    """AGORA-216 — «коли не спите обоє»: his PRIVATE_HOURS in his clock, her AWAKE_HOURS in hers, a night of a block
    awake by AWAKE_NIGHT_HOURS."""
    import asyncio
    import dataclasses

    from tests.test_private_runtime import nudger

    monkeypatch.setenv("PRIVATE_HOURS", "08-01")
    monkeypatch.setenv("AWAKE_HOURS", "08-01")
    story, places, night = world
    agent = nudger(tmp_path, monkeypatch)
    agent.cfg = dataclasses.replace(agent.cfg, life=story, places=places, night_place=night)
    now = ms(*when, "America/Santiago")
    agent.clock = lambda: now
    agent.last_private_ms = now - 7 * 3_600_000
    assert asyncio.run(agent.maybe_private_nudge()) is due


def test_her_world_line_tells_her_nights(tmp_path, monkeypatch, world):
    import dataclasses

    from agents.place import nights_line
    from tests.test_archive import kira

    story, places, night = world
    scl = ZoneInfo("America/Santiago")
    assert nights_line(datetime(2026, 11, 10, 15, 0, tzinfo=scl), story) == "Сьогодні в тебе ніч на телескопі."
    assert nights_line(datetime(2026, 11, 11, 3, 0, tzinfo=scl), story) == "Ти зараз на нічній зміні біля телескопа."
    assert nights_line(datetime(2026, 11, 18, 3, 0, tzinfo=scl), story) == "Ти зараз на нічній зміні біля телескопа."
    assert nights_line(datetime(2026, 11, 18, 15, 0, tzinfo=scl), story) == "Наступні ночі на телескопі — з 8 по 11 грудня."
    assert nights_line(datetime(2026, 12, 20, 15, 0, tzinfo=scl), story) == ""
    cross = parse_life(STORY.replace("- 2026-12-08 – 2026-12-11", "- 2026-11-28 – 2026-12-02"))
    assert nights_line(datetime(2026, 11, 20, 15, 0, tzinfo=scl), cross) == (
        "Наступні ночі на телескопі — з 28 листопада по 2 грудня.")
    agent = kira(tmp_path, monkeypatch)
    agent.cfg = dataclasses.replace(agent.cfg, life=story, places=places, night_place=night)
    agent.clock = lambda: ms(2026, 11, 10, 21, 0, "America/Santiago")
    assert agent.prompt_layers()["world"].endswith("там уже середа. Сьогодні в тебе ніч на телескопі.")


def test_a_talk_day_of_another_zone_is_never_written_twice():
    """AGORA-216 — Kyiv's day already written; after the move Santiago's day overlapping it by five hours is held,
    while a DST neighbour (an hour) never is."""
    from agents.talk import period_of, periods_due

    kyiv_day = period_of("day", ms(2026, 11, 8, 12, 0, "Europe/Kyiv"), "Europe/Kyiv")[0]
    line = ms(2026, 11, 8, 20, 0, "America/Santiago")                      # Kyiv's 9 Nov 01:00, Santiago's 8 Nov
    now = ms(2026, 11, 13, 12, 0, "America/Santiago")
    due = periods_due(now, "America/Santiago", [line], {("day", kyiv_day)}, hour_days=3, day_days=7)
    assert due == []
    due = periods_due(now, "America/Santiago", [line], set(), hour_days=3, day_days=7)
    assert [lv for lv, _, _ in due] == ["day"]
    oct_25 = period_of("day", ms(2026, 10, 25, 12, 0, "Europe/Kyiv"), "Europe/Kyiv")   # the DST day: 25 hours
    after = ms(2026, 10, 26, 12, 0, "Europe/Kyiv")
    due = periods_due(ms(2026, 10, 31, 12, 0, "Europe/Kyiv"), "Europe/Kyiv", [after], {("day", oct_25[0])}, 3, 7)
    assert [lv for lv, _, _ in due] == ["day"]


def test_the_panel_shows_her_weather_wherever_she_is(tmp_path):
    from agents.weather import load_weather, save_weather
    from panel.memory import weather_view

    save_weather(tmp_path / "kira.weather.json", "2026-11-10 paranal", "гора Параналь: ясно")
    assert load_weather(tmp_path / "kira.weather.json", "2026-11-10") is None          # the agent keys by place
    assert weather_view(tmp_path, "kira", date(2026, 11, 10)) == {"date": "2026-11-10", "line": "гора Параналь: ясно"}
    assert weather_view(tmp_path, "kira", date(2026, 11, 11)) is None
