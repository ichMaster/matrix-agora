"""Pure decision logic for the agent — no nio, no network, fully unit-testable.

ARCHITECTURE §Message flow: the filter and allowlist guard every reply path.
"""

from __future__ import annotations

from dataclasses import dataclass

from agents.config import AgentConfig


@dataclass(frozen=True)
class Verdict:
    handle: bool
    reason: str  # "ok" when handle is True, otherwise why it was ignored


def should_handle(room_id: str, sender: str, cfg: AgentConfig, other_agent: str | None = None) -> Verdict:
    """The message filter: only the Agora room, never self, allowlisted senders only."""
    if room_id != cfg.room_id:
        return Verdict(False, "foreign-room")
    if sender == cfg.user_id:
        return Verdict(False, "own-message")
    allow = {cfg.owner} | ({other_agent} if other_agent else set())
    if sender not in allow:
        return Verdict(False, "sender-not-allowlisted")
    return Verdict(True, "ok")


def should_join_invite(room_id: str, inviter: str, cfg: AgentConfig) -> bool:
    """Join only the owner's invite into the Agora room."""
    return room_id == cfg.room_id and inviter == cfg.owner


def should_reply(sender: str, cfg: AgentConfig) -> bool:
    """Reply to the owner alone until v1.2's turn-taking: two LLM bots that
    answer each other would loop forever."""
    return sender == cfg.owner


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


def build_instruction(name: str, persona: str) -> str:
    """The system instruction: the persona plus the literal Ukrainian rules line."""
    return f"{persona}\n\nТи — {name}. Відповідай лише від себе, коротко, без префікса з іменем."


ECHO_MAX_CHARS = 4000
ENTRY_MAX_CHARS = 4000


def echo_reply(name: str, text: str) -> str:
    """The literal v0.5 reply format (the bot sends exactly this), bounded so a
    pasted huge text is never doubled in full."""
    if len(text) > ECHO_MAX_CHARS:
        text = text[:ECHO_MAX_CHARS] + "…"
    return f"{name} чує: {text}"
