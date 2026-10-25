"""v5.7 — Кіра in Telegram at run time: one private chat with two doors, the answer back to its door, voice both
ways, writing first to the last door, the backlog before a start, the poller's errors (nio, the Bot API, Deepgram
and ElevenLabs mocked; the clock injected)."""

import asyncio
import json
import logging
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agents import agent as agent_mod
from agents.agent import Agent
from agents.config import AgentConfig
from agents.private import (
    PRIVATE_CANT_LISTEN,
    PRIVATE_NOT_HEARD,
    PrivateState,
    load_private_state,
    save_private_state,
)
from agents.telegram import Reply, TelegramBot, load_telegram_state
from tests.test_private_runtime import DM, KIRA, OWNER, SECRET, KindLLM, ms, text

TOKEN = "123456789:AAH-secret-token-xyz"
OWNER_TG = 424242
STRANGER = 777


def tg(uid, body=None, sender=OWNER_TG, at=None, voice=None, chat_type="private"):
    msg = {"message_id": uid, "date": (at or ms(17)) // 1000, "from": {"id": sender},
           "chat": {"id": sender, "type": chat_type}}
    if voice is not None:
        msg["voice"] = voice
    else:
        msg["text"] = body
    return {"update_id": uid, "message": msg}


class FakeBot:
    def __init__(self):
        self.send_message = AsyncMock(return_value=True)
        self.send_voice = AsyncMock(return_value=True)
        self.send_chat_action = AsyncMock(return_value=True)
        self.get_file = AsyncMock(return_value="voice/file_1.oga")
        self.download = AsyncMock(return_value=b"OggS-owner")
        self.get_updates = AsyncMock()


class FakeTTS:
    def __init__(self, pcm=b"\x01\x00" * 24_000):
        self.pcm, self.voice_id, self.calls = pcm, "KiraVoice0123456789x", []

    async def synth(self, text):
        self.calls.append(text)
        return self.pcm


@pytest.fixture
def ogg(monkeypatch):
    async def encode(pcm, timeout_s=60.0):
        return b"OggS-kira"
    monkeypatch.setattr(agent_mod, "encode_opus", encode)


def kira(tmp_path, monkeypatch, env=True, stt=True, llm=None):
    monkeypatch.setenv("TIMEZONE", "Europe/Kyiv")
    if env:
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
        monkeypatch.setenv("TELEGRAM_OWNER_ID", str(OWNER_TG))
    if stt:
        monkeypatch.setenv("DEEPGRAM_API_KEY", "dg-secret-key")
    caps = frozenset({"canon", "summary", "voice", "world", "private", "telegram"})
    cfg = AgentConfig(**{**AgentConfig(name="Кіра", user_id=KIRA, canon="Канон.", homeserver="http://hs",
                                       room_id="!room", owner=OWNER, password="pw").__dict__, "capabilities": caps})
    agent = Agent(cfg, llm=llm or KindLLM())
    agent.private_file = tmp_path / "kira.private.json"
    agent.telegram_file = tmp_path / "kira.telegram.json"
    agent.private_room = None
    agent.client = SimpleNamespace(room_send=AsyncMock(), join=AsyncMock(), room_leave=AsyncMock(),
                                   room_typing=AsyncMock(), rooms={}, invited_rooms={})
    agent.started, agent.started_ms = True, ms(8)
    agent.clock = lambda: ms(18)
    if agent.telegram is not None:
        agent.telegram = FakeBot()
    agent.tts, agent.voice_off, agent.voice_monthly_chars = FakeTTS(), None, 1_000_000
    return agent


def run_batch(agent, *updates):
    """Feed a batch, then run the pending answer at once (no delay in a test)."""
    spawned = []
    agent._spawn = lambda coro: spawned.append(coro)
    asyncio.run(agent.on_telegram(list(updates)))
    for coro in spawned:
        coro.close()
    if spawned:
        asyncio.run(agent.private_later(0))
    return spawned


def run_matrix(agent, *events):
    spawned = []
    agent._spawn = lambda coro: spawned.append(coro)
    for e in events:
        asyncio.run(agent.on_message(SimpleNamespace(room_id=DM), e))
    for coro in spawned:
        coro.close()
    if spawned:
        asyncio.run(agent.private_later(0))
    return spawned


def texts_sent(agent):
    return [c.args[1] for c in agent.telegram.send_message.await_args_list]


def no_secret_in(caplog):
    for record in caplog.records:
        line = record.getMessage()
        assert TOKEN not in line and str(OWNER_TG) not in line and SECRET not in line and "dg-secret" not in line


# --- start-up ---------------------------------------------------------------------------------------------------------
def test_the_keys_leave_the_environment_at_start(tmp_path, monkeypatch):
    agent = kira(tmp_path, monkeypatch)
    for var in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_OWNER_ID", "DEEPGRAM_API_KEY"):
        assert var not in os.environ
    assert agent.telegram_owner == OWNER_TG and agent.stt is not None


@pytest.mark.parametrize(("token", "owner", "why"), [
    ("", "424242", "no TELEGRAM_BOT_TOKEN"),
    (TOKEN, "", "no TELEGRAM_OWNER_ID"),
    (TOKEN, "@ich", "TELEGRAM_OWNER_ID is not a number"),
])
def test_without_the_token_or_the_owners_id_telegram_is_off(tmp_path, monkeypatch, caplog, token, owner, why):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", token)
    monkeypatch.setenv("TELEGRAM_OWNER_ID", owner)
    agent = kira(tmp_path, monkeypatch, env=False)
    assert agent.telegram is None and f"telegram off: {why}" in caplog.text
    no_secret_in(caplog)


def test_without_deepgrams_key_she_cannot_listen(tmp_path, monkeypatch, caplog):
    agent = kira(tmp_path, monkeypatch, stt=False)
    assert agent.telegram is not None and agent.stt is None and "telegram: hearing off" in caplog.text
    asyncio.run(agent.on_telegram([tg(5, voice={"file_id": "F", "duration": 2})]))
    assert texts_sent(agent) == [PRIVATE_CANT_LISTEN] and agent.llm.kinds == []


def test_a_bot_without_the_capability_is_never_made(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setenv("TELEGRAM_OWNER_ID", str(OWNER_TG))
    cfg = AgentConfig(name="Ада", user_id="@ada:agora.lan", canon="К.", homeserver="http://hs", room_id="!room",
                      owner=OWNER, password="pw")
    assert Agent(cfg, llm=KindLLM()).telegram is None


# --- one private chat, two doors --------------------------------------------------------------------------------------
def test_the_owners_telegram_text_is_answered_there_in_voice_then_text(tmp_path, monkeypatch, caplog, ogg):
    caplog.set_level(logging.INFO)
    agent = kira(tmp_path, monkeypatch)
    assert len(run_batch(agent, tg(10, f"Як ти? {SECRET}"))) == 1
    bot = agent.telegram
    assert bot.send_voice.await_args.args == (OWNER_TG, b"OggS-kira", 1)       # her own voice note first
    assert texts_sent(agent) == ["Привіт, сонце."]                            # then the same words
    assert agent.tts.calls == ["Привіт, сонце."] and agent.client.room_send.await_count == 0
    assert bot.send_chat_action.await_args.args == (OWNER_TG, "record_voice")
    assert agent.llm.kinds == ["private"]
    assert agent.session[-2:] == [("Ich (наодинці)", f"Як ти? {SECRET}"), ("Кіра (наодинці)", "Привіт, сонце.")]
    assert load_private_state(agent.private_file, "").last_channel == "telegram"
    usage = [json.loads(line) for line in agent.usage_file.read_text().splitlines()]
    assert [u["kind"] for u in usage if u["kind"] == "tts"] == ["tts"]
    assert "private: answered (telegram)" in caplog.text and "voice: sent" in caplog.text
    no_secret_in(caplog)


def test_one_history_for_both_doors(tmp_path, monkeypatch, ogg):
    agent = kira(tmp_path, monkeypatch)
    agent.private_room = DM
    agent.voice_reply_p = 0.0                                                # Element's line goes as text here
    run_batch(agent, tg(10, "Сказав у телеграмі"))
    run_matrix(agent, text(OWNER, "А тепер в Element", ms(17, 5), "$m"))
    transcript = agent.llm.calls[-1][0]
    assert "Ich: Сказав у телеграмі" in transcript and "Ich: А тепер в Element" in transcript
    assert agent.client.room_send.await_args.kwargs["room_id"] == DM            # the Element answer stays there
    assert load_private_state(agent.private_file, "").last_channel == "matrix"
    assert agent.telegram.send_message.await_count == 1                       # only the Telegram answer


def test_a_pending_answer_goes_to_the_door_he_wrote_from_last(tmp_path, monkeypatch, ogg):
    agent = kira(tmp_path, monkeypatch)
    agent.private_room = DM
    spawned = []
    agent._spawn = lambda coro: spawned.append(coro)
    asyncio.run(agent.on_message(SimpleNamespace(room_id=DM), text(OWNER, "з Element", ms(17), "$a")))
    asyncio.run(agent.on_telegram([tg(11, "і з телеграму", at=ms(17, 1))]))  # coalesced into the pending answer
    for coro in spawned:
        coro.close()
    asyncio.run(agent.private_later(0))
    assert len(spawned) == 1 and agent.llm.kinds == ["private"]
    assert texts_sent(agent) == ["Привіт, сонце."] and agent.client.room_send.await_count == 0


def test_a_stranger_a_group_and_an_edit_get_nothing(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    agent = kira(tmp_path, monkeypatch)
    edit = {"update_id": 13, "edited_message": tg(13, "змінено")["message"]}
    assert run_batch(agent, tg(11, "привіт", sender=STRANGER), tg(12, "усім", chat_type="group"), edit) == []
    assert agent.telegram.send_message.await_count == 0 and agent.session == [] and agent.private_history == []
    assert "ignored: stranger (telegram text)" in caplog.text and "ignored: not-private (telegram text)" in caplog.text
    assert "ignored: edit (telegram edit)" in caplog.text
    no_secret_in(caplog)


def test_what_he_wrote_before_the_start_is_context_never_answered(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    agent = kira(tmp_path, monkeypatch)
    old = tg(9, "Поки тебе не було", at=ms(7))                               # before started_ms = 08:00
    voice = tg(10, voice={"file_id": "F"}, at=ms(7, 30))
    assert run_batch(agent, old, voice) == []
    assert agent.private_history == [("Ich", "Поки тебе не було")] and agent.session == []
    assert agent.telegram.send_message.await_count == 0 and agent.telegram.download.await_count == 0
    assert "telegram: 2 messages from before the start read as context" in caplog.text


# --- hearing a voice note ---------------------------------------------------------------------------------------------
def test_a_voice_note_is_heard_and_answered_in_voice(tmp_path, monkeypatch, caplog, ogg):
    caplog.set_level(logging.INFO)
    agent = kira(tmp_path, monkeypatch)
    agent.stt = SimpleNamespace(transcribe=AsyncMock(return_value=(f"Я вдома {SECRET}", 3200)))
    run_batch(agent, tg(20, voice={"file_id": "F9", "duration": 3, "mime_type": "audio/ogg", "file_size": 9000}))
    agent.telegram.get_file.assert_awaited_once_with("F9")
    assert agent.telegram.download.await_args.args == ("voice/file_1.oga", 20_000_000)
    assert agent.stt.transcribe.await_args.args == (b"OggS-owner", "audio/ogg")
    assert agent.private_history[0] == ("Ich", f"Я вдома {SECRET}")
    assert agent.telegram.send_voice.await_count == 1 and texts_sent(agent) == ["Привіт, сонце."]
    stt = [json.loads(line) for line in agent.usage_file.read_text().splitlines() if '"stt"' in line]
    assert len(stt) == 1 and stt[0]["audio_ms"] == 3200 and stt[0]["ok"] is True
    assert "telegram: heard (3200 ms)" in caplog.text
    no_secret_in(caplog)


@pytest.mark.parametrize(("size", "download", "heard"), [
    (9000, b"OggS", (None, 1500)),           # nothing heard
    (9000, None, None),                      # the download failed
    (30_000_000, b"OggS", None),             # over the cap: never fetched
])
def test_an_unheard_voice_note_gets_a_short_fixed_line(tmp_path, monkeypatch, size, download, heard):
    agent = kira(tmp_path, monkeypatch)
    agent.telegram.download = AsyncMock(return_value=download)
    agent.stt = SimpleNamespace(transcribe=AsyncMock(return_value=heard))
    assert run_batch(agent, tg(21, voice={"file_id": "F", "file_size": size})) == []
    assert texts_sent(agent) == [PRIVATE_NOT_HEARD] and agent.llm.kinds == [] and agent.private_history == []
    if size > 20_000_000:
        assert agent.telegram.get_file.await_count == 0


# --- the voice in Telegram ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("setup", "why"), [
    (lambda a: setattr(a, "voice_monthly_chars", 3), "monthly cap"),
    (lambda a: setattr(a, "tts", FakeTTS(pcm=None)), "tts failed"),
    (lambda a: setattr(a.telegram, "send_voice", AsyncMock(return_value=False)), "send failed"),
])
def test_when_the_voice_cannot_be_made_the_text_goes_alone(tmp_path, monkeypatch, caplog, ogg, setup, why):
    caplog.set_level(logging.INFO)
    agent = kira(tmp_path, monkeypatch)
    setup(agent)
    asyncio.run(agent.send_telegram("Добраніч."))
    assert texts_sent(agent) == ["Добраніч."] and f"voice: text only ({why}, telegram)" in caplog.text


def test_without_a_voice_she_types(tmp_path, monkeypatch):
    agent = kira(tmp_path, monkeypatch)
    agent.tts, agent.voice_off = None, "no voice id"
    run_batch(agent, tg(10, "Привіт"))
    assert agent.telegram.send_chat_action.await_args.args == (OWNER_TG, "typing")
    assert agent.telegram.send_voice.await_count == 0 and texts_sent(agent) == ["Привіт, сонце."]


# --- writing first ----------------------------------------------------------------------------------------------------
def test_she_writes_first_to_the_door_he_used_last_and_it_survives_a_restart(tmp_path, monkeypatch, ogg):
    agent = kira(tmp_path, monkeypatch)
    agent.private_room = DM
    agent.private_history, agent.last_private_ms = [("Ich", "раніше")], ms(10)
    agent.private_idle_ms, agent.private_per_day, agent.private_hours = 3_600_000, 2, (10, 22)
    save_private_state(agent.private_file, PrivateState(room=DM, day="2026-10-20", last_channel="telegram"))
    assert asyncio.run(agent.maybe_private_nudge()) is True
    assert agent.llm.kinds == ["private_nudge"] and texts_sent(agent) == ["Привіт, сонце."]
    assert agent.client.room_send.await_count == 0
    assert load_private_state(agent.private_file, "2026-10-20").last_channel == "telegram"


def test_she_writes_first_in_telegram_even_without_an_element_chat(tmp_path, monkeypatch, ogg):
    agent = kira(tmp_path, monkeypatch)
    agent.private_history, agent.last_private_ms = [("Ich", "раніше")], ms(10)
    agent.private_idle_ms, agent.private_per_day, agent.private_hours = 3_600_000, 2, (10, 22)
    assert asyncio.run(agent.maybe_private_nudge()) is True                 # last door matrix, but only Telegram is open
    assert texts_sent(agent) == ["Привіт, сонце."]


# --- the poller -------------------------------------------------------------------------------------------------------
def poll(agent, monkeypatch, *replies):
    waits = []

    async def sleep(s):
        waits.append(s)
    monkeypatch.setattr(agent_mod.asyncio, "sleep", sleep)
    agent.telegram.get_updates = AsyncMock(side_effect=list(replies))
    agent.on_telegram = AsyncMock()
    asyncio.run(agent.telegram_poll())
    return waits


def test_the_offset_is_saved_after_every_batch_and_a_refused_token_stops_the_poller(tmp_path, monkeypatch, caplog):
    agent = kira(tmp_path, monkeypatch)
    batch = [tg(30, "a"), tg(31, "b")]
    waits = poll(agent, monkeypatch, Reply(True, batch), Reply(True, []), Reply(False, status=401))
    assert agent.on_telegram.await_args.args == (batch,)
    assert load_telegram_state(agent.telegram_file).offset == 32
    assert [c.args[0] for c in agent.telegram.get_updates.await_args_list] == [None, 32, 32]
    assert waits == [] and "telegram off: refused (HTTP 401)" in caplog.text
    assert os.stat(agent.telegram_file).st_mode & 0o777 == 0o600


def test_a_429_waits_as_told_and_failures_back_off(tmp_path, monkeypatch):
    agent = kira(tmp_path, monkeypatch)
    waits = poll(agent, monkeypatch, Reply(False, status=429, retry_after=7), Reply(False, status=409),
                 Reply(False), Reply(False, status=502), Reply(True, []), Reply(False), Reply(False, status=404))
    assert waits == [7, 10, 20, 40, 5]                       # 429 as told; then 5 s doubling, reset by a good poll


def test_a_crash_in_a_batch_never_stops_the_poller(tmp_path, monkeypatch, caplog):
    agent = kira(tmp_path, monkeypatch)
    waits = []

    async def sleep(s):
        waits.append(s)
    monkeypatch.setattr(agent_mod.asyncio, "sleep", sleep)
    agent.telegram.get_updates = AsyncMock(side_effect=[Reply(True, [tg(40, "x")]), Reply(False, status=401)])
    agent.on_telegram = AsyncMock(side_effect=RuntimeError("boom"))
    asyncio.run(agent.telegram_poll())
    assert waits == [5] and "telegram: poll failed" in caplog.text


def test_the_bot_is_the_real_client_in_production(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setenv("TELEGRAM_OWNER_ID", str(OWNER_TG))
    caps = frozenset({"canon", "private", "telegram"})
    cfg = AgentConfig(name="Кіра", user_id=KIRA, canon="К.", homeserver="http://hs", room_id="!room", owner=OWNER,
                      password="pw", capabilities=caps)
    assert isinstance(Agent(cfg, llm=KindLLM()).telegram, TelegramBot)
