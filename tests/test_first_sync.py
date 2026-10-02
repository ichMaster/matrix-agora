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


def make_agent() -> Agent:
    agent = Agent(CFG)
    agent.client = SimpleNamespace(room_send=AsyncMock(), join=AsyncMock(), room_leave=AsyncMock())
    return agent


def msg(room_id="!room", sender="@ich:agora.lan", body="привіт"):
    return SimpleNamespace(room_id=room_id), SimpleNamespace(sender=sender, body=body)


def test_backlog_before_first_sync_is_never_answered():
    agent = make_agent()  # started is False: the first sync's events are not processed
    room, event = msg()
    asyncio.run(agent.on_message(room, event))
    agent.client.room_send.assert_not_awaited()


def test_after_first_sync_the_owner_gets_an_echo():
    agent = make_agent()
    agent.started = True
    room, event = msg()
    asyncio.run(agent.on_message(room, event))
    agent.client.room_send.assert_awaited_once()
    kwargs = agent.client.room_send.await_args.kwargs
    assert kwargs["room_id"] == "!room"
    assert kwargs["content"]["msgtype"] == "m.text"
    assert kwargs["content"]["body"] == "Ада чує: привіт"


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
