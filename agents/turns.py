"""Turn-taking: who replies, after what delay — pure functions, rng injected.

ARCHITECTURE §Turn-taking. Both agents derive `bot_streak` from the same room
timeline, so the count agrees with no shared state.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from agents.config import AgentConfig

# Ukrainian case forms of the agent names (lowercase). Бруно is invariant.
NAME_FORMS = {
    "Ада": ["ада", "ади", "аді", "аду", "адою", "адо"],
    "Бруно": ["бруно"],
}

PASS_RE = re.compile(r"^\W*PASS\W*$")


@dataclass(frozen=True)
class ReplyDecision:
    reply: bool
    delay_s: float = 0.0
    reason: str = ""


def mentions(text: str, name: str, user_id: str) -> bool:
    """True when `text` names this agent (any case form) or its Matrix id."""
    low = text.lower()
    if user_id.lower() in low:
        return True
    forms = NAME_FORMS.get(name, [name.lower()])
    return any(re.search(rf"(?<!\w){re.escape(f)}(?!\w)", low) for f in forms)


def bot_streak(history: list[tuple[str, str]], owner_name: str) -> int:
    """Consecutive agent messages since the owner's last one (from the tail)."""
    n = 0
    for name, _ in reversed(history):
        if name == owner_name:
            break
        n += 1
    return n


def decide_reply(
    sender: str,
    text: str,
    streak: int,
    cfg: AgentConfig,
    other_agent: str | None,
    other_name: str | None,
    *,
    max_bot_turns: int,
    bot_reply_p: float,
    reply_delay_s: float,
    rng: Callable[[], float],
) -> ReplyDecision:
    """The who-replies rule for one incoming, already-allowlisted message."""
    if sender == cfg.owner:
        mine = mentions(text, cfg.name, cfg.user_id)
        others = bool(other_name) and mentions(text, other_name, other_agent or "")
        if mine:
            return ReplyDecision(True, 0.0, "owner-mentioned-me")
        if others:
            return ReplyDecision(False, reason="owner-mentioned-other")
        return ReplyDecision(True, 1.0 + rng() * max(reply_delay_s - 1.0, 0.0), "owner-no-mention")
    if other_agent and sender == other_agent:
        if streak >= max_bot_turns:
            return ReplyDecision(False, reason="streak-limit")
        if mentions(text, cfg.name, cfg.user_id):
            # addressed by name: answer for sure — still bounded by the streak above
            return ReplyDecision(True, 1.0 + rng() * max(reply_delay_s - 1.0, 0.0), "agent-mentioned-me")
        if rng() >= bot_reply_p:
            return ReplyDecision(False, reason="probability")
        return ReplyDecision(True, 1.0 + rng() * max(reply_delay_s - 1.0, 0.0), "agent-reply")
    return ReplyDecision(False, reason="not-allowlisted")


def is_pass(reply: str) -> bool:
    """Exactly PASS (whitespace/punctuation-tolerant) means: send nothing."""
    return bool(PASS_RE.match(reply.strip()))
