"""v5.12 — the reading and the reflection in the idle watcher's steps (AGORA-134): a fake Gemini by kind, an
injected clock, canned sources (Zaxid.net's feed and page, the Guardian), SQLite in a temp dir — no network."""

import asyncio
import logging
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from agents import citynews
from agents.agent import Agent
from agents.archive import Archive
from agents.config import AgentConfig
from agents.logic import BANNED_RE
from agents.reading import Sources, load_state
from agents.world import local_now
from tests.test_private_runtime import AGORA, DM, KIRA, OWNER

TZ = "Europe/Kyiv"
PAGE = ('<script type="application/ld+json">{"@type": "NewsArticle", "articleBody": '
        '"У Львові відкрили новий телескоп у планетарії. Перший показ — у суботу."}</script>')


def ms(h, mi=0, d=20):
    return int(datetime(2026, 10, d, h, mi, tzinfo=ZoneInfo(TZ)).timestamp() * 1000)


class ThinkLLM:
    """Answers by kind from a queue; a kind may raise or wait on an event."""

    def __init__(self, answers=None, hold=None, raise_on=(), none_on=()):
        self.answers = {k: list(v) for k, v in (answers or {}).items()}
        self.calls, self.hold, self.raise_on, self.none_on = [], hold or {}, raise_on, set(none_on)

    async def generate(self, contents, system, max_output_tokens=400, kind="reply"):
        self.calls.append((kind, system, contents))
        if kind in self.raise_on:
            raise RuntimeError("down")
        if kind in self.hold:
            await self.hold[kind].wait()
        if kind in self.none_on:  # the client's failure: logged by it, None to the caller
            return None
        queue = self.answers.get(kind)
        return queue.pop(0) if queue else "Привіт, сонце."

    async def embed(self, texts, task="RETRIEVAL_DOCUMENT", kind="embed"):
        return [[1.0, float(len(t) % 7)] for t in texts]

    def kinds(self):
        return [k for k, _, _ in self.calls]


def guardian_fetch(body="Scientists found water on a moon of Saturn."):
    async def fetch(url):
        if "/search?" in url:
            return {"response": {"results": [{"id": "science/2026/oct/20/moon", "webTitle": "Water on a moon",
                                              "webUrl": "https://www.theguardian.com/science/2026/oct/20/moon",
                                              "webPublicationDate": "2026-10-20T06:00:00Z",
                                              "fields": {"trailText": "A find"}}]}}
        return {"response": {"content": {"webTitle": "Water on a moon", "webUrl": "https://www.theguardian.com/x",
                                         "fields": {"bodyText": body}}}}
    return fetch


def feed():
    return [citynews.Item("Новий телескоп у планетарії", "https://zaxid.net/news/n1", "Показ у суботу",
                          "2026-10-20T05:00:00+00:00"),
            citynews.Item("Ремонт трамвайної колії", "https://zaxid.net/news/n2", "", "2026-10-20T06:00:00+00:00")]


def thinker(tmp_path, monkeypatch, llm, page=PAGE, key="K"):
    monkeypatch.setenv("TIMEZONE", TZ)
    for var, value in (("READING_EVERY_S", "10800"), ("READING_HOURS", "08-01"), ("READING_PICKS", "2"),
                       ("READING_SECTIONS", "science"), ("REFLECT_EVERY_S", "3600")):
        monkeypatch.setenv(var, value)
    caps = frozenset({"canon", "summary", "voice", "world", "private", "recall", "thoughts"})
    cfg = AgentConfig(name="Кіра", user_id=KIRA, canon="Канон Кіри.", homeserver="http://hs", room_id=AGORA,
                      owner=OWNER, password="pw", capabilities=caps, reading="Читає про космос і про Львів.")
    agent = Agent(cfg, llm=llm)
    agent.memory_file = tmp_path / "kira.memory.md"
    agent.archive = Archive(tmp_path / "kira.archive.db")
    agent.recall_n = 6
    agent.private_file = tmp_path / "kira.private.json"
    agent.private_room = DM
    agent.client = SimpleNamespace(room_send=AsyncMock(), room_typing=AsyncMock(), rooms={}, invited_rooms={})
    agent.started, agent.started_ms = True, ms(8)
    clock = [ms(10)]
    agent.clock = lambda: clock[0]
    agent._spawn = lambda coro: coro.close()
    agent.voice_reply_p = 0.0
    agent.citynews_fetch = AsyncMock(return_value=feed())

    async def text(url):
        return page

    agent.reading_sources = Sources(key, fetch_json=guardian_fetch(), fetch_text=text)
    return agent, clock


def now_of(agent):
    return local_now(agent.clock(), agent.tz)


# --- the reading -------------------------------------------------------------------------------------------------
def test_a_reading_picks_from_both_sources_and_writes_a_thought_on_each(tmp_path, monkeypatch):
    llm = ThinkLLM({"reading": ["3, 1"], "thought": ["Вода на супутнику — оце масштаб.", "Телескоп! Піду в суботу."]})
    agent, _ = thinker(tmp_path, monkeypatch, llm)
    asyncio.run(agent.ensure_reading(now_of(agent)))
    assert llm.kinds() == ["reading", "thought", "thought"]
    pick_system, pick_contents = llm.calls[0][1], llm.calls[0][2]
    assert pick_contents.splitlines() == ["1. [ZAXID.NET] Новий телескоп у планетарії — Показ у суботу",
                                          "2. [ZAXID.NET] Ремонт трамвайної колії",
                                          "3. [The Guardian] Water on a moon — A find"]
    assert "Читає про космос і про Львів." in pick_system and "щонайбільше 2" in pick_system
    assert "Scientists found water" in llm.calls[1][2] and "Перший показ" in llm.calls[2][2]
    thoughts = agent.day_thoughts(now_of(agent).date())
    assert [(t.kind, t.place, t.source, t.title, t.link) for t in thoughts] == [
        ("news", "thought", "guardian", "Water on a moon", "https://www.theguardian.com/science/2026/oct/20/moon"),
        ("news", "thought", "zaxid", "Новий телескоп у планетарії", "https://zaxid.net/news/n1")]
    assert [x.text for x in agent.archive.latest("thought", 5)] == [t.text for t in thoughts]
    state = load_state(agent.reading_file)
    assert state.last_reading_ms == ms(10) and set(state.seen) == {
        "https://zaxid.net/news/n1", "https://zaxid.net/news/n2", "science/2026/oct/20/moon"}   # every shown item
    for _, system, _ in llm.calls:
        assert not BANNED_RE.search(system)


def test_the_reading_runs_once_a_period_in_its_hours_and_never_shows_an_item_twice(tmp_path, monkeypatch):
    llm = ThinkLLM({"reading": ["0", "0"]})
    agent, clock = thinker(tmp_path, monkeypatch, llm)
    asyncio.run(agent.ensure_reading(now_of(agent)))
    assert llm.kinds() == ["reading"]                     # `0`: nothing picked, no thought
    clock[0] = ms(12)
    asyncio.run(agent.ensure_reading(now_of(agent)))      # within the period
    assert llm.kinds() == ["reading"]
    clock[0] = ms(13, 30)
    asyncio.run(agent.ensure_reading(now_of(agent)))      # a new period, but nothing new to show
    assert llm.kinds() == ["reading"]
    clock[0] = ms(3, 0, d=21)
    agent.citynews_fetch = AsyncMock(return_value=[citynews.Item("Нічна новина", "https://zaxid.net/news/n9", "",
                                                                 "2026-10-21T00:30:00+00:00")])
    assert not agent.reading_is_due(now_of(agent))        # 03:00 is outside 08-01


def test_a_restart_never_reads_twice_and_a_failure_backs_off(tmp_path, monkeypatch, caplog):
    llm = ThinkLLM(raise_on=("reading",))
    agent, _ = thinker(tmp_path, monkeypatch, llm)
    asyncio.run(agent.ensure_reading(now_of(agent)))
    assert load_state(agent.reading_file).last_reading_ms == ms(10)   # saved before the call
    assert "reading failed" in caplog.text and agent._reading_retry_ms == ms(10) + 600_000
    again, _ = thinker(tmp_path, monkeypatch, ThinkLLM())               # a restart in the same period
    assert not again.reading_is_due(now_of(again))


def test_a_pick_with_no_full_text_is_skipped(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    llm = ThinkLLM({"reading": ["1"]})
    agent, _ = thinker(tmp_path, monkeypatch, llm, page="<html>без тексту</html>")
    asyncio.run(agent.ensure_reading(now_of(agent)))
    assert llm.kinds() == ["reading"] and agent.day_thoughts(now_of(agent).date()) == []
    assert "had no text" in caplog.text


def test_without_a_key_she_reads_zaxid_only(tmp_path, monkeypatch):
    llm = ThinkLLM({"reading": ["0"]})
    agent, _ = thinker(tmp_path, monkeypatch, llm, key="")
    asyncio.run(agent.ensure_reading(now_of(agent)))
    assert "[The Guardian]" not in llm.calls[0][2] and "[ZAXID.NET]" in llm.calls[0][2]


def test_a_banned_word_gets_one_regeneration_then_the_thought_is_dropped(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    llm = ThinkLLM({"reading": ["1", "1"], "thought": ["Я лише модель.", "Цікаво.", "Звичайний бот.", "Я бот."]})
    agent, clock = thinker(tmp_path, monkeypatch, llm)
    asyncio.run(agent.ensure_reading(now_of(agent)))
    assert llm.kinds() == ["reading", "thought", "thought"]
    assert [t.text for t in agent.day_thoughts(now_of(agent).date())] == ["Цікаво."]   # regenerated once
    agent.citynews_fetch = AsyncMock(return_value=[citynews.Item("Інша новина", "https://zaxid.net/news/n3", "",
                                                                 "2026-10-20T09:00:00+00:00")])
    clock[0] = ms(13, 30)
    asyncio.run(agent.ensure_reading(now_of(agent)))
    assert llm.kinds()[3:] == ["reading", "thought", "thought"]
    assert len(agent.day_thoughts(now_of(agent).date())) == 1                          # dropped
    assert "модель" not in caplog.text and "бот" not in caplog.text


# --- the reflection ------------------------------------------------------------------------------------------
def talk(agent, place, rows, start):
    for i, (who, text) in enumerate(rows):
        agent._archive(f"{place}:{start + i}", start + i * 1000, place, "matrix", who, text)


def test_the_first_reflection_starts_from_now_and_then_each_place_with_new_lines_is_thought_over(tmp_path,
                                                                                                    monkeypatch):
    llm = ThinkLLM({"reflection": ["Він сьогодні говорив тихіше, ніж звичайно.\n- Хочу спитати його про гори.",
                                   "Ада знову про слова, а я про зорі."]})
    agent, clock = thinker(tmp_path, monkeypatch, llm)
    talk(agent, "private", [("Ich", "Старе."), ("Кіра", "Старе теж.")], ms(9))
    asyncio.run(agent.ensure_reflection(now_of(agent)))
    assert llm.kinds() == []                                    # the past is never reflected on
    talk(agent, "private", [("Ich", "Привіт, як ти?"), ("Кіра", "Добре! А ти?")], ms(10, 20))
    talk(agent, "agora", [("Ада", "Слово «зоря» гарне."), ("Кіра", "А зоря — це плазма.")], ms(10, 30))
    clock[0] = ms(11, 5)
    asyncio.run(agent.ensure_reflection(now_of(agent)))
    assert llm.kinds() == ["reflection", "reflection"]
    private_call, agora_call = llm.calls
    assert "Ich: Привіт, як ти?" in private_call[2] and "Старе" not in private_call[2]
    assert "наодинці" in private_call[1] and "в Агорі" in agora_call[1]
    assert "Нічого не вигадуй: ні слів, ні вчинків Ich чи інших" in private_call[1]
    thoughts = agent.day_thoughts(now_of(agent).date())
    assert [(t.kind, t.place, t.source, t.text) for t in thoughts] == [
        ("reflection", "thought_private", "private", "Він сьогодні говорив тихіше, ніж звичайно."),
        ("reflection", "thought_private", "private", "Хочу спитати його про гори."),
        ("reflection", "thought", "agora", "Ада знову про слова, а я про зорі.")]
    clock[0] = ms(12, 10)
    asyncio.run(agent.ensure_reflection(now_of(agent)))         # nothing new since: no call
    assert len(llm.calls) == 2


def test_only_her_own_lines_bring_no_reflection_and_the_period_holds(tmp_path, monkeypatch):
    llm = ThinkLLM()
    agent, clock = thinker(tmp_path, monkeypatch, llm)
    asyncio.run(agent.ensure_reflection(now_of(agent)))
    talk(agent, "private", [("Кіра", "Ти тут?"), ("Кіра", "Ну добре.")], ms(10, 10))
    clock[0] = ms(10, 40)
    asyncio.run(agent.ensure_reflection(now_of(agent)))         # within the hour
    clock[0] = ms(11, 10)
    asyncio.run(agent.ensure_reflection(now_of(agent)))         # her own lines only
    assert llm.kinds() == []


def test_no_answer_waits_for_a_reflection(tmp_path, monkeypatch):
    hold = asyncio.Event()
    llm = ThinkLLM({"reflection": ["Думаю про це."]}, hold={"reflection": hold})
    agent, clock = thinker(tmp_path, monkeypatch, llm)

    async def scene():
        await agent.ensure_reflection(now_of(agent))
        talk(agent, "private", [("Ich", "Ти тут?")], ms(10, 10))
        clock[0] = ms(11, 10)
        reflecting = asyncio.create_task(agent.ensure_reflection(now_of(agent)))
        await asyncio.sleep(0)                                   # the reflection's call is open now
        agent.private_history = [("Ich", "Ти тут?")]
        sent = await asyncio.wait_for(agent.private_reply(), timeout=2)
        open_while_answering = not reflecting.done()
        hold.set()
        await reflecting
        return sent, open_while_answering

    sent, open_while_answering = asyncio.run(scene())
    assert sent and open_while_answering
    assert llm.kinds()[0] == "reflection" and "private" in llm.kinds()
    assert [t.text for t in agent.day_thoughts(now_of(agent).date())] == ["Думаю про це."]


def test_the_watcher_spawns_them_and_an_agent_without_thoughts_never_reads(tmp_path, monkeypatch):
    llm = ThinkLLM()
    agent, _ = thinker(tmp_path, monkeypatch, llm)
    assert agent.reading_is_due(now_of(agent)) and agent.reflection_is_due()
    other = Agent(AgentConfig(name="Ада", user_id="@ada:agora.lan", canon="К.", homeserver="h", room_id=AGORA,
                              owner=OWNER, password="pw"), llm=llm)
    assert not other.reading_is_due(now_of(agent)) and not other.reflection_is_due()
    assert other.reading_sources._key == ""


def test_her_guardian_key_leaves_the_environment_and_claudes_is_untouched(monkeypatch):
    import os
    monkeypatch.setenv("GUARDIAN_API_KEY", "her-key")
    caps = frozenset({"canon", "summary", "voice", "world", "private", "recall", "thoughts"})
    cfg = AgentConfig(name="Кіра", user_id=KIRA, canon="К.", homeserver="http://hs", room_id=AGORA, owner=OWNER,
                      password="pw", capabilities=caps, reading="Р.")
    agent = Agent(cfg, llm=ThinkLLM())
    assert agent.reading_sources._key == "her-key" and "GUARDIAN_API_KEY" not in os.environ
    monkeypatch.setenv("GUARDIAN_API_KEY", "claudes-key")
    Agent(AgentConfig(name="Ада", user_id="@ada:agora.lan", canon="К.", homeserver="h", room_id=AGORA, owner=OWNER,
                      password="pw"), llm=ThinkLLM())
    assert os.environ["GUARDIAN_API_KEY"] == "claudes-key"     # only a person with `thoughts` takes it


# --- code review #1: a failed call uses nothing up -------------------------------------------------------------
def test_a_failed_pick_keeps_the_items_fresh_and_the_reading_comes_back_soon(tmp_path, monkeypatch):
    llm = ThinkLLM({"reading": ["1"], "thought": ["Телескоп! Піду в суботу."]}, none_on={"reading"})
    agent, clock = thinker(tmp_path, monkeypatch, llm)
    asyncio.run(agent.ensure_reading(now_of(agent)))
    state = load_state(agent.reading_file)
    assert state.seen == {} and state.last_reading_ms == 0          # nothing shown is used up, the time restored
    assert agent._reading_retry_ms == ms(10) + 600_000               # tried again in 10 minutes
    llm.none_on.clear()
    clock[0] = ms(10, 5)
    asyncio.run(agent.ensure_reading(now_of(agent)))                 # still backing off
    assert llm.kinds() == ["reading"]
    clock[0] = ms(10, 11)
    asyncio.run(agent.ensure_reading(now_of(agent)))
    assert llm.kinds() == ["reading", "reading", "thought"]
    assert "1. [ZAXID.NET] Новий телескоп у планетарії" in llm.calls[1][2]   # the same items, shown again
    assert [t.text for t in agent.day_thoughts(now_of(agent).date())] == ["Телескоп! Піду в суботу."]


def test_a_failed_reflection_keeps_its_place_and_reads_the_same_lines_next_time(tmp_path, monkeypatch):
    llm = ThinkLLM({"reflection": ["Він питав, як я."]}, none_on={"reflection"})
    agent, clock = thinker(tmp_path, monkeypatch, llm)
    asyncio.run(agent.ensure_reflection(now_of(agent)))
    talk(agent, "private", [("Ich", "Привіт, як ти?")], ms(10, 20))
    clock[0] = ms(11, 5)
    asyncio.run(agent.ensure_reflection(now_of(agent)))
    assert llm.kinds() == ["reflection"] and agent.day_thoughts(now_of(agent).date()) == []
    llm.none_on.clear()
    clock[0] = ms(12, 10)
    asyncio.run(agent.ensure_reflection(now_of(agent)))
    assert llm.kinds() == ["reflection", "reflection"] and "Ich: Привіт, як ти?" in llm.calls[1][2]
    assert [t.text for t in agent.day_thoughts(now_of(agent).date())] == ["Він питав, як я."]
