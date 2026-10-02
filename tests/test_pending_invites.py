"""Invites pending from before startup are joined (owner+room only) or left."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from agents.agent import Agent
from tests.test_first_sync import CFG


def test_pending_owner_invite_is_joined_others_left():
    agent = Agent(CFG)
    agent.client = SimpleNamespace(
        join=AsyncMock(), room_leave=AsyncMock(), room_send=AsyncMock(),
        invited_rooms={
            "!room": SimpleNamespace(inviter="@ich:agora.lan"),
            "!trap": SimpleNamespace(inviter="@mallory:agora.lan"),
        },
    )
    asyncio.run(agent.join_pending_invites())
    agent.client.join.assert_awaited_once_with("!room")
    agent.client.room_leave.assert_awaited_once_with("!trap")
