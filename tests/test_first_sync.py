"""The first-sync rule: nothing received before `started` is ever answered."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from agents.agent import Agent
from agents.config import AgentConfig

CFG = AgentConfig(
    name="Ада", user_id="@ada:agora.lan", persona="x",
    homeserver="http://hs", room_id="!room", owner="@ich:agora.lan", password="pw",
)


class FakeLLM:
    def __init__(self, text="(відповідь)"):
        self.text = text
        self.calls = []

    async def generate(self, transcript, system_instruction):
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
        async def generate(self, transcript, system_instruction):
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
