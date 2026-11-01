"""v5.18 — Кіра's videos in Telegram: her кружечок in her own voice, and short clips of what she sees.

A last line of her answer names one (`КРУЖЕЧОК: …` / `ВІДЕО: …`, cut by `agents/photo.py`'s `split_photo`). Its first
frame is her photo, made by the image model (`frame_shot`, `FRAME_ASPECT`, `FRAME_LINES`): a front-camera close-up of
her for a кружечок, a vertical faceless shot for a clip.
- **The кружечок:** Kling AI Avatar v2 on fal.ai takes the frame and her voice (her answer, voiced by ElevenLabs; mp3
  through ffmpeg) and returns her face speaking it (`NoteMaker`, fal's queue API); ffmpeg cuts it square for
  Telegram's round video message (`square_note`).
- **The clip:** Gemini Omni Flash takes the frame and an English request (`clip_request`, pure) and returns a short
  video with the sound of the place and no speech (`ClipMaker`, the SDK's interactions in the background, polled).

Each maker retries once on a server error or a timeout; a block, or a second failure, is a reason, never a crash. The
log holds outcomes and types only — never her description, a request, the key, a data URI or a URL.
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
KEY_VAR = "FAL_KEY"                # server/kira.env: fal.ai/dashboard/keys, preset API (docs/fal-ai.md)
MODEL = "gemini-omni-1.1-flash"    # the owner, 2026-11-01: Google's video model for her clips
RESOLUTIONS = ("720p", "1080p")
NOTE_MODEL = "fal-ai/kling-video/ai-avatar/v2/standard"   # $0.0562 a second (fal's pricing API, 2026-11-01)
NOTE_MODELS = (NOTE_MODEL, "fal-ai/kling-video/ai-avatar/v2/pro")  # Pro: $0.115 a second
QUEUE_URL = "https://queue.fal.run"
QUEUE_HOST = urlsplit(QUEUE_URL).hostname
POLL_S = 10.0
TIMEOUT_S = 600.0                  # minutes are expected; neither service names a time
NOTE_SIDE = 640                    # Telegram's round video message: a square, at most 640 px
NOTE_MAX_S = 60                    # … and at most a minute
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
FFMPEG_MP3 = ("ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "s16le", "-ar", str(RATE), "-ac", "1",
              "-i", "pipe:0", "-c:a", "libmp3lame", "-b:a", "96k", "-f", "mp3", "pipe:1")
NOTE_FILTER = f"crop='min(iw,ih)':'min(iw,ih)',scale={NOTE_SIDE}:{NOTE_SIDE},setsar=1"


def ffmpeg_square(src: str, dst: str) -> tuple[str, ...]:
    """The fixed argv that cuts a video square for a round video message: the centre square, 640×640, H.264 + AAC, at
    most a minute, `+faststart` — only the two temporary paths vary, never a word of hers."""
    return ("ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", src, "-t", str(NOTE_MAX_S),
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


def data_uri(data: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


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
        """The clip, or why there is none: one retry on a server error or a timeout; a block is final."""
        request = clip_request(shot, moment)
        for attempt in (1, 2):
            try:
                done = await asyncio.wait_for(self._run(request, frame, mime), self._timeout_s)
            except Exception as exc:  # noqa: BLE001 — any provider failure: no clip, never a crash
                self._report(None, False)
                if attempt == 1 and _retryable(exc):
                    log.info("video: %s — once more", type(exc).__name__)
                    continue
                log.warning("video: failed (%s)", type(exc).__name__)
                return Video(None, why="failed")
            return await self._result(done)
        return Video(None, why="failed")  # never reached: the loop returns

    async def _run(self, request: str, frame: bytes, mime: str):
        interactions = self._client.aio.interactions
        it = await interactions.create(
            model=self.model,
            input=[{"type": "image", "data": base64.b64encode(frame).decode("ascii"), "mime_type": mime},
                   {"type": "text", "text": request}],
            response_format={"type": "video", "aspect_ratio": "9:16", "resolution": self.resolution,
                             "delivery": "uri"},
            generation_config={"video_config": {"task": "image_to_video"}},
            background=True)
        while getattr(it, "status", None) in WORKING:
            await self._sleep(self._poll_s)
            it = await interactions.get(it.id)
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
    """Kling AI Avatar v2 on fal (the queue API): her frame and her voice → her face speaking it."""

    def __init__(self, key: str, model: str = NOTE_MODEL, sink: NoteSink | None = None, poll_s: float = POLL_S,
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

    async def make(self, frame: bytes, frame_mime: str, mp3: bytes) -> Video:
        """Her кружечок before the square cut, or why there is none: one retry on a 5xx or a timeout."""
        body = {"image_url": data_uri(frame, frame_mime), "audio_url": data_uri(mp3, "audio/mpeg"),
                "prompt": NOTE_PROMPT}
        for attempt in (1, 2):
            try:
                return await asyncio.wait_for(self._run(body), self._timeout_s)
            except (_Retry, TimeoutError, aiohttp.ClientConnectionError) as exc:
                self._report(None, False)
                if attempt == 1:
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
        """One call to fal's queue — the key goes to its host only, never elsewhere."""
        if urlsplit(url).hostname != QUEUE_HOST:
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
                raise RuntimeError(f"HTTP {resp.status}")
            return data if isinstance(data, dict) else {}

    async def _run(self, body: dict) -> Video:
        async with ClientSession() as session:
            sent = await self._queue(session, "POST", f"{QUEUE_URL}/{self.model}", json=body)
            status_url, response_url = sent.get("status_url"), sent.get("response_url")
            if not status_url or not response_url:
                raise RuntimeError("no request")
            while True:
                status = await self._queue(session, "GET", status_url)
                if status.get("status") not in FAL_WORKING:
                    break
                await self._sleep(self._poll_s)
            result = await self._queue(session, "GET", response_url)
            video = result.get("video") if isinstance(result.get("video"), dict) else {}
            if not video.get("url"):
                raise _Blocked
            async with session.get(video["url"]) as resp:  # fal's storage: no key sent there
                if resp.status >= 500:
                    raise _Retry(f"HTTP {resp.status}")
                if resp.status != 200:
                    raise RuntimeError(f"HTTP {resp.status}")
                data = await resp.read()
        seconds = result.get("duration")
        seconds = float(seconds) if isinstance(seconds, int | float) and not isinstance(seconds, bool) else None
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


async def pcm_to_mp3(pcm: bytes, timeout_s: float = 60.0) -> bytes | None:
    """Her voice's PCM → mp3 for fal, through ffmpeg's fixed argv; None on any failure (logged by its code)."""
    out = await _ffmpeg(FFMPEG_MP3, pcm, timeout_s, "mp3")
    return out or None


async def square_note(mp4: bytes, timeout_s: float = 120.0) -> bytes | None:
    """A video cut square for a round video message, through temporary files in a 0700 folder removed after; None on
    any failure (logged by its code)."""
    with tempfile.TemporaryDirectory(prefix="note-") as folder:  # mkdtemp: 0700
        src, dst = Path(folder) / "in.mp4", Path(folder) / "out.mp4"
        with os.fdopen(os.open(src, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as out:
            out.write(mp4)
        if await _ffmpeg(ffmpeg_square(str(src), str(dst)), None, timeout_s, "square") is None:
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
