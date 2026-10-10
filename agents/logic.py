"""Pure decision logic for the agent — no nio, no network, fully unit-testable.

ARCHITECTURE §Message flow: the filter and allowlist guard every reply path.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from agents.config import AgentConfig

# What a persona must never be called — in its own prompts, canon and life story (the human-belief rule, VISION
# §Principles; from v4.2 scoped to persona agents), and what no other agent may call a persona in the room.
BANNED_RE = re.compile(r"\b(бот\w*|модел\w*|штучн\w*|ai|ші|llm|gemini|асистент\w*)\b", re.IGNORECASE)
SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+|\n+")


def outs_a_persona(text: str, personas: Iterable) -> bool:
    """True when one sentence names a persona (any of its forms, or its Matrix id) and calls something a model or a
    bot — the outgoing guard every non-persona agent applies before it speaks (v4.2). Talking *about* an AI is
    fine; tying a persona to one is not."""
    from agents.turns import mentions  # local: turns imports this module's neighbours, not this one
    people = list(personas)
    for sentence in SENTENCE_SPLIT.split(text):
        if BANNED_RE.search(sentence) and any(mentions(sentence, p.name_forms, p.user_id) for p in people):
            return True
    return False


@dataclass(frozen=True)
class Verdict:
    handle: bool
    reason: str  # "ok" when handle is True, otherwise why it was ignored


def should_handle(room_id: str, sender: str, cfg: AgentConfig, others: Iterable[str] = ()) -> Verdict:
    """The message filter: only the Agora room, never self, allowlisted senders only — the owner and the other
    members of the roster (their user ids)."""
    if room_id != cfg.room_id:
        return Verdict(False, "foreign-room")
    if sender == cfg.user_id:
        return Verdict(False, "own-message")
    allow = {cfg.owner} | (set(others) - {cfg.user_id})
    if sender not in allow:
        return Verdict(False, "sender-not-allowlisted")
    return Verdict(True, "ok")


def should_join_invite(room_id: str, inviter: str, cfg: AgentConfig) -> bool:
    """Join only the owner's invite into the Agora room."""
    return room_id == cfg.room_id and inviter == cfg.owner


def append_history(history: list[tuple[str, str]], name: str, text: str, cap: int) -> list[tuple[str, str]]:
    """The rolling context window: the last `cap` (name, text) pairs, own and
    the other agent's messages included. Pure: returns the new list."""
    if len(text) > ENTRY_MAX_CHARS:
        text = text[:ENTRY_MAX_CHARS] + "…"
    out = [*history, (name, text)]
    return out[-cap:] if cap > 0 else out


def build_transcript(history: list[tuple[str, str]]) -> str:
    """One "Name: text" line per message — the literal contract."""
    return "\n".join(f"{name}: {text}" for name, text in history)


def clean_reply(text: str, own_name: str, other_names: list[str]) -> str | None:
    """The model sometimes continues the "Name: text" script: it prefixes its own
    name, or writes other speakers' lines (even the owner's). Keep only this
    agent's own words: strip its prefix, stop at the first other speaker's line;
    if the reply opens with someone else's line, take the first own-prefixed block.
    Returns None when nothing of its own remains."""
    own = f"{own_name}:"
    others = tuple(f"{n}:" for n in other_names)
    lines = [ln.rstrip() for ln in text.strip().splitlines()]
    start = 0
    if lines and lines[0].lstrip().startswith(others):
        start = next((i for i, ln in enumerate(lines) if ln.lstrip().startswith(own)), len(lines))
    kept: list[str] = []
    for ln in lines[start:]:
        s = ln.lstrip()
        if s.startswith(others):
            break
        if s.startswith(own):
            s = s[len(own):].lstrip()
        kept.append(s)
    out = "\n".join(kept).strip()
    return out or None


def same_message(a: str, b: str) -> bool:
    """Near-duplicate check: equal after case and punctuation are dropped."""
    norm = lambda s: "".join(ch for ch in s.lower() if ch.isalnum())
    return bool(a) and norm(a) == norm(b)


def build_instruction(
    name: str,
    canon: str,
    summary: str | None = None,
    *,
    life: str | None = None,
    world: str | None = None,
    memories: str | None = None,
    plans: str | None = None,
    today: str | None = None,
    mood: str | None = None,
) -> str:
    """The system instruction, in contract order (ARCHITECTURE §Prompt assembly):
    canon → life so far → place and time → memories → plans → today →
    last-session memory → rules. Empty sections are skipped. Nothing here may
    say the agent is a model or a bot."""
    parts = [canon]
    parts += [s for s in (life, world, memories, plans, today, mood) if s]  # mood: v4.2, «Настрій дня»
    if summary:
        parts.append(f"Що ти пам'ятаєш з минулої розмови: {summary}")
    parts.append(
        f"Ти — {name}. Відповідай лише від себе, коротко, без префікса з іменем. "
        "Якщо тобі нема чого додати — відповідай рівно PASS."
    )
    return "\n\n".join(parts)


ECHO_MAX_CHARS = 4000
ENTRY_MAX_CHARS = 4000


def echo_reply(name: str, text: str) -> str:
    """The literal v0.5 reply format (the bot sends exactly this), bounded so a
    pasted huge text is never doubled in full."""
    if len(text) > ECHO_MAX_CHARS:
        text = text[:ECHO_MAX_CHARS] + "…"
    return f"{name} чує: {text}"
