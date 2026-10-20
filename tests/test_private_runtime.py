"""v5.6 — Кіра in her private chat at run time: the invite, the start, answering, one memory, writing first (nio and
the model mocked, the clock injected)."""

import asyncio
import logging
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from nio import RoomMessage

from agents.agent import Agent
from agents.config import AgentConfig
from agents.private import PRIVATE_BRIEF, PRIVATE_DISCRETION, PRIVATE_NUDGE, PrivateState, load_private_state
from agents.roster import load_roster
from tests.test_first_sync import CFG, FakeLLM

OWNER, KIRA, ADA = CFG.owner, "@kira:agora.lan", "@ada:agora.lan"
AGORA, DM, OTHER = CFG.room_id, "!dm:agora.lan", "!other:agora.lan"
SECRET = "таємниця-7319"
TZ = "Europe/Kyiv"


def ms(hour, minute=0):
    return int(datetime(2026, 10, 20, hour, minute, tzinfo=ZoneInfo(TZ)).timestamp() * 1000)


class KindLLM(FakeLLM):
    def __init__(self, text="Привіт, сонце."):
        super().__init__(text)
        self.kinds = []

    async def generate(self, transcript, system_instruction, max_output_tokens=400, kind="reply"):
        self.kinds.append(kind)
        return await super().generate(transcript, system_instruction, max_output_tokens, kind)


def kira(tmp_path, monkeypatch, private=True, llm=None):
    monkeypatch.setenv("TIMEZONE", TZ)
    caps = frozenset({"canon", "summary", "voice", "world"} | ({"private"} if private else set()))
    cfg = AgentConfig(**{**CFG.__dict__, "name": "Кіра", "user_id": KIRA, "capabilities": caps})
    agent = Agent(cfg, llm=llm or KindLLM())
    agent.memory_file = tmp_path / "kira.memory.md"
    agent.private_file = tmp_path / "kira.private.json"
    agent.private_room = None
    agent.client = SimpleNamespace(room_send=AsyncMock(), join=AsyncMock(), room_leave=AsyncMock(),
                                   room_typing=AsyncMock(), rooms={}, invited_rooms={})
    agent.join_room = AsyncMock(return_value=True)
    agent.started, agent.started_ms = True, ms(8)
    agent.clock = lambda: ms(18)
    return agent


def text(sender, body, ts=None, eid="$e", edit=False):
    content = {"msgtype": "m.text", "body": body}
    if edit:
        content["m.relates_to"] = {"rel_type": "m.replace", "event_id": "$x"}
    return RoomMessage.parse_event({"event_id": eid, "sender": sender, "origin_server_ts": ts or ms(17),
                                    "type": "m.room.message", "content": content})


def sent_to(agent):
    return [(c.kwargs["room_id"], c.kwargs["content"]["body"]) for c in agent.client.room_send.await_args_list]


# --- the invite and the start ---------------------------------------------------------------------------------------
def test_the_owners_invite_opens_the_private_chat_and_a_second_room_is_refused(tmp_path, monkeypatch):
    agent = kira(tmp_path, monkeypatch)
    invite = lambda room, who: asyncio.run(agent.on_invite(
        SimpleNamespace(room_id=room), SimpleNamespace(state_key=KIRA, membership="invite", sender=who)))
    invite(DM, OWNER)
    assert agent.private_room == DM and load_private_state(agent.private_file, "").room == DM
    invite(OTHER, OWNER)                                                   # one private room per person
    invite("!x:agora.lan", ADA)                                            # never a member's invite
    assert agent.private_room == DM and agent.client.room_leave.await_count == 2
    plain = kira(tmp_path / "b", monkeypatch, private=False)
    asyncio.run(plain.on_invite(SimpleNamespace(room_id=DM),
                                SimpleNamespace(state_key=KIRA, membership="invite", sender=OWNER)))
    assert plain.private_room is None and plain.client.room_leave.await_count == 1


def test_at_start_the_room_is_rediscovered_and_its_history_read(tmp_path, monkeypatch):
    agent = kira(tmp_path, monkeypatch)
    agent.client.rooms = {AGORA: SimpleNamespace(users={OWNER: 1, KIRA: 1, ADA: 1}),
                          DM: SimpleNamespace(users={OWNER: 1, KIRA: 1})}
    newest_first = [text(KIRA, "Я теж.", ms(16, 5), "$2"), text(OWNER, "Сумую за горами.", ms(16), "$1"),
                    text(ADA, "чужий рядок", ms(15), "$0")]
    agent.client.room_messages = AsyncMock(return_value=SimpleNamespace(chunk=newest_first))
    asyncio.run(agent.start_private("s1"))
    assert agent.private_room == DM and load_private_state(agent.private_file, "").room == DM
    assert agent.private_history == [("Ich", "Сумую за горами."), ("Кіра", "Я теж.")]
    assert agent.last_private_ms == ms(16, 5)


# --- answering ------------------------------------------------------------------------------------------------------
def answer(agent, *events):
    """Feed private messages, then run the pending answer at once (no typing delay in a test)."""
    spawned = []
    agent._spawn = lambda coro: spawned.append(coro)
    for e in events:
        asyncio.run(agent.on_message(SimpleNamespace(room_id=DM), e))
    for coro in spawned:
        coro.close()
    if spawned:
        asyncio.run(agent.private_later(0))
    return spawned


def test_the_owners_private_message_is_answered_there_from_the_private_prompt(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    agent = kira(tmp_path, monkeypatch)
    agent.private_room = DM
    agent.history = [("Бруно", "агорний рядок")]                            # Agora's context window
    spawned = answer(agent, text(OWNER, f"Як твій день? {SECRET}"))
    assert len(spawned) == 1
    assert sent_to(agent) == [(DM, "Привіт, сонце.")]                       # in the private chat, never in Agora
    transcript, system = agent.llm.calls[0]
    assert PRIVATE_BRIEF in system and PRIVATE_DISCRETION not in system
    assert f"Ich: Як твій день? {SECRET}" in transcript and "агорний рядок" not in transcript
    assert agent.llm.kinds == ["private"]
    assert agent.session[-2:] == [("Ich (наодинці)", f"Як твій день? {SECRET}"), ("Кіра (наодинці)", "Привіт, сонце.")]
    assert agent.private_history[-1] == ("Кіра", "Привіт, сонце.")
    assert "private: answered" in caplog.text and all(SECRET not in r.getMessage() for r in caplog.records)


def test_a_stranger_a_member_or_an_edit_in_the_private_chat_is_ignored(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    agent = kira(tmp_path, monkeypatch)
    agent.private_room = DM
    assert answer(agent, text("@mallory:agora.lan", "привіт"), text(ADA, "Кіро, а я?"),
                  text(OWNER, "* виправлено", edit=True)) == []
    assert agent.client.room_send.await_count == 0 and agent.session == []
    assert caplog.text.count("ignored: sender-not-allowlisted (private chat)") == 2 and "ignored: edit" in caplog.text


def test_a_message_during_an_answer_coalesces_and_gets_its_own_pass(tmp_path, monkeypatch):
    agent = kira(tmp_path, monkeypatch)
    agent.private_room = DM
    original = agent.private_reply

    async def reply_and_hear_another(nudge=False):
        sent = await original(nudge)
        if agent.llm.kinds == ["private"]:                                 # the owner writes during the first
            agent.on_private(text(OWNER, "І ще одне", ms(17, 1), "$b"))
        return sent

    agent.private_reply = reply_and_hear_another
    answer(agent, text(OWNER, "Перше", ms(17), "$a"))
    assert agent.llm.kinds == ["private", "private"] and agent.client.room_send.await_count == 2
    assert agent._private_pending is False


def test_her_agora_prompt_keeps_the_private_talk_to_herself(tmp_path, monkeypatch):
    agent = kira(tmp_path, monkeypatch)
    assert PRIVATE_DISCRETION in agent.build_prompt() and PRIVATE_BRIEF not in agent.build_prompt()
    assert PRIVATE_DISCRETION not in agent.build_prompt(private=PRIVATE_BRIEF)
    plain = kira(tmp_path / "b", monkeypatch, private=False)
    assert PRIVATE_DISCRETION not in plain.build_prompt()


# --- writing first --------------------------------------------------------------------------------------------------
def nudger(tmp_path, monkeypatch):
    agent = kira(tmp_path, monkeypatch)
    agent.private_room = DM
    agent.private_history = [("Ich", "Добраніч."), ("Кіра", "Добраніч!")]
    agent.last_private_ms = ms(11)                                         # seven hours of private silence
    return agent


def test_she_writes_first_after_a_long_silence_in_the_owners_hours(tmp_path, monkeypatch):
    agent = nudger(tmp_path, monkeypatch)
    assert asyncio.run(agent.maybe_private_nudge()) is True
    assert sent_to(agent) == [(DM, "Привіт, сонце.")] and PRIVATE_NUDGE in agent.llm.calls[0][1]
    assert agent.llm.kinds == ["private_nudge"]
    state = load_private_state(agent.private_file, "2026-10-20")
    assert (state.count, state.last_ms, state.sent_ms, state.room) == (1, ms(18), ms(18), DM)
    assert asyncio.run(agent.maybe_private_nudge()) is False                # she just wrote: the chat isn't quiet


def test_she_never_writes_first_out_of_hours_while_answering_after_a_restart_or_before_a_first_talk(tmp_path,
                                                                                                    monkeypatch):
    late = nudger(tmp_path / "late", monkeypatch)
    late.clock = lambda: ms(23)
    busy = nudger(tmp_path / "busy", monkeypatch)
    busy._private_pending = True
    restarted = nudger(tmp_path / "restart", monkeypatch)
    restarted.started_ms = ms(17)                                          # a restart an hour ago
    never = nudger(tmp_path / "never", monkeypatch)
    never.private_history = []
    capped = nudger(tmp_path / "capped", monkeypatch)
    from agents.private import save_private_state
    save_private_state(capped.private_file, PrivateState(DM, ms(9), "2026-10-20", 2))
    for agent in (late, busy, restarted, never, capped):
        assert asyncio.run(agent.maybe_private_nudge()) is False
        assert agent.client.room_send.await_count == 0


# --- who has it ------------------------------------------------------------------------------------------------------
def test_only_kira_has_a_private_chat():
    assert [n for n, m in load_roster("agora").items() if m.can("private")] == ["kira"]
