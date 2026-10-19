"""v5.4 — the Agora recording, on command: a stretch of the room as one audio file, each line in the voice of the one
who said it (ROADMAP §v5.4, ARCHITECTURE §The herald).

The decisions are pure: the command and its period, and the plan — the room's events turned into pieces (a voice
message as it is, a line to be spoken in its speaker's voice, a time mark). Nothing of the room is kept: Hermes
reads it from the homeserver when asked, and the only thing that remains is the file he sends.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from agents.world import MONTHS_GEN

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


def recording_request(text: str, now_ms: int, tz: str) -> tuple[int, int] | None:
    """The owner's «запис …»: a short message (at most six words) with «запис» / «записи» / «запиши» — the period it
    asks for: «за вчора» the whole of yesterday; «з HH» / «з HH:MM» today from then; otherwise today until now."""
    low = (text or "").lower()
    words = re.findall(r"[^\W_]+(?:['’][^\W_]+)?", low)
    if not (0 < len(words) <= RECORD_MAX_WORDS) or not RECORD_WORDS & set(words):
        return None
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
