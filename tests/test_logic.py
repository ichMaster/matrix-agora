import pytest

from agents.config import AgentConfig
from agents.logic import echo_reply, should_handle, should_join_invite

CFG = AgentConfig(
    name="Ада", user_id="@ada:agora.lan", persona="x",
    homeserver="http://hs", room_id="!room", owner="@ich:agora.lan", password="pw",
)
OTHER = "@bruno:agora.lan"


@pytest.mark.parametrize("room,sender,expect,reason", [
    ("!room", "@ich:agora.lan", True, "ok"),            # owner
    ("!room", OTHER, True, "ok"),                        # the other agent
    ("!room", "@ada:agora.lan", False, "own-message"),   # self
    ("!other", "@ich:agora.lan", False, "foreign-room"), # another room
    ("!dm", OTHER, False, "foreign-room"),               # a DM is just another room
    ("!room", "@mallory:agora.lan", False, "sender-not-allowlisted"),
])
def test_filter_table(room, sender, expect, reason):
    v = should_handle(room, sender, CFG, OTHER)
    assert (v.handle, v.reason) == (expect, reason)


def test_filter_without_other_agent_allows_owner_only():
    assert should_handle("!room", OTHER, CFG, other_agent=None).handle is False
    assert should_handle("!room", "@ich:agora.lan", CFG, other_agent=None).handle is True


@pytest.mark.parametrize("room,inviter,expect", [
    ("!room", "@ich:agora.lan", True),
    ("!room", "@mallory:agora.lan", False),
    ("!other", "@ich:agora.lan", False),
])
def test_invite_rule(room, inviter, expect):
    assert should_join_invite(room, inviter, CFG) is expect


def test_echo_format_is_the_literal_contract():
    assert echo_reply("Ада", "привіт") == "Ада чує: привіт"


def test_v05_echoes_the_owner_only_no_bot_loop():
    from agents.logic import should_echo
    assert should_echo("@ich:agora.lan", CFG) is True
    assert should_echo(OTHER, CFG) is False  # otherwise ada and bruno echo each other forever
