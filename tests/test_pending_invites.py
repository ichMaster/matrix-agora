"""Invites pending from before startup are joined (owner+room only) or left."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from agents.agent import Agent
from tests.test_first_sync import CFG


def test_pending_owner_invite_is_joined_others_left():
    agent = Agent(CFG)
    agent.client = SimpleNamespace(
        room_leave=AsyncMock(), room_send=AsyncMock(),
        invited_rooms={
            "!room": SimpleNamespace(inviter="@ich:agora.lan"),
            "!trap": SimpleNamespace(inviter="@mallory:agora.lan"),
        },
    )
    agent.join_room = AsyncMock(return_value=True)
    asyncio.run(agent.join_pending_invites())
    agent.join_room.assert_awaited_once_with("!room")
    agent.client.room_leave.assert_awaited_once_with("!trap")
