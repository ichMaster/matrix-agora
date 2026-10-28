"""v5.11 — events of her life: the hourly roll, the kinds' weights, her story's dated events on their date, the truth
guard, the append-only day file, the capability and the settings. Gemini is mocked; the clock and the rng injected."""

import asyncio
import os
import random
import stat
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from agents.agent import Agent
from agents.config import AgentConfig
from agents.events import (
    DEFAULT_WEIGHTS,
    KINDS,
    Event,
    block,
    event_ok,
    event_request,
    events_for_prompt,
    forbidden_re,
    hour_due,
    parse_day,
    parse_weights,
    roll_event,
    rolled_marker,
)
from agents.life import parse_life
from agents.roster import TYPES, RosterError, parse_member
from agents.settings import BY_NAME, concerns, validate
from tests.test_first_sync import CFG
from tests.test_life_events import STORY

KYIV = ZoneInfo("Europe/Kyiv")


def at(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=KYIV)


# --- the pure decisions ------------------------------------------------------------------------------------------
def test_parse_weights_and_bad_specs():
    assert parse_weights(DEFAULT_WEIGHTS) == {"everyday": 6, "joyful": 2, "inspiring": 2, "heavy": 1}
    assert parse_weights("joyful:1") == {"everyday": 0, "joyful": 1, "inspiring": 0, "heavy": 0}
    for bad in ("", "everyday", "everyday:x", "everyday:-1", "sad:2", "everyday:1,everyday:2", "everyday:0,heavy:0",
                "everyday:inf"):
        with pytest.raises(ValueError):
            parse_weights(bad)


def test_the_roll_misses_at_one_minus_p_and_never_at_p_zero():
    weights = parse_weights(DEFAULT_WEIGHTS)
    assert roll_event(lambda: 0.5, 0.12, weights) is None
    assert roll_event(lambda: 0.0, 0.0, weights) is None
    seq = iter([0.05, 0.0])
    assert roll_event(lambda: next(seq), 0.12, weights) == "everyday"
    seq = iter([0.05, 0.9999])
    assert roll_event(lambda: next(seq), 0.12, weights) == "heavy"


def test_the_kinds_follow_their_weights():
    rng = random.Random(7).random
    weights = parse_weights(DEFAULT_WEIGHTS)
    kinds = [roll_event(rng, 1.0, weights) for _ in range(11000)]
    share = {k: kinds.count(k) / len(kinds) for k in KINDS}
    assert abs(share["everyday"] - 6 / 11) < 0.02 and abs(share["joyful"] - 2 / 11) < 0.02
    assert abs(share["inspiring"] - 2 / 11) < 0.02 and abs(share["heavy"] - 1 / 11) < 0.015
    assert all(roll_event(rng, 1.0, parse_weights("joyful:1")) == "joyful" for _ in range(50))


def test_once_an_hour_in_the_window():
    assert hour_due(at("2026-10-27 14:05"), True, set())
    assert not hour_due(at("2026-10-27 14:50"), True, {14})
    assert not hour_due(at("2026-10-27 14:05"), False, set())


def test_the_day_file_round_trip_and_what_a_prompt_sees():
    text = (rolled_marker(8) + block(Event("09:00", "story", "surprise", "Подзвонила подруга.")) + rolled_marker(9)
            + block(Event("14:00", "joyful", "rolled", "Мені  подарували\nкнижку.")) + "<!-- news-rolled https://x/1 -->\n"
            + block(Event("15:00", "heard", "news", "Почула про новий трамвай.", "https://zaxid.net/a")))
    day = parse_day(text)
    assert day.rolled == {8, 9} and day.news == {"https://x/1"}
    assert [(e.time, e.kind, e.source) for e in day.events] == [
        ("09:00", "story", "surprise"), ("14:00", "joyful", "rolled"), ("15:00", "heard", "news")]
    assert day.events[1].text == "Мені подарували книжку." and day.events[2].link == "https://zaxid.net/a"
    seen = events_for_prompt(day.events)
    assert seen == "[09:00] Подзвонила подруга.\n[14:00] Мені подарували книжку.\n[15:00] Почула про новий трамвай."
    for hidden in ("joyful", "rolled", "surprise", "news", "story", "https://", "<!--", "heard"):
        assert hidden not in seen
    assert parse_day(None).events == () and parse_day("сміття без блоків").events == ()


@pytest.mark.parametrize("text,ok", [
    ("Подзвонила мама і розповіла про сусідку.", True),
    ("Ich написав мені листа.", False),
    ("Зустріла Іча на Ринку.", False),
    ("Бруно приніс мені каву.", False),
    ("Перекладала з Адою до ночі.", False),           # a member's name form in another case
    ("Мені здалося, що я лише модель.", False),       # a banned word
    ("Купила адаптер для телескопа.", True),          # «ада» inside a word is no name
    ("", False),
])
def test_the_guard(text, ok):
    forbidden = forbidden_re(["Ада", "ада", "адою", "аді", "Бруно", "бруно"])
    assert event_ok(text, forbidden) is ok


def test_the_request_frame_and_its_rules():
    system, contents = event_request("Кіра", "Канон.", "heavy", at("2026-10-27 14:00"), "Робота в планетарії.",
                                     "Атакама.", "- обсерваторія", "ти сьогодні тиха", "[09:00] Подзвонила подруга.")
    assert system.endswith("Ти — Кіра.") and "Канон." in system
    for part in ("Робота в планетарії.", "Атакама.", "- обсерваторія", "Настрій дня: ти сьогодні тиха",
                 "[09:00] Подзвонила подруга.", "14:00", "важка подія", "Ich і люди з Агори"):
        assert part in contents
    assert "не називай цього" in contents  # the next chapter stays a silent direction


# --- the capability and the settings -----------------------------------------------------------------------------
def test_the_capability_is_a_persons_and_needs_life_and_today():
    base = {"name": "Кіра", "user_id": "@kira:agora.lan", "type": "persona"}
    assert parse_member("kira", {**base, "capabilities": {"events": True}}).can("events")
    assert "events" not in TYPES["persona"]
    with pytest.raises(RosterError, match="persona type only"):
        parse_member("kit", {"name": "Кіт", "user_id": "@kit:agora.lan", "type": "creature",
                             "capabilities": {"events": True}})
    for missing in ("today", "life"):
        with pytest.raises(RosterError, match=f"needs '{missing}'"):
            parse_member("kira", {**base, "capabilities": {"events": True, missing: False}})


def test_the_settings_validate_and_concern_her_alone():
    assert validate("EVENT_WEIGHTS", " everyday:6, joyful:2,inspiring:2,heavy:1 ") == (DEFAULT_WEIGHTS, None)
    assert validate("EVENT_WEIGHTS", "sad:1")[0] is None
    assert validate("EVENT_P", "0.2") == ("0.2", None) and validate("EVENT_P", "1.5")[0] is None
    assert validate("EVENT_HOURS", "08-01") == ("08-01", None) and validate("EVENT_HOURS", "8-8")[0] is None
    kira = parse_member("kira", {"name": "Кіра", "user_id": "@kira:agora.lan", "capabilities": {"events": True}})
    ada = parse_member("ada", {"name": "Ада", "user_id": "@ada:agora.lan"})
    for name in ("EVENT_P", "EVENT_WEIGHTS", "EVENT_HOURS"):
        assert concerns(BY_NAME[name], kira) and not concerns(BY_NAME[name], ada)


# --- the agent ----------------------------------------------------------------------------------------------------
class EventLLM:
    def __init__(self, *texts):
        self.texts = list(texts) or ["Мені подзвонила мама і покликала на вечерю."]
        self.calls = []

    async def generate(self, transcript, system_instruction, max_output_tokens=400, kind="reply"):
        self.calls.append((kind, transcript))
        return self.texts.pop(0) if len(self.texts) > 1 else self.texts[0]


async def no_news():
    return []


def person(tmp_path, llm, when, rolls=(0.0, 0.0), caps=frozenset({"events"}), monkeypatch=None):
    cfg = AgentConfig(**{**CFG.__dict__, "name": "Кіра", "user_id": "@kira:agora.lan",
                         "capabilities": TYPES["persona"] | caps, "life": parse_life(STORY)})
    agent = Agent(cfg, llm=llm)
    agent.memory_file = tmp_path / "kira.memory.md"
    agent.citynews_fetch = no_news
    seq = iter(rolls)
    agent.rng = lambda: next(seq, 0.99)
    agent.clock = lambda: int(at(when).timestamp() * 1000)
    return agent


def tick(agent, when):
    agent.clock = lambda: int(at(when).timestamp() * 1000)
    asyncio.run(agent.ensure_events(at(when)))


def test_an_hour_rolls_once_and_a_hit_is_written_and_kept(tmp_path):
    llm = EventLLM()
    agent = person(tmp_path, llm, "2026-10-27 14:00")
    tick(agent, "2026-10-27 14:00")
    tick(agent, "2026-10-27 14:40")
    events = agent.day_events(at("2026-10-27 14:00").date())
    assert [(e.time, e.kind, e.source) for e in events] == [("14:00", "everyday", "rolled")]
    assert [k for k, _ in llm.calls] == ["event"]
    path = agent.events_file(at("2026-10-27 14:00").date())
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    restarted = person(tmp_path, EventLLM(), "2026-10-27 14:50")  # a restart within the hour: no second roll
    tick(restarted, "2026-10-27 14:50")
    assert len(restarted.day_events(at("2026-10-27 14:00").date())) == 1 and restarted.llm.calls == []


def test_no_roll_outside_her_hours_and_no_catch_up(tmp_path):
    llm = EventLLM()
    agent = person(tmp_path, llm, "2026-10-27 07:30", rolls=(0.0,) * 10)
    tick(agent, "2026-10-27 07:30")                      # before 08:00
    tick(agent, "2026-10-27 23:10")                      # from 23:00
    assert agent.day_events(at("2026-10-27 07:30").date()) == [] and llm.calls == []
    tick(agent, "2026-10-27 12:00")                      # the hours 08–11 she was not running for stay unrolled
    assert parse_day(agent._read_raw(agent.events_file(at("2026-10-27 12:00").date()))).rolled == {12}


def test_the_window_past_midnight(tmp_path, monkeypatch):
    monkeypatch.setenv("EVENT_HOURS", "08-01")
    agent = person(tmp_path, EventLLM(), "2026-10-28 00:30")
    tick(agent, "2026-10-28 00:30")
    assert [e.time for e in agent.day_events(at("2026-10-28 00:30").date())] == ["00:30"]


def test_a_miss_is_marked_and_p_zero_rolls_nothing(tmp_path, monkeypatch):
    llm = EventLLM()
    agent = person(tmp_path, llm, "2026-10-27 10:00", rolls=(0.5,))
    tick(agent, "2026-10-27 10:00")
    assert parse_day(agent._read_raw(agent.events_file(at("2026-10-27 10:00").date()))).rolled == {10}
    monkeypatch.setenv("EVENT_P", "0")
    zero = person(tmp_path / "z", llm, "2026-10-27 11:00", rolls=(0.0,) * 5)
    tick(zero, "2026-10-27 11:00")
    assert zero.day_events(at("2026-10-27 11:00").date()) == [] and llm.calls == []


def test_a_surprise_arrives_on_its_date_never_before_and_once(tmp_path):
    llm = EventLLM()
    agent = person(tmp_path, llm, "2026-10-28 09:00", rolls=(0.99,) * 10)
    tick(agent, "2026-10-28 09:00")
    assert agent.day_events(at("2026-10-28 09:00").date()) == []
    tick(agent, "2026-10-29 09:00")
    tick(agent, "2026-10-29 10:00")
    events = agent.day_events(at("2026-10-29 09:00").date())
    assert [(e.kind, e.source, e.time) for e in events] == [("story", "surprise", "09:00")]
    assert "подруга з Единбурга" in events[0].text
    tick(agent, "2026-11-03 08:00")
    assert [e.source for e in agent.day_events(at("2026-11-03 08:00").date())] == ["known"]


def test_an_event_naming_the_room_is_regenerated_once_then_dropped(tmp_path):
    llm = EventLLM("Бруно приніс мені каву.", "Подзвонила мама.")
    agent = person(tmp_path, llm, "2026-10-27 15:00")
    tick(agent, "2026-10-27 15:00")
    assert [e.text for e in agent.day_events(at("2026-10-27 15:00").date())] == ["Подзвонила мама."]
    llm = EventLLM("Ich написав мені.", "Зустріла Ірму в архіві.")
    agent = person(tmp_path / "b", llm, "2026-10-27 15:00")
    tick(agent, "2026-10-27 15:00")
    assert agent.day_events(at("2026-10-27 15:00").date()) == [] and len(llm.calls) == 2


def test_the_call_reads_her_frame_and_the_last_events(tmp_path):
    llm = EventLLM()
    agent = person(tmp_path, llm, "2026-10-27 14:00", rolls=(0.0, 0.0, 0.0, 0.0))
    tick(agent, "2026-10-27 14:00")
    tick(agent, "2026-10-27 16:00")
    contents = llm.calls[1][1]
    assert "Робота в планетарії" in contents and "Майбутнє" in contents
    assert "[14:00] Мені подзвонила мама" in contents
    assert "Події" not in contents and "подруга з Единбурга" not in contents  # no surprise ahead of its date


def test_a_failed_call_means_no_event_and_the_hour_stays_rolled(tmp_path):
    class Fail(EventLLM):
        async def generate(self, *a, **k):
            self.calls.append(("event", ""))
    agent = person(tmp_path, Fail(), "2026-10-27 14:00")
    tick(agent, "2026-10-27 14:00")
    day = parse_day(agent._read_raw(agent.events_file(at("2026-10-27 14:00").date())))
    assert day.events == () and day.rolled == {14}


def test_another_person_and_the_cat_have_no_events(tmp_path):
    llm = EventLLM()
    agent = person(tmp_path, llm, "2026-10-27 14:00", caps=frozenset())
    tick(agent, "2026-10-27 14:00")
    assert not (tmp_path / "kira.events").exists() and llm.calls == [] and agent.day_events(at("2026-10-27 14:00").date()) == []


def test_a_story_event_with_odd_spacing_enters_once(tmp_path):
    """Review #2: a canon line with a double space or a tab was compared raw against the day file's normalized text,
    so the event was entered again at every watcher tick."""
    llm = EventLLM()
    agent = person(tmp_path, llm, "2026-10-29 09:00", rolls=(0.99,) * 10)
    agent.cfg = AgentConfig(**{**agent.cfg.__dict__, "life": parse_life(
        STORY.replace("Подзвонила стара подруга з Единбурга.", "Подзвонила  стара\tподруга з Единбурга."))})
    for when in ("09:00", "09:00", "09:30", "10:00"):
        tick(agent, f"2026-10-29 {when}")
    events = agent.day_events(at("2026-10-29 09:00").date())
    assert [e.text for e in events] == ["Подзвонила стара подруга з Единбурга."]


def test_a_timed_story_event_falls_from_its_time(tmp_path, caplog):
    """Review #4: an evening event of her story fell at the first waking tick and was told as done in the morning;
    with a time it falls at the first tick from then, told at that time, and a time past her hours is warned about."""
    life = parse_life(STORY.replace("- 2026-11-03 · known", "- 2026-11-03 19:00 · known")
                      .replace("- 2027-02-14 · known", "- 2027-02-14 23:30 · known"))
    llm = EventLLM()
    agent = person(tmp_path, llm, "2026-11-03 08:00", rolls=(0.99,) * 10)
    agent.cfg = AgentConfig(**{**agent.cfg.__dict__, "life": life})
    for when in ("08:00", "12:00", "18:59"):
        tick(agent, f"2026-11-03 {when}")
    assert agent.day_events(at("2026-11-03 08:00").date()) == []
    tick(agent, "2026-11-03 19:00")
    tick(agent, "2026-11-03 20:00")
    events = agent.day_events(at("2026-11-03 08:00").date())
    assert [(e.time, e.kind, e.source) for e in events] == [("19:00", "story", "known")]
    assert agent.events_ahead(at("2026-11-03 08:00").date(), at("2026-11-10 08:00").date()) == (
        "- сьогодні, о 19:00: Дедлайн статті про змінні зорі.")
    cfg = AgentConfig(**{**CFG.__dict__, "name": "Кіра", "user_id": "@kira:agora.lan",
                         "capabilities": TYPES["persona"] | {"events"}, "life": life})
    Agent(cfg, llm=llm)
    assert "2027-02-14 at 23:30 is outside EVENT_HOURS" in caplog.text
