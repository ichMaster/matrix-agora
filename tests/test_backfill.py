import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from nio import RoomMessage

from agents.agent import Agent
from tests.test_first_sync import CFG, FakeLLM


def ev(sender, body, ts, msgtype="m.text"):
    return RoomMessage.parse_event({
        "event_id": f"${ts}", "sender": sender, "origin_server_ts": ts, "type": "m.room.message",
        "content": {"msgtype": msgtype, "body": body},
    })


def test_seed_is_chronological_capped_and_never_replied_to():
    agent = Agent(CFG, llm=FakeLLM())
    agent.client = SimpleNamespace(room_send=AsyncMock(), room_typing=AsyncMock())
    agent.history_n = 3
    newest_first = [ev("@ada:agora.lan", "четверте", 4), ev("@bruno:agora.lan", "третє", 3),
                    ev("@ich:agora.lan", "notice", 25, msgtype="m.notice"),
                    ev("@ich:agora.lan", "друге", 2), ev("@ich:agora.lan", "перше", 1)]
    n = agent.seed_context(newest_first)
    assert n == 3
    assert agent.history == [("Ich", "друге"), ("Бруно", "третє"), ("Ада", "четверте")]
    assert [ts for _, ts in agent.timeline] == [2, 3, 4]
    assert agent.session == []                      # already summarized — never again
    agent.client.room_send.assert_not_awaited()     # never replied to


def test_backfill_asks_the_room_backwards_from_the_first_sync():
    agent = Agent(CFG, llm=FakeLLM())
    agent.client = SimpleNamespace(room_messages=AsyncMock(return_value=SimpleNamespace(chunk=[])))
    asyncio.run(agent.backfill("s123"))
    kwargs = agent.client.room_messages.await_args.kwargs
    assert agent.client.room_messages.await_args.args[0] == "!room"
    assert kwargs["start"] == "s123" and kwargs["limit"] == agent.history_n
