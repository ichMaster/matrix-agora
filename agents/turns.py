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
TRAILING_PASS_RE = re.compile(r"\s*\bPASS\W*$")


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


def bot_streak(
    timeline: list[tuple[str, int]] | list[tuple[str, str]],
    owner_name: str,
    now_ms: int | None = None,
    window_ms: int | None = None,
) -> int:
    """Consecutive agent messages since the owner's last one (from the tail).

    With a window, only agent messages newer than `now_ms - window_ms` count, so
    the limit is a rate (MAX_BOT_TURNS per window), not a lock until the owner
    speaks. Timeline entries are (name, server_ts_ms) — the same server
    timestamps both agents see, so they still agree with no shared state.
    """
    n = 0
    for name, ts in reversed(timeline):
        if name == owner_name:
            break
        if window_ms is not None and now_ms is not None and int(ts) < now_ms - window_ms:
            break
        n += 1
    return n


def streak_frees_at(
    timeline: list[tuple[str, int]], owner_name: str, now_ms: int, window_ms: int, max_turns: int,
) -> int | None:
    """When a blocked streak drops below `max_turns` (server ms), or None if not blocked."""
    counted: list[int] = []
    for name, ts in reversed(timeline):
        if name == owner_name or ts < now_ms - window_ms:
            break
        counted.append(ts)
    if len(counted) < max_turns or max_turns <= 0:
        return None
    return counted[max_turns - 1] + window_ms + 1


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


def strip_pass(reply: str) -> str | None:
    """The reply without the PASS sentinel, or None when nothing of its own is left.

    The model sometimes writes its text and then PASS — on its own line or at the very end — and the literal word
    reached the room (2026-10-04 chat). A standalone PASS line and a trailing PASS are dropped; the rest is sent.
    """
    kept = [line for line in reply.strip().splitlines() if not PASS_RE.match(line.strip())]
    text = TRAILING_PASS_RE.sub("", "\n".join(kept).rstrip()).strip()
    return text if re.search(r"\w", text) else None
