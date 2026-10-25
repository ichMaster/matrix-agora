"""v5.9 — emotion in a person's voice: ElevenLabs audio tags (ROADMAP §v5.9, features/voice-emotion.md).

She writes one or two tags from the palette verified on her voice (`[laughs]`, `[sighs]`, `[whispers]` …), inline,
in her own reply. One reply then goes out two ways: the synthesiser gets it as written, so her voice performs the
tags; everything else — the message, her history, the session, the archive, the other members — gets her words alone,
with nothing in the tags' place (the owner, 2026-10-25: no emote, no emoji). A model that does not render tags reads
them aloud, so it never receives one. The split is pure.
"""

from __future__ import annotations

import re
from typing import Self

# measured on her voice on 2026-10-25: these perform the tags; `eleven_turbo_v2_5` (and the other v2 models) read them
# aloud as words
TAG_MODELS = frozenset({"eleven_v3", "eleven_v3_conversational", "eleven_v4", "eleven_v4_turbo"})
# a tag: a bracket that opens with a letter of any case and holds 2–40 characters, none a digit, and is not a link's
# text — `[Laughs]`, `Так[laughs]`, `[sighs.]`, `[зам’ялася]` go (review #3); `[1]`, `arr[i]`, `[ОСТРІВ 3]` and
# `[тут](url)` stay. Her palette puts nothing else in square brackets.
TAG_RE = re.compile(r"\[([^\W\d_][^\[\]\n\d]{1,39})\](?!\()")


RUN_RE = re.compile(rf"[ \t]*(?:{TAG_RE.pattern}[ \t]*)+")  # a run of tags with the spaces around it


def _gap(m: re.Match) -> str:
    """What a removed run of tags leaves: one space between words; nothing at a line's edge, after an opening quote
    or bracket, or before punctuation. Text without tags is never touched (review #5)."""
    before = m.string[m.start() - 1] if m.start() else "\n"
    after = m.string[m.end()] if m.end() < len(m.string) else "\n"
    return "" if before in "\n(«„“" or after in "\n,.!?…:;)»”" else " "


def split_tags(reply: str) -> tuple[str, str]:
    """(text, speech): her words with every tag removed and the spaces tidied; the reply as written for the voice."""
    text = RUN_RE.sub(_gap, reply or "")
    text = "\n".join(line.strip() for line in text.split("\n")).strip()
    return text, reply or ""


class Spoken(str):
    """Her words — the `str` every caller stores, compares and sends as text — carrying the speech for her voice."""

    speech: str

    def __new__(cls, words: str, speech: str) -> Self:
        obj = super().__new__(cls, words)
        obj.speech = speech
        return obj


def spoken(line: str) -> tuple[str, str]:
    """(the words, what the synthesiser gets) of a line — a plain `str` is both."""
    return str(line), getattr(line, "speech", None) or str(line)


def speech_for(model: str, text: str, speech: str) -> str:
    """What the synthesiser gets: the speech on a model that performs tags, the words alone on any other."""
    return speech if model in TAG_MODELS else text
