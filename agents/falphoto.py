"""v6.5 — her photos on fal.ai: Seedream 4, with fal's safety checker off (the owner, 2026-11-08: «зроби fal.ai
перемикання на цю модель з enable_safety_checker відключеним»).

The owner chose Seedream after ten probes (2026-11-09): FLUX PuLID kept her face but made no scene. A selfie goes to
Seedream 4 Edit with her reference faces (her main face and three drawn, as for Google's model), put on fal's storage
first; a photo without her goes to Seedream 4 text-to-image with none, so no reference puts her into it. The request
(English) is built by the caller (`agents/agent.py` `_fal_prompt`: her backup writes the scene, the code its own
lines). Seedream's answer names no `has_nsfw_concepts` (PuLID's did): a photo its checker flags comes back black, so a
black photo is `blocked`, as a flagged or an empty one, and never sent. One retry on a server error, a dropped
connection or a timeout before fal accepts the job, never after. The log holds the model, the outcome and the time —
never the request, a URL or the key.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

import aiohttp

from agents import video
from agents.photo import Made, Shot, pick_faces
from agents.video import FAL_WORKING, QUEUE_URL, FalQueue, _Blocked, _ffmpeg, _Retry

log = logging.getLogger("agent.falphoto")

EDIT_MODEL = "fal-ai/bytedance/seedream/v4/edit"           # a selfie: her faces as references
TEXT_MODEL = "fal-ai/bytedance/seedream/v4/text-to-image"  # a photo without her
SIZE = {"width": 1152, "height": 1536}                     # 3:4, as her Google photos
POLL_S = 2.0                                               # a photo took 12–47 s in the probes
TIMEOUT_S = 180.0
BLACK_MEAN = 3                                             # of 255: a photo darker than this on average is black
FFMPEG_GREY = ("ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0", "-vf", "scale=8:8,format=gray",
               "-frames:v", "1", "-f", "rawvideo", "pipe:1")

ImageSink = Callable[..., None]  # (model, images, ok, blocked, latency_ms=)


def model_for(shot: Shot) -> str:
    """The model for a shot (pure): the edit model for a selfie (her faces), text-to-image for a photo without her."""
    return EDIT_MODEL if shot.kind == "selfie" else TEXT_MODEL


def request_body(prompt: str, face_urls: list[str]) -> dict:
    """The job (pure): the request, her faces' URLs for a selfie, 3:4, one image, the safety checker off."""
    body = {"prompt": prompt, "image_size": dict(SIZE), "num_images": 1, "enable_safety_checker": False}
    if face_urls:
        body["image_urls"] = list(face_urls)
    return body


def flagged(result: dict) -> bool:
    """Whether fal says the image is unsafe (pure): any `true` in `has_nsfw_concepts` (Seedream names none)."""
    flags = result.get("has_nsfw_concepts")
    return isinstance(flags, list) and any(f is True for f in flags)


async def is_black(image: bytes, timeout_s: float = 30.0) -> bool | None:
    """Whether a photo is black (fal's checker returns a flagged photo so): its 8×8 grey frame's mean under
    `BLACK_MEAN`, through ffmpeg's fixed argv; None when ffmpeg fails (logged by its code)."""
    out = await _ffmpeg(FFMPEG_GREY, image, timeout_s, "black check")
    if not out:
        return None
    return sum(out) / len(out) < BLACK_MEAN


class FalPhotoMaker(FalQueue):
    """Her photo on Seedream 4 through fal's queue API, beside Google's `PhotoMaker`."""

    _what = "photo"
    _log = log
    _mono = staticmethod(time.monotonic)  # the calls' clock — a test sets its own

    def __init__(self, key: str, faces: list | None = None, main_face: str | None = None,
                 sink: ImageSink | None = None, rng: Callable[[], float] | None = None, poll_s: float = POLL_S,
                 timeout_s: float = TIMEOUT_S, sleep: Callable[[float], Awaitable] = asyncio.sleep) -> None:
        super().__init__(key, poll_s, sleep)
        self.faces, self.main_face = faces or [], main_face
        self._sink, self._rng, self._timeout_s = sink, rng or random.random, timeout_s

    def __repr__(self) -> str:  # never the key
        return f"FalPhotoMaker(faces={len(self.faces)})"

    def _report(self, model: str, images: int | None, ok: bool, t0: float, blocked: str | None = None) -> None:
        if self._sink is None:
            return
        try:
            self._sink(model, images, ok, blocked, latency_ms=round((self._mono() - t0) * 1000))
        except Exception:
            log.exception("usage accounting failed")

    async def make(self, shot: Shot, prompt: str) -> Made:
        """Her photo, or why there is none: `blocked` (flagged, black, empty, or a selfie without faces) or `failed`
        (an error after the retry) — never a crash."""
        model = model_for(shot)
        refs = pick_faces(self.faces, self._rng, self.main_face) if shot.kind == "selfie" else []
        if shot.kind == "selfie" and not refs:
            log.warning("photo: no faces for a selfie (fal)")
            return Made(None, why="blocked")
        for attempt in (1, 2):
            submitted: list = []
            t0 = self._mono()
            try:
                image, mime, images, unsafe = await asyncio.wait_for(self._run(model, prompt, refs, submitted),
                                                                     self._timeout_s)
            except (_Retry, TimeoutError, aiohttp.ClientConnectionError) as exc:
                self._report(model, None, False, t0)
                if submitted and isinstance(exc, TimeoutError):  # a job still queued is never paid for
                    await self._cancel(submitted[0])
                if attempt == 1 and not submitted:
                    log.info("photo: %s on fal — once more", type(exc).__name__)
                    continue
                log.warning("photo: failed on fal (%s)", type(exc).__name__)
                return Made(None, why="failed")
            except _Blocked:
                self._report(model, None, False, t0, "answer")
                log.warning("photo: blocked on fal (empty)")
                return Made(None, why="blocked")
            except Exception as exc:  # noqa: BLE001 — any other failure: no photo, never a crash
                self._report(model, None, False, t0)
                log.warning("photo: failed on fal (%s)", type(exc).__name__)
                return Made(None, why="failed")
            why = "flagged" if unsafe else None
            if why is None and await is_black(image) is True:
                why = "black"
            if why:
                self._report(model, images, False, t0, "answer")  # fal made it: paid for, never sent
                log.warning("photo: blocked on fal (%s)", why)
                return Made(None, why="blocked")
            self._report(model, images, True, t0)
            log.info("photo: made on fal (%s, %.0f s)", model.rsplit("/", 1)[-1], self._mono() - t0)
            return Made(image, mime, "ok")
        return Made(None, why="failed")  # never reached: the loop returns

    async def _run(self, model: str, prompt: str, refs: list, submitted: list) -> tuple[bytes, str, int, bool]:
        """The job: her faces on fal's storage (a selfie), the request, the result fetched — the first image, its
        type, how many fal made, and whether it flags them."""
        async with video.ClientSession() as session:
            urls = [await self._upload(session, data, mime) for _, data, mime in refs]
            sent = await self._queue(session, "POST", f"{QUEUE_URL}/{model}", json=request_body(prompt, urls))
            status_url, response_url = sent.get("status_url"), sent.get("response_url")
            if not status_url or not response_url:
                raise RuntimeError("no request")
            submitted.append(sent.get("cancel_url"))
            while True:
                status = await self._again(lambda: self._queue(session, "GET", status_url))
                if status.get("status") not in FAL_WORKING:
                    break
                await self._sleep(self._poll_s)
            result = await self._again(lambda: self._queue(session, "GET", response_url))
            images = [i for i in result.get("images") or [] if isinstance(i, dict) and i.get("url")]
            if not images:
                raise _Blocked
            data = await self._again(lambda: self._download(session, images[0]["url"]))
        if not data:
            raise _Blocked
        return data, images[0].get("content_type") or "image/jpeg", len(images), flagged(result)


# --- the owner's switch (`/photos fal|google`), kept in `state/<name>.photos.json` -----------------------------------
ROUTES = ("google", "fal")


def load_photo_route(path: Path) -> str:
    """Where her photos go: `google` (the default; a missing or corrupt file too) or `fal`."""
    try:
        route = json.loads(path.read_text(encoding="utf-8")).get("route")
    except (OSError, ValueError, AttributeError):
        return "google"
    return route if route in ROUTES else "google"


def save_photo_route(path: Path, route: str) -> None:
    """Atomic, private from birth (0600): the route only, never a text."""
    if route not in ROUTES:
        raise ValueError(f"unknown photo route {route!r}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, json.dumps({"route": route}).encode())
    finally:
        os.close(fd)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
