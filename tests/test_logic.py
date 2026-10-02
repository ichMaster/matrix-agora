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


def test_huge_messages_are_echoed_truncated():
    from agents.logic import ECHO_MAX_CHARS
    out = echo_reply("Ада", "x" * (ECHO_MAX_CHARS + 500))
    assert out.endswith("…") and len(out) < ECHO_MAX_CHARS + 50


def test_history_is_capped_and_keeps_everyone():
    from agents.logic import append_history
    h = []
    for i in range(35):
        h = append_history(h, "Ich" if i % 3 == 0 else ("Ада" if i % 3 == 1 else "Бруно"), f"m{i}", 30)
    assert len(h) == 30 and h[-1] == ("Ада", "m34") and h[0] == ("Бруно", "m5")


def test_transcript_is_name_colon_text_lines():
    from agents.logic import build_transcript
    assert build_transcript([("Ich", "привіт"), ("Ада", "вітаю")]) == "Ich: привіт\nАда: вітаю"


def test_instruction_is_the_literal_ukrainian_contract():
    from agents.logic import build_instruction
    out = build_instruction("Ада", "Персона.")
    assert out.startswith("Персона.")
    assert "Ти — Ада. Відповідай лише від себе, коротко, без префікса з іменем." in out
    assert out.endswith("Якщо тобі нема чого додати — відповідай рівно PASS.")


def test_history_entries_are_bounded():
    from agents.logic import ENTRY_MAX_CHARS, append_history
    h = append_history([], "Ich", "x" * (ENTRY_MAX_CHARS + 999), 30)
    assert len(h[0][1]) == ENTRY_MAX_CHARS + 1 and h[0][1].endswith("…")
