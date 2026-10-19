"""v5.4 — the Agora recording, on command: a stretch of the room as one audio file, each line in the voice of the one
who said it (ROADMAP §v5.4, ARCHITECTURE §The herald).

The decisions are pure: the command and its period, and the plan — the room's events turned into pieces (a voice
message as it is, a line to be spoken in its speaker's voice, a time mark). Nothing of the room is kept: Hermes
reads it from the homeserver when asked, and the only thing that remains is the file he sends.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from agents.voice import RATE, encode_opus
from agents.world import MONTHS_GEN

log = logging.getLogger("agent.recording")

RECORD_WORDS = frozenset({"запис", "записи", "запиши"})
RECORD_MAX_WORDS = 6
VOICE_TEXT_S = 30          # a member's text within this many seconds after its voice message is that voice's words
GAP_MS = 15 * 60 * 1000    # a silence longer than this gets a spoken time mark

# «о першій» … — the locative ordinal of an hour (a time mark), and the genitive (the opening's «з … до …»)
HOURS_AT = ["опівночі", "о першій", "о другій", "о третій", "о четвертій", "о п'ятій", "о шостій", "о сьомій",
            "о восьмій", "о дев'ятій", "о десятій", "об одинадцятій", "о дванадцятій", "о тринадцятій",
            "о чотирнадцятій", "о п'ятнадцятій", "о шістнадцятій", "о сімнадцятій", "о вісімнадцятій",
            "о дев'ятнадцятій", "о двадцятій", "о двадцять першій", "о двадцять другій", "о двадцять третій"]
HOURS_GEN = ["опівночі", "першої", "другої", "третьої", "четвертої", "п'ятої", "шостої", "сьомої", "восьмої",
             "дев'ятої", "десятої", "одинадцятої", "дванадцятої", "тринадцятої", "чотирнадцятої", "п'ятнадцятої",
             "шістнадцятої", "сімнадцятої", "вісімнадцятої", "дев'ятнадцятої", "двадцятої", "двадцять першої",
             "двадцять другої", "двадцять третьої"]
CLOSING = "Це все з Агори. Гермес, ваш вісник."


@dataclass(frozen=True)
class Event:
    """One room message as the recording reads it: a text or an audio message."""
    event_id: str
    sender: str
    ts: int
    kind: str                    # "text" | "audio"
    body: str = ""
    mxc: str = ""
    mime: str = "audio/ogg"
    caption: str | None = None   # a voice's words as its caption (the voice-only lines of 2026-10-18)
    edit: bool = False


@dataclass(frozen=True)
class Piece:
    """One sound of the recording: an existing voice message, a line to speak in its speaker's voice, a time mark."""
    kind: str                    # "audio" | "speak" | "gap"
    speaker: str = ""
    ts: int = 0
    text: str = ""
    mxc: str = ""
    mime: str = "audio/ogg"


def _local_midnight(day, tz: str) -> int:
    return int(datetime.combine(day, time(0, 0), ZoneInfo(tz)).timestamp() * 1000)


def _words(text: str) -> list[str]:
    return re.findall(r"[^\W_]+(?:['’][^\W_]+)?", (text or "").lower())


def asks_recording(text: str) -> bool:
    """A short owner message (at most six words) with «запис» / «записи» / «запиши»."""
    words = _words(text)
    return 0 < len(words) <= RECORD_MAX_WORDS and bool(RECORD_WORDS & set(words))


def recording_request(text: str, now_ms: int, tz: str) -> tuple[int, int] | None:
    """The owner's «запис …» (`asks_recording`) — the period it asks for: «за вчора» the whole of yesterday;
    «з HH» / «з HH:MM» today from then; otherwise today until now. None for anything else."""
    if not asks_recording(text):
        return None
    low = (text or "").lower()
    words = _words(text)
    now = datetime.fromtimestamp(now_ms / 1000, ZoneInfo(tz))
    today = _local_midnight(now.date(), tz)
    if "вчора" in words:
        return _local_midnight(now.date() - timedelta(days=1), tz), today
    m = re.search(r"\bз\s+(\d{1,2})(?:[:.](\d{2}))?\b", low)
    if m and int(m[1]) < 24 and int(m[2] or 0) < 60:
        start = int(datetime.combine(now.date(), time(int(m[1]), int(m[2] or 0)), ZoneInfo(tz)).timestamp() * 1000)
        if start < now_ms:
            return start, now_ms
    return today, now_ms


def _action(text: str) -> bool:
    t = (text or "").strip()
    return t.startswith("*") and t.endswith("*")


def plan_recording(events: list[Event], owner: str, members: set[str], gap_ms: int = GAP_MS) -> list[Piece]:
    """The room's events (oldest first) as the recording's pieces: a member's voice message as it is, its text
    within `VOICE_TEXT_S` consumed; the owner's voice as it is; the owner's typed line and a member's text-only line
    to be spoken in their voices; an action purr, an edit, Hermes's transcript and any other sender left out; a
    time mark before a line that follows more than `gap_ms` of silence."""
    pieces: list[Piece] = []
    last_voice: dict[str, int] = {}     # sender → the ts of its latest voice whose words are not yet seen
    last_ts: int | None = None

    def add(piece: Piece) -> None:
        nonlocal last_ts
        if last_ts is not None and piece.ts - last_ts > gap_ms:
            pieces.append(Piece("gap", ts=piece.ts))
        pieces.append(piece)
        last_ts = piece.ts

    for e in events:
        if e.edit or (e.sender != owner and e.sender not in members):
            continue
        if e.kind == "audio":
            if e.mxc:
                add(Piece("audio", e.sender, e.ts, e.caption or "", e.mxc, e.mime))
                if e.sender != owner:
                    last_voice[e.sender] = e.ts
            continue
        text = (e.body or "").strip()
        if not text:
            continue
        voiced_at = last_voice.pop(e.sender, None)
        if voiced_at is not None and e.ts - voiced_at <= VOICE_TEXT_S * 1000:
            continue  # the words of the voice just added
        if e.sender != owner and _action(text):
            continue
        add(Piece("speak", e.sender, e.ts, text))
    return pieces


def hour_words(hour: int) -> str:
    return HOURS_AT[hour % 24]


def gap_line(ts: int, tz: str) -> str:
    """A time mark after a long silence, spoken by Hermes: «О сімнадцятій.»"""
    words = hour_words(datetime.fromtimestamp(ts / 1000, ZoneInfo(tz)).hour)
    return words[0].upper() + words[1:] + "."


def opening_line(first_ts: int, last_ts: int, tz: str) -> str:
    """«Агора, 19 жовтня, з десятої до двадцять третьої.» — the day of the first line, its hour and the last one's."""
    first = datetime.fromtimestamp(first_ts / 1000, ZoneInfo(tz))
    last = datetime.fromtimestamp(last_ts / 1000, ZoneInfo(tz))
    return f"Агора, {first.day} {MONTHS_GEN[first.month - 1]}, з {HOURS_GEN[first.hour]} до {HOURS_GEN[last.hour]}."


# --- the assembly -----------------------------------------------------------------------------------------------------
PAUSE_S = 0.5             # between two lines
MARK_PAUSE_S = 1.5        # around a time mark
PART_MAX_S = 3600         # a part at most an hour: ~14.4 MB of Opus at 32 kb/s, under the homeserver's 20 MiB
DECODE_TIMEOUT_S = 120
LOUDNORM = "loudnorm=I=-18:TP=-2:LRA=11"  # a phone's voice and an ElevenLabs voice equally loud
_OUT = ("-af", LOUDNORM, "-f", "s16le", "-ar", str(RATE), "-ac", "1", "pipe:1")


def decode_argv(path: str | None) -> list[str]:
    """ffmpeg's fixed argv: a file (any format, seekable — an m4a needs it) or raw 24 kHz PCM from stdin, to
    levelled s16le 24 kHz mono on stdout."""
    head = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
    src = ["-i", path] if path else ["-f", "s16le", "-ar", str(RATE), "-ac", "1", "-i", "pipe:0"]
    return [*head, *src, *_OUT]


async def decode_to_pcm(data: bytes, raw: bool = False) -> bytes | None:
    """A voice message's bytes (or a TTS's raw PCM) → levelled PCM; None on any failure (logged by its code)."""
    path = None
    try:
        if not raw:
            fd, path = tempfile.mkstemp(suffix=".audio")
            with os.fdopen(fd, "wb") as f:
                f.write(data)
        proc = await asyncio.create_subprocess_exec(*decode_argv(path), stdin=asyncio.subprocess.PIPE,
                                                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            out, _ = await asyncio.wait_for(proc.communicate(input=data if raw else None), timeout=DECODE_TIMEOUT_S)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            log.error("decode timed out")
            return None
        if proc.returncode != 0 or not out:
            log.error("decode failed: ffmpeg exit %s", proc.returncode)
            return None
        return out[: len(out) - len(out) % 2]
    except OSError as exc:
        log.error("decode failed: %s", type(exc).__name__)
        return None
    finally:
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass


def silence(seconds: float) -> bytes:
    return b"\x00\x00" * int(RATE * seconds)


def pcm_seconds(pcm: bytes) -> float:
    return len(pcm) / 2 / RATE


def split_parts(durations: list[float], max_s: float = PART_MAX_S) -> list[list[int]]:
    """The pieces' indices grouped into parts of at most `max_s` seconds, cut only between pieces (a piece longer
    than a part is a part of its own)."""
    parts: list[list[int]] = []
    current: list[int] = []
    total = 0.0
    for i, d in enumerate(durations):
        if current and total + d > max_s:
            parts.append(current)
            current, total = [], 0.0
        current.append(i)
        total += d
    if current:
        parts.append(current)
    return parts


async def assemble(sounds: list[tuple[bytes, bool]], max_s: float = PART_MAX_S) -> list[tuple[bytes, int]]:
    """Levelled PCM pieces (each with whether it is a time mark) → the parts as OGG/Opus with their length in ms:
    a short pause between lines, a longer one around a time mark, a new part before an hour is passed."""
    blocks = []
    for pcm, mark in sounds:
        pad = silence(MARK_PAUSE_S if mark else PAUSE_S)
        blocks.append(pad + pcm + (pad if mark else b""))
    out = []
    for part in split_parts([pcm_seconds(b) for b in blocks], max_s):
        pcm = b"".join(blocks[i] for i in part) + silence(PAUSE_S)
        ogg = await encode_opus(pcm)
        if ogg is None:
            log.error("recording: a part could not be encoded")
            return []
        out.append((ogg, int(pcm_seconds(pcm) * 1000)))
    return out
