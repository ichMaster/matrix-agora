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
from agents.herald import CHAT_THINKING, Herald, needs_private_room, route
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
        self.private_events: list = []  # the private room's lines, newest first
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

    fail_page: int | None = None  # review #3: this page answers with an error

    async def room_messages(self, room_id, start=None, direction=None, limit=100):
        from nio import RoomMessagesError
        if room_id != AGORA:                                           # the private room: one page of the chat
            return SimpleNamespace(chunk=self.private_events[:limit], end="end")
        page = 0 if start == "s1" else int(start[1:])
        if page == self.fail_page:
            return RoomMessagesError("bad gateway", "502")
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

    async def think(self, contents, system_instruction, model=None, max_output_tokens=None, kind="digest_voice",
                    level=None):
        self.calls.append(SimpleNamespace(contents=contents, system=system_instruction, model=model, kind=kind,
                                          level=level))
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
    ("default", "abc123XYZ", {}, "text: voice id malformed"),            # review #6: no request, no tts line
])
def test_without_a_voice_the_digest_goes_out_as_text(tmp_path, monkeypatch, caplog, tts, voice, env, why):
    caplog.set_level(logging.INFO)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    h, client = make(tmp_path, monkeypatch, events=talk(6), tts=tts, voice=voice, state=DigestState(room="!dm"), **env)
    asyncio.run(h.digest(asked=True))
    sent = private(client)
    assert [c["msgtype"] for c in sent] == ["m.text"] and why in caplog.text
    if "malformed" in why:
        assert not (tmp_path / "hermes.usage.jsonl").exists() or "tts" not in (tmp_path / "hermes.usage.jsonl").read_text()


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
    h, client = make(tmp_path, monkeypatch, events=talk(6, 11), llm=llm, state=DigestState(room="!dm"))
    h.new_count = 6
    asyncio.run(h.tick())
    assert client.sent == [] and h._retry_at == ms(14) + herald_mod.RETRY_MS
    asyncio.run(h.tick())
    assert len(llm.calls) == 1                                          # not again before the retry time
    assert h.new_count == 6                                             # review #2: a failure keeps the count
    llm.texts = ["Вісті з Олімпу: Ада і Бруно сперечались."]
    h.clock = lambda: ms(14, 11)                                        # the retry time: tried again, no new talk
    asyncio.run(h.tick())
    assert len(llm.calls) == 2 and [c["msgtype"] for c in private(client)] == ["m.audio", "m.text"]
    assert h.new_count == 0


def test_lines_that_arrive_during_a_digest_count_toward_the_next_one(tmp_path, monkeypatch):
    """Review #2: the count drops only by what the digest saw when it began."""
    h, client = make(tmp_path, monkeypatch, events=talk(6), state=DigestState(room="!dm"))
    h.new_count = 6
    think = h.llm.think

    async def slow_think(*a, **kw):
        h.new_count += 2                                                # two lines while the model thinks
        return await think(*a, **kw)

    h.llm.think = slow_think
    asyncio.run(h.tick())
    assert private(client) and h.new_count == 2


# --- a question about the history ------------------------------------------------------------------------------------
def test_a_question_reads_the_last_days_and_answers_in_text(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    yesterday = [ev(BRUNO, f"поїду в Карпати {SECRET}", ms(20, day=16)), ev(ADA, "давно", ms(10, day=1))]
    llm = FakeLLM("Бруно вчора збирався в Карпати.")
    h, client = make(tmp_path, monkeypatch, events=yesterday, llm=llm, state=DigestState(room="!dm"))
    assert asyncio.run(h.answer("що Бруно казав учора про подорож?")) is True
    assert private(client) == [{"msgtype": "m.text", "body": "Бруно вчора збирався в Карпати."}]
    call = llm.calls[0]
    assert call.kind == "ask" and call.level == CHAT_THINKING == "low"   # a chat answers in seconds
    assert call.contents.startswith(f"Агора за останні дні:\n16.10 20:00 Бруно: поїду в Карпати {SECRET}")
    assert "давно" not in call.contents                                 # older than the window
    assert call.contents.endswith("\n\nIch: що Бруно казав учора про подорож?")
    assert "це розмова, а не підсумок" in call.system
    assert SECRET not in caplog.text and "ask: answered (1 messages read, text: asked in text)" in caplog.text


def test_the_owner_chats_with_hermes_and_a_follow_up_has_its_context(tmp_path, monkeypatch):
    """The owner, 2026-10-18: «він зазвичай відповідає цілим дайджестом». A message is a conversation: the chat
    brief, your recent lines (his digest text among them), and what was just written — never the line twice."""
    llm = FakeLLM("Вітаю, смертний! Олімп тихий, а я тут.")
    h, client = make(tmp_path, monkeypatch, llm=llm, state=DigestState(room="!dm"))
    client.private_events = [ev(OWNER, "а що ще?", ms(14, 2), "$now"),
                             ev(CFG.user_id, "Агора, 10:00–10:07 · 8 повідомлень\n\nВісті з Олімпу…", ms(14, 1)),
                             ev(OWNER, "привіт", ms(14)),
                             ev(ADA, "чужий рядок", ms(13))]          # never another sender's
    assert asyncio.run(h.answer("а що ще?", "$now")) is True
    contents = llm.calls[0].contents
    assert contents.startswith("Агора за останні дні:\n(тиша)")         # a quiet week still gets an answer
    assert "Ваша недавня розмова:\nIch: привіт\nГермес: Агора, 10:00–10:07 · 8 повідомлень" in contents
    assert contents.endswith("\n\nIch: а що ще?") and contents.count("а що ще?") == 1 and "чужий" not in contents
    assert private(client) == [{"msgtype": "m.text", "body": "Вітаю, смертний! Олімп тихий, а я тут."}]


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



@pytest.mark.parametrize("fail_page", [0, 1])
def test_a_failed_page_never_moves_the_point_or_says_nothing_new(tmp_path, monkeypatch, caplog, fail_page):
    """Review #3: 250 lines since the point and a page answers 502 — no digest from a partial read, the point stays,
    «підсумок» never hears "nothing new", and the retry reads it all."""
    room = talk(251, 9)
    point = room[-1]
    llm = FakeLLM()
    h, client = make(tmp_path, monkeypatch, events=room, llm=llm,
                     state=DigestState(room="!dm", point_event=point.event_id, point_ts=point.server_timestamp))
    client.fail_page = fail_page
    assert asyncio.run(h.digest(asked=True)) is False
    assert client.sent == [] and llm.calls == [] and "the room could not be read" in caplog.text
    assert load_digest_state(tmp_path / "hermes.digest.json").point_event == point.event_id
    client.fail_page = None
    assert asyncio.run(h.digest(asked=True)) is True
    assert llm.calls[0].contents.count("\n") == 249                  # all 250 lines since the point


def test_a_question_is_never_answered_from_a_partial_read(tmp_path, monkeypatch):
    llm = FakeLLM()
    h, client = make(tmp_path, monkeypatch, events=talk(5), llm=llm, state=DigestState(room="!dm"))
    client.fail_page = 0
    assert asyncio.run(h.answer("що було?")) is False and client.sent == [] and llm.calls == []



def test_a_room_made_this_run_is_trusted_only_until_the_sync_brings_it_back(tmp_path, monkeypatch):
    """Review #4: the owner declines the invite — once the sync shows the room without him, a new one is made
    instead of sending every digest (and paid voice) into a room nobody reads."""
    h, client = make(tmp_path, monkeypatch)
    first = asyncio.run(h.ensure_private_room())
    assert asyncio.run(h.ensure_private_room()) == first and len(client.created) == 1   # not synced yet: trusted
    client.rooms[first] = SimpleNamespace(users={CFG.user_id: 1}, invited_users={})     # synced, the owner declined
    second = asyncio.run(h.ensure_private_room())
    assert second != first and len(client.created) == 2
    client.rooms[second] = SimpleNamespace(users={CFG.user_id: 1}, invited_users={OWNER: 1})  # invited: kept
    assert asyncio.run(h.ensure_private_room()) == second and len(client.created) == 2



def test_a_stop_waits_for_a_digest_on_its_way(tmp_path, monkeypatch, caplog):
    """Review #8: a deploy's SIGTERM mid-digest — the voice and the state land before the client closes, so the
    restart never sends the same stretch again; a digest stuck past the bound is left to the cancel."""
    h, client = make(tmp_path, monkeypatch, events=talk(6), state=DigestState(room="!dm"))
    think = h.llm.think

    async def scenario():
        gate = asyncio.Event()

        async def slow(*a, **kw):
            await gate.wait()
            return await think(*a, **kw)

        h.llm.think = slow
        digest = asyncio.create_task(h.digest())
        await asyncio.sleep(0)
        drain = asyncio.create_task(h.drain(5))
        await asyncio.sleep(0.01)
        assert not drain.done()                                       # waiting for the digest
        gate.set()
        await drain
        assert digest.done() and digest.result() is True

    asyncio.run(scenario())
    assert [c["msgtype"] for c in private(client)] == ["m.audio", "m.text"]
    assert load_digest_state(tmp_path / "hermes.digest.json").last_ms == ms(14)

    async def stuck():
        h._busy = asyncio.Lock()                                      # a fresh loop: a fresh lock (one loop in life)
        h.llm.think = lambda *a, **kw: asyncio.Event().wait()
        h.state = DigestState(room="!dm")
        task = asyncio.create_task(h.digest())
        await asyncio.sleep(0)
        await h.drain(0.05)
        task.cancel()

    asyncio.run(stuck())
    assert "still running after" in caplog.text



def edit(sender, body, ts, of="$orig"):
    return RoomMessage.parse_event({
        "event_id": f"$edit{ts}", "sender": sender, "origin_server_ts": ts, "type": "m.room.message",
        "content": {"msgtype": "m.text", "body": f"* {body}", "m.new_content": {"msgtype": "m.text", "body": body},
                    "m.relates_to": {"rel_type": "m.replace", "event_id": of}}})


def test_edits_are_never_counted_digested_or_answered(tmp_path, monkeypatch):
    """Review #9: an edited question would cost a second Pro answer, an edited line would appear twice."""
    from agents.logic import is_edit
    assert is_edit(edit(OWNER, "x", 1)) and not is_edit(ev(OWNER, "x", 1))
    room = [edit(ADA, "репліка 5 (виправлено)", ms(10, 6)), *talk(6)]
    llm = FakeLLM()
    h, client = make(tmp_path, monkeypatch, events=room, llm=llm, state=DigestState(room="!dm"))
    h.started = True

    async def owner_edits():
        await h.on_message(SimpleNamespace(room_id="!dm"), edit(OWNER, "що Бруно казав учора?", ms(14)))
        await h.on_message(SimpleNamespace(room_id=AGORA), edit(ADA, "виправлено", ms(14)))
        await asyncio.gather(*h._tasks)

    asyncio.run(owner_edits())
    assert client.sent == [] and llm.calls == [] and h.new_count == 0
    asyncio.run(h.digest())
    assert "виправлено" not in llm.calls[0].contents and len(llm.calls[0].contents.splitlines()) == 6



# --- v5.2: hearing ----------------------------------------------------------------------------------------------------
class FakeSTT:
    def __init__(self, text="Адо, як ти?", ms=2400):
        self.text, self.ms, self.calls = text, ms, []

    async def transcribe(self, audio, content_type="audio/ogg"):
        self.calls.append((audio, content_type))
        return self.text, self.ms


def voice(sender, eid, size=9000, ts=None):
    return RoomMessage.parse_event({"event_id": eid, "sender": sender, "origin_server_ts": ts or ms(14),
                                    "type": "m.room.message",
                                    "content": {"msgtype": "m.audio", "body": "Voice message", "url": "mxc://agora.lan/v1",
                                                "org.matrix.msc3245.voice": {},
                                                "info": {"mimetype": "audio/ogg", "size": size, "duration": 2400}}})


def hearing(tmp_path, monkeypatch, stt=None, **kw):
    downloads = []

    async def fake_download(client, mxc, max_bytes):
        downloads.append((mxc, max_bytes))
        return b"OggS-voice"

    monkeypatch.setattr(herald_mod, "download", fake_download)
    h, client = make(tmp_path, monkeypatch, state=DigestState(room="!dm"), **kw)
    h.stt = stt if stt is not None else FakeSTT()
    h.started = True
    return h, client, downloads


async def heard(h, room_id, event):
    await h.on_audio(SimpleNamespace(room_id=room_id), event)
    await asyncio.gather(*h._tasks)


def test_the_owners_voice_in_agora_becomes_one_transcript_reply(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    stt = FakeSTT(f"Адо, як ти? {SECRET}")
    h, client, downloads = hearing(tmp_path, monkeypatch, stt=stt)
    asyncio.run(heard(h, AGORA, voice(OWNER, "$voice")))
    assert downloads == [("mxc://agora.lan/v1", herald_mod.TRANSCRIBE_MAX_BYTES)]
    assert stt.calls == [(b"OggS-voice", "audio/ogg")]
    assert client.sent == [(AGORA, {"msgtype": "m.text", "body": f"🎙 Ich: Адо, як ти? {SECRET}",
                                    "m.relates_to": {"m.in_reply_to": {"event_id": "$voice"}}})]
    assert h.new_count == 1                                            # it counts toward the next digest
    usage = [json.loads(x) for x in (tmp_path / "hermes.usage.jsonl").read_text().splitlines()]
    assert [(u["kind"], u["engine"], u["audio_ms"]) for u in usage] == [("stt", "deepgram", 2400)]
    assert all(SECRET not in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("room,sender,why", [
    (AGORA, ADA, "audio-not-owner"), ("!other", OWNER, "foreign-room"),
])
def test_anyone_elses_voice_or_another_room_is_ignored(tmp_path, monkeypatch, caplog, room, sender, why):
    caplog.set_level(logging.INFO)
    h, client, downloads = hearing(tmp_path, monkeypatch)
    asyncio.run(heard(h, room, voice(sender, "$v")))
    assert client.sent == [] and downloads == [] and f"ignored: {why}" in caplog.text


@pytest.mark.parametrize("case", ["over the cap", "nothing heard", "hearing off", "first sync"])
def test_an_unhearable_voice_stays_silent(tmp_path, monkeypatch, caplog, case):
    caplog.set_level(logging.INFO)
    h, client, downloads = hearing(tmp_path, monkeypatch, stt=FakeSTT(text=None, ms=1500))
    event = voice(OWNER, "$v", size=herald_mod.TRANSCRIBE_MAX_BYTES + 1 if case == "over the cap" else 9000)
    if case == "hearing off":
        h.stt = None
    if case == "first sync":
        h.started = False
    asyncio.run(heard(h, AGORA, event))
    assert client.sent == []
    if case == "over the cap":
        assert downloads == [] and "over the cap" in caplog.text
    if case == "nothing heard":
        assert "nothing heard" in caplog.text
        usage = json.loads((tmp_path / "hermes.usage.jsonl").read_text())
        assert (usage["kind"], usage["audio_ms"], usage["ok"]) == ("stt", 1500, True)   # Deepgram heard silence
    if case == "hearing off":
        assert downloads == [] and "hearing off" in caplog.text


def test_every_agora_send_is_a_transcript_reply_to_an_owners_voice(tmp_path, monkeypatch):
    """v5.2: his one kind of Agora message; everything else still goes only to his room."""
    h, client, _ = hearing(tmp_path, monkeypatch, events=talk(6))
    asyncio.run(heard(h, AGORA, voice(OWNER, "$v1")))
    asyncio.run(h.digest(asked=True))
    asyncio.run(h.answer("привіт"))
    agora = [c for r, c in client.sent if r == AGORA]
    assert agora and all(c["body"].startswith("🎙 Ich: ") and c["m.relates_to"]["m.in_reply_to"]["event_id"] == "$v1"
                         for c in agora)
    assert len(agora) == 1 and len(private(client)) >= 2


def test_a_voice_question_in_his_room_is_answered_in_voice_and_a_typed_one_in_text(tmp_path, monkeypatch):
    llm = FakeLLM("Вітаю, смертний.", "І тобі привіт.")
    h, client, _ = hearing(tmp_path, monkeypatch, llm=llm, stt=FakeSTT("привіт, Гермесе"))
    asyncio.run(heard(h, "!dm", voice(OWNER, "$q1")))
    assert [c["msgtype"] for c in private(client)] == ["m.audio", "m.text"]
    assert llm.calls[0].contents.endswith("Ich: привіт, Гермесе") and h._heard == {"$q1": "привіт, Гермесе"}
    client.sent.clear()
    asyncio.run(h.answer("а як справи?", "$q2"))
    assert [c["msgtype"] for c in private(client)] == ["m.text"]


def test_a_spoken_pidsumok_brings_a_digest(tmp_path, monkeypatch):
    h, client, _ = hearing(tmp_path, monkeypatch, events=talk(6), stt=FakeSTT("Підсумок!"))
    asyncio.run(heard(h, "!dm", voice(OWNER, "$q")))
    sent = private(client)
    assert [c["msgtype"] for c in sent] == ["m.audio", "m.text"] and sent[1]["body"].startswith("Агора, ")


def test_his_readers_take_his_transcripts_as_the_owners_lines(tmp_path, monkeypatch):
    room = [text_reply := RoomMessage.parse_event({
        "event_id": "$tr", "sender": CFG.user_id, "origin_server_ts": ms(13), "type": "m.room.message",
        "content": {"msgtype": "m.text", "body": "🎙 Ich: Адо, як ти?",
                    "m.relates_to": {"m.in_reply_to": {"event_id": "$voice"}}}}), voice(OWNER, "$voice", ts=ms(12, 59))]
    assert text_reply.body.startswith("🎙")
    llm = FakeLLM()
    h, _client = make(tmp_path, monkeypatch, events=[*room, *talk(5)], llm=llm, state=DigestState(room="!dm"))
    asyncio.run(h.digest(asked=True))
    assert llm.calls[0].contents.splitlines()[-1] == "13:00 Ich: Адо, як ти?"     # the owner's, not Гермес's


def test_his_room_hears_the_voice_questions_he_heard_in_the_chat(tmp_path, monkeypatch):
    llm = FakeLLM("Так, пам'ятаю.")
    h, client = make(tmp_path, monkeypatch, llm=llm, state=DigestState(room="!dm"))
    h._heard = {"$q1": "що казав Бруно?"}
    client.private_events = [voice(OWNER, "$q1", ts=ms(14)), voice(OWNER, "$never-heard", ts=ms(13))]
    asyncio.run(h.answer("а ще?", "$q2"))
    assert "Ваша недавня розмова:\nIch: що казав Бруно?" in llm.calls[0].contents


def test_a_failure_while_hearing_is_logged_and_he_keeps_running(tmp_path, monkeypatch, caplog):
    """v5.2 review #1: an exception in the hearing task is a log line, not asyncio's lost-task traceback."""
    h, client, _ = hearing(tmp_path, monkeypatch)

    async def broken(*a, **kw):
        raise RuntimeError("deepgram exploded")

    h.stt.transcribe = broken
    asyncio.run(heard(h, AGORA, voice(OWNER, "$v")))
    assert client.sent == [] and "hearing failed (he keeps running)" in caplog.text


def test_a_malformed_info_is_treated_as_empty(tmp_path, monkeypatch):
    """v5.2 review #2: `"info": "x"` from a client never raises in `hear`."""
    h, client, _ = hearing(tmp_path, monkeypatch)
    event = voice(OWNER, "$v")
    event.source["content"]["info"] = "x"
    asyncio.run(heard(h, AGORA, event))
    assert [r for r, _ in client.sent] == [AGORA]
