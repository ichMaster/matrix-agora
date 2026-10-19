"""v5.3 — the agents answer in voice: every line goes through `send_line` — in the agent's own voice first when it
should and can, a reply to the owner's voice it answers, then always the same text (TTS, ffmpeg and the upload
mocked; the usage files in a temporary state/)."""

import asyncio
import json
import logging
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from nio import UploadResponse

from agents import speech as speech_mod
from tests.test_first_sync import FakeLLM, make_agent, run_with_tasks
from tests.test_transcripts import OWNER, ROOM, transcript, voice_event

KEY = "sk-voice-key-0123456789"
SECRET = "НЕВИМОВНЕ-СЛОВО"


class FakeTTS:
    def __init__(self, ok=True):
        self.ok, self.texts = ok, []

    async def synth(self, text):
        self.texts.append(text)
        return b"\x10\x00\x20\x00" * 2400 if self.ok else None


async def fake_encode(pcm):
    return b"OggS" + pcm[:8]


def voiced_agent(tmp_path, monkeypatch, voice_id="AdaVoice0123456789", key=KEY, p="1.0", cap="50000", llm=None):
    monkeypatch.setenv("VOICE_ID", voice_id)
    monkeypatch.setenv("VOICE_REPLY_P", p)
    monkeypatch.setenv("VOICE_MONTHLY_CHARS", cap)
    if key:
        monkeypatch.setenv("ELEVENLABS_API_KEY", key)
    else:
        monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.setattr(speech_mod, "encode_opus", fake_encode)
    agent = make_agent(llm)
    agent.memory_file = tmp_path / "ada.memory.md"                 # its usage file and the budget read here
    agent.client.upload = AsyncMock(return_value=(UploadResponse(content_uri="mxc://agora.lan/ada"), None))
    if agent.tts is not None:
        agent.tts = FakeTTS()
    agent.started = True
    agent.rng = lambda: 0.0
    return agent


def sent(agent):
    return [c.kwargs["content"] for c in agent.client.room_send.await_args_list]


def test_the_key_never_stays_in_the_environment(tmp_path, monkeypatch):
    """Claude's CLI inherits the environment: the key is out of it before the responder exists."""
    agent = voiced_agent(tmp_path, monkeypatch)
    assert "ELEVENLABS_API_KEY" not in os.environ and agent.tts is not None


def test_an_answer_to_the_owners_voice_is_a_labelled_voice_then_its_text(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    agent = voiced_agent(tmp_path, monkeypatch, p="0.0", llm=FakeLLM(f"Привіт, Ich! {SECRET}"))
    asyncio.run(agent.on_audio(ROOM, voice_event(OWNER, "$voice")))
    asyncio.run(run_with_tasks(agent, ROOM, transcript("Адо, як ти?", eid="$tr")))
    audio, text = sent(agent)                                          # the iPhone shows no caption (2026-10-18)
    assert audio["msgtype"] == "m.audio" and audio["org.matrix.msc3245.voice"] == {}
    assert "m.relates_to" not in audio and "m.relates_to" not in text  # never a reply
    assert audio["body"] == "Голосове повідомлення" and "filename" not in audio   # a label: the words only once
    assert text == {"msgtype": "m.text", "body": f"Привіт, Ich! {SECRET}"}
    usage = json.loads((tmp_path / "ada.usage.jsonl").read_text().splitlines()[-1])
    assert (usage["kind"], usage["characters"]) == ("tts", len(text["body"]))
    assert all(SECRET not in r.getMessage() for r in caplog.records) and "voice: sent" in caplog.text


@pytest.mark.parametrize("p,voiced", [("0.0", False), ("1.0", True)])
def test_a_typed_question_is_voiced_by_the_share(tmp_path, monkeypatch, p, voiced):
    agent = voiced_agent(tmp_path, monkeypatch, p=p)
    room, event = SimpleNamespace(room_id="!room"), SimpleNamespace(sender=OWNER, body="Адо, як ти?",
                                                                     event_id="$typed", server_timestamp=1)
    asyncio.run(run_with_tasks(agent, room, event))
    kinds = [c["msgtype"] for c in sent(agent)]
    assert kinds == (["m.audio", "m.text"] if voiced else ["m.text"])
    if voiced:
        assert "m.relates_to" not in sent(agent)[0]                    # not an answer to a voice


@pytest.mark.parametrize("case,why", [
    ("no voice id", "no voice id"), ("no key", "no ELEVENLABS_API_KEY"), ("bad id", "voice id malformed"),
    ("tts fails", "tts failed"), ("cap", "monthly cap"),
])
def test_without_a_voice_the_line_goes_out_as_text(tmp_path, monkeypatch, caplog, case, why):
    caplog.set_level(logging.INFO)
    kw = {"no voice id": {"voice_id": ""}, "no key": {"key": ""}, "bad id": {"voice_id": "short"},
          "cap": {"cap": "10"}}.get(case, {})
    agent = voiced_agent(tmp_path, monkeypatch, **kw)
    if case == "tts fails":
        agent.tts = FakeTTS(ok=False)
    asyncio.run(agent.send_line("!room", "Мені добре, дякую.", "$e"))
    assert [c["msgtype"] for c in sent(agent)] == ["m.text"] and why in caplog.text


def test_the_budget_counts_every_speaker_but_the_herald(tmp_path, monkeypatch):
    from agents.usage import tts_usage_line
    agent = voiced_agent(tmp_path, monkeypatch, cap="1000")
    month = "2026-10-18T10:00:00+03:00"
    (tmp_path / "bruno.usage.jsonl").write_text(json.dumps(tts_usage_line(month, "bruno", "m", 990, True)) + "\n")
    (tmp_path / "hermes.usage.jsonl").write_text(json.dumps(tts_usage_line(month, "hermes", "m", 90000, True)) + "\n")
    agent.clock = lambda: 1_792_310_400_000                             # 2026-10-18 (Kyiv)
    asyncio.run(agent.send_line("!room", "Привіт.", "$e"))             # 990 + 7 ≤ 1000: Hermes not counted
    assert [c["msgtype"] for c in sent(agent)] == ["m.audio", "m.text"]
    agent.client.room_send.reset_mock()
    asyncio.run(agent.send_line("!room", "Ще одне довше речення.", "$f"))  # its own 7 chars now count too
    assert [c["msgtype"] for c in sent(agent)] == ["m.text"]


def test_pass_and_the_checks_still_mean_nothing_at_all(tmp_path, monkeypatch):
    agent = voiced_agent(tmp_path, monkeypatch, llm=FakeLLM("PASS"))
    room, event = SimpleNamespace(room_id="!room"), SimpleNamespace(sender=OWNER, body="Адо?", event_id="$q",
                                                                     server_timestamp=1)
    asyncio.run(run_with_tasks(agent, room, event))
    assert sent(agent) == [] and agent.tts.texts == []


@pytest.mark.parametrize("purr,kinds", [("Мрррр.", ["m.audio", "m.text"]), ("*потягується*", ["m.text"])])
def test_the_cat_may_purr_aloud_but_never_reads_an_action(tmp_path, monkeypatch, purr, kinds):
    agent = voiced_agent(tmp_path, monkeypatch)
    asyncio.run(agent.send_line("!room", purr, "$e", answering="$e"))
    assert [c["msgtype"] for c in sent(agent)] == kinds


def test_a_failed_voice_send_still_sends_the_text(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    agent = voiced_agent(tmp_path, monkeypatch)
    calls = []

    async def flaky(**kw):
        calls.append(kw["content"]["msgtype"])
        if kw["content"]["msgtype"] == "m.audio":
            raise ConnectionError("gone")

    agent.client.room_send = flaky
    asyncio.run(agent.send_line("!room", "Привіт.", "$e"))
    assert calls == ["m.audio", "m.text"] and "voice: text only (send failed (ConnectionError))" in caplog.text



def test_every_speaker_reads_a_members_voiced_line_by_its_caption(tmp_path, monkeypatch):
    """The voice-only lines already in the room (2026-10-18, 21:08 until the switch back): Bruno's captioned voice
    is, for Ada, Bruno's line — her history, her turn rules — on a restart too; a labelled voice is nothing (its
    text follows as its own message)."""
    from nio import RoomMessage

    def member_voice(sender, eid, body, filename="bruno-1.ogg"):
        content = {"msgtype": "m.audio", "body": body, "url": "mxc://agora.lan/b", "org.matrix.msc3245.voice": {},
                   "info": {"mimetype": "audio/ogg", "size": 10, "duration": 900}}
        if filename:
            content["filename"] = filename
        return RoomMessage.parse_event({"event_id": eid, "sender": sender, "origin_server_ts": 5_000,
                                        "type": "m.room.message", "content": content})

    agent = voiced_agent(tmp_path, monkeypatch, p="0.0")
    asyncio.run(agent.on_audio(ROOM, member_voice("@bruno:agora.lan", "$b1", "Адо, а ти що читаєш?")))
    assert agent.history[-1] == ("Бруно", "Адо, а ти що читаєш?") and agent.timeline[-1][2] == "$b1"
    asyncio.run(agent.on_audio(ROOM, member_voice("@bruno:agora.lan", "$b2", "Голосове повідомлення", filename=None)))
    assert agent.history[-1] == ("Бруно", "Адо, а ти що читаєш?")      # a plain voice carries no line
    seeded = make_agent()
    assert seeded.seed_context([member_voice("@bruno:agora.lan", "$b3", "Привіт усім.")]) == 1
    assert seeded.history == [("Бруно", "Привіт усім.")]
