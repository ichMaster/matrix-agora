"""v5.18 — her videos' seam (`agents/video.py`, the markers in `agents/photo.py`): the `КРУЖЕЧОК:` / `ВІДЕО:` line cut
from her answer, the first frame's shot and aspect, the clip's English request, Omni Flash through the SDK's
interactions (polled, one retry), Kling Avatar on fal's queue (polled, one retry, the key to fal's host only), and
ffmpeg's fixed argvs — a block or a second failure a reason, never a crash (google-genai, aiohttp and ffmpeg mocked; no
network; made-up descriptions)."""

import asyncio
import base64
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from agents import video as vd
from agents.photo import Shot, photo_note, photo_request, split_photo
from agents.video import (
    CLIP_STYLE,
    FFMPEG_MP3,
    FRAME_ASPECT,
    FRAME_LINES,
    NOTE_MODEL,
    ClipMaker,
    NoteMaker,
    Video,
    clip_request,
    frame_shot,
    pcm_to_mp3,
    square_note,
)
from tests.test_photo import EVENING, image, maker

SECRET = "опис-5180"
KEY = "fal-key-5180"


async def no_sleep(s):
    return None


# --- the markers ----------------------------------------------------------------------------------------------------
def test_a_video_line_is_cut_and_the_last_media_line_of_any_kind_names_the_shot():
    assert split_photo("Ось що в мене\nКРУЖЕЧОК: я на балконі ввечері") == (
        "Ось що в мене", Shot("note", "я на балконі ввечері"))
    assert split_photo("Глянь\nВІДЕО: дощ на вікні") == ("Глянь", Shot("clip", "дощ на вікні"))
    assert split_photo("а\nФОТО: чашка\nб\nВІДЕО: море") == ("а\nб", Shot("clip", "море"))  # the last one counts
    assert split_photo("а\nКРУЖЕЧОК: кухня\nСЕЛФІ: я") == ("а", Shot("selfie", "я"))
    assert split_photo("Ось я знову [кружечок: я на кухні] 🙂") == ("Ось я знову 🙂", Shot("note", "я на кухні"))
    assert split_photo("Дивись\n[Відео: туман над містом]") == ("Дивись", Shot("clip", "туман над містом"))
    assert split_photo("Відео з концерту в мене десь є") == ("Відео з концерту в мене десь є", None)  # no colon
    assert photo_note("Ось", Shot("note", "я на кухні")) == "Ось\n[кружечок: я на кухні]"
    assert photo_note("Ось", Shot("clip", "море")) == "Ось\n[відео: море]"


# --- the frame ------------------------------------------------------------------------------------------------------
def test_a_notes_frame_is_her_square_selfie_and_a_clips_a_vertical_faceless_shot():
    assert frame_shot(Shot("note", SECRET)) == Shot("selfie", SECRET)
    assert frame_shot(Shot("clip", SECRET)) == Shot("photo", SECRET)
    assert frame_shot(Shot("photo", "чашка")) == Shot("photo", "чашка")
    assert FRAME_ASPECT == {"note": "1:1", "clip": "9:16"}
    request = photo_request(frame_shot(Shot("note", SECRET)), EVENING, FRAME_LINES["note"])
    assert request.endswith(FRAME_LINES["note"]) and "front-camera" in request and SECRET in request
    assert FRAME_LINES["note"] not in photo_request(Shot("selfie", SECRET), EVENING)


def test_the_frame_takes_its_aspect_and_its_line():
    photos, models, _ = maker(image(), image())
    asyncio.run(photos.make(frame_shot(Shot("note", "я")), EVENING, aspect="1:1", extra=FRAME_LINES["note"]))
    asyncio.run(photos.make(frame_shot(Shot("clip", "море")), EVENING, aspect="9:16", extra=FRAME_LINES["clip"]))
    (_, note_contents, note_config), (_, clip_contents, clip_config) = models.calls
    assert note_config.image_config.aspect_ratio == "1:1" and len(note_contents) == 5  # her four faces
    assert clip_config.image_config.aspect_ratio == "9:16" and len(clip_contents) == 1   # the prompt alone
    assert FRAME_LINES["note"] in note_contents[-1] and FRAME_LINES["clip"] in clip_contents[-1]


# --- the clip's request -----------------------------------------------------------------------------------------------
def test_the_clip_request_holds_her_words_her_moment_and_the_sound_line_in_english():
    request = clip_request(Shot("clip", f"дощ на вікні {SECRET}"), EVENING)
    assert SECRET in request and CLIP_STYLE in request and "evening in autumn, around 21:15, in Lviv" in request
    assert "no dialogue" in request and "Nobody's face" in request and "хмарно, +8, дрібний дощ" in request
    for word in ("ранок", "вечір", "осінь", "відео"):                                  # the template is English
        assert word not in request.replace(f"дощ на вікні {SECRET}", "").replace("хмарно, +8, дрібний дощ", "")


# --- Omni Flash -------------------------------------------------------------------------------------------------------
class StatusError(Exception):
    def __init__(self, code):
        super().__init__(f"HTTP {code}")
        self.status_code = code


def interaction(status, video=None, errors=None, usage=True):
    return SimpleNamespace(id="it-1", status=status, output_video=video, errors=errors,
                           usage=SimpleNamespace(total_input_tokens=1300, total_output_tokens=4200,
                                                 total_tokens=5500) if usage else None)


class Interactions:
    """The SDK's `aio.interactions`: `create` answers or raises in turn, `get` walks the given states."""

    def __init__(self, creates, gets=()):
        self.creates, self.gets, self.calls, self.polled = list(creates), list(gets), [], 0

    async def create(self, **kw):
        self.calls.append(kw)
        out = self.creates.pop(0)
        if isinstance(out, Exception):
            raise out
        return out

    async def get(self, id):
        self.polled += 1
        return self.gets.pop(0)


class Files:
    def __init__(self, data=b"MP4-uri"):
        self.data, self.asked = data, []

    async def download(self, file):
        self.asked.append(file)
        return self.data


def clips(creates, gets=(), files=None):
    seen = []
    sink = lambda kind, model, usage, ok, **kw: seen.append((kind, model, usage, ok, kw))
    inter, files = Interactions(creates, gets), files or Files()
    client = SimpleNamespace(aio=SimpleNamespace(interactions=inter, files=files))
    return ClipMaker(client, sink=sink, sleep=no_sleep), inter, files, seen


def done_by_uri():
    return interaction("completed", SimpleNamespace(data=None, uri="files/abc", mime_type="video/mp4"))


def test_a_clip_is_polled_to_its_end_fetched_by_its_uri_and_counted_as_video(caplog):
    caplog.set_level(logging.INFO)
    maker_, inter, files, seen = clips([interaction("queued")], [interaction("in_progress"), done_by_uri()])
    made = asyncio.run(maker_.make(Shot("clip", f"море {SECRET}"), EVENING, b"FRAME", "image/jpeg"))
    assert made == Video(b"MP4-uri", "video/mp4") and inter.polled == 2 and files.asked == ["files/abc"]
    call = inter.calls[0]
    assert call["model"] == "gemini-omni-1.1-flash" and call["background"] is True
    assert call["generation_config"] == {"video_config": {"task": "image_to_video"}}
    assert call["response_format"] == {"type": "video", "aspect_ratio": "9:16", "resolution": "720p",
                                       "delivery": "uri"}
    assert call["input"][0] == {"type": "image", "data": base64.b64encode(b"FRAME").decode(), "mime_type": "image/jpeg"}
    assert SECRET in call["input"][1]["text"]
    [(kind, model, usage, ok, kw)] = seen
    assert (kind, model, ok, kw) == ("video", "gemini-omni-1.1-flash", True, {})
    assert (usage.prompt_token_count, usage.candidates_token_count) == (1300, 4200)
    assert SECRET not in caplog.text and "files/abc" not in caplog.text


def test_an_inline_clip_is_decoded():
    inline = interaction("completed", SimpleNamespace(data=base64.b64encode(b"MP4-inline").decode(), uri=None,
                                                      mime_type="video/mp4"))
    maker_, _, files, _ = clips([inline])
    assert asyncio.run(maker_.make(Shot("clip", "море"), EVENING, b"F", "image/png")).data == b"MP4-inline"
    assert files.asked == []


def test_one_retry_on_a_server_error_then_a_reason_never_a_crash(caplog):
    caplog.set_level(logging.INFO)
    maker_, inter, _, seen = clips([StatusError(503), done_by_uri()])
    assert asyncio.run(maker_.make(Shot("clip", "море"), EVENING, b"F", "image/png")).why == "ok"
    assert len(inter.calls) == 2 and [s[3] for s in seen] == [False, True]
    maker_, inter, _, _ = clips([StatusError(503), TimeoutError()])
    assert asyncio.run(maker_.make(Shot("clip", "море"), EVENING, b"F", "image/png")) == Video(None, why="failed")
    maker_, inter, _, _ = clips([StatusError(400)])                                    # a 4xx: no second try
    assert asyncio.run(maker_.make(Shot("clip", "море"), EVENING, b"F", "image/png")).why == "failed"
    assert len(inter.calls) == 1 and "video: failed (TimeoutError)" in caplog.text


@pytest.mark.parametrize("final,why", [
    (interaction("failed", errors=[SimpleNamespace(code="400", message="Blocked by the safety filter")]), "blocked"),
    (interaction("completed", video=None), "blocked"),
    (interaction("failed", errors=[SimpleNamespace(code="500", message="internal")]), "failed"),
    (interaction("cancelled"), "failed"),
])
def test_a_block_or_a_failed_interaction_is_a_reason(final, why):
    maker_, _, _, seen = clips([interaction("in_progress")], [final])
    assert asyncio.run(maker_.make(Shot("clip", "море"), EVENING, b"F", "image/png")) == Video(None, why=why)
    assert seen[-1][3] is False and (seen[-1][4] == {"blocked": "answer"}) == (why == "blocked")


def test_a_clip_that_never_ends_is_a_timeout(monkeypatch):
    maker_, inter, _, _ = clips([interaction("queued"), interaction("queued")],
                                [interaction("in_progress")] * 1000)
    maker_._timeout_s = 0.01

    async def slow(s):
        await asyncio.sleep(0.005)
    maker_._sleep = slow
    assert asyncio.run(maker_.make(Shot("clip", "море"), EVENING, b"F", "image/png")).why == "failed"
    assert len(inter.calls) == 2                                                          # retried once


# --- Kling Avatar on fal ----------------------------------------------------------------------------------------------
class FakeResponse:
    def __init__(self, status, data=None, body=b""):
        self.status, self.data, self.body = status, data, body

    async def json(self, content_type=None):
        if self.data is None:
            raise ValueError("no json")
        return self.data

    async def read(self):
        return self.body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeSession:
    """fal's queue and its storage: answers in turn; keeps each call's method, URL, headers and body."""

    def __init__(self, replies, seen):
        self.replies, self.seen = replies, seen

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def request(self, method, url, headers=None, json=None):
        self.seen.append((method, url, headers, json))
        return self.replies.pop(0)

    def get(self, url, headers=None):
        self.seen.append(("GET", url, headers, None))
        return self.replies.pop(0)


STATUS = "https://queue.fal.run/fal-ai/kling-video/requests/r1/status"
RESULT = "https://queue.fal.run/fal-ai/kling-video/requests/r1"
CDN = "https://v3.fal.media/files/abc/note.mp4"


def submitted():
    return FakeResponse(200, {"request_id": "r1", "status_url": STATUS, "response_url": RESULT})


def finished(duration=12.4):
    return [FakeResponse(200, {"status": "IN_PROGRESS"}), FakeResponse(200, {"status": "COMPLETED"}),
            FakeResponse(200, {"video": {"url": CDN, "content_type": "video/mp4"}, "duration": duration}),
            FakeResponse(200, body=b"MP4-note")]


def notes(monkeypatch, *replies):
    seen, sinks = [], []
    queue = list(replies)
    monkeypatch.setattr(vd, "ClientSession", lambda **kw: FakeSession(queue, seen))
    sink = lambda model, video_ms, ok, blocked: sinks.append((model, video_ms, ok, blocked))
    return NoteMaker(KEY, sink=sink, sleep=no_sleep), seen, sinks


def test_a_note_is_submitted_polled_and_fetched_with_the_key_only_on_fals_queue(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    note, seen, sinks = notes(monkeypatch, submitted(), *finished())
    made = asyncio.run(note.make(b"FRAME", "image/png", b"MP3"))
    assert made == Video(b"MP4-note", "video/mp4", 12.4)
    method, url, headers, body = seen[0]
    assert (method, url) == ("POST", f"https://queue.fal.run/{NOTE_MODEL}")
    assert headers["Authorization"] == f"Key {KEY}"
    assert body["image_url"] == "data:image/png;base64," + base64.b64encode(b"FRAME").decode()
    assert body["audio_url"] == "data:audio/mpeg;base64," + base64.b64encode(b"MP3").decode()
    assert [s[1] for s in seen[1:]] == [STATUS, STATUS, RESULT, CDN]
    assert all(s[2]["Authorization"] == f"Key {KEY}" for s in seen[:4]) and seen[4][2] is None  # never to the CDN
    assert sinks == [(NOTE_MODEL, 12400, True, None)]
    for secret in (KEY, CDN, STATUS, "base64"):
        assert secret not in caplog.text
    assert KEY not in repr(note)


def test_one_retry_on_a_5xx_then_a_reason(monkeypatch, caplog):
    note, _, sinks = notes(monkeypatch, FakeResponse(503, {"detail": "busy"}), submitted(), *finished())
    assert asyncio.run(note.make(b"F", "image/png", b"M")).why == "ok" and [s[2] for s in sinks] == [False, True]
    note, _, sinks = notes(monkeypatch, FakeResponse(502), FakeResponse(503))
    assert asyncio.run(note.make(b"F", "image/png", b"M")) == Video(None, why="failed")
    assert sinks == [(NOTE_MODEL, None, False, None)] * 2


def test_a_content_check_is_blocked_and_another_4xx_failed(monkeypatch):
    note, _, sinks = notes(monkeypatch, submitted(), FakeResponse(200, {"status": "COMPLETED"}),
                           FakeResponse(422, {"detail": [{"type": "content_policy_violation", "msg": "flagged"}]}))
    assert asyncio.run(note.make(b"F", "image/png", b"M")) == Video(None, why="blocked")
    assert sinks == [(NOTE_MODEL, None, False, "answer")]
    note, seen, _ = notes(monkeypatch, FakeResponse(400, {"detail": "bad audio"}))
    assert asyncio.run(note.make(b"F", "image/png", b"M")).why == "failed" and len(seen) == 1   # no second try
    note, _, _ = notes(monkeypatch, submitted(), FakeResponse(200, {"status": "COMPLETED"}), FakeResponse(200, {}))
    assert asyncio.run(note.make(b"F", "image/png", b"M")).why == "blocked"                    # no video in it


def test_an_unknown_model_is_the_standard_one():
    assert NoteMaker(KEY, model="fal-ai/other").model == NOTE_MODEL
    assert NoteMaker(KEY, model="fal-ai/kling-video/ai-avatar/v2/pro").model.endswith("/pro")


# --- ffmpeg -----------------------------------------------------------------------------------------------------------
class FakeProc:
    def __init__(self, code, out, on_run=None):
        self.returncode, self.out, self.input, self.on_run = code, out, None, on_run

    async def communicate(self, input=None):
        self.input = input
        if self.on_run:
            self.on_run()
        return self.out, b""


def test_the_mp3_runs_the_fixed_argv(monkeypatch):
    seen = {}

    async def fake_exec(*argv, **kw):
        seen["argv"], seen["proc"] = argv, FakeProc(0, b"ID3...")
        return seen["proc"]

    monkeypatch.setattr(vd.asyncio, "create_subprocess_exec", fake_exec)
    assert asyncio.run(pcm_to_mp3(b"\x00\x00" * 8)) == b"ID3..."
    assert seen["argv"] == FFMPEG_MP3 and seen["proc"].input == b"\x00\x00" * 8
    assert FFMPEG_MP3[FFMPEG_MP3.index("-c:a") + 1] == "libmp3lame"


def test_the_square_cut_runs_through_a_private_folder_removed_after(monkeypatch):
    seen = {}

    async def fake_exec(*argv, **kw):
        src, dst = argv[argv.index("-i") + 1], argv[-1]
        seen["argv"], seen["src"] = argv, src
        seen["mode"] = Path(src).parent.stat().st_mode & 0o777
        seen["in"] = Path(src).read_bytes()
        return FakeProc(0, b"", on_run=lambda: Path(dst).write_bytes(b"SQUARE"))

    monkeypatch.setattr(vd.asyncio, "create_subprocess_exec", fake_exec)
    assert asyncio.run(square_note(b"MP4")) == b"SQUARE"
    assert seen["in"] == b"MP4" and seen["mode"] == 0o700 and not Path(seen["src"]).parent.exists()
    argv = seen["argv"]
    assert argv[argv.index("-vf") + 1] == vd.NOTE_FILTER and "640:640" in vd.NOTE_FILTER
    assert argv[argv.index("-t") + 1] == "60" and argv[argv.index("-movflags") + 1] == "+faststart"


@pytest.mark.parametrize("code", [1, 0])
def test_a_failed_cut_is_none(monkeypatch, caplog, code):
    async def fake_exec(*argv, **kw):
        return FakeProc(code, b"")                                                     # exit 0, no file written

    monkeypatch.setattr(vd.asyncio, "create_subprocess_exec", fake_exec)
    assert asyncio.run(square_note(b"MP4")) is None
    assert asyncio.run(pcm_to_mp3(b"\x00\x00")) is None


def test_no_ffmpeg_is_none(monkeypatch):
    async def missing(*argv, **kw):
        raise FileNotFoundError("ffmpeg")

    monkeypatch.setattr(vd.asyncio, "create_subprocess_exec", missing)
    assert asyncio.run(pcm_to_mp3(b"\x00\x00")) is None and asyncio.run(square_note(b"M")) is None


# --- until its flow (AGORA-166) ----------------------------------------------------------------------------------------
@pytest.fixture
def ogg(monkeypatch):
    from agents import agent as agent_mod

    async def encode(pcm, timeout_s=60.0):
        return b"OggS-kira"
    monkeypatch.setattr(agent_mod, "encode_opus", encode)


def test_a_video_line_is_never_made_a_photo(tmp_path, monkeypatch, ogg, caplog):
    from tests.test_photo_route import her
    from tests.test_private_runtime import ms
    caplog.set_level(logging.INFO)
    agent = her(tmp_path, monkeypatch, "Ось я\nКРУЖЕЧОК: я на балконі")
    agent.private_line("запиши кружечок", ms(17), "telegram", "tg:1")
    assert asyncio.run(agent.private_reply()) is True
    assert agent.photos.shots == [] and agent.sent == ["voice", ("text", "Ось я")]
    assert "video: dropped (off)" in caplog.text
