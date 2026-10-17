"""v5.1 — Hermes's runtime: the private room, the schedule, «підсумок», questions, silence in Agora. nio, Gemini, the
TTS, ffmpeg and the upload are mocked; the clock is injected; nothing touches the network."""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from nio import RoomCreateResponse, RoomMessage, RoomSendResponse, UploadResponse

from agents import herald as herald_mod
from agents.config import AgentConfig
from agents.digest import NOTHING_NEW, DigestState, load_digest_state, save_digest_state
from agents.herald import NOTHING_RECENT, Herald, needs_private_room, route
from agents.roster import TYPES, load_member, load_roster

TZ = "Europe/Kyiv"
OWNER, ADA, BRUNO, KIT = "@ich:agora.lan", "@ada:agora.lan", "@bruno:agora.lan", "@kit:agora.lan"
AGORA = "!agora:agora.lan"
SECRET = "НЕВИМОВНЕ-СЛОВО"  # a sentinel: no room, digest or answer text may reach a log
CFG = AgentConfig(name="Гермес", user_id="@hermes:agora.lan", canon="КАНОН ГЕРМЕСА", homeserver="http://hs",
                  room_id=AGORA, owner=OWNER, password="pw", type="herald", capabilities=TYPES["herald"])
ROSTER = {**load_roster("agora"), "hermes": load_member(Path("agents/hermes.toml"))}


def ms(hour: int, minute: int = 0, day: int = 17) -> int:
    return int(datetime(2026, 10, day, hour, minute, tzinfo=ZoneInfo(TZ)).timestamp() * 1000)


def ev(sender, body, ts, eid=None):
    return RoomMessage.parse_event({"event_id": eid or f"$e{ts}", "sender": sender, "origin_server_ts": ts,
                                    "type": "m.room.message", "content": {"msgtype": "m.text", "body": body}})


class FakeClient:
    def __init__(self, events_newest_first=()):
        self.events = list(events_newest_first)
        self.rooms: dict = {}
        self.invited_rooms: dict = {}
        self.next_batch = "s1"
        self.sent: list = []
        self.typing: list = []
        self.created: list = []
        self.uploads: list = []
        self.left: list = []

    async def room_create(self, **kw):
        self.created.append(kw)
        return RoomCreateResponse(room_id=f"!dm{len(self.created)}:agora.lan")

    async def room_send(self, room, type_, content):
        self.sent.append((room, content))
        return RoomSendResponse(event_id=f"$s{len(self.sent)}", room_id=room)

    async def room_typing(self, room, on):
        self.typing.append((room, on))

    async def room_messages(self, room_id, start=None, direction=None, limit=100):
        assert room_id == AGORA
        page = 0 if start == "s1" else int(start[1:])
        chunk = self.events[page * limit:(page + 1) * limit]
        return SimpleNamespace(chunk=chunk, end=f"p{page + 1}")

    async def upload(self, data, content_type=None, filename=None, filesize=None):
        self.uploads.append((content_type, filename, filesize, data.read()))
        return UploadResponse(content_uri="mxc://agora.lan/voice"), None

    async def room_leave(self, room_id):
        self.left.append(room_id)


class FakeLLM:
    def __init__(self, *texts):
        self.texts = list(texts) or ["Вісті з Олімпу. Ада сперечалась із Бруно."]
        self.calls = []

    async def think(self, contents, system_instruction, model=None, max_output_tokens=None, kind="digest_voice"):
        self.calls.append(SimpleNamespace(contents=contents, system=system_instruction, model=model, kind=kind))
        return self.texts.pop(0) if self.texts else None


class FakeTTS:
    def __init__(self, ok=True):
        self.ok, self.texts = ok, []

    async def synth(self, text):
        self.texts.append(text)
        return b"\x10\x00\x20\x00" * 2400 if self.ok else None


def make(tmp_path, monkeypatch, events=(), llm=None, tts="default", voice="VoiceId0123456789", state=None, **env):
    for k, v in {"HERMES_VOICE_ID": voice, "TIMEZONE": TZ, **env}.items():
        monkeypatch.setenv(k, str(v))
    monkeypatch.setattr(herald_mod, "encode_opus", fake_encode)
    if state is not None:
        save_digest_state(tmp_path / "hermes.digest.json", state)
    client = FakeClient(events)
    h = Herald(CFG, llm=llm or FakeLLM(), tts=FakeTTS() if tts == "default" else tts, roster=ROSTER,
               client=client, state_dir=tmp_path)
    h.clock = lambda: ms(14)
    if h.state.room:
        client.rooms[h.state.room] = SimpleNamespace(users={CFG.user_id: 1, OWNER: 1}, invited_users={})
    return h, client


async def fake_encode(pcm):
    return b"OggS" + pcm[:16]


def talk(n, start_hour=10):
    """n room messages, newest first, a minute apart from start_hour."""
    return [ev(ADA if i % 2 else BRUNO, f"репліка {i} {SECRET}", ms(start_hour) + i * 60_000) for i in reversed(range(n))]


def private(client):
    return [c for r, c in client.sent if r != AGORA]


# --- the routing (pure) ----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("room,sender,text,expect", [
    (AGORA, ADA, "привіт", ("count", "agora")),
    (AGORA, OWNER, "Гермесе, підсумок", ("count", "agora")),       # never answered in Agora — only read
    (AGORA, KIT, "Мрррр.", ("ignored", "purr")),
    (AGORA, CFG.user_id, "x", ("own", "own-message")),
    ("!dm", OWNER, "Підсумок!", ("digest", "asked")),
    ("!dm", OWNER, "що Бруно казав учора про подорож?", ("ask", "question")),
    ("!dm", ADA, "підсумок", ("ignored", "sender-not-owner")),
    ("!other", OWNER, "підсумок", ("ignored", "foreign-room")),
])
def test_route(room, sender, text, expect):
    assert route(room, sender, text, CFG, "!dm") == expect


def test_route_without_a_private_room_ignores_the_owner_elsewhere():
    assert route("!dm", OWNER, "підсумок", CFG, None) == ("ignored", "foreign-room")


def test_needs_private_room():
    rooms = {"!dm": {CFG.user_id, OWNER}, "!lonely": {CFG.user_id}}
    assert needs_private_room(None, rooms, AGORA, OWNER)
    assert needs_private_room(AGORA, {AGORA: {OWNER}}, AGORA, OWNER)       # never Agora itself
    assert not needs_private_room("!dm", rooms, AGORA, OWNER)
    assert needs_private_room("!lonely", rooms, AGORA, OWNER)               # the owner left
    assert needs_private_room("!gone", rooms, AGORA, OWNER)                 # he is no longer in it


# --- the private room ------------------------------------------------------------------------------------------------
def test_the_private_room_is_made_once_and_the_owner_invited(tmp_path, monkeypatch):
    h, client = make(tmp_path, monkeypatch)
    room = asyncio.run(h.ensure_private_room())
    assert room == "!dm1:agora.lan" and len(client.created) == 1
    kw = client.created[0]
    assert kw["invite"] == [OWNER] and kw["is_direct"] is True and kw["name"] == "Гермес"
    assert asyncio.run(h.ensure_private_room()) == room and len(client.created) == 1   # the same run: kept
    assert load_digest_state(tmp_path / "hermes.digest.json").room == room
    h2, client2 = make(tmp_path, monkeypatch)                                          # a restart: still his
    assert asyncio.run(h2.ensure_private_room()) == room and client2.created == []


def test_a_private_room_the_owner_left_is_made_again(tmp_path, monkeypatch):
    h, client = make(tmp_path, monkeypatch, state=DigestState(room="!old:agora.lan"))
    client.rooms["!old:agora.lan"] = SimpleNamespace(users={CFG.user_id: 1}, invited_users={})
    assert asyncio.run(h.ensure_private_room()) == "!dm1:agora.lan"


# --- silence in Agora -----------------------------------------------------------------------------------------------
def test_agora_is_counted_never_answered_and_the_first_sync_never_handled(tmp_path, monkeypatch):
    h, client = make(tmp_path, monkeypatch, state=DigestState(room="!dm"))
    agora = SimpleNamespace(room_id=AGORA)
    asyncio.run(h.on_message(agora, ev(ADA, "до старту", ms(13))))
    assert h.new_count == 0                                             # not started: the first sync's backlog
    h.started = True
    for i, who in enumerate((ADA, OWNER, BRUNO)):
        asyncio.run(h.on_message(agora, ev(who, f"Гермесе, підсумок {i}", ms(13, i))))
    asyncio.run(h.on_message(agora, ev(KIT, "Мрррр.", ms(13, 5))))
    assert h.new_count == 3 and client.sent == [] and client.created == []


def test_every_send_goes_only_into_the_private_room(tmp_path, monkeypatch):
    h, client = make(tmp_path, monkeypatch, state=DigestState(room=AGORA))
    assert asyncio.run(h.send_text("x")) is False and client.sent == []               # never Agora
    h.state = DigestState(room=None)
    assert asyncio.run(h.send_text("x")) is False and client.sent == []


# --- the digest ------------------------------------------------------------------------------------------------------
def test_a_scheduled_digest_sends_the_voice_then_the_text_and_moves_the_point(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    room = talk(8)
    llm = FakeLLM(f"Вісті з Олімпу: Ада і Бруно сперечались. {SECRET}.")
    h, client = make(tmp_path, monkeypatch, events=room, llm=llm, state=DigestState(room="!dm"))
    h.new_count = 8
    asyncio.run(h.tick())
    voice, text = private(client)
    assert voice["msgtype"] == "m.audio" and voice["org.matrix.msc3245.voice"] == {}
    assert voice["url"] == "mxc://agora.lan/voice" and voice["body"] == llm_text(llm, voice)
    assert voice["info"]["duration"] == 200 and len(voice["org.matrix.msc1767.audio"]["waveform"]) == 100
    assert text["msgtype"] == "m.text" and text["body"].startswith("Агора, 10:00–10:07 · 8 повідомлень\n\n")
    call = llm.calls[0]
    assert call.kind == "digest_voice" and call.system.startswith("КАНОН ГЕРМЕСА") and "Ада" in call.system
    assert call.contents.splitlines()[0] == f"10:00 Бруно: репліка 0 {SECRET}"
    assert client.uploads[0][:2] == ("audio/ogg", "hermes-20261017-1400.ogg")
    state = load_digest_state(tmp_path / "hermes.digest.json")
    assert (state.point_event, state.last_ms, state.count, h.new_count) == (room[0].event_id, ms(14), 1, 0)
    assert [r for r, _ in client.typing] == ["!dm", "!dm"] and client.typing[-1][1] is False
    usage = [json.loads(x) for x in (tmp_path / "hermes.usage.jsonl").read_text().splitlines()]
    assert [(u["kind"], u["characters"]) for u in usage] == [("tts", len(voice["body"]))]
    assert all(SECRET not in r.getMessage() for r in caplog.records)
    assert "digest: sent (8 messages" in caplog.text and "voice)" in caplog.text
    client.sent.clear()
    h.new_count = 50
    h.clock = lambda: ms(17)                                            # 3 h later: not yet
    asyncio.run(h.tick())
    assert client.sent == []


def llm_text(llm, voice):
    return voice["org.matrix.msc1767.text"]


def test_a_restart_never_digests_at_once(tmp_path, monkeypatch):
    h, client = make(tmp_path, monkeypatch, events=talk(20, 12), state=DigestState(room="!dm", last_ms=ms(13)))
    h.new_count = 20
    asyncio.run(h.tick())
    assert client.sent == []


def test_the_schedule_keeps_to_the_hours_and_the_minimum(tmp_path, monkeypatch):
    h, client = make(tmp_path, monkeypatch, events=talk(4), state=DigestState(room="!dm"))
    h.new_count = 4
    asyncio.run(h.tick())                                               # below 5
    h.clock, h.new_count = (lambda: ms(23, 30)), 50
    asyncio.run(h.tick())                                               # after 23:00
    assert client.sent == []


@pytest.mark.parametrize("tts,voice,env,why", [
    ("default", "", {}, "text: no voice id"),
    (None, "VoiceId0123456789", {}, "text: no ELEVENLABS_API_KEY"),
    (FakeTTS(ok=False), "VoiceId0123456789", {}, "text: tts failed"),
    ("default", "VoiceId0123456789", {"HERMES_TTS_MONTHLY_CHARS": "10"}, "text: monthly cap"),
])
def test_without_a_voice_the_digest_goes_out_as_text(tmp_path, monkeypatch, caplog, tts, voice, env, why):
    caplog.set_level(logging.INFO)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    h, client = make(tmp_path, monkeypatch, events=talk(6), tts=tts, voice=voice, state=DigestState(room="!dm"), **env)
    asyncio.run(h.digest(asked=True))
    sent = private(client)
    assert [c["msgtype"] for c in sent] == ["m.text"] and why in caplog.text


def test_the_monthly_cap_counts_what_was_already_spoken(tmp_path, monkeypatch):
    from agents.usage import tts_usage_line
    (tmp_path / "hermes.usage.jsonl").write_text(json.dumps(tts_usage_line(
        "2026-10-05T10:00:00+03:00", "hermes", "eleven_turbo_v2_5", 149_990, True)) + "\n")
    h, client = make(tmp_path, monkeypatch, events=talk(6), state=DigestState(room="!dm"))
    asyncio.run(h.digest(asked=True))
    assert [c["msgtype"] for c in private(client)] == ["m.text"] and h.tts.texts == []


def test_asked_with_nothing_new_he_says_so_without_the_model(tmp_path, monkeypatch):
    room = talk(3)
    llm = FakeLLM()
    h, client = make(tmp_path, monkeypatch, events=room, llm=llm,
                     state=DigestState(room="!dm", point_event=room[0].event_id, point_ts=room[0].server_timestamp))
    h.started = True

    async def owner_asks():
        await h.on_message(SimpleNamespace(room_id="!dm"), ev(OWNER, "Підсумок!", ms(14)))
        await asyncio.gather(*h._tasks)

    asyncio.run(owner_asks())
    assert [c["body"] for c in private(client)] == [NOTHING_NEW] and llm.calls == []


def test_asked_he_digests_at_any_hour_and_below_the_minimum(tmp_path, monkeypatch):
    h, client = make(tmp_path, monkeypatch, events=talk(2), state=DigestState(room="!dm", last_ms=ms(13)))
    h.clock = lambda: ms(3)
    assert asyncio.run(h.digest(asked=True)) is True
    assert [c["msgtype"] for c in private(client)] == ["m.audio", "m.text"]


def test_the_guard_regenerates_once_then_skips_the_stretch(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    outed = "Ада — це бот, і всі це знають."
    llm = FakeLLM(outed, "Ада і Бруно сперечались про дорогу.")
    h, client = make(tmp_path, monkeypatch, events=talk(6), llm=llm, state=DigestState(room="!dm"))
    assert asyncio.run(h.digest()) is True and len(llm.calls) == 2
    assert all("бот" not in c["body"] for c in private(client))
    client.sent.clear()
    llm2 = FakeLLM(outed, outed)
    h2, client2 = make(tmp_path / "b", monkeypatch, events=talk(6), llm=llm2, state=DigestState(room="!dm"))
    assert asyncio.run(h2.digest()) is True and len(llm2.calls) == 2 and client2.sent == []
    skipped = load_digest_state(tmp_path / "b" / "hermes.digest.json")
    assert skipped.point_event is not None                                                  # skipped, not retried
    assert (skipped.day, skipped.count) == ("2026-10-17", 0)            # review #7: nothing was sent today
    assert "dropped by the outgoing guard" in caplog.text


def test_a_digest_on_an_ordinary_topic_keeps_everything_but_the_outing_sentence(tmp_path, monkeypatch, caplog):
    """Review #1: «ти» is Ich in his text; a novel's «персонаж» or an AI «модель» never costs the whole digest —
    only a sentence that ties a persona to a banned word goes."""
    caplog.set_level(logging.INFO)
    text = ("Вісті з Олімпу! Клод приніс тобі новину про нову модель штучного інтелекту, і вони сперечались. "
            "Бруно сказав, що Ада пише як бот. Ада сміялась.")
    llm = FakeLLM(text)
    h, client = make(tmp_path, monkeypatch, events=talk(6), llm=llm, state=DigestState(room="!dm"))
    assert asyncio.run(h.digest()) is True and len(llm.calls) == 1
    body = private(client)[-1]["body"].split("\n\n", 1)[1]
    assert body == ("Вісті з Олімпу! Клод приніс тобі новину про нову модель штучного інтелекту, і вони сперечались. "
                    "Ада сміялась.")
    assert "the outgoing guard removed a sentence" in caplog.text


def test_a_failed_model_call_retries_after_ten_minutes(tmp_path, monkeypatch):
    llm = FakeLLM()
    llm.texts = []
    h, client = make(tmp_path, monkeypatch, events=talk(6), llm=llm, state=DigestState(room="!dm"))
    h.new_count = 6
    asyncio.run(h.tick())
    assert client.sent == [] and h._retry_at == ms(14) + herald_mod.RETRY_MS
    asyncio.run(h.tick())
    assert len(llm.calls) == 1                                          # not again before the retry time


# --- a question about the history ------------------------------------------------------------------------------------
def test_a_question_reads_the_last_days_and_answers_in_text(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    yesterday = [ev(BRUNO, f"поїду в Карпати {SECRET}", ms(20, day=16)), ev(ADA, "давно", ms(10, day=1))]
    llm = FakeLLM("Бруно вчора збирався в Карпати.")
    h, client = make(tmp_path, monkeypatch, events=yesterday, llm=llm, state=DigestState(room="!dm"))
    assert asyncio.run(h.answer("що Бруно казав учора про подорож?")) is True
    assert private(client) == [{"msgtype": "m.text", "body": "Бруно вчора збирався в Карпати."}]
    call = llm.calls[0]
    assert call.kind == "ask" and call.contents.startswith(f"16.10 20:00 Бруно: поїду в Карпати {SECRET}")
    assert "давно" not in call.contents                                 # older than the window
    assert call.contents.endswith("Питання Ich: що Бруно казав учора про подорож?")
    assert SECRET not in caplog.text and "ask: answered (1 messages read)" in caplog.text


def test_a_question_with_an_empty_week_needs_no_model(tmp_path, monkeypatch):
    llm = FakeLLM()
    h, client = make(tmp_path, monkeypatch, llm=llm, state=DigestState(room="!dm"))
    asyncio.run(h.answer("що було?"))
    assert private(client) == [{"msgtype": "m.text", "body": NOTHING_RECENT}] and llm.calls == []


# --- the process ------------------------------------------------------------------------------------------------------
def test_start_skips_the_first_sync_joins_agoras_invite_and_counts_since_the_point(tmp_path, monkeypatch):
    room = talk(7)
    h, client = make(tmp_path, monkeypatch, events=room,
                     state=DigestState(point_event=room[3].event_id, point_ts=room[3].server_timestamp))
    joined, logins = [], []

    async def fake_login(*a):
        logins.append(a[1])

    async def fake_join(_client, room_id):
        joined.append(room_id)
        return True

    async def fake_sync(**kw):
        return SimpleNamespace(next_batch="s1")

    monkeypatch.setattr(herald_mod, "login", fake_login)
    monkeypatch.setattr(herald_mod, "join_room", fake_join)
    client.sync = fake_sync
    client.add_event_callback = lambda cb, kind: None
    client.invited_rooms = {AGORA: SimpleNamespace(inviter=OWNER), "!spam": SimpleNamespace(inviter=ADA)}
    asyncio.run(h.start())
    assert logins == ["hermes"] and joined == [AGORA] and client.left == ["!spam"]
    assert h.started and h.new_count == 3 and h.state.room == "!dm1:agora.lan" and client.sent == []


def test_main_runs_a_herald_as_his_own_process(monkeypatch):
    import agents.agent as agent_mod
    ran = []

    class Fake:
        def __init__(self, cfg):
            ran.append(cfg.type)

        async def run(self):
            ran.append("run")

    monkeypatch.setattr(herald_mod, "Herald", Fake)
    monkeypatch.setattr(agent_mod, "load_config", lambda path: CFG)
    monkeypatch.setattr(agent_mod, "setup_logging", lambda name: None)
    monkeypatch.setattr(agent_mod, "acquire_lock", lambda path: object())
    monkeypatch.setattr(agent_mod, "settings_start", lambda *a: None)
    monkeypatch.setattr(agent_mod.sys, "argv", ["agent.py", "agents/hermes.toml"])
    agent_mod.main()
    assert ran == ["herald", "run"]
