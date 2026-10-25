"""v5.7 — Кіра in Telegram: the Bot API client (aiohttp mocked), the update parsing, the allowlist and the offset
state. No test reaches the network, and no log line carries the token, an id or a word."""

import asyncio
import json
import logging
import os
from typing import ClassVar

import pytest

from agents import telegram
from agents.telegram import (
    TEXT_MAX,
    TelegramBot,
    TelegramState,
    Update,
    allowed,
    fit_text,
    load_telegram_state,
    next_offset,
    parse_update,
    save_telegram_state,
)

TOKEN = "123456789:AAH-secret-token-xyz"
OWNER = 424242
STRANGER = 777


def message(uid=1, sender=OWNER, chat_type="private", **fields):
    return {"update_id": uid, "message": {"message_id": 9, "date": 1_761_400_000,
                                          "from": {"id": sender, "is_bot": False},
                                          "chat": {"id": sender, "type": chat_type}, **fields}}


# --- parsing ---------------------------------------------------------------------------------------------------------

def test_a_text_message_is_parsed():
    u = parse_update(message(5, text="Привіт"))
    assert u == Update(5, OWNER, OWNER, "private", 1_761_400_000_000, "text", text="Привіт")


def test_a_voice_note_is_parsed():
    u = parse_update(message(6, voice={"file_id": "F1", "duration": 4, "mime_type": "audio/ogg", "file_size": 9000}))
    assert (u.kind, u.file_id, u.duration_s, u.mime, u.file_size) == ("voice", "F1", 4, "audio/ogg", 9000)


def test_an_edit_a_sticker_and_another_update_type():
    edit = {"update_id": 7, "edited_message": message(text="x")["message"]}
    assert parse_update(edit).kind == "edit"
    assert parse_update(message(8, sticker={"file_id": "S"})).kind == "other"
    assert parse_update({"update_id": 9, "channel_post": {"text": "x"}}).kind == "other"


@pytest.mark.parametrize("raw", [None, [], "x", {}, {"update_id": "1"}, {"message": {}}])
def test_malformed_updates_are_none(raw):
    assert parse_update(raw) is None


def test_odd_fields_never_break_the_parse():
    raw = {"update_id": 3, "message": {"from": "x", "chat": [], "date": "now", "voice": {"file_id": 5}}}
    u = parse_update(raw)
    assert (u.sender, u.chat_id, u.chat_type, u.date_ms, u.kind) == (None, None, "", 0, "other")


# --- the allowlist ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize(("raw", "verdict"), [
    (message(text="hi"), (True, "ok")),
    (message(voice={"file_id": "F"}), (True, "ok")),
    (message(sender=STRANGER, text="hi"), (False, "stranger")),
    (message(chat_type="group", text="hi"), (False, "not-private")),
    (message(sender=STRANGER, chat_type="supergroup", text="hi"), (False, "not-private")),
    ({"update_id": 2, "edited_message": message(text="x")["message"]}, (False, "edit")),
    (message(sticker={"file_id": "S"}), (False, "unsupported")),
    (message(text="/start"), (False, "command")),                # review #6: a bot's word never reaches her prompt
    (message(text="  /help me"), (False, "command")),
    (message(text="а/б тест"), (True, "ok")),
    ({"update_id": 4, "channel_post": {"text": "x"}}, (False, "not-private")),
])
def test_only_the_owners_private_text_or_voice_is_handled(raw, verdict):
    v = allowed(parse_update(raw), OWNER)
    assert (v.handle, v.reason) == verdict


# --- the offset ------------------------------------------------------------------------------------------------------

def test_the_next_offset_confirms_the_whole_batch():
    assert next_offset([{"update_id": 10}, {"update_id": 12}, {"bad": 1}], 3) == 13
    assert next_offset([], 3) == 3
    assert next_offset([], None) is None


def test_the_offset_survives_a_restart_privately(tmp_path):
    path = tmp_path / "kira.telegram.json"
    assert load_telegram_state(path) == TelegramState()  # the first start
    save_telegram_state(path, TelegramState(42))
    assert load_telegram_state(path).offset == 42
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert json.loads(path.read_text()) == {"offset": 42}  # no text, no token, no id


@pytest.mark.parametrize("body", ["{", "[]", '{"offset": "x"}'])
def test_a_corrupt_state_starts_fresh(tmp_path, body):
    path = tmp_path / "kira.telegram.json"
    path.write_text(body)
    assert load_telegram_state(path) == TelegramState()


# --- one message's text ----------------------------------------------------------------------------------------------

def test_a_long_text_is_cut_at_a_sentence():
    assert fit_text("Коротко.") == "Коротко."
    long = ("Речення тут. " * 400).strip()
    cut = fit_text(long)
    assert len(cut) <= TEXT_MAX and cut.endswith(".")
    assert fit_text("а" * 5000) == "а" * TEXT_MAX  # no sentence: cut at the limit


# --- the client (aiohttp mocked) -------------------------------------------------------------------------------------

class FakeContent:
    def __init__(self, body):
        self.body = body

    async def iter_chunked(self, n):
        for i in range(0, len(self.body), n):
            yield self.body[i:i + n]


class FakeResponse:
    def __init__(self, status, body, length=None):
        self.status, self.body = status, body
        self.content_length = length
        self.content = FakeContent(body if isinstance(body, bytes) else b"")

    async def json(self, content_type=None):
        if isinstance(self.body, bytes):
            raise ValueError("not json")
        return self.body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class FakeSession:
    calls: ClassVar[list] = []
    replies: ClassVar[list] = []
    fail: Exception | None = None

    def __init__(self, timeout=None):
        self.timeout = timeout

    async def __aenter__(self):
        if FakeSession.fail:
            raise FakeSession.fail
        return self

    async def __aexit__(self, *a):
        return False

    def post(self, url, json=None, data=None):
        FakeSession.calls.append({"url": url, "json": json, "data": data, "timeout": self.timeout})
        return FakeResponse(*FakeSession.replies.pop(0))

    def get(self, url):
        FakeSession.calls.append({"url": url, "timeout": self.timeout})
        return FakeResponse(*FakeSession.replies.pop(0))


@pytest.fixture
def session(monkeypatch):
    FakeSession.calls, FakeSession.replies, FakeSession.fail = [], [], None
    monkeypatch.setattr(telegram.aiohttp, "ClientSession", FakeSession)
    return FakeSession


def ok(result):
    return (200, {"ok": True, "result": result})


def no_secret_in(caplog):
    for record in caplog.records:
        line = record.getMessage()
        assert TOKEN not in line and "AAH-secret" not in line and str(OWNER) not in line and "Привіт" not in line


def test_get_updates_long_polls_from_the_offset(session, caplog):
    caplog.set_level(logging.DEBUG)
    session.replies = [ok([message(10, text="Привіт")])]
    reply = asyncio.run(TelegramBot(TOKEN).get_updates(10))
    assert reply.ok and reply.result[0]["update_id"] == 10
    call = session.calls[0]
    assert call["url"] == f"https://api.telegram.org/bot{TOKEN}/getUpdates"
    assert call["json"] == {"timeout": 30, "allowed_updates": ["message", "edited_message"], "offset": 10}
    assert call["timeout"].total == 40
    no_secret_in(caplog)


def test_the_first_poll_has_no_offset(session):
    session.replies = [ok([])]
    asyncio.run(TelegramBot(TOKEN).get_updates(None))
    assert "offset" not in session.calls[0]["json"]


def test_send_message_is_plain_text_cut_to_one_message(session):
    session.replies = [ok({"message_id": 1})]
    assert asyncio.run(TelegramBot(TOKEN).send_message(OWNER, "Речення. " * 1000)) is True
    body = session.calls[0]["json"]
    assert set(body) == {"chat_id", "text"} and body["chat_id"] == OWNER and len(body["text"]) <= TEXT_MAX


def test_send_voice_is_a_multipart_ogg_voice_note(session):
    session.replies = [ok({"message_id": 2})]
    assert asyncio.run(TelegramBot(TOKEN).send_voice(OWNER, b"OggS-bytes", 3)) is True
    call = session.calls[0]
    assert call["url"].endswith("/sendVoice")
    fields = {opts["name"]: (headers, value) for opts, headers, value in call["data"]._fields}
    assert fields["chat_id"][1] == str(OWNER) and fields["duration"][1] == "3"
    headers, value = fields["voice"]
    assert value == b"OggS-bytes" and headers["Content-Type"] == "audio/ogg"


def test_a_chat_action_and_a_file_path(session):
    session.replies = [ok(True), ok({"file_id": "F", "file_path": "voice/file_7.oga"})]
    bot = TelegramBot(TOKEN)
    assert asyncio.run(bot.send_chat_action(OWNER, "record_voice")) is True
    assert session.calls[0]["json"] == {"chat_id": OWNER, "action": "record_voice"}
    assert asyncio.run(bot.get_file("F")) == "voice/file_7.oga"


def test_a_download_is_read_whole_under_the_cap(session):
    session.replies = [(200, b"a" * 200_000, 200_000)]
    assert asyncio.run(TelegramBot(TOKEN).download("voice/f.oga", 1_000_000)) == b"a" * 200_000
    assert session.calls[0]["url"] == f"https://api.telegram.org/file/bot{TOKEN}/voice/f.oga"


@pytest.mark.parametrize("length", [2_000_000, None])
def test_a_download_over_the_cap_is_refused(session, caplog, length):
    session.replies = [(200, b"a" * 2_000_000, length)]
    assert asyncio.run(TelegramBot(TOKEN).download("voice/f.oga", 1_000_000)) is None
    assert "over the cap" in caplog.text
    no_secret_in(caplog)


@pytest.mark.parametrize(("reply", "status", "retry"), [
    ((401, {"ok": False, "error_code": 401, "description": "Unauthorized"}), 401, None),
    ((409, {"ok": False, "error_code": 409, "description": "Conflict: another getUpdates"}), 409, None),
    ((429, {"ok": False, "error_code": 429, "parameters": {"retry_after": 7}}), 429, 7),
    ((502, b"<html>bad gateway</html>"), 502, None),
    ((200, {"ok": True, "result": "not a list"}), None, None),
])
def test_a_failed_poll_carries_its_status_and_wait(session, caplog, reply, status, retry):
    session.replies = [reply]
    got = asyncio.run(TelegramBot(TOKEN).get_updates(1))
    assert (got.ok, got.status, got.retry_after) == (False, status, retry)
    no_secret_in(caplog)
    assert "Unauthorized" not in caplog.text and "Conflict" not in caplog.text  # Telegram's text is never logged


def test_a_network_failure_is_named_by_its_type_only(session, caplog):
    session.fail = OSError(f"cannot connect to https://api.telegram.org/bot{TOKEN}/getUpdates")
    bot = TelegramBot(TOKEN)
    assert asyncio.run(bot.get_updates(1)).ok is False
    assert asyncio.run(bot.send_message(OWNER, "Привіт")) is False
    assert asyncio.run(bot.send_voice(OWNER, b"x", 1)) is False
    assert asyncio.run(bot.get_file("F")) is None
    assert asyncio.run(bot.download("voice/f.oga", 10)) is None
    assert "OSError" in caplog.text
    no_secret_in(caplog)


def test_the_bot_never_shows_its_token():
    bot = TelegramBot(TOKEN)
    assert TOKEN not in repr(bot) and TOKEN not in str(bot)
