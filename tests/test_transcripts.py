"""v5.2 — one transcript, shared by every agent: Hermes's «🎙 Ich: …» reply to the owner's voice event is, for every
speaker, the owner's own line — the speaker Ich, the transcript's event id; R1, the fallback, the session and the
backfill apply as to a typed message. The audio itself is never answered."""

import asyncio
import logging
from types import SimpleNamespace

from nio import RoomMessage

from agents.logic import TRANSCRIPT_PREFIX, replied_to, transcript_content, transcript_of
from tests.test_first_sync import make_agent, run_with_tasks

OWNER, HERMES, ADA = "@ich:agora.lan", "@hermes:agora.lan", "@ada:agora.lan"
ROOM = SimpleNamespace(room_id="!room")


def text_event(sender, body, eid, ts=1_000, content_extra=None):
    content = {"msgtype": "m.text", "body": body, **(content_extra or {})}
    return RoomMessage.parse_event({"event_id": eid, "sender": sender, "origin_server_ts": ts,
                                    "type": "m.room.message", "content": content})


def voice_event(sender, eid, ts=900):
    return RoomMessage.parse_event({"event_id": eid, "sender": sender, "origin_server_ts": ts, "type": "m.room.message",
                                    "content": {"msgtype": "m.audio", "body": "Voice message",
                                                "url": "mxc://agora.lan/v", "org.matrix.msc3245.voice": {},
                                                "info": {"mimetype": "audio/ogg", "size": 9000, "duration": 2000}}})


def transcript(text, voice="$voice", eid="$tr", sender=HERMES, ts=1_000):
    content = transcript_content(voice, text)
    return text_event(sender, content["body"], eid, ts, {"m.relates_to": content["m.relates_to"]})


# --- the rule (pure) ------------------------------------------------------------------------------------------------
def test_the_transcript_content_is_a_prefixed_reply_to_the_voice():
    c = transcript_content("$voice", "Адо, привіт")
    assert c == {"msgtype": "m.text", "body": "🎙 Ich: Адо, привіт",
                 "m.relates_to": {"m.in_reply_to": {"event_id": "$voice"}}}
    assert TRANSCRIPT_PREFIX == "🎙 Ich: " and replied_to(transcript("x")) == "$voice"


def test_only_the_transcribers_prefixed_reply_to_a_seen_owner_voice_counts():
    voices = ["$voice"]
    assert transcript_of(transcript("Адо, привіт"), HERMES, voices) == "Адо, привіт"
    assert transcript_of(transcript("x", sender=ADA), HERMES, voices) is None              # another sender
    assert transcript_of(transcript("x", voice="$other"), HERMES, voices) is None          # a voice not seen
    assert transcript_of(transcript("x"), None, voices) is None                            # no transcriber
    assert transcript_of(text_event(HERMES, "Адо, привіт", "$t", content_extra={
        "m.relates_to": {"m.in_reply_to": {"event_id": "$voice"}}}), HERMES, voices) is None  # no prefix
    edit = text_event(HERMES, "* 🎙 Ich: x", "$e", content_extra={"m.relates_to": {"rel_type": "m.replace",
                                                                                   "event_id": "$tr"}})
    assert transcript_of(edit, HERMES, voices) is None
    assert transcript_of(transcript("   "), HERMES, voices) is None                         # nothing heard


# --- the speakers ---------------------------------------------------------------------------------------------------
def started_agent():
    agent = make_agent()
    agent.started = True
    agent.rng = lambda: 0.0
    return agent


def test_the_owners_voice_is_never_answered_but_remembered(caplog):
    caplog.set_level(logging.INFO)
    agent = started_agent()
    asyncio.run(agent.on_audio(ROOM, voice_event(OWNER, "$voice")))
    asyncio.run(agent.on_audio(ROOM, voice_event(ADA, "$ada-voice")))
    asyncio.run(agent.on_audio(SimpleNamespace(room_id="!dm"), voice_event(OWNER, "$dm-voice")))
    assert agent.owner_voices == ["$voice"] and agent.transcriber == HERMES
    agent.client.room_send.assert_not_awaited()
    assert "ignored: audio (transcribed by Hermes)" in caplog.text
    assert caplog.text.count("ignored: audio") == 2                      # v5.3: a member's voice is never logged


def test_a_transcript_is_the_owners_message_named_or_not():
    agent = started_agent()
    asyncio.run(agent.on_audio(ROOM, voice_event(OWNER, "$voice")))
    asyncio.run(run_with_tasks(agent, ROOM, transcript("Адо, як ти?", eid="$tr")))
    agent.client.room_send.assert_awaited_once()                   # named → Ada answers, as to typed words
    assert agent.history[-1] == ("Ich", "Адо, як ти?")
    assert agent.last_owner == ("$tr", "Адо, як ти?")              # the transcript's event id
    assert agent.timeline[-1][:3] == ("Ich", 1_000, "$tr")
    assert ("Ich", "Адо, як ти?") in agent.session                  # the journal and the memories read it as his
    typed = started_agent()
    unnamed = transcript("що нового?", voice="$v2", eid="$tr2")
    agent.owner_voices.append("$v2")
    assert agent.decide(OWNER, "що нового?", "$tr2", 2_000) == typed.decide(OWNER, "що нового?", "$tr2", 2_000)
    asyncio.run(agent.on_message(ROOM, unnamed))
    assert agent.history[-1] == ("Ich", "що нового?")


def test_any_other_line_from_hermes_stays_unallowlisted(caplog):
    caplog.set_level(logging.INFO)
    agent = started_agent()
    asyncio.run(run_with_tasks(agent, ROOM, transcript("Адо, привіт", voice="$never-seen")))
    agent.client.room_send.assert_not_awaited()
    assert "ignored: sender-not-allowlisted" in caplog.text
    assert agent.history[-1] == ("Гермес", "🎙 Ich: Адо, привіт")     # seen as his, never as the owner's


def test_a_restart_seeds_a_transcript_as_the_owners_line():
    agent = make_agent()
    newest_first = [transcript("Адо, привіт", eid="$tr", ts=1_000), voice_event(OWNER, "$voice", ts=900),
                    text_event(ADA, "раніше", "$a", ts=800)]
    assert agent.seed_context(newest_first) == 2
    assert agent.history == [("Ада", "раніше"), ("Ich", "Адо, привіт")]
    assert agent.last_owner == ("$tr", "Адо, привіт") and agent.owner_voices == ["$voice"]
