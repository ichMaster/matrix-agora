"""The first-sync rule: nothing received before `started` is ever answered."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from agents.agent import Agent
from agents.config import AgentConfig

CFG = AgentConfig(
    name="Ада", user_id="@ada:agora.lan", canon="Канон.",
    homeserver="http://hs", room_id="!room", owner="@ich:agora.lan", password="pw",
)


class FakeLLM:
    def __init__(self, text="(відповідь)"):
        self.text = text
        self.calls = []

    async def generate(self, transcript, system_instruction, max_output_tokens=400, kind="reply"):
        self.calls.append((transcript, system_instruction))
        return self.text


def make_agent(llm=None) -> Agent:
    agent = Agent(CFG, llm=llm or FakeLLM())
    agent.client = SimpleNamespace(
        room_send=AsyncMock(), join=AsyncMock(), room_leave=AsyncMock(), room_typing=AsyncMock(),
    )
    return agent


def msg(room_id="!room", sender="@ich:agora.lan", body="привіт"):
    return SimpleNamespace(room_id=room_id), SimpleNamespace(sender=sender, body=body)


def test_backlog_before_first_sync_is_never_answered():
    agent = make_agent()  # started is False: the first sync's events are not processed
    room, event = msg()
    asyncio.run(agent.on_message(room, event))
    agent.client.room_send.assert_not_awaited()


async def run_with_tasks(agent, room, event):
    await agent.on_message(room, event)
    await asyncio.sleep(0)  # let the scheduled reply task run
    for t in asyncio.all_tasks():
        if t is not asyncio.current_task():
            await t


def test_after_first_sync_the_owner_gets_a_reply():
    agent = make_agent()
    agent.started = True
    agent.rng = lambda: 0.0
    room, event = msg(body="Адо, привіт")  # mention → immediate reply
    asyncio.run(run_with_tasks(agent, room, event))
    agent.client.room_send.assert_awaited_once()
    kwargs = agent.client.room_send.await_args.kwargs
    assert kwargs["room_id"] == "!room"
    assert kwargs["content"]["msgtype"] == "m.text"
    assert kwargs["content"]["body"] == "(відповідь)"
    # typing toggled on and off around the call
    states = [c.args for c in agent.client.room_typing.await_args_list]
    assert states == [("!room", True), ("!room", False)]


def test_failed_llm_means_silence_and_typing_reset():
    class FailingLLM(FakeLLM):
        async def generate(self, transcript, system_instruction, **kw):
            return None

    agent = make_agent(llm=FailingLLM())
    agent.started = True
    agent.rng = lambda: 0.0
    room, event = msg(body="Адо, привіт")
    asyncio.run(run_with_tasks(agent, room, event))
    agent.client.room_send.assert_not_awaited()
    states = [c.args for c in agent.client.room_typing.await_args_list]
    assert states == [("!room", True), ("!room", False)]


def test_history_includes_everyone_in_the_room():
    agent = make_agent()
    agent.started = True
    for sender, body in [("@ich:agora.lan", "питання"), ("@bruno:agora.lan", "думка"), ("@ada:agora.lan", "своє")]:
        room, event = msg(sender=sender, body=body)
        asyncio.run(agent.on_message(room, event))
    assert agent.history == [("Ich", "питання"), ("Бруно", "думка"), ("Ада", "своє")]


def test_handler_exception_never_escapes():
    agent = make_agent()
    agent.started = True
    agent.client.room_send = AsyncMock(side_effect=RuntimeError("boom"))
    room, event = msg()
    asyncio.run(agent.on_message(room, event))  # must not raise — sync_forever survives


def test_the_other_agents_message_is_not_echoed():
    agent = make_agent()
    agent.started = True
    room, event = msg(sender="@bruno:agora.lan")
    asyncio.run(agent.on_message(room, event))
    agent.client.room_send.assert_not_awaited()


def test_scheduled_replies_hold_a_strong_reference():
    agent = make_agent()
    agent.started = True
    agent.rng = lambda: 0.0

    async def run():
        room, event = msg(body="Адо, привіт")
        await agent.on_message(room, event)
        assert len(agent._tasks) == 1  # strong ref held while pending
        for t in list(agent._tasks):
            await t
        assert not agent._tasks  # discarded when done

    asyncio.run(run())


def _agent_msg(sender, body, ts):
    return SimpleNamespace(room_id="!room"), SimpleNamespace(sender=sender, body=body, server_timestamp=ts)


def test_streak_limit_pauses_then_resumes_when_the_window_frees(monkeypatch):
    real_sleep = asyncio.sleep

    async def fast_sleep(_):
        await real_sleep(0)

    monkeypatch.setattr("agents.agent.asyncio.sleep", fast_sleep)
    agent = make_agent()
    agent.started = True
    agent.rng = lambda: 0.0  # passes every probability gate
    agent.max_bot_turns = 2
    agent.bot_window_ms = 600_000

    async def run():
        for sender, body, ts in [("@ich:agora.lan", "тема", 0), ("@bruno:agora.lan", "б1", 1_000),
                                 ("@ada:agora.lan", "а1", 2_000)]:
            room, event = _agent_msg(sender, body, ts)
            await agent.on_message(room, event)
        stale = list(agent._tasks)
        for t in stale:
            t.cancel()
        await asyncio.gather(*stale, return_exceptions=True)  # let the cancellations settle
        agent.client.room_send.reset_mock()
        # Bruno's second turn hits the limit (streak = 2) → paused, then resumed
        room, event = _agent_msg("@bruno:agora.lan", "б2", 3_000)
        await agent.on_message(room, event)
        assert len(agent._tasks) == 1
        for t in list(agent._tasks):
            await t
        agent.client.room_send.assert_awaited_once()  # the conversation continued after the pause

    asyncio.run(run())


def test_resume_is_dropped_when_the_conversation_moved_on(monkeypatch):
    real_sleep = asyncio.sleep
    async def slow_then_fast(_):
        await real_sleep(0.05)

    monkeypatch.setattr("agents.agent.asyncio.sleep", slow_then_fast)
    agent = make_agent()
    agent.started = True
    agent.rng = lambda: 0.0
    agent.max_bot_turns = 2
    agent.bot_window_ms = 600_000

    async def run():
        for sender, body, ts in [("@ich:agora.lan", "тема", 0), ("@bruno:agora.lan", "б1", 1_000),
                                 ("@ada:agora.lan", "а1", 2_000)]:
            room, event = _agent_msg(sender, body, ts)
            await agent.on_message(room, event)
        stale = list(agent._tasks)
        for t in stale:
            t.cancel()
        await asyncio.gather(*stale, return_exceptions=True)  # let the cancellations settle
        agent.client.room_send.reset_mock()
        room, event = _agent_msg("@bruno:agora.lan", "б2", 3_000)
        await agent.on_message(room, event)  # paused
        pending = list(agent._tasks)
        # the owner speaks before the resume fires; the owner's own reply task is cancelled
        room, event = _agent_msg("@ich:agora.lan", "нова тема", 4_000)
        await agent.on_message(room, event)
        others = [t for t in agent._tasks if t not in pending]
        for t in others:
            t.cancel()
        await asyncio.gather(*others, return_exceptions=True)
        for t in pending:
            await t
        agent.client.room_send.assert_not_awaited()  # stale resume dropped

    asyncio.run(run())


def test_one_pending_reply_per_agent_coalesces_triggers():
    agent = make_agent()
    agent.started = True
    agent.rng = lambda: 0.0

    async def run():
        for body, ts in [("всім привіт", 1), ("ще одне", 2)]:  # two owner messages, no mentions
            room, event = _agent_msg("@ich:agora.lan", body, ts)
            await agent.on_message(room, event)
        assert len(agent._tasks) == 1  # the second trigger joined the pending reply
        for t in list(agent._tasks):
            await t
        agent.client.room_send.assert_awaited_once()
        assert agent._reply_pending is False

    asyncio.run(run())


def test_script_continuation_never_reaches_the_room():
    agent = make_agent(llm=FakeLLM("Ада: Привіт!\nIch: Я цього не казав"))
    agent.started = True
    agent.rng = lambda: 0.0

    async def run():
        room, event = _agent_msg("@ich:agora.lan", "Адо, привіт", 1)
        await agent.on_message(room, event)
        for t in list(agent._tasks):
            await t

    asyncio.run(run())
    assert agent.client.room_send.await_args.kwargs["content"]["body"] == "Привіт!"
