"""v5.17 — Кіра's photos in Telegram: the line she writes for one, the request built from it, and the image call.

A last line of her answer names a shot — `ФОТО: …` (without her) or `СЕЛФІ: …` (with her: a selfie, or someone took
her) — and is never sent (`split_photo`, as «ЗАПАМ'ЯТАЙ»). The request to Google's image model is English, built from
her words and her moment (`photo_request`, pure): the part of the day, her day's weather, the season, what she wears
in a selfie — never the reference photos' clothes — and a casual phone snapshot's look. A selfie takes the owner's
reference photos of her face (`kira.face/`: `kira.png` always, three more drawn each time). The call retries once on a
server error or a timeout; a block, or a second failure, is a reason, never a crash. The log holds outcomes and types
only — never her description, the request or a path.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from google.genai import errors as genai_errors
from google.genai import types

from agents.emotion import split_tags
from agents.world import part_of_day, season

log = logging.getLogger("agent.photo")

MODEL = "gemini-nano-banana-2.1"   # the owner, 2026-10-31: Google's image model, Nano Banana 2.1
SIZES = ("1K", "2K")
MAIN_FACE = "kira.png"
FACES_PER_SHOT = 4                 # the model takes up to 4 character references
FACE_SUFFIXES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
TIMEOUT_S = 90                     # a photo took 11–40 s in the owner's test
KINDS = {"ФОТО": "photo", "СЕЛФІ": "selfie"}
# the marker, as «ЗАПАМ'ЯТАЙ»'s: a line of its own in any case — after a quote, a bullet or a number — or, in capitals,
# anywhere in a line; a colon or a dash after it. Everything from the marker to the line's end is the shot.
_MARK = r"(?P<kind>ФОТО|СЕЛФІ)[ \t*_»\"')\]]*[:—–-][ \t*_]*(?P<shot>[^\n]*)"
MARK_LINE_RE = re.compile(r"^[ \t>*_\-–—•\d.)«\"'(\[]*" + _MARK, re.MULTILINE | re.IGNORECASE)
MARK_ANY_RE = re.compile(r"[«\"'(\[]*[ \t]*" + _MARK)
PARTS = {"ранок": "morning", "день": "afternoon", "вечір": "evening", "ніч": "night"}
SEASONS = {"зима": "winter", "весна": "spring", "літо": "summer", "осінь": "autumn"}
STYLE = ("A casual photo taken on a smartphone and sent in a private chat: natural light, slightly imperfect framing, "
         "real textures, no studio look. No other identifiable person in focus, no text, caption or watermark on the "
         "image.")
SELFIE = ("The young woman in the photo is the same person as in the reference photos: keep her face, hair and "
          "features exactly. She is 23, from Lviv, Ukraine. She wears what suits the weather and the scene described "
          "below — not the clothes of the reference photos.")


@dataclass(frozen=True)
class Shot:
    kind: str          # `photo` | `selfie`
    description: str   # her words: what is in the shot


@dataclass(frozen=True)
class Moment:
    when: datetime
    weather: str | None = None   # her day's weather line (v5.10), as written
    city: str = "Lviv"


@dataclass(frozen=True)
class Made:
    image: bytes | None
    mime: str = "image/jpeg"
    why: str = "ok"    # `ok` | `blocked` (the filter, or no image) | `failed` (an error after the retry)


def split_photo(text: str) -> tuple[str, Shot | None]:
    """Her line without its photo markers, and the shot the last one names — a marker is never sent."""
    lines, shot = [], None
    for line in (text or "").split("\n"):
        m = MARK_LINE_RE.match(line) or MARK_ANY_RE.search(line)
        if m is None:
            lines.append(line)
            continue
        description = split_tags(m.group("shot"))[0].strip(" \t«»\"'*_()[]")  # no voice tag in a shot
        if description:
            shot = Shot(KINDS[m.group("kind").upper()], description)
        kept = line[:m.start()].rstrip()
        if kept:
            lines.append(kept)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip(), shot


def photo_request(shot: Shot, moment: Moment) -> str:
    """The image model's instruction (pure, English): who, if she is in it; the shot in her words; the moment; the
    look of a phone snapshot."""
    when = moment.when
    parts = [SELFIE] if shot.kind == "selfie" else ["Nobody's face is in the shot unless the description says so."]
    parts.append(f"The shot, as she describes it (in Ukrainian): {shot.description}")
    moment_line = (f"It is {PARTS[part_of_day(when.hour)]} in {SEASONS[season(when.month)]}, around {when:%H:%M}, in "
                   f"{moment.city} unless the description names another place.")
    if moment.weather:
        moment_line += f" Today's weather there (in Ukrainian): {moment.weather}"
    parts += [moment_line, STYLE]
    return "\n".join(parts)


def load_faces(folder: Path | None) -> list[tuple[str, bytes, str]]:
    """The owner's reference photos of her face: the folder's own png/jpg files (never `places/`), by name; a missing
    or unreadable folder is none."""
    faces = []
    try:
        paths = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in FACE_SUFFIXES)
    except (OSError, AttributeError):
        return []
    for path in paths:
        try:
            faces.append((path.name, path.read_bytes(), FACE_SUFFIXES[path.suffix.lower()]))
        except OSError:
            continue
    return faces


def pick_faces(faces: list, rng: Callable[[], float]) -> list:
    """`kira.png` always (else the first), and three others drawn by `rng`, so the references' clothes and light vary."""
    if not faces:
        return []
    main = next((f for f in faces if f[0] == MAIN_FACE), faces[0])
    rest = [f for f in faces if f is not main]
    picked = []
    while rest and len(picked) < FACES_PER_SHOT - 1:
        picked.append(rest.pop(min(int(rng() * len(rest)), len(rest) - 1)))
    return [main, *picked]


def _image_of(resp) -> tuple[bytes, str] | None:
    for candidate in getattr(resp, "candidates", None) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            data = getattr(part, "inline_data", None)
            if data is not None and getattr(data, "data", None):
                return data.data, getattr(data, "mime_type", None) or "image/jpeg"
    return None


class PhotoMaker:
    """Google's image model through the Gemini SDK (`client.aio.models.generate_content`), her faces for a selfie."""

    def __init__(self, client, model: str = MODEL, size: str = "1K", faces: list | None = None,
                 sink: Callable | None = None, rng: Callable[[], float] | None = None,
                 timeout_s: float = TIMEOUT_S) -> None:
        self._client, self.model, self.size = client, model, size if size in SIZES else "1K"
        self.faces = faces or []
        self._sink, self._rng, self._timeout_s = sink, rng or random.random, timeout_s

    def _report(self, usage, ok: bool, blocked: str | None = None) -> None:
        if self._sink is None:
            return
        try:
            if blocked:
                self._sink("photo", self.model, usage, ok, blocked=blocked)
            else:
                self._sink("photo", self.model, usage, ok)
        except Exception:
            log.exception("usage accounting failed")

    async def make(self, shot: Shot, moment: Moment) -> Made:
        """The photo, or why there is none: one retry on a server error or a timeout; a block is final."""
        refs = pick_faces(self.faces, self._rng) if shot.kind == "selfie" else []
        if shot.kind == "selfie" and not refs:
            log.warning("photo: no faces for a selfie")
            return Made(None, why="blocked")
        contents = [*(types.Part.from_bytes(data=data, mime_type=mime) for _, data, mime in refs),
                    photo_request(shot, moment)]
        config = types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(aspect_ratio="3:4", image_size=self.size),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
        for attempt in (1, 2):
            try:
                resp = await asyncio.wait_for(
                    self._client.aio.models.generate_content(model=self.model, contents=contents, config=config),
                    self._timeout_s)
            except (genai_errors.ServerError, TimeoutError) as exc:
                self._report(None, False)
                if attempt == 1:
                    log.info("photo: %s — once more", type(exc).__name__)
                    continue
                log.warning("photo: failed (%s)", type(exc).__name__)
                return Made(None, why="failed")
            except Exception as exc:  # noqa: BLE001 — any other provider failure: no photo, never a crash
                self._report(None, False)
                log.warning("photo: failed (%s)", type(exc).__name__)
                return Made(None, why="failed")
            usage = getattr(resp, "usage_metadata", None)
            image = _image_of(resp)
            if image is None:
                feedback = getattr(resp, "prompt_feedback", None)
                stage = "prompt" if getattr(feedback, "block_reason", None) else "answer"
                self._report(usage, False, stage)
                log.warning("photo: blocked (%s)", stage)
                return Made(None, why="blocked")
            self._report(usage, True)
            return Made(image[0], image[1], "ok")
        return Made(None, why="failed")  # never reached: the loop returns
