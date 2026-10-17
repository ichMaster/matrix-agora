"""v5.1 — the voice: ElevenLabs TTS (aiohttp mocked), Opus through ffmpeg (the subprocess mocked), the duration,
the waveform and the voice-message content."""

import asyncio
import logging
import math
import shutil
import struct
from typing import ClassVar

import pytest

from agents import voice
from agents.voice import (
    FFMPEG,
    TTS_MODEL,
    ElevenLabsTTS,
    duration_ms,
    encode_opus,
    voice_content,
    waveform,
)

KEY = "sk-secret-key-0123456789"
VOICE = "AbCdEfGhIj0123456789"


class FakeResponse:
    def __init__(self, status, body):
        self.status, self.body = status, body

    async def read(self):
        return self.body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class FakeSession:
    seen: ClassVar[dict] = {}
    reply = (200, b"\x01\x00\x02\x00")
    fail: Exception | None = None

    def __init__(self, timeout=None):
        FakeSession.seen["timeout"] = timeout

    async def __aenter__(self):
        if FakeSession.fail:
            raise FakeSession.fail
        return self

    async def __aexit__(self, *a):
        return False

    def post(self, url, json=None, headers=None):
        FakeSession.seen.update(url=url, json=json, headers=headers)
        return FakeResponse(*FakeSession.reply)


@pytest.fixture
def session(monkeypatch):
    FakeSession.seen, FakeSession.reply, FakeSession.fail = {}, (200, b"\x01\x00\x02\x00\x03"), None
    monkeypatch.setattr(voice.aiohttp, "ClientSession", FakeSession)
    return FakeSession


def test_the_request_asks_for_ukrainian_pcm_in_the_turbo_model(session, caplog):
    caplog.set_level(logging.DEBUG)
    pcm = asyncio.run(ElevenLabsTTS(KEY, VOICE).synth("Вітаю, смертний!"))
    assert pcm == b"\x01\x00\x02\x00"  # an odd trailing byte is dropped
    seen = session.seen
    assert seen["url"] == f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE}?output_format=pcm_24000"
    assert seen["headers"]["xi-api-key"] == KEY
    assert TTS_MODEL == "eleven_turbo_v2_5"
    assert seen["json"] == {"text": "Вітаю, смертний!", "model_id": "eleven_turbo_v2_5", "language_code": "uk",
                            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "style": 0.4}}
    assert seen["timeout"].total == 60
    assert all(KEY not in r.getMessage() and "смертний" not in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("reply,fail,why", [
    ((401, b"denied"), None, "HTTP 401"), ((200, b""), None, "no audio"), (None, OSError("down"), "OSError"),
])
def test_a_failed_request_is_none_logged_without_the_key(session, caplog, reply, fail, why):
    if reply:
        session.reply = reply
    session.fail = fail
    assert asyncio.run(ElevenLabsTTS(KEY, VOICE).synth("текст")) is None
    assert why in caplog.text and KEY not in caplog.text and "текст" not in caplog.text


def test_a_malformed_voice_id_never_reaches_the_network(session):
    assert asyncio.run(ElevenLabsTTS(KEY, "../../admin").synth("текст")) is None
    assert "url" not in session.seen


# --- ffmpeg ---------------------------------------------------------------------------------------------------------
class FakeProc:
    def __init__(self, code, out):
        self.returncode, self.out, self.input = code, out, None

    async def communicate(self, input=None):
        self.input = input
        return self.out, b""


def test_the_encode_runs_the_fixed_argv(monkeypatch):
    seen = {}

    async def fake_exec(*argv, **kw):
        seen["argv"] = argv
        seen["proc"] = FakeProc(0, b"OggS...")
        return seen["proc"]

    monkeypatch.setattr(voice.asyncio, "create_subprocess_exec", fake_exec)
    assert asyncio.run(encode_opus(b"\x00\x00" * 10)) == b"OggS..."
    assert seen["argv"] == FFMPEG and seen["proc"].input == b"\x00\x00" * 10
    assert FFMPEG[FFMPEG.index("-c:a") + 1] == "libopus" and FFMPEG[-3:] == ("-f", "ogg", "pipe:1")


@pytest.mark.parametrize("code,out", [(1, b""), (0, b"")])
def test_a_failed_encode_is_none(monkeypatch, caplog, code, out):
    async def fake_exec(*argv, **kw):
        return FakeProc(code, out)

    monkeypatch.setattr(voice.asyncio, "create_subprocess_exec", fake_exec)
    assert asyncio.run(encode_opus(b"\x00\x00")) is None
    assert f"ffmpeg exit {code}" in caplog.text


def test_no_ffmpeg_is_none(monkeypatch):
    async def missing(*argv, **kw):
        raise FileNotFoundError("ffmpeg")

    monkeypatch.setattr(voice.asyncio, "create_subprocess_exec", missing)
    assert asyncio.run(encode_opus(b"\x00\x00")) is None


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed here (the image has it)")
def test_a_real_encode_makes_ogg():
    pcm = b"".join(struct.pack("<h", int(8000 * math.sin(i / 10))) for i in range(24_000))
    out = asyncio.run(encode_opus(pcm))
    assert out is not None and out.startswith(b"OggS") and b"OpusHead" in out


# --- duration, waveform, content -----------------------------------------------------------------------------------
def test_duration_and_waveform():
    second = struct.pack("<h", 0) * 12_000 + struct.pack("<h", -16000) * 12_000  # quiet half, loud half
    assert duration_ms(second) == 1000 and duration_ms(b"") == 0
    wave = waveform(second)
    assert len(wave) == 100 and all(0 <= v <= 1024 for v in wave)
    assert wave[:50] == [0] * 50 and wave[50:] == [1024] * 50
    assert waveform(b"\x00\x00" * 500) == [0] * 100 and waveform(b"") == [0] * 100
    assert len(waveform(b"\x10\x00" * 7)) == 100  # fewer samples than points


def test_the_voice_message_content():
    c = voice_content("mxc://agora.lan/abc", 4096, 61_500, [1, 2], "Вісті з Агори.", "hermes-20261017-1405.ogg")
    assert c["msgtype"] == "m.audio" and c["body"] == "Вісті з Агори." and c["url"] == "mxc://agora.lan/abc"
    assert c["info"] == {"mimetype": "audio/ogg", "size": 4096, "duration": 61_500}
    assert c["org.matrix.msc1767.audio"] == {"duration": 61_500, "waveform": [1, 2]}
    assert c["org.matrix.msc3245.voice"] == {} and c["org.matrix.msc1767.text"] == "Вісті з Агори."
    assert c["filename"] == "hermes-20261017-1405.ogg"
