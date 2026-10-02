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


def should_echo(sender: str, cfg: AgentConfig) -> bool:
    """v0.5 only: echo the owner alone. Echoing the other agent would make the
    two bots echo each other forever — turn-taking arrives in v1.2."""
    return sender == cfg.owner


def echo_reply(name: str, text: str) -> str:
    """The literal v0.5 reply format (the bot sends exactly this)."""
    return f"{name} чує: {text}"
