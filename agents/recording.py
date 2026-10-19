"""v5.4 — the Agora recording, on request: a stretch of the room as one audio file, each line in the voice of the one
who said it (ROADMAP §v5.4, ARCHITECTURE §The herald).

No command (the owner, 2026-10-20): it is Hermes's skill. His chat brief describes it (`RECORD_SKILL`), he
understands the request from the conversation, and his answer ends with one line naming the period
(`recording_mark`). The decisions are pure: the period that line asks for, and the plan — the room's events turned
into pieces (a voice message as it is, a line to be spoken in its speaker's voice, a long silence's pause). Nothing
of the room is kept: Hermes reads it from the homeserver when asked, and the only thing that remains is the file he
sends.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from agents.voice import RATE, encode_opus
from agents.world import MONTHS_GEN, WEEKDAYS

log = logging.getLogger("agent.recording")

RECORD_MAX_MS = 25 * 3600 * 1000   # at most a day (the autumn day is 25 hours long)
VOICE_TEXT_S = 30          # a member's text within this many seconds after its voice message is that voice's words
GAP_MS = 15 * 60 * 1000    # a silence longer than this gets a longer pause

# «першої» … — the genitive of an hour, for the opening's «з … до …»
HOURS_GEN = ["опівночі", "першої", "другої", "третьої", "четвертої", "п'ятої", "шостої", "сьомої", "восьмої",
             "дев'ятої", "десятої", "одинадцятої", "дванадцятої", "тринадцятої", "чотирнадцятої", "п'ятнадцятої",
             "шістнадцятої", "сімнадцятої", "вісімнадцятої", "дев'ятнадцятої", "двадцятої", "двадцять першої",
             "двадцять другої", "двадцять третьої"]
CLOSING = "Це все з Агори. Гермес, ваш вісник."
# the skill, in his chat brief: the request understood from the conversation, the period named in one line
RECORD_SKILL = (
    "Ти вмієш ще одне: зібрати запис Агори — один аудіофайл, де кожна репліка звучить голосом того, хто її сказав, "
    "а рядки, які Ich набрав, — його власним голосом. Коли Ich просить запис, аудіо чи послухати розмову Агори за "
    "якийсь час, відповідай одним коротким реченням, а останнім рядком напиши рівно: ЗАПИС: РРРР-ММ-ДД ГГ:ХХ — "
    "РРРР-ММ-ДД ГГ:ХХ — початок і кінець за місцевим часом. Коли він не каже, за який час, — від півночі сьогодні "
    "до тепер; «вчора» — увесь учорашній день, від півночі до півночі; година, що сьогодні ще не настала, — "
    "учорашня. Не довше доби. Цей рядок пиши лише тоді, коли він справді просить запис, і ніколи його не пояснюй."
)


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
    """One sound of the recording: an existing voice message, a line to speak in its speaker's voice, a long
    silence's pause."""
    kind: str                    # "audio" | "speak" | "gap" (a longer pause, no words)
    speaker: str = ""
    ts: int = 0
    text: str = ""
    mxc: str = ""
    mime: str = "audio/ogg"


_MARK_RE = re.compile(
    r"^[\s*`«\"']*ЗАПИС\s*:\s*(\d{4}-\d{2}-\d{2})[ T]+(\d{1,2})[:.](\d{2})\s*(?:—|–|-|до)\s*"
    r"(\d{4}-\d{2}-\d{2})[ T]+(\d{1,2})[:.](\d{2})[\s*`»\"'.]*$", re.IGNORECASE | re.MULTILINE)


def _at(day: str, hour: str, minute: str, zone: ZoneInfo) -> int:
    d = date.fromisoformat(day)
    h, m = int(hour), int(minute)
    if h == 24 and m == 0:  # «24:00» — the next midnight
        d, h = d + timedelta(days=1), 0
    return int(datetime.combine(d, time(h, m), zone).timestamp() * 1000)


def recording_mark(text: str, now_ms: int, tz: str) -> tuple[str, tuple[int, int] | None]:
    """His chat answer → (its words for Ich without the «ЗАПИС: … — …» line, the period that line asks for). The
    period is kept only when it parses, starts before it ends (its end never past now) and is at most a day;
    otherwise None (logged, never the text)."""
    m = _MARK_RE.search(text or "")
    if not m:
        return (text or "").strip(), None
    words = (text[: m.start()] + text[m.end():]).strip()
    zone = ZoneInfo(tz)
    try:
        start, end = _at(m[1], m[2], m[3], zone), _at(m[4], m[5], m[6], zone)
    except ValueError:
        log.warning("recording: the asked period does not parse")
        return words, None
    end = min(end, now_ms)
    if not start < end or end - start > RECORD_MAX_MS:
        log.warning("recording: the asked period is not valid")
        return words, None
    return words, (start, end)


def now_line(now_ms: int, tz: str) -> str:
    """«Зараз: вівторок, 20 жовтня 2026, 01:05.» — so he can name the period he is asked for."""
    now = datetime.fromtimestamp(now_ms / 1000, ZoneInfo(tz))
    return f"Зараз: {WEEKDAYS[now.weekday()]}, {now.day} {MONTHS_GEN[now.month - 1]} {now.year}, {now:%H:%M}."


def _action(text: str) -> bool:
    t = (text or "").strip()
    return t.startswith("*") and t.endswith("*")


def plan_recording(events: list[Event], owner: str, members: set[str], gap_ms: int = GAP_MS) -> list[Piece]:
    """The room's events (oldest first) as the recording's pieces: a member's voice message as it is, its text
    within `VOICE_TEXT_S` consumed; the owner's voice as it is; the owner's typed line and a member's text-only line
    to be spoken in their voices; an action purr, an edit, Hermes's transcript and any other sender left out; a
    longer pause before a line that follows more than `gap_ms` of silence — no spoken time (the owner, 2026-10-20)."""
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


def opening_line(first_ts: int, last_ts: int, tz: str) -> str:
    """«Агора, 19 жовтня, з десятої до двадцять третьої.» — the day of the first line, its hour and the last one's."""
    first = datetime.fromtimestamp(first_ts / 1000, ZoneInfo(tz))
    last = datetime.fromtimestamp(last_ts / 1000, ZoneInfo(tz))
    return f"Агора, {first.day} {MONTHS_GEN[first.month - 1]}, з {HOURS_GEN[first.hour]} до {HOURS_GEN[last.hour]}."


# --- the assembly -----------------------------------------------------------------------------------------------------
PAUSE_S = 0.5             # between two lines
MARK_PAUSE_S = 1.5        # around the opening and the closing
GAP_PAUSE_S = 1.5         # a long silence in the room: this much more quiet before the next line
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
