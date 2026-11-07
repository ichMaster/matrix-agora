"""v5.17 — Кіра's photos in Telegram: the line she writes for one, the request built from it, and the image call.

A last line of her answer names a shot — `ФОТО: …` (without her) or `СЕЛФІ: …` (with her: a selfie, or someone took
her) — and is never sent (`split_photo`, as «ЗАПАМ'ЯТАЙ»). The request to Google's image model is English, built from
her words and her moment (`photo_request`, pure): the part of the day, her day's weather, the season, what she wears
in a selfie — never the reference photos' clothes — and a casual phone snapshot's look. A selfie takes the owner's
reference photos of her face (`<localpart>.face/`: `<localpart>.png` always, three more drawn each time). The call
retries once on a server error or a timeout; a block, or a second failure, is a reason, never a crash. The log holds outcomes and types
only — never her description, the request or a path.

v5.18: the same line may name a video instead — `КРУЖЕЧОК: …` (her round video message, her answer said in it) or
`ВІДЕО: …` (a short clip of what she sees); one media line per answer, the last one counts. Its first frame is made
here too (`make(..., aspect=, extra=)`); the video itself in `agents/video.py`.

v6.2: a selfie is the person's own, not Кіра's — her main face photo by her localpart, her age on the shot's day from
her chart's birth date, and her look (`agents/canon/<localpart>.look.md`, English lines for the image model: her eyes,
makeup or none, her figure and how she dresses) in its line (`selfie_line`, pure).
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from agents.emotion import split_tags
from agents.world import part_of_day, season

log = logging.getLogger("agent.photo")

MODEL = "gemini-nano-banana-2.1"   # the owner, 2026-10-31: Google's image model, Nano Banana 2.1
SIZES = ("1K", "2K")
FACES_PER_SHOT = 4                 # the model takes up to 4 character references
FACE_SUFFIXES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
TIMEOUT_S = 90                     # a photo took 11–40 s in the owner's test
KINDS = {"ФОТО": "photo", "СЕЛФІ": "selfie", "КРУЖЕЧОК": "note", "ВІДЕО": "clip",  # v5.18: the videos
         "ГІТАРА": "play"}  # v6.3: a video of her playing the guitar (her TOML's `play`)
# the marker, as «ЗАПАМ'ЯТАЙ»'s: a line of its own in any case — after a quote, a bullet or a number — or, in capitals,
# anywhere in a line; a colon or a dash after it. Everything from the marker to the line's end is the shot.
_MARK = r"(?P<kind>КРУЖЕЧОК|СЕЛФІ|ФОТО|ВІДЕО|ГІТАРА)[ \t*_»\"')\]]*[:—–-][ \t*_]*(?P<shot>[^\n]*)"
MARK_LINE_RE = re.compile(r"^[ \t>*_\-–—•\d.)«\"'(\[]*" + _MARK, re.MULTILINE | re.IGNORECASE)
MARK_ANY_RE = re.compile(r"[«\"'(\[]*[ \t]*" + _MARK)
# v5.17 review #2: her kept note, `[селфі: …]` / `[фото: …]`, anywhere in a line and in any case — Gemini may echo it
NOTE_RE = re.compile(r"\[[ \t]*(?P<kind>КРУЖЕЧОК|СЕЛФІ|ФОТО|ВІДЕО|ГІТАРА)[ \t]*[:—–-][ \t]*(?P<shot>[^\]\n]*)\]", re.IGNORECASE)
PARTS = {"ранок": "morning", "день": "afternoon", "вечір": "evening", "ніч": "night"}
SEASONS = {"зима": "winter", "весна": "spring", "літо": "summer", "осінь": "autumn"}
STYLE = ("A casual photo taken on a smartphone and sent in a private chat: natural light, slightly imperfect framing, "
         "real textures, no studio look. No other identifiable person in focus, no text, caption or watermark on the "
         "image.")
# v6.2: a selfie's line, head and tail fixed; her age and her look between them are her own (`selfie_line`) —
# Кіра's look file carries v5.25's rule (the owner, 2026-11-05: «вона не носить ніколи мейкапу і це її позиція
# природньої краси»)
SELFIE_HEAD = ("The young woman in the photo is the same person as in the reference photos: keep her face, hair and "
               "features exactly.")
SELFIE_TAIL = "She wears what suits the weather and the scene described below — not the clothes of the reference photos."


# her private brief's skill (v5.17, the owner): understood from the talk, never a keyword — and never a word that a
# picture is made: she takes it
PHOTO_SKILL = (
    "Ти можеш надсилати Ich фото зі свого життя і селфі — коли він просить або коли тобі самій хочеться щось йому "
    "показати. Тоді в самому кінці додай окремий останній рядок: слово ФОТО великими літерами, двокрапка і що на "
    "кадрі, одним реченням, як ти описала б свій знімок; коли ти сама в кадрі (селфі, або тебе хтось сфотографував) — "
    "напиши СЕЛФІ замість ФОТО. Він побачить фото, а не цей рядок. Не хочеш чи не можеш зараз сфотографувати — просто "
    "скажи це своїми словами."
)
PHOTO_FAILED = "Фото цього разу не вийшло надіслати — не згадуй його й не обіцяй."


@dataclass(frozen=True)
class Shot:
    kind: str          # `photo` | `selfie` | v5.18 `note` (her кружечок) | `clip` (a short video)
    description: str   # her words: what is in the shot


@dataclass(frozen=True)
class Moment:
    when: datetime
    weather: str | None = None   # her day's weather line (v5.10), as written
    city: str = "Lviv"
    south: bool = False          # v5.27: her place is in the southern hemisphere — November is spring


@dataclass(frozen=True)
class Made:
    image: bytes | None
    mime: str = "image/jpeg"
    why: str = "ok"    # `ok` | `blocked` (the filter, or no image) | `failed` (an error after the retry)


def split_photo(text: str) -> tuple[str, Shot | None]:
    """Her line without its photo markers, and the shot the last one names — a marker is never sent. One that names
    nothing — an empty line, her kept `[селфі: ...]` echoed — gives a shot with no description, unless a described one
    is there too (code review v5.21 #1: her words may promise it, so it is a photo that did not come out)."""
    lines, shot = [], None
    for line in (text or "").split("\n"):
        m = MARK_LINE_RE.match(line) or MARK_ANY_RE.search(line)
        if m is not None and m.group("kind").upper() == "ГІТАРА" and m.group("kind") != "ГІТАРА":
            m = None  # v6.3: her playing line in capitals only — «Гітара — моє друге хобі» is a line of hers
        note = NOTE_RE.search(line) if m is None else None
        if m is None and note is None:
            lines.append(line)
            continue
        found = m or note
        description = split_tags(found.group("shot"))[0].strip(" \t«»\"'*_()[]")  # no voice tag in a shot
        kind = KINDS[found.group("kind").upper()]
        if description.strip(" .…"):
            shot = Shot(kind, description)
        elif shot is None or not shot.description:  # her kept `[селфі: ...]`, echoed, or an empty line
            shot = Shot(kind, "")
        kept = (line[:m.start()] if m is not None
                else re.sub(r"[ \t]{2,}", " ", line[:note.start()] + line[note.end():])).rstrip()
        if kept:
            lines.append(kept)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip(), shot


# v5.23 (the owner, 2026-11-03: «знайди нарешті що це блокує» — then «забери з тексту взагалі селфі чи фото воно в
# історії не потрібно»): her kept note `[селфі: ...]` in a close scene made Gemini 3.1 Pro block her whole private
# prompt (`prohibited_content`: five lines — her words under the blanket, the note, his «продовжуй» — blocked together,
# and the same prompt without the notes passed). No note is kept any more, and an older line's note is cut out before
# any prompt reads it.


def strip_notes(text: str) -> str:
    """Her line without its kept notes (pure): every `[селфі: ...]`, `[фото: ...]`, `[кружечок: ...]`, `[відео: ...]`
    cut out, a line left empty dropped; "" when nothing else was in it."""
    if not NOTE_RE.search(text or ""):
        return text or ""  # a line with no note stays exactly as it is
    lines = [re.sub(r"[ \t]{2,}", " ", NOTE_RE.sub("", line)).rstrip() for line in (text or "").split("\n")]
    return "\n".join(line for line in lines if line.strip()).strip()


def moment_line(moment: Moment) -> str:
    """Her moment in English (pure): the part of the day, the season, the time, the city unless named, the weather."""
    when = moment.when
    line = (f"It is {PARTS[part_of_day(when.hour)]} in {SEASONS[season(when.month, moment.south)]}, around "
            f"{when:%H:%M}, in "
            f"{moment.city} unless the description names another place.")
    if moment.weather:
        line += f" Today's weather there (in Ukrainian): {moment.weather}"
    return line


def age_on(birth: date | None, day: date) -> int | None:
    """Her age on `day` (pure): whole years since `birth`; none without a birth date."""
    if birth is None:
        return None
    return day.year - birth.year - ((day.month, day.day) < (birth.month, birth.day))


def selfie_line(birth: date | None, look: str, day: date) -> str:
    """Who is in a selfie (pure, English): the same person as in her references, her age on the shot's day (none
    without a birth date), her look as her file has it (none without one), and clothes that suit the scene."""
    age = age_on(birth, day)
    parts = [SELFIE_HEAD, f"She is {age}." if age is not None else "", look.strip(), SELFIE_TAIL]
    return " ".join(p for p in parts if p)


def load_look(path: Path | None) -> str:
    """Her look for the image model (`agents/canon/<localpart>.look.md`): its lines but `#` comments, joined with a
    space; a missing, unreadable or empty file is none."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, AttributeError):
        return ""
    return " ".join(line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#"))


def photo_request(shot: Shot, moment: Moment, extra: str | None = None, who: str | None = None) -> str:
    """The image model's instruction (pure, English): who, if she is in it (v6.2: her own `selfie_line`, or one with
    no age and no look); the shot in her words; the moment; the look of a phone snapshot; v5.18: a video's frame line
    (`extra`)."""
    if shot.kind == "selfie":
        parts = [who or selfie_line(None, "", moment.when.date())]
    else:
        parts = ["Nobody's face is in the shot unless the description says so."]
    parts.append(f"The shot, as she describes it (in Ukrainian): {shot.description}")
    parts += [moment_line(moment), STYLE]
    if extra:
        parts.append(extra)
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


def pick_faces(faces: list, rng: Callable[[], float], main_name: str | None = None) -> list:
    """Her main photo always (v6.2: `<localpart>.png`, named by the maker; else the first), and three others drawn by
    `rng`, so the references' clothes and light vary."""
    if not faces:
        return []
    main = next((f for f in faces if f[0] == main_name), faces[0])
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


# v5.22 — when this task's image call began (on the maker's monotonic clock), and for what: her photo, or a video's
# first frame (`frame`) — read by `_report`; a context variable, so a frame made in the background never mixes in
_CALL: ContextVar[tuple[float, str] | None] = ContextVar("photo_call", default=None)


class PhotoMaker:
    """Google's image model through the Gemini SDK (`client.aio.models.generate_content`), her faces for a selfie."""

    _mono = staticmethod(time.monotonic)  # v5.22: the calls' clock — a test sets its own

    def __init__(self, client, model: str = MODEL, size: str = "1K", faces: list | None = None,
                 sink: Callable | None = None, rng: Callable[[], float] | None = None,
                 timeout_s: float = TIMEOUT_S, main_face: str | None = None, birth: date | None = None,
                 look: str = "") -> None:
        self._client, self.model, self.size = client, model, size if size in SIZES else "1K"
        self.faces = faces or []
        self.main_face, self.birth, self.look = main_face, birth, look  # v6.2: whose selfie it is
        self._sink, self._rng, self._timeout_s = sink, rng or random.random, timeout_s

    def _report(self, usage, ok: bool, blocked: str | None = None) -> None:
        if self._sink is None:
            return
        t0, kind = _CALL.get() or (None, "photo")
        latency = round((self._mono() - t0) * 1000) if t0 is not None else None  # v5.22: the call's time
        try:
            if blocked:
                self._sink(kind, self.model, usage, ok, blocked=blocked, latency_ms=latency)
            else:
                self._sink(kind, self.model, usage, ok, latency_ms=latency)
        except Exception:
            log.exception("usage accounting failed")

    async def make(self, shot: Shot, moment: Moment, aspect: str = "3:4", extra: str | None = None,
                   kind: str = "photo") -> Made:
        """The photo, or why there is none: one retry on a server error or a timeout; a block is final. v5.18: a
        video's first frame takes its own `aspect` and a frame line (`extra`); v5.22: and its usage line's `kind` is
        `frame`, so the `photo` lines are the photos she sent."""
        refs = pick_faces(self.faces, self._rng, self.main_face) if shot.kind == "selfie" else []
        if shot.kind == "selfie" and not refs:
            log.warning("photo: no faces for a selfie")
            return Made(None, why="blocked")
        contents = [*(types.Part.from_bytes(data=data, mime_type=mime) for _, data, mime in refs),
                    photo_request(shot, moment, extra, selfie_line(self.birth, self.look, moment.when.date()))]
        config = types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(aspect_ratio=aspect, image_size=self.size),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
        for attempt in (1, 2):
            _CALL.set((self._mono(), kind))  # v5.22: each attempt is its own call, with its own time
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


def photo_maker(model: str, size: str, faces: list, sink: Callable, main_face: str | None = None,
                birth: date | None = None, look: str = "") -> PhotoMaker:
    """Her photos on Google's image model, through a client of their own (the Gemini key from the environment); v6.2:
    her main face photo, birth date and look make her selfie her own."""
    return PhotoMaker(genai.Client(), model or MODEL, size, faces, sink, main_face=main_face, birth=birth, look=look)
