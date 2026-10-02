import asyncio
import re
import stat
from types import SimpleNamespace
from unittest.mock import AsyncMock

from agents.agent import Agent
from agents.memory import (
    build_summary_request,
    cap_words,
    load_memory,
    save_memory,
    session_ended,
)
from tests.test_first_sync import CFG, FakeLLM

BANNED = re.compile(r"\b(бот\w*|модел\w*|штучн\w*|ai|ші|llm|gemini|асистент\w*)\b", re.IGNORECASE)


# --- the memory file ---
def test_round_trip_atomic_private(tmp_path):
    p = tmp_path / "state" / "ada.memory.md"
    save_memory(p, "говорили про каву")
    assert stat.S_IMODE(p.stat().st_mode) == 0o600
    assert not p.with_suffix(".tmp").exists()
    assert load_memory(p) == "говорили про каву"


def test_missing_memory_means_none(tmp_path):
    assert load_memory(tmp_path / "nope.md") is None


def test_corrupt_memory_means_start_without_memory(tmp_path):
    p = tmp_path / "bad.md"
    p.write_bytes(b"\xff\xfe\xfa")
    assert load_memory(p) is None


# --- pure helpers ---
def test_session_ended_after_idle_only():
    assert session_ended(1_000, 1_000 + 900_000, 900_000) is True
    assert session_ended(1_000, 1_000 + 899_999, 900_000) is False
    assert session_ended(None, 10**9, 900_000) is False


def test_cap_words():
    assert cap_words("а б в", 5) == "а б в"
    assert cap_words("а б в г", 2) == "а б…"


def test_summary_request_carries_previous_session_and_cap_and_no_banned_words():
    system, contents = build_summary_request(
        "Ада", "Канон.", "минулого разу про каву", [("Ich", "привіт"), ("Бруно", "хай")], 200,
    )
    assert system.startswith("Канон.") and "не більше 200 слів" in system
    assert contents.startswith("Попередня нотатка: минулого разу про каву")
    assert "Ich: привіт\nБруно: хай" in contents
    assert not BANNED.search(system), "the summary prompt must never call the agent a model or a bot"
    assert "Попередня" not in build_summary_request("Ада", "К.", None, [("Ich", "x")], 50)[1]


# --- the agent's summarize / timeline cap / shutdown ---
def make(tmp_path, llm=None):
    agent = Agent(CFG, llm=llm or FakeLLM("ми говорили про каву і погоду"))
    agent.client = SimpleNamespace(room_send=AsyncMock(), room_typing=AsyncMock(), join=AsyncMock(),
                                   room_leave=AsyncMock())
    agent.memory_file = tmp_path / "ada.memory.md"
    agent.started = True
    return agent


def test_summarize_writes_the_file_and_clears_the_session(tmp_path):
    agent = make(tmp_path)
    agent.session = [("Ich", "кава чи чай?"), ("Бруно", "кава")]
    assert asyncio.run(agent.summarize()) is True
    assert load_memory(agent.memory_file) == "ми говорили про каву і погоду"
    assert agent.summary == "ми говорили про каву і погоду" and agent.session == []


def test_failed_summary_keeps_the_previous_file_and_the_session(tmp_path):
    class Failing(FakeLLM):
        async def generate(self, *a, **k):
            return None

    agent = make(tmp_path, llm=Failing())
    save_memory(agent.memory_file, "старий підсумок")
    agent.summary = "старий підсумок"
    agent.session = [("Ich", "нове")]
    assert asyncio.run(agent.summarize()) is False
    assert load_memory(agent.memory_file) == "старий підсумок"
    assert agent.session == [("Ich", "нове")]


def test_summary_is_capped_to_the_word_limit(tmp_path):
    agent = make(tmp_path, llm=FakeLLM("слово " * 500))
    agent.summary_max_words = 20
    agent.session = [("Ich", "x")]
    asyncio.run(agent.summarize())
    assert len(load_memory(agent.memory_file).split()) == 20


def test_timeline_cap_triggers_an_early_summary(tmp_path):
    agent = make(tmp_path)
    agent.session_max = 3
    agent.rng = lambda: 0.99  # keep replies out of the way: probability gates fail
    agent.max_bot_turns = 0

    async def run():
        for i, sender in enumerate(["@bruno:agora.lan", "@ada:agora.lan", "@bruno:agora.lan"]):
            room = SimpleNamespace(room_id="!room")
            event = SimpleNamespace(sender=sender, body=f"m{i}", server_timestamp=i)
            await agent.on_message(room, event)
        for t in list(agent._tasks):
            await t

    asyncio.run(run())
    assert load_memory(agent.memory_file) is not None and agent.session == []


def test_shutdown_summary_is_bounded_by_the_timeout(tmp_path):
    class Slow(FakeLLM):
        async def generate(self, *a, **k):
            await asyncio.sleep(5)
            return "запізно"

    agent = make(tmp_path, llm=Slow())
    agent.session = [("Ich", "бувай")]
    asyncio.run(agent.shutdown(timeout_s=0.05))  # must return quickly, never hang
    assert load_memory(agent.memory_file) is None


def test_failing_summaries_at_the_cap_never_storm(tmp_path):
    class Failing(FakeLLM):
        def __init__(self):
            super().__init__()
            self.n = 0

        async def generate(self, *a, **k):
            self.n += 1

    llm = Failing()
    agent = make(tmp_path, llm=llm)
    agent.session_max = 3
    agent.max_bot_turns = 0
    agent.rng = lambda: 0.99
    agent.clock = lambda: 1_000_000  # frozen: no 60 s cooldown passes

    async def run():
        for i in range(40):
            room = SimpleNamespace(room_id="!room")
            event = SimpleNamespace(sender="@bruno:agora.lan", body=f"m{i}", server_timestamp=i)
            await agent.on_message(room, event)
            for t in list(agent._tasks):
                await t

    asyncio.run(run())
    assert llm.n == 1                      # one attempt, then the cooldown holds
    assert len(agent.session) <= 2 * 3     # and the session stays bounded
