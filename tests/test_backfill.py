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
    assert [e[1] for e in agent.timeline] == [2, 3, 4]
    assert [e[2] for e in agent.timeline] == ["$2", "$3", "$4"]  # v4.1: event ids for R2/R3
    assert [e[3] for e in agent.timeline] == [False, False, False]  # v4.2: none is a purr
    assert agent.last_owner == ("$2", "друге")  # the owner's latest message survives a restart
    assert agent.session == []                      # already summarized — never again
    agent.client.room_send.assert_not_awaited()     # never replied to


def test_backfill_asks_the_room_backwards_from_the_first_sync():
    agent = Agent(CFG, llm=FakeLLM())
    agent.client = SimpleNamespace(room_messages=AsyncMock(return_value=SimpleNamespace(chunk=[])))
    asyncio.run(agent.backfill("s123"))
    kwargs = agent.client.room_messages.await_args.kwargs
    assert agent.client.room_messages.await_args.args[0] == "!room"
    assert kwargs["start"] == "s123" and kwargs["limit"] == agent.history_n


def test_backfill_pages_back_until_the_wide_window_is_full():
    """v4.5: the homeserver caps a page at 100 events, so Claude's 150-line window seeded only 100."""
    agent = Agent(CFG, llm=FakeLLM())
    agent.wide_n = 150
    page1 = SimpleNamespace(chunk=[ev("@ich:agora.lan", f"m{t}", t) for t in range(250, 150, -1)], end="t2")
    page2 = SimpleNamespace(chunk=[ev("@ich:agora.lan", f"m{t}", t) for t in range(150, 50, -1)], end="t3")
    agent.client = SimpleNamespace(room_messages=AsyncMock(side_effect=[page1, page2]))
    asyncio.run(agent.backfill("s1"))
    calls = agent.client.room_messages.await_args_list
    assert [c.kwargs["start"] for c in calls] == ["s1", "t2"] and calls[0].kwargs["limit"] == 100
    assert len(agent._texts) == 150 and agent.history[-1] == ("Ich", "m250")


def test_backfill_stops_at_the_rooms_start():
    agent = Agent(CFG, llm=FakeLLM())
    agent.wide_n = 150
    page = SimpleNamespace(chunk=[ev("@ich:agora.lan", "m1", 1)], end=None)
    agent.client = SimpleNamespace(room_messages=AsyncMock(return_value=page))
    asyncio.run(agent.backfill("s1"))
    assert agent.client.room_messages.await_count == 1 and agent.history == [("Ich", "m1")]
