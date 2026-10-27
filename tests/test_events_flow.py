"""v5.11 — where events go: «Сьогодні» (refreshed when one falls, even within the hour), the day memory, and the next
plans (the recent events and the known ones ahead, never a surprise). A member without `events` sends what it sent
before. Gemini is mocked; the clock injected."""

import asyncio
from datetime import date

from agents.chronicle import day_memory_request, today_request
from agents.events import Event, block
from agents.plans import plan_request
from tests.test_events import at, person


class FlowLLM:
    """The today block, the plans, the day memory and the events, each answered by its kind."""

    def __init__(self, event="Мені подзвонила мама."):
        self.event = event
        self.calls = []

    async def generate(self, transcript, system_instruction, max_output_tokens=400, kind="reply"):
        self.calls.append((kind, transcript))
        return {"plan": "- піти в обсерваторію\n- подзвонити мамі", "today": "Сьогодні вже: робота.\nЩе сьогодні: сеанс.",
                "day_memory": "Того дня я працювала.", "event": self.event}.get(kind, "(відповідь)")

    def of(self, kind):
        return [c for k, c in self.calls if k == kind]


def put(agent, day, *events):
    for e in events:
        agent._append_events(day, block(e))


def now_is(agent, when):
    agent.clock = lambda: int(at(when).timestamp() * 1000)
    return at(when)


HIDDEN = ("joyful", "rolled", "surprise", "· news", "story", "zaxid.net", "<!--", "heard")


def test_the_today_block_tells_the_days_events_and_refreshes_when_one_falls(tmp_path):
    llm = FlowLLM()
    agent = person(tmp_path, llm, "2026-10-27 14:05")
    day = at("2026-10-27 14:05").date()
    asyncio.run(agent.ensure_today(now_is(agent, "2026-10-27 14:05")))
    asyncio.run(agent.ensure_today(now_is(agent, "2026-10-27 14:20")))
    assert len(llm.of("today")) == 1 and "Що з тобою сьогодні сталося" not in llm.of("today")[0]
    put(agent, day, Event("14:30", "joyful", "rolled", "Мені подарували книжку."),
        Event("14:31", "heard", "news", "Почула про трамвай.", "https://zaxid.net/a"))
    asyncio.run(agent.ensure_today(now_is(agent, "2026-10-27 14:40")))
    asyncio.run(agent.ensure_today(now_is(agent, "2026-10-27 14:50")))
    assert len(llm.of("today")) == 2                          # once for the new events, then cached again
    contents = llm.of("today")[1]
    assert "Що з тобою сьогодні сталося" in contents and "[14:30] Мені подарували книжку." in contents
    assert "[14:31] Почула про трамвай." in contents and "обов'язково" in contents
    assert not any(h in contents for h in HIDDEN)
    assert agent.today_section(at("2026-10-27 14:50")).startswith("Сьогодні:\nСьогодні вже")


def test_the_day_memory_tells_that_days_events(tmp_path):
    llm = FlowLLM()
    agent = person(tmp_path, llm, "2026-10-28 00:10")
    put(agent, date(2026, 10, 27), Event("16:00", "heavy", "rolled", "Мені відмовили в гранті."))
    put(agent, date(2026, 10, 26), Event("12:00", "joyful", "rolled", "Чужий день."))
    asyncio.run(agent.ensure_day_memory(date(2026, 10, 27)))
    contents = llm.of("day_memory")[0]
    assert "[16:00] Мені відмовили в гранті." in contents and "Чужий день" not in contents
    assert "з подробицями" in contents and not any(h in contents for h in HIDDEN)


def test_the_plans_answer_the_last_events_and_expect_the_known_ones_never_a_surprise(tmp_path):
    llm = FlowLLM()
    agent = person(tmp_path, llm, "2026-10-27 00:05")
    put(agent, date(2026, 10, 26), Event("18:00", "heavy", "rolled", "Мене підвів телескоп."))
    put(agent, date(2026, 10, 15), Event("10:00", "joyful", "rolled", "Давня радість."))
    asyncio.run(agent.ensure_plans(date(2026, 10, 27)))
    year, month, week, day = llm.of("plan")
    for contents in (year, month, week, day):
        assert "[18:00] Мене підвів телескоп." in contents and "вчора, понеділок, 26 жовтня" in contents
        assert "Давня радість" not in contents                          # beyond the last seven days
        assert "подруга з Единбурга" not in contents                    # the surprise of 29 October, never ahead
        assert not any(h in contents for h in HIDDEN)
    assert "вівторок, 3 листопада: Дедлайн статті" in day and "вівторок, 3 листопада: Дедлайн статті" in week
    assert "Дедлайн статті" in year and "Дедлайн статті" not in month    # the rest of October holds nothing known
    assert "Прем'єра" not in year                                       # 2027 is beyond the year's plan


def test_a_member_without_events_sends_what_it_sent_before(tmp_path):
    llm = FlowLLM()
    agent = person(tmp_path, llm, "2026-10-27 14:05", caps=frozenset())
    asyncio.run(agent.ensure_plans(date(2026, 10, 27)))
    asyncio.run(agent.ensure_today(now_is(agent, "2026-10-27 14:05")))
    asyncio.run(agent.ensure_day_memory(date(2026, 10, 26)))
    life = agent.cfg.life
    chapter = next(c for c in life.chapters if c.start == 2024)
    assert llm.of("today")[0] == today_request("Кіра", agent.cfg.canon, at("2026-10-27 14:05"), chapter.body,
                                               agent._read(agent.plan_paths(date(2026, 10, 27))["day"]), None, None,
                                               agent.max_words["today"])[1]
    assert agent._read(agent.today_file).startswith("<!-- 2026-10-27T14 -->")
    for contents in llm.of("plan") + llm.of("day_memory"):
        assert "сталося" not in contents and "чекає" not in contents


def test_the_requests_without_events_are_unchanged():
    when = at("2026-10-27 14:05")
    assert today_request("К", "c", when, "b", "p", "j", "x", 50) == today_request("К", "c", when, "b", "p", "j", "x",
                                                                                   50, None)
    args = ("К", "c", date(2026, 10, 26), "b", [], "j", "p", "t", 50)
    assert day_memory_request(*args) == day_memory_request(*args, None)
    plan = ("day", "К", "c", "понеділок", "b", None, [], None, None, [None] * 5, 120, ["Ада"])
    assert plan_request(*plan) == plan_request(*plan, None, None)


def test_no_event_naming_the_room_ever_reaches_a_request(tmp_path):
    llm = FlowLLM(event="Ich приніс мені каву, а Бруно сміявся.")
    agent = person(tmp_path, llm, "2026-10-27 14:00")
    asyncio.run(agent.ensure_events(now_is(agent, "2026-10-27 14:00")))
    asyncio.run(agent.ensure_today(now_is(agent, "2026-10-27 14:10")))
    assert agent.day_events(date(2026, 10, 27)) == []
    assert "Ich приніс" not in llm.of("today")[0] and "Бруно" not in llm.of("today")[0]
    banned = FlowLLM(event="Я відчула себе моделлю.")
    agent = person(tmp_path / "b", banned, "2026-10-27 14:00")
    asyncio.run(agent.ensure_events(now_is(agent, "2026-10-27 14:00")))
    assert agent.day_events(date(2026, 10, 27)) == []
