"""The reply engine seam (v4.1): one interface for every engine, so later ones (Claude, Lumi) plug in.

`GeminiResponder` keeps the v1.1–v3 contract exactly — the system instruction in the ARCHITECTURE §Prompt
assembly order and the `"Name: text"` transcript — and adds the finish reason, so a reply cut by the token cap is
trimmed to its last complete sentence (never sent mid-sentence).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol

from agents.logic import build_transcript

SENTENCE_END = re.compile(r"[.!?…](?:[»\")\]]*)(?=\s|$)")


@dataclass(frozen=True)
class Turn:
    lines: list[tuple[str, str]]  # the context window, (speaker, text), oldest first
    instruction: str | None       # the system instruction (None: the engine owns its identity)
    max_tokens: int
    kind: str = "reply"
    effort: str | None = None     # v4.5: a higher reasoning effort for an engine that has one (Claude the philosopher)


@dataclass(frozen=True)
class Reply:
    text: str
    finish: str = "stop"  # "stop" | "max_tokens"
    usage: dict = field(default_factory=dict)


class Responder(Protocol):
    async def respond(self, turn: Turn) -> Reply | None: ...


class GeminiResponder:
    """Wraps the Gemini seam; usage accounting stays in its sink, unchanged."""

    def __init__(self, llm) -> None:
        self.llm = llm

    async def respond(self, turn: Turn) -> Reply | None:
        transcript = build_transcript(turn.lines)
        complete = getattr(self.llm, "complete", None)
        if complete is None:  # a seam with only generate() (older fakes): never cut
            text = await self.llm.generate(transcript, turn.instruction, max_output_tokens=turn.max_tokens,
                                           kind=turn.kind)
            return Reply(text) if text else None
        out = await complete(transcript, turn.instruction, max_output_tokens=turn.max_tokens, kind=turn.kind)
        return Reply(*out) if out else None


def responder_for(engine: str, llm) -> Responder:
    if engine == "gemini":
        return GeminiResponder(llm)
    raise ValueError(f"no responder for engine {engine!r}")


def trim_to_sentence(text: str) -> str | None:
    """A reply cut by the cap → its text up to the last complete sentence; None when no sentence is complete."""
    ends = list(SENTENCE_END.finditer(text))
    if not ends:
        return None
    kept = text[:ends[-1].end()].strip()
    return kept or None
