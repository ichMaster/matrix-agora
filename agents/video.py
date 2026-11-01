"""v5.18 — Кіра's videos in Telegram: her кружечок in her own voice, and short clips of what she sees.

A last line of her answer names one (`КРУЖЕЧОК: …` / `ВІДЕО: …`, cut by `agents/photo.py`'s `split_photo`). Its first
frame is her photo, made by the image model (`frame_shot`, `FRAME_ASPECT`, `FRAME_LINES`): a front-camera close-up of
her for a кружечок, a vertical faceless shot for a clip.
- **The кружечок:** VEED Fabric 1.0 on fal.ai (the owner, after the live test; Kling AI Avatar v2 stays a choice)
  takes the frame and her voice (her answer, voiced by ElevenLabs; mp3 through ffmpeg), both put on fal's storage
  first, and returns her face speaking it (`NoteMaker`, fal's queue API); ffmpeg cuts it square for Telegram's round
  video message (`square_note`).
- **The clip:** Gemini Omni Flash takes the frame and an English request (`clip_request`, pure) and returns a short
  video with the sound of the place and no speech (`ClipMaker`, the SDK's interactions in the background, polled).

Each maker retries once on a server error or a timeout; a block, or a second failure, is a reason, never a crash. The
log holds outcomes and types only — never her description, a request, the key or a URL.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import aiohttp
from google import genai
from google.genai import errors as genai_errors

from agents.photo import Moment, Shot, moment_line
from agents.voice import RATE

log = logging.getLogger("agent.video")

KINDS = ("note", "clip")
USAGE_KINDS = ("video", "video_note")  # the usage lines a video is paid by (review #1: the day's cap counts them)
KEY_VAR = "FAL_KEY"                # server/kira.env: fal.ai/dashboard/keys, preset API (docs/fal-ai.md)
MODEL = "gemini-omni-1.1-flash"    # the owner, 2026-11-01: Google's video model for her clips
RESOLUTIONS = ("720p", "1080p")
NOTE_MODEL = "veed/fabric-1.0"     # the owner, 2026-11-01: $0.08 a second, ~40 s for 17 s of her voice (Kling: ~10 min)
QUEUE_URL = "https://queue.fal.run"
QUEUE_HOST = urlsplit(QUEUE_URL).hostname
UPLOAD_URL = "https://rest.alpha.fal.ai/storage/upload/initiate?storage_type=fal-cdn-v3"  # Fabric takes no data URI
UPLOAD_HOST = urlsplit(UPLOAD_URL).hostname
FILE_NAMES = {"image/jpeg": "frame.jpg", "image/png": "frame.png", "audio/mpeg": "voice.mp3"}
POLL_S = 10.0
NOTE_POLL_S = 3.0                  # a кружечок takes under a minute now: its status is asked more often (free)
TIMEOUT_S = 600.0                  # minutes are expected; neither service names a time
NOTE_SIDE = 640                    # Telegram's round video message: a square, at most 640 px
NOTE_MAX_S = 60                    # … and at most a minute
NOTE_LEAD_MS = 1000                # the owner (live test): Telegram cut her first sound, 0.3 s of silence too little
WORKING = ("queued", "in_progress")                    # the interaction's states before a final one
FAL_WORKING = ("IN_QUEUE", "IN_PROGRESS")
BLOCK_WORDS = ("safety", "policy", "prohibited", "blocked", "nsfw", "moderation")

FRAME_ASPECT = {"note": "1:1", "clip": "9:16"}
FRAME_LINES = {
    "note": ("This is a front-camera selfie, the first frame of a round video message: her face and shoulders fill the "
             "square frame, she looks into the camera, her mouth relaxed and closed, as if about to speak."),
    "clip": "This is the first frame of a short vertical phone video.",
}
CLIP_STYLE = ("A handheld phone video with natural motion, as someone films what they see. The sound of the place only: "
              "no dialogue, no voice, no narration, no music. No text, caption or watermark. Nobody's face.")
NOTE_PROMPT = "She talks to the front camera of her phone, with natural small head movements and blinks."
NOTE_MODELS = {  # each model's own fields beside the frame and the voice (fal's pricing API, 2026-11-01)
    NOTE_MODEL: {"resolution": "480p"},                                   # cut to 640×640 anyway
    "fal-ai/kling-video/ai-avatar/v2/standard": {"prompt": NOTE_PROMPT},  # $0.0562 a second
    "fal-ai/kling-video/ai-avatar/v2/pro": {"prompt": NOTE_PROMPT},       # $0.115 a second
}

# her private brief's skill (v5.18, the owner): understood from the talk, never a keyword — and never a word that a
# video is made: she records it
NOTE_SKILL = (
    "Ти можеш записати Ich кружечок — коротке відеоповідомлення, де ти кажеш йому свою відповідь у камеру телефона, — "
    "коли він просить або коли тобі самій хочеться, щоб він тебе побачив і почув. Тоді напиши відповідь як завжди, щоб уголос вона була не довша за пів хвилини, а в самому кінці додай окремий "
    "останній рядок: слово КРУЖЕЧОК великими літерами, двокрапка і де ти зараз і що навколо тебе, одним реченням."
)
CLIP_SKILL = (
    "Ти можеш зняти для Ich коротке відео того, що бачиш, — без себе в кадрі й без слів, лише звуки місця, — коли він "
    "просить або коли тобі самій хочеться щось йому показати. Тоді в самому кінці додай окремий останній рядок: слово ВІДЕО великими літерами, двокрапка і що на відео, одним реченням."
)
SKILL_TAIL = ("Відео приходить йому трохи пізніше за твої слова. В одній відповіді — щонайбільше одне фото чи відео. "
              "Не хочеш чи не можеш зараз — просто скажи це своїми словами.")
VIDEO_FAILED = ("Відео, яке ти щойно хотіла надіслати Ich, не надіслалося. Скажи про це дуже коротко, одним реченням, "
                "своїми словами, або нічого не кажи. Нічого нового не обіцяй.")


def video_skill(kinds: tuple[str, ...]) -> str:
    """Her video skill for the kinds she may send now (pure): the кружечок, the clip, or both; empty for none."""
    parts = [NOTE_SKILL] * ("note" in kinds) + [CLIP_SKILL] * ("clip" in kinds)
    return " ".join([*parts, SKILL_TAIL]) if parts else ""


def ffmpeg_mp3(lead_ms: int = NOTE_LEAD_MS) -> tuple[str, ...]:
    """The fixed argv of her voice for a кружечок: PCM → mp3, after `lead_ms` of silence (`VIDEO_NOTE_LEAD_MS`) — in
    the video fal makes from it too, so her lips keep time; only the number varies."""
    return ("ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "s16le", "-ar", str(RATE), "-ac", "1",
            "-i", "pipe:0", "-af", f"adelay={max(0, int(lead_ms))}:all=1", "-c:a", "libmp3lame", "-b:a", "96k",
            "-f", "mp3", "pipe:1")


NOTE_FILTER = f"crop='min(iw,ih)':'min(iw,ih)',scale={NOTE_SIDE}:{NOTE_SIDE},setsar=1"
# the owner, 2026-11-01: a round video message needs no big picture — her frame goes to fal at 640×640, a small JPEG
FFMPEG_FRAME = ("ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0", "-vf", NOTE_FILTER, "-frames:v", "1",
                "-q:v", "3", "-c:v", "mjpeg", "-f", "image2", "pipe:1")


def ffmpeg_square(src: str, voice: str, dst: str) -> tuple[str, ...]:
    """The fixed argv that cuts a video square for a round video message: the centre square, 640×640, H.264, with her
    own voice as its sound (review #3: fal's output may carry none) in AAC, at most a minute, `+faststart` — only the
    three temporary paths vary, never a word of hers."""
    return ("ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", src, "-i", voice,
            "-map", "0:v:0", "-map", "1:a:0", "-t", str(NOTE_MAX_S), "-shortest",
            "-vf", NOTE_FILTER, "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", dst)


@dataclass(frozen=True)
class Video:
    data: bytes | None
    mime: str = "video/mp4"
    seconds: float | None = None
    why: str = "ok"    # `ok` | `blocked` (a filter, or no video) | `failed` (an error after the retry)


def frame_shot(shot: Shot) -> Shot:
    """The photo a video starts from: her кружечок is a selfie of her, a clip a shot of what she sees (pure)."""
    return Shot({"note": "selfie", "clip": "photo"}.get(shot.kind, shot.kind), shot.description)


def clip_request(shot: Shot, moment: Moment) -> str:
    """Omni Flash's instruction (pure, English): the shot in her words, her moment, a phone video's look and sound."""
    return "\n".join([f"The video, as she describes it (in Ukrainian): {shot.description}", moment_line(moment),
                      CLIP_STYLE])


def _retryable(exc: BaseException) -> bool:
    """A server error or a dropped connection, worth one more try: the SDK's `ServerError`, the interactions client's
    5xx status errors (`status_code`) and its connection or timeout errors, a timeout."""
    if isinstance(exc, genai_errors.ServerError | TimeoutError):
        return True
    code = getattr(exc, "status_code", None)
    return (isinstance(code, int) and code >= 500) or type(exc).__name__ in ("APIConnectionError", "APITimeoutError")


def _blocked_words(text: str | None) -> bool:
    low = (text or "").lower()
    return any(w in low for w in BLOCK_WORDS)


class _Retry(Exception):
    """A server error worth one more try (5xx, a dropped connection)."""


class _Blocked(Exception):
    pass


class ClipMaker:
    """Gemini Omni Flash through the SDK (`client.aio.interactions`, in the background, polled), from her frame."""

    def __init__(self, client, model: str = MODEL, resolution: str = "720p", sink: Callable | None = None,
                 poll_s: float = POLL_S, timeout_s: float = TIMEOUT_S,
                 sleep: Callable[[float], Awaitable] = asyncio.sleep) -> None:
        self._client, self.model = client, model
        self.resolution = resolution if resolution in RESOLUTIONS else "720p"
        self._sink, self._poll_s, self._timeout_s, self._sleep = sink, poll_s, timeout_s, sleep

    def _report(self, usage, ok: bool, blocked: str | None = None) -> None:
        if self._sink is None:
            return
        try:
            if blocked:
                self._sink("video", self.model, usage, ok, blocked=blocked)
            else:
                self._sink("video", self.model, usage, ok)
        except Exception:
            log.exception("usage accounting failed")

    async def make(self, shot: Shot, moment: Moment, frame: bytes, mime: str) -> Video:
        """The clip, or why there is none: one retry on a server error or a timeout before the job is accepted — never
        once it is (review #2: it would run and be billed twice); a block is final."""
        request = clip_request(shot, moment)
        for attempt in (1, 2):
            submitted: list = []
            try:
                done = await asyncio.wait_for(self._run(request, frame, mime, submitted), self._timeout_s)
            except Exception as exc:  # noqa: BLE001 — any provider failure: no clip, never a crash
                self._report(None, False)
                if attempt == 1 and not submitted and _retryable(exc):
                    log.info("video: %s — once more", type(exc).__name__)
                    continue
                log.warning("video: failed (%s)", type(exc).__name__)
                return Video(None, why="failed")
            return await self._result(done)
        return Video(None, why="failed")  # never reached: the loop returns

    async def _run(self, request: str, frame: bytes, mime: str, submitted: list):
        interactions = self._client.aio.interactions
        it = await interactions.create(
            model=self.model,
            input=[{"type": "image", "data": base64.b64encode(frame).decode("ascii"), "mime_type": mime},
                   {"type": "text", "text": request}],
            response_format={"type": "video", "aspect_ratio": "9:16", "resolution": self.resolution,
                             "delivery": "uri"},
            generation_config={"video_config": {"task": "image_to_video"}},
            background=True)
        submitted.append(True)
        while getattr(it, "status", None) in WORKING:
            await self._sleep(self._poll_s)
            try:
                it = await interactions.get(it.id)
            except Exception as exc:  # review #2: the job is accepted — a server error asks again, never resubmits
                if not _retryable(exc):
                    raise
                log.info("video: %s while waiting — asking again", type(exc).__name__)
        return it

    async def _result(self, it) -> Video:
        raw = getattr(it, "usage", None)
        usage = None if raw is None else SimpleNamespace(
            prompt_token_count=getattr(raw, "total_input_tokens", None),
            candidates_token_count=getattr(raw, "total_output_tokens", None),
            total_token_count=getattr(raw, "total_tokens", None))
        status = getattr(it, "status", None)
        video = getattr(it, "output_video", None)
        if status != "completed" or video is None:
            errors = getattr(it, "errors", None) or []
            said = " ".join(f"{getattr(e, 'code', '') or ''} {getattr(e, 'message', '') or ''}" for e in errors)
            blocked = status == "completed" or _blocked_words(said)
            self._report(usage, False, "answer" if blocked else None)
            log.warning("video: %s (%s)", "blocked" if blocked else "failed", status)
            return Video(None, why="blocked" if blocked else "failed")
        try:
            if getattr(video, "data", None):
                data = base64.b64decode(video.data)
            else:
                data = await self._client.aio.files.download(file=video.uri)
        except Exception as exc:  # noqa: BLE001 — made but not fetched: no clip, never a crash
            self._report(usage, False)
            log.warning("video: not fetched (%s)", type(exc).__name__)
            return Video(None, why="failed")
        if not data:
            self._report(usage, False, "answer")
            log.warning("video: blocked (empty)")
            return Video(None, why="blocked")
        self._report(usage, True)
        return Video(data, getattr(video, "mime_type", None) or "video/mp4")


ClientSession = aiohttp.ClientSession  # the seam: a test passes its own (tests/conftest.py guards the network)
NoteSink = Callable[[str, int | None, bool, str | None], None]  # (model, video ms, ok, blocked)


class NoteMaker:
    """Her кружечок's model on fal (the queue API; VEED Fabric 1.0 or Kling AI Avatar v2): her frame and her voice, put
    on fal's storage, → her face speaking it."""

    def __init__(self, key: str, model: str = NOTE_MODEL, sink: NoteSink | None = None, poll_s: float = NOTE_POLL_S,
                 timeout_s: float = TIMEOUT_S, sleep: Callable[[float], Awaitable] = asyncio.sleep) -> None:
        self._key = key
        self.model = model if model in NOTE_MODELS else NOTE_MODEL
        self._sink, self._poll_s, self._timeout_s, self._sleep = sink, poll_s, timeout_s, sleep

    def __repr__(self) -> str:  # never the key
        return f"NoteMaker(model={self.model!r})"

    def _report(self, video_ms: int | None, ok: bool, blocked: str | None = None) -> None:
        if self._sink is None:
            return
        try:
            self._sink(self.model, video_ms, ok, blocked)
        except Exception:
            log.exception("usage accounting failed")

    async def make(self, frame: bytes, frame_mime: str, mp3: bytes, seconds: float | None = None) -> Video:
        """Her кружечок before the square cut, or why there is none: one retry on a 5xx or a timeout before fal accepts
        the job — never once it has (review #2: it would run and be billed twice). `seconds` (her voice's length) is
        the video's when fal names none (Fabric does not)."""
        files = ((frame, frame_mime), (mp3, "audio/mpeg"))
        for attempt in (1, 2):
            submitted: list = []
            try:
                return await asyncio.wait_for(self._run(files, seconds, submitted), self._timeout_s)
            except (_Retry, TimeoutError, aiohttp.ClientConnectionError) as exc:
                self._report(None, False)
                if submitted and isinstance(exc, TimeoutError):  # the live test: a job still queued is never paid for
                    await self._cancel(submitted[0])
                if attempt == 1 and not submitted:
                    log.info("video: %s — once more", type(exc).__name__)
                    continue
                log.warning("video: failed (%s)", type(exc).__name__)
                return Video(None, why="failed")
            except _Blocked:
                self._report(None, False, "answer")
                log.warning("video: blocked (fal)")
                return Video(None, why="blocked")
            except Exception as exc:  # noqa: BLE001 — any other failure: no кружечок, never a crash
                self._report(None, False)
                log.warning("video: failed (%s)", type(exc).__name__)
                return Video(None, why="failed")
        return Video(None, why="failed")  # never reached: the loop returns

    async def _queue(self, session, method: str, url: str, **kw) -> dict:
        """One call to fal's queue or its upload — the key goes to those hosts only, never elsewhere."""
        if urlsplit(url).hostname not in (QUEUE_HOST, UPLOAD_HOST):
            raise ValueError("not fal's queue")
        headers = {"Authorization": f"Key {self._key}", "Content-Type": "application/json"}
        async with session.request(method, url, headers=headers, **kw) as resp:
            try:
                data = await resp.json(content_type=None)
            except ValueError:
                data = None
            if resp.status >= 500:
                raise _Retry(f"HTTP {resp.status}")
            if resp.status >= 400:
                detail = data.get("detail") if isinstance(data, dict) else None
                if _blocked_words(str(detail)):
                    raise _Blocked
                # the live test: fal locks an account whose credits ran out — the log names that, never fal's words
                log.warning("video: fal HTTP %s%s", resp.status,
                            " (balance exhausted)" if "balance" in str(detail).lower() else "")
                raise RuntimeError(f"HTTP {resp.status}")
            return data if isinstance(data, dict) else {}

    async def _again(self, call):
        """Review #2: once fal has the job, a 5xx or a dropped connection asks again (within `make`'s timeout)."""
        while True:
            try:
                return await call()
            except (_Retry, aiohttp.ClientConnectionError) as exc:
                log.info("video: %s while waiting — asking again", type(exc).__name__)
                await self._sleep(self._poll_s)

    async def _upload(self, session, data: bytes, mime: str) -> str:
        """A file put on fal's storage for the job (the live test: Fabric takes no data URI): fal names a signed URL to
        put it to — no key sent there — and the file's own URL, which the job names."""
        init = await self._queue(session, "POST", UPLOAD_URL,
                                 json={"content_type": mime, "file_name": FILE_NAMES.get(mime, "file")})
        upload_url, file_url = init.get("upload_url"), init.get("file_url")
        if not upload_url or not file_url:
            raise RuntimeError("no upload")
        async with session.put(upload_url, data=data, headers={"Content-Type": mime}) as resp:
            if resp.status >= 500:
                raise _Retry(f"HTTP {resp.status}")
            if resp.status >= 300:
                raise RuntimeError(f"HTTP {resp.status}")
        return file_url

    async def _download(self, session, url: str) -> bytes:
        async with session.get(url) as resp:  # fal's storage: no key sent there
            if resp.status >= 500:
                raise _Retry(f"HTTP {resp.status}")
            if resp.status != 200:
                raise RuntimeError(f"HTTP {resp.status}")
            return await resp.read()

    async def _cancel(self, cancel_url: str | None) -> None:
        """A job that ran out of time is cancelled, so fal never bills one still in its queue (one that already runs
        cannot be); best effort, by outcome only."""
        if not cancel_url:
            return
        try:
            async with ClientSession() as session:
                await asyncio.wait_for(self._queue(session, "PUT", cancel_url), 15)
            log.info("video: fal job cancelled")
        except Exception as exc:  # noqa: BLE001 — already running or done: nothing to undo
            log.info("video: fal job not cancelled (%s)", type(exc).__name__)

    async def _run(self, files: tuple, hint: float | None, submitted: list) -> Video:
        async with ClientSession() as session:
            image_url, audio_url = [await self._upload(session, data, mime) for data, mime in files]
            body = {"image_url": image_url, "audio_url": audio_url, **NOTE_MODELS[self.model]}
            sent = await self._queue(session, "POST", f"{QUEUE_URL}/{self.model}", json=body)
            status_url, response_url = sent.get("status_url"), sent.get("response_url")
            if not status_url or not response_url:
                raise RuntimeError("no request")
            submitted.append(sent.get("cancel_url"))
            seen = None
            while True:
                status = await self._again(lambda: self._queue(session, "GET", status_url))
                state, place = status.get("status"), status.get("queue_position")
                if (state, place) != seen:  # the live test: where the minutes go — fal's state, never a URL
                    seen = (state, place)
                    log.info("video: fal %s%s", state, f" (queue {place})" if isinstance(place, int) else "")
                if state not in FAL_WORKING:
                    break
                await self._sleep(self._poll_s)
            result = await self._again(lambda: self._queue(session, "GET", response_url))
            video = result.get("video") if isinstance(result.get("video"), dict) else {}
            if not video.get("url"):
                raise _Blocked
            data = await self._again(lambda: self._download(session, video["url"]))
        seconds = result.get("duration")
        seconds = float(seconds) if isinstance(seconds, int | float) and not isinstance(seconds, bool) else hint
        if not data:
            raise _Blocked
        self._report(round(seconds * 1000) if seconds is not None else None, True)
        return Video(data, video.get("content_type") or "video/mp4", seconds)


async def _ffmpeg(argv: tuple[str, ...], data: bytes | None, timeout_s: float, what: str) -> bytes | None:
    try:
        proc = await asyncio.create_subprocess_exec(*argv, stdin=asyncio.subprocess.PIPE if data is not None else None,
                                                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    except OSError as exc:
        log.error("%s failed: %s", what, type(exc).__name__)
        return None
    try:
        out, _ = await asyncio.wait_for(proc.communicate(input=data), timeout=timeout_s)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        log.error("%s timed out after %.0fs", what, timeout_s)
        return None
    if proc.returncode != 0:
        log.error("%s failed: ffmpeg exit %s", what, proc.returncode)
        return None
    return out if out is not None else b""


async def shrink_frame(image: bytes, timeout_s: float = 30.0) -> bytes | None:
    """Her кружечок's frame as a 640×640 JPEG for fal (the owner: a кружечок needs no big picture), through ffmpeg's
    fixed argv; None on any failure (logged by its code) — the caller then sends the frame as made."""
    out = await _ffmpeg(FFMPEG_FRAME, image, timeout_s, "frame")
    return out or None


async def pcm_to_mp3(pcm: bytes, lead_ms: int = NOTE_LEAD_MS, timeout_s: float = 60.0) -> bytes | None:
    """Her voice's PCM → mp3 for fal, after `lead_ms` of silence, through ffmpeg's fixed argv; None on any failure
    (logged by its code)."""
    out = await _ffmpeg(ffmpeg_mp3(lead_ms), pcm, timeout_s, "mp3")
    return out or None


async def square_note(mp4: bytes, mp3: bytes, timeout_s: float = 120.0) -> bytes | None:
    """A video cut square for a round video message, her voice (`mp3`) its sound, through temporary files in a 0700
    folder removed after; None on any failure (logged by its code)."""
    with tempfile.TemporaryDirectory(prefix="note-") as folder:  # mkdtemp: 0700
        src, voice, dst = Path(folder) / "in.mp4", Path(folder) / "voice.mp3", Path(folder) / "out.mp4"
        for path, data in ((src, mp4), (voice, mp3)):
            with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as out:
                out.write(data)
        if await _ffmpeg(ffmpeg_square(str(src), str(voice), str(dst)), None, timeout_s, "square") is None:
            return None
        try:
            data = dst.read_bytes()
        except OSError as exc:
            log.error("square failed: %s", type(exc).__name__)
            return None
    return data or None


def clip_maker(model: str, resolution: str, sink: Callable) -> ClipMaker:
    """Her clips on Google's video model, through a client of their own (the Gemini key from the environment)."""
    return ClipMaker(genai.Client(), model or MODEL, resolution, sink)
