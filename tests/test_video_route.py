"""v5.18 — her videos after her private answer: the skill in Gemini's prompt in Telegram only, under the day's cap and
while no video is being made; her `КРУЖЕЧОК:` / `ВІДЕО:` line cut; her answer sent at once (for a кружечок her voice held
for it); the video made in the background from her photo and sent, kept as a file and named in a line of hers; a
кружечок that does not come out is her voice note after all, a clip one short line of hers; dropped from the backup,
in Element, past the cap and while busy (nio, Gemini, the makers, ffmpeg and Telegram mocked; an injected clock;
made-up lines)."""

import asyncio
import logging
import os
import stat
from unittest.mock import AsyncMock

import pytest

from agents import agent as agent_mod
from agents.photo import Made, Shot
from agents.private import PRIVATE_BRIEF
from agents.video import CLIP_SKILL, FRAME_LINES, NOTE_SKILL, SKILL_TAIL, VIDEO_FAILED, Video, video_skill
from tests.test_photo_route import her
from tests.test_private_runtime import ms
from tests.test_telegram_runtime import FakeTTS

SECRET = "кадр-5182"


class Notes:
    """Her кружечок's model on fal: one `Video` for every кружечок; keeps the calls."""

    def __init__(self, made):
        self.made, self.calls = made, []

    async def make(self, frame, mime, mp3, seconds=None):
        self.calls.append((frame, mime, mp3))
        return self.made


class Clips:
    """Omni Flash: one `Video` for every clip; keeps the calls."""

    def __init__(self, made):
        self.made, self.calls = made, []

    async def make(self, shot, moment, frame, mime):
        self.calls.append((shot, frame, mime))
        return self.made


@pytest.fixture
def media(monkeypatch):
    async def encode(pcm, timeout_s=60.0):
        return b"OggS-kira"

    async def mp3(pcm, lead_ms=1000, timeout_s=60.0):
        return b"MP3"

    async def square(mp4, mp3, timeout_s=120.0):
        assert mp3 == b"MP3"                                                             # review #3: her voice
        return b"SQUARE-" + mp4

    monkeypatch.setattr(agent_mod, "encode_opus", encode)
    monkeypatch.setattr(agent_mod, "pcm_to_mp3", mp3)
    monkeypatch.setattr(agent_mod, "square_note", square)

    async def shrink(image, timeout_s=30.0):
        return b"SMALL-" + image

    monkeypatch.setattr(agent_mod, "shrink_frame", shrink)


def kira(tmp_path, monkeypatch, *answers, note=None, clip=None, made=None):
    agent = her(tmp_path, monkeypatch, *answers, made=made)
    agent.cfg = agent.cfg.__class__(**{**agent.cfg.__dict__, "capabilities": agent.cfg.capabilities | {"videos"}})
    agent.notes = Notes(note or Video(b"RAW", seconds=12.0))
    agent.clips = Clips(clip or Video(b"CLIP", seconds=8.0))
    agent.video_day_max, agent.video_note_max_s = 4, 30
    agent.spawned = []
    agent._spawn = agent.spawned.append
    bot = agent.telegram

    async def send_note(chat_id, mp4, duration_s, length):
        agent.sent.append(("note", mp4, duration_s, length))
        return True

    async def send_clip(chat_id, mp4, duration_s=None, width=None, height=None):
        agent.sent.append(("clip", mp4, duration_s))
        return True

    bot.send_video_note, bot.send_video = AsyncMock(side_effect=send_note), AsyncMock(side_effect=send_clip)
    return agent


def owner_says(agent, text, when, door, key):
    """His line, its pending answer dropped: the test answers by itself, at once."""
    agent.private_line(text, when, door, key)
    for coro in agent.spawned:
        coro.close()
    agent.spawned.clear()
    agent._private_pending = False


def after(agent):
    """What her answer left in the background, run to its end."""
    while agent.spawned:
        asyncio.run(agent.spawned.pop(0))


def videos_dir(agent):
    return agent.memory_file.parent / "kira.videos" / "2026-10-20"


def her_lines(agent):
    return [x.text for x in agent.archive.latest("private", 10, gemini=False) if x.speaker == "Кіра"]


def test_a_kruzhechok_holds_her_voice_and_follows_her_words_in_her_voice(tmp_path, monkeypatch, media, caplog):
    caplog.set_level(logging.INFO)
    agent = kira(tmp_path, monkeypatch, f"Ось я тут\nКРУЖЕЧОК: я на балконі ввечері {SECRET}")
    owner_says(agent, "запиши кружечок", ms(17), "telegram", "tg:1")
    assert asyncio.run(agent.private_reply()) is True
    prompt = agent.llm.calls[0][0]
    assert NOTE_SKILL in prompt and CLIP_SKILL in prompt                                 # offered to Gemini
    assert agent.sent == [("text", "Ось я тут")] and agent._video_busy                   # her voice held, not sent
    after(agent)
    assert agent.sent[1:] == [("note", b"SQUARE-RAW", 12, 640)]
    assert agent.photos.shots == [Shot("selfie", f"я на балконі ввечері {SECRET}")]
    assert agent.photos.frames == [("1:1", FRAME_LINES["note"])]
    assert agent.photos.kinds == ["frame"]                       # v5.22: a frame is never counted as a photo
    assert agent.notes.calls == [(b"SMALL-JPEG", "image/jpeg", b"MP3")]               # 640×640 to fal
    assert any(c.args[1] == "record_video_note" for c in agent.telegram.send_chat_action.call_args_list)
    assert her_lines(agent) == ["Ось я тут", "[кружечок: ...]"]                         # never what is in it
    assert agent.private_history[-1] == ("Кіра", "[кружечок: ...]")
    [kept] = list(videos_dir(agent).iterdir())
    assert kept.name == "180000.mp4" and kept.read_bytes() == b"SQUARE-RAW"
    assert stat.S_IMODE(os.stat(kept).st_mode) == 0o600 and stat.S_IMODE(os.stat(kept.parent).st_mode) == 0o700
    assert "video: sent (note, telegram, 0 s)" in caplog.text and not agent._video_busy
    assert SECRET not in caplog.text and str(kept) not in caplog.text


@pytest.mark.parametrize("how", ["blocked", "failed", "frame", "telegram"])
def test_a_kruzhechok_that_does_not_come_out_is_her_voice_note_after_all(tmp_path, monkeypatch, media, caplog, how):
    caplog.set_level(logging.INFO)
    agent = kira(tmp_path, monkeypatch, "Ось я\nКРУЖЕЧОК: я на кухні",
                 note=Video(None, why=how) if how in ("blocked", "failed") else None,
                 made=Made(None, why="blocked") if how == "frame" else None)
    if how == "telegram":
        agent.telegram.send_video_note = AsyncMock(return_value=False)
    owner_says(agent, "запиши кружечок", ms(17), "telegram", "tg:1")
    assert asyncio.run(agent.private_reply()) is True
    after(agent)
    assert agent.sent == [("text", "Ось я"), "voice"]                                   # her voice, never lost
    assert not videos_dir(agent).exists() and her_lines(agent) == ["Ось я"]
    assert "her voice note instead" in caplog.text and not agent._video_busy


@pytest.mark.parametrize("why", ["too long", "no voice"])
def test_no_voice_or_a_long_one_is_her_answer_as_now_and_no_kruzhechok(tmp_path, monkeypatch, media, caplog, why):
    caplog.set_level(logging.INFO)
    agent = kira(tmp_path, monkeypatch, "Слухай\nКРУЖЕЧОК: я в бусі")
    if why == "too long":
        agent.tts = FakeTTS(pcm=b"\x01\x00" * 24_000 * 31)
    else:
        agent.voice_monthly_chars = 0                                                     # the speakers' cap
    owner_says(agent, "запиши кружечок", ms(17), "telegram", "tg:1")
    assert asyncio.run(agent.private_reply()) is True
    assert agent.sent == (["voice", ("text", "Слухай")] if why == "too long" else [("text", "Слухай")])
    assert agent.spawned == [] and f"video: dropped ({why})" in caplog.text and not agent._video_busy


def test_a_clip_follows_her_answer_from_a_vertical_faceless_frame(tmp_path, monkeypatch, media, caplog):
    caplog.set_level(logging.INFO)
    agent = kira(tmp_path, monkeypatch, f"Глянь, що тут\nВІДЕО: дощ на вікні {SECRET}")
    owner_says(agent, "що бачиш?", ms(17), "telegram", "tg:1")
    assert asyncio.run(agent.private_reply()) is True
    assert agent.sent == ["voice", ("text", "Глянь, що тут")]                           # her answer as now
    after(agent)
    assert agent.sent[2:] == [("clip", b"CLIP", 8)]
    assert agent.photos.shots == [Shot("photo", f"дощ на вікні {SECRET}")]
    assert agent.photos.frames == [("9:16", FRAME_LINES["clip"])]
    assert [c[0] for c in agent.clips.calls] == [Shot("clip", f"дощ на вікні {SECRET}")]
    assert any(c.args[1] == "upload_video" for c in agent.telegram.send_chat_action.call_args_list)
    assert her_lines(agent)[-1] == "[відео: ...]"
    assert "video: sent (clip, telegram, 0 s)" in caplog.text and SECRET not in caplog.text


def test_a_clip_that_does_not_come_out_draws_one_short_line_or_nothing(tmp_path, monkeypatch, media, caplog):
    caplog.set_level(logging.INFO)
    agent = kira(tmp_path, monkeypatch, "Глянь\nВІДЕО: море", "Ой, відео не пішло.", clip=Video(None, why="failed"))
    owner_says(agent, "покажи", ms(17), "telegram", "tg:1")
    assert asyncio.run(agent.private_reply()) is True
    after(agent)
    redraw = agent.llm.calls[1][0]
    assert VIDEO_FAILED in redraw and CLIP_SKILL not in redraw and NOTE_SKILL not in redraw
    assert agent.sent == ["voice", ("text", "Глянь"), "voice", ("text", "Ой, відео не пішло.")]
    assert her_lines(agent) == ["Глянь", "Ой, відео не пішло."] and not videos_dir(agent).exists()
    assert "a line of hers instead" in caplog.text and not agent._private_pending
    silent = kira(tmp_path / "s", monkeypatch, "Глянь\nВІДЕО: море", None, clip=Video(None, why="blocked"))
    owner_says(silent, "покажи", ms(17), "telegram", "tg:1")
    asyncio.run(silent.private_reply())
    after(silent)
    assert silent.sent == ["voice", ("text", "Глянь")]                                   # an empty answer: nothing


def test_an_owner_line_that_came_while_her_short_line_was_drawn_is_answered(tmp_path, monkeypatch, media):
    agent = kira(tmp_path, monkeypatch, "Глянь\nВІДЕО: море", "Не пішло, вибач.", clip=Video(None, why="failed"))
    owner_says(agent, "покажи", ms(17), "telegram", "tg:1")
    asyncio.run(agent.private_reply())
    says = agent.llm.generate

    async def generate(*a, **kw):
        agent._private_again = True                                                      # he writes meanwhile
        return await says(*a, **kw)

    agent.llm.generate = generate
    coro = agent.spawned.pop(0)
    asyncio.run(coro)
    assert [c.__name__ for c in agent.spawned] == ["private_later"] and agent._private_pending
    agent.spawned.pop().close()


@pytest.mark.parametrize("how,why", [("busy", "busy"), ("cap", "cap"), ("element", "element"), ("no key", "off")])
def test_the_skill_is_withheld_and_the_line_dropped(tmp_path, monkeypatch, media, caplog, how, why):
    from tests.test_archive import DM
    caplog.set_level(logging.INFO)
    agent = kira(tmp_path, monkeypatch, "Привіт!\nКРУЖЕЧОК: я в бусі")
    door, key = "telegram", "tg:1"
    if how == "busy":
        agent._video_busy = True
    elif how == "cap":
        videos_dir(agent).mkdir(parents=True)
        for i in range(4):
            (videos_dir(agent) / f"0{i}0000.mp4").write_bytes(b"x")
    elif how == "element":
        agent.private_room, agent.voice_reply_p, door, key = DM, 0.0, "matrix", "$p1"
    else:
        agent.notes = None                                                                # no FAL_KEY: clips only
    owner_says(agent, "привіт", ms(17), door, key)
    assert asyncio.run(agent.private_reply()) is True
    prompt = agent.llm.calls[0][0]
    assert NOTE_SKILL not in prompt
    assert (CLIP_SKILL in prompt) == (how == "no key")
    assert agent.spawned == [] and f"video: dropped ({why})" in caplog.text


def test_the_skill_is_geminis_alone_never_the_backups(tmp_path, monkeypatch):
    from agents.fallback import FallbackResponder
    from tests.test_private_route import Backup
    agent = kira(tmp_path, monkeypatch)
    agent.fallback = Backup(text="Ось.\nВІДЕО: море")
    agent.fallback_responder = FallbackResponder(agent.fallback)
    agent.fallback_context, agent.fallback_history_n = 32000, 60
    agent._offer_video = ("note", "clip")
    assert NOTE_SKILL in asyncio.run(agent._gemini_private_prompt(PRIVATE_BRIEF))
    prompt, _ = asyncio.run(agent._backup_private_prompt(PRIVATE_BRIEF))
    assert NOTE_SKILL not in prompt and CLIP_SKILL not in prompt
    assert str(asyncio.run(agent._backup_text(PRIVATE_BRIEF, "private"))) == "Ось."    # its line dropped


def test_a_line_she_writes_first_can_carry_a_clip(tmp_path, monkeypatch, media):
    agent = kira(tmp_path, monkeypatch, "Глянь, яке небо\nВІДЕО: захід сонця над Високим Замком")
    owner_says(agent, "добраніч", ms(9), "telegram", "tg:0")
    assert asyncio.run(agent.private_reply(nudge=True, channel="telegram")) is True
    after(agent)
    assert agent.sent == ["voice", ("text", "Глянь, яке небо"), ("clip", b"CLIP", 8)]


def test_the_skill_never_says_a_video_is_made():
    for words in (NOTE_SKILL, CLIP_SKILL, SKILL_TAIL, VIDEO_FAILED):
        low = words.lower()
        assert not any(w in low for w in ("модел", "бот", "штучн", "інтелект", "генер", "згенер", "ші "))
    assert "КРУЖЕЧОК" in NOTE_SKILL and "ВІДЕО" in CLIP_SKILL
    assert video_skill(("clip",)) == f"{CLIP_SKILL} {SKILL_TAIL}" and video_skill(()) == ""
    assert video_skill(("note", "clip")) == f"{NOTE_SKILL} {CLIP_SKILL} {SKILL_TAIL}"



def test_her_next_video_waits_out_the_pause_after_her_last(tmp_path, monkeypatch, media):
    """v5.22 (the owner, 2026-11-02: «те саме постав для відео але більше паузу»): after a video, no video
    skill until `VIDEO_GAP_S` has passed — read from today's kept videos' names."""
    agent = kira(tmp_path, monkeypatch, "Ось")
    agent.video_gap_s = 6000
    videos_dir(agent).mkdir(parents=True)
    (videos_dir(agent) / "170000.mp4").write_bytes(b"MP4")                                  # her last video, at 17:00
    agent.clock = lambda: ms(18, 30)
    assert agent._video_closed("telegram", "note") == "pause" and agent._video_kinds("telegram") == ()
    agent.clock = lambda: ms(18, 41)
    assert agent._video_closed("telegram", "note") is None and "note" in agent._video_kinds("telegram")


def test_a_video_paid_for_counts_toward_the_cap_even_when_it_did_not_go(tmp_path, monkeypatch, media, caplog):
    # v5.18 review #1: fal billed, then the square cut failed — no file kept, yet the day's cap must see it
    import json

    from agents.usage import usage_line, video_note_usage_line
    caplog.set_level(logging.INFO)
    agent = kira(tmp_path, monkeypatch, "Привіт!\nКРУЖЕЧОК: я в бусі")
    agent.video_day_max = 2
    agent.usage_file.parent.mkdir(parents=True, exist_ok=True)
    lines = [video_note_usage_line("2026-10-20T10:00:00+03:00", "kira", "fal-ai/x", 9000, True),
             usage_line("2026-10-20T11:00:00+03:00", "kira", "video", "gemini-omni-1.1-flash", None, True),
             video_note_usage_line("2026-10-20T12:00:00+03:00", "kira", "fal-ai/x", None, False),  # failed: unpaid
             video_note_usage_line("2026-10-19T12:00:00+03:00", "kira", "fal-ai/x", 9000, True)]   # another day
    agent.usage_file.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    assert agent.videos_today() == 2 and not videos_dir(agent).exists()
    owner_says(agent, "запиши кружечок", ms(17), "telegram", "tg:1")
    assert asyncio.run(agent.private_reply()) is True
    assert NOTE_SKILL not in agent.llm.calls[0][0] and "video: dropped (cap)" in caplog.text



def test_the_log_says_how_long_a_video_took(tmp_path, monkeypatch, media, caplog):
    # v5.18 review #4: the DoD notes the time each video took — the log says it, and nothing of hers
    caplog.set_level(logging.INFO)
    agent = kira(tmp_path, monkeypatch, f"Глянь\nВІДЕО: море {SECRET}")
    owner_says(agent, "що бачиш?", ms(17), "telegram", "tg:1")
    asyncio.run(agent.private_reply())
    times = iter([ms(18), ms(18) + 143_400])
    agent.clock = lambda: next(times, ms(18) + 143_400)
    after(agent)
    assert "video: sent (clip, telegram, 143 s)" in caplog.text and SECRET not in caplog.text



def test_a_frame_that_cannot_be_shrunk_goes_as_made(tmp_path, monkeypatch, media):
    async def broken(image, timeout_s=30.0):
        return None

    monkeypatch.setattr(agent_mod, "shrink_frame", broken)
    agent = kira(tmp_path, monkeypatch, "Ось\nКРУЖЕЧОК: я на кухні", made=Made(b"PNG", "image/png", "ok"))
    owner_says(agent, "запиши кружечок", ms(17), "telegram", "tg:1")
    asyncio.run(agent.private_reply())
    after(agent)
    assert agent.notes.calls == [(b"PNG", "image/png", b"MP3")] and agent.sent[-1][0] == "note"
