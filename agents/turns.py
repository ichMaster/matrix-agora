"""Turn-taking for N agents (v4.1): who replies, after what delay — pure functions, rng injected.

ARCHITECTURE §Turn-taking. Every agent derives every decision from the same inputs — the server-assigned
`event_id`, the shared room timeline and the roster that ships in every image — so they all agree with no shared
state and no coordination (never add any).
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from agents.config import AgentConfig
from agents.roster import Member

PASS_RE = re.compile(r"^\W*PASS\W*$")
TRAILING_PASS_RE = re.compile(r"\s*\bPASS\W*$")
# the owner addressing the whole room → every member answers. Only in an addressing position — the start of the
# message, right before , ! ? or its end, or after «ви»/«вам» — so «я кожен день гуляю» is no address (review #4)
_GROUP = r"(?:всі|усі|всім|усім|кожен|кожна|кожному)"
GROUP_RE = re.compile(
    rf"^\W*{_GROUP}(?!\w)|(?<!\w){_GROUP}\s*(?:[,!?]|$)|(?<!\w)(?:ви|вам)\s+{_GROUP}(?!\w)", re.IGNORECASE)

# a timeline entry: (speaker name, server_ts_ms, event_id[, purr]) — the same for every agent in the room
Entry = tuple

# v4.2 — the cat's purrs: produced in code (zero tokens); every agent recognises one in the timeline
PURRS = ("Мрррр.", "Мур.", "Мур-мур…", "*потягується*", "*мружиться*", "Мрр… *позіхає*")
# One way only to split a line into tokens: the separators trail each token, so nothing can backtrack (review #1).
PURR_RE = re.compile(r"^(?:(?:м+у*р+(?:-м+у*р+)?|\*[^*\n]{1,30}\*)[\s.,!…]*)+$", re.IGNORECASE)
PURR_MAX_CHARS = 80


def is_purr(text: str) -> bool:
    """A purr-only line («Мрррр.», «мур-мур…», «*потягується*»): it never counts in a wave, never makes anyone
    answer, and is transparent to "the latest message" (v4.2)."""
    t = (text or "").strip()
    return bool(t) and len(t) <= PURR_MAX_CHARS and bool(PURR_RE.match(t))


def _real(timeline: list) -> list:
    """The timeline without purrs."""
    return [e for e in timeline if not (len(e) > 3 and e[3])]


@dataclass(frozen=True)
class ReplyDecision:
    reply: bool
    delay_s: float = 0.0
    reason: str = ""
    purr: bool = False  # v4.2: the reply is a purr, produced in code


def mentions(text: str, forms: Iterable[str], user_id: str) -> bool:
    """True when `text` names this agent — any of its `name_forms` from the roster, as a whole word — or its
    Matrix id."""
    low = text.lower()
    if user_id.lower() in low:
        return True
    return any(re.search(rf"(?<!\w){re.escape(f)}(?!\w)", low) for f in forms)


def addresses_everyone(text: str) -> bool:
    return bool(GROUP_RE.search(text))


def rank(event_id: str, members: Iterable[Member]) -> list[str]:
    """Weighted rendezvous (highest-random-weight) hashing: the members' localparts, highest score first.

    The same `event_id` always gives the same order on every machine — `hashlib`, never Python's salted `hash()`;
    a member's share of first places follows its weight; different events give different orders."""
    def score(m: Member) -> tuple[float, str]:
        return (-m.weight / math.log(uniform(event_id, m.localpart)), m.localpart)
    return [m.localpart for m in sorted(members, key=score, reverse=True)]


def uniform(event_id: str, localpart: str) -> float:
    """A deterministic draw strictly inside (0, 1): 52 bits of sha256, centred — (x + 0.5) / 2**52 is exactly
    representable, so it never rounds to 0.0 or 1.0 (code review #6: the old (x + 1) / (2**64 + 1) rounded to 1.0
    for the top digests)."""
    x = int.from_bytes(hashlib.sha256(f"{event_id}\n{localpart}".encode()).digest()[:8], "big") >> 12
    return (x + 0.5) / 2**52


def named(text: str, members: Iterable[Member]) -> list[Member]:
    return [m for m in members if mentions(text, m.name_forms, m.user_id)]


def owner_repliers(event_id: str, text: str, roster: Mapping[str, Member], k: int) -> list[str]:
    """R1 — who answers an owner message: the named agents; on a group address every ranked and mention-only
    member; otherwise the top `k` ranked members by `rank`."""
    by_name = named(text, roster.values())
    if by_name:
        return [m.localpart for m in by_name]
    if addresses_everyone(text):
        return [m.localpart for m in roster.values() if m.mode in ("ranked", "mention-only")]
    return rank(event_id, [m for m in roster.values() if m.mode == "ranked"])[:max(k, 0)]


def next_speaker(event_id: str, sender_id: str, text: str, roster: Mapping[str, Member]) -> str | None:
    """R2 — the one candidate to follow an agent message: among the members it names (ranked or mention-only),
    otherwise among the ranked members — never its sender; top by `rank`."""
    others = [m for m in roster.values() if m.user_id != sender_id]
    by_name = [m for m in named(text, others) if m.mode in ("ranked", "mention-only")]
    pool = by_name or [m for m in others if m.mode == "ranked"]
    return rank(event_id, pool)[0] if pool else None


def wave_count(timeline: list[Entry], owner_name: str, now_ms: int | None = None,
               window_ms: int | None = None) -> int:
    """Agent messages since the owner's last one, newest first — **including** the message being answered (the
    timeline's last entry). With a window, only those newer than `now_ms - window_ms` count, so the limit is a
    rate (MAX_BOT_TURNS per window), not a lock until the owner speaks. Replaces v1.2's `bot_streak`, which
    excluded the answered message: the same behavior needs MAX_BOT_TURNS + 1."""
    n = 0
    for name, ts, *_ in reversed(_real(timeline)):
        if name == owner_name:
            break
        if window_ms is not None and now_ms is not None and int(ts) < now_ms - window_ms:
            break
        n += 1
    return n


def wave_frees_at(timeline: list[Entry], owner_name: str, now_ms: int, window_ms: int, max_turns: int) -> int | None:
    """When a blocked wave drops below `max_turns` (server ms), or None if it is not blocked."""
    counted: list[int] = []
    for name, ts, *_ in reversed(_real(timeline)):
        if name == owner_name or ts < now_ms - window_ms:
            break
        counted.append(ts)
    if len(counted) < max_turns or max_turns <= 0:
        return None
    return counted[max_turns - 1] + window_ms + 1


def pending_answers(timeline: list[Entry], owner_event_id: str | None, chosen_names: set[str], owner_name: str,
                    now_ms: int | None = None, lapse_ms: int | None = None) -> int:
    """How many of the owner's chosen repliers have not answered yet. Every agent computes the chosen set from the
    same owner message (`owner_repliers` is deterministic), so the answers still on their way are reserved in the
    wave: an agent-to-agent reply never overtakes them. A reservation lapses `lapse_ms` (FALLBACK_S) after the
    owner's message — a chosen agent that passed, failed or is away never holds the wave (code review #2)."""
    real = _real(timeline)
    for i, (name, ts, eid, *_) in enumerate(real):
        if eid == owner_event_id:
            if lapse_ms is not None and now_ms is not None and now_ms - ts >= lapse_ms:
                return 0
            arrived = {n for n, *_ in real[i + 1:] if n != owner_name}
            return len(chosen_names - arrived)
    return 0


def reservation_lapses_at(timeline: list[Entry], owner_event_id: str | None, lapse_ms: int) -> int | None:
    """When the owner's pending answers stop holding the wave (server ms), or None if the message is not seen."""
    for _name, ts, eid, *_ in timeline:
        if eid == owner_event_id:
            return ts + lapse_ms
    return None


def still_current(timeline: list[Entry], trigger_id: str, owner_name: str, now_ms: int, window_ms: int,
                  max_turns: int, reserved: int = 0) -> bool:
    """R3 — an agent-to-agent reply fires only while the message it answers is still the latest one and the wave
    (with the owner's answers still on their way) is still below the limit."""
    real = _real(timeline)  # a purr is transparent: it never makes a message "not the latest"
    return bool(real) and real[-1][2] == trigger_id and \
        wave_count(timeline, owner_name, now_ms, window_ms) + reserved < max_turns


def fallback_due(timeline: list[Entry], owner_event_id: str) -> bool:
    """True while the owner's message is still the room's latest: no agent has answered it and the owner has not
    written again (a newer owner message brings its own R1)."""
    real = _real(timeline)
    return bool(real) and real[-1][2] == owner_event_id


def fallback_replier(event_id: str, text: str, roster: Mapping[str, Member], k: int) -> str | None:
    """The best-ranked ranked member that R1 did not choose — only for an unnamed, non-group owner message."""
    if named(text, roster.values()) or addresses_everyone(text):
        return None
    chosen = set(owner_repliers(event_id, text, roster, k))
    rest = [m for m in roster.values() if m.mode == "ranked" and m.localpart not in chosen]
    return rank(event_id, rest)[0] if rest else None


def decide_reply(
    sender: str,
    text: str,
    event_id: str,
    wave: int,
    cfg: AgentConfig,
    me: Member,
    roster: Mapping[str, Member],
    *,
    owner_repliers_k: int,
    max_bot_turns: int,
    bot_reply_p: float,
    reply_delay_s: float,
    rng: Callable[[], float],
    react_p: float = 0.3,
    purr_p: float = 0.8,
) -> ReplyDecision:
    """The who-replies rule for one incoming, already-allowlisted message. `wave` is `wave_count` with the message
    itself plus the owner's answers still on their way (`pending_answers`); answers to the owner never wait for
    it, agent-to-agent replies stay below `max_bot_turns`."""
    def delay() -> float:
        return 1.0 + rng() * max(reply_delay_s - 1.0, 0.0)

    allowed = sender == cfg.owner or any(m.user_id == sender for m in roster.values())
    if me.mode == "ambient" and allowed and sender != me.user_id:
        return _ambient(sender, text, event_id, wave, cfg, me, max_bot_turns, react_p, purr_p, delay)
    if sender != cfg.owner and is_purr(text):
        return ReplyDecision(False, reason="purr")  # a purr never makes anyone answer
    if sender == cfg.owner:
        if me.localpart not in owner_repliers(event_id, text, roster, owner_repliers_k):
            return ReplyDecision(False, reason="owner-chose-others")
        if mentions(text, me.name_forms, me.user_id):
            return ReplyDecision(True, 0.0, "owner-mentioned-me")
        return ReplyDecision(True, delay(), "owner-chose-me")
    if any(m.user_id == sender for m in roster.values()) and sender != me.user_id:
        if next_speaker(event_id, sender, text, roster) != me.localpart:
            return ReplyDecision(False, reason="not-next-speaker")
        if wave >= max_bot_turns:
            return ReplyDecision(False, reason="wave-limit")
        if rng() >= bot_reply_p:  # naming decides who, not whether
            return ReplyDecision(False, reason="probability")
        return ReplyDecision(True, delay(), "next-speaker")
    return ReplyDecision(False, reason="not-allowlisted")


def ambient_draw(event_id: str, text: str, m: Member, react_p: float, purr_p: float,
                 from_owner: bool) -> str | None:
    """An ambient member's deterministic reaction to one message: "speak", "purr" or None. Every agent computes the
    same answer from the event id and the shared settings — so the owner's pending answers can include the cat's."""
    named = mentions(text, m.name_forms, m.user_id)
    if from_owner and named:
        return "speak"
    if uniform(event_id, "react:" + m.localpart) >= min(1.0, react_p * (2 if named else 1)):
        return None
    return "purr" if uniform(event_id, "purr:" + m.localpart) < purr_p else "speak"


def owner_speakers(event_id: str, text: str, roster: Mapping[str, Member], k: int, react_p: float,
                   purr_p: float) -> list[str]:
    """Everyone who will *speak* to an owner message: R1's chosen plus the ambient members whose draw is a spoken
    reaction — the answers reserved in the wave while they are on their way."""
    out = owner_repliers(event_id, text, roster, k)
    out += [m.localpart for m in roster.values()
            if m.mode == "ambient" and ambient_draw(event_id, text, m, react_p, purr_p, True) == "speak"]
    return out


def _ambient(sender: str, text: str, event_id: str, wave: int, cfg: AgentConfig, me: Member, max_bot_turns: int,
             react_p: float, purr_p: float, delay: Callable[[], float]) -> ReplyDecision:
    """v4.2 — an ambient member (the cat): named by the owner, it always answers; otherwise it reacts on its own
    deterministic draw (`react_p`, doubled when an agent names it — raised, not forced), and a reaction is a purr
    with `purr_p`. A purr is free and never limited; a spoken reaction to an agent obeys the wave limit."""
    from_owner = sender == cfg.owner
    draw = ambient_draw(event_id, text, me, react_p, purr_p, from_owner)
    if from_owner and mentions(text, me.name_forms, me.user_id):
        return ReplyDecision(True, 0.0, "owner-mentioned-me", purr=False)
    if draw is None:
        return ReplyDecision(False, reason="ambient-quiet")
    if not from_owner and is_purr(text):
        return ReplyDecision(False, reason="purr")  # never purrs at a purr; the owner's «мур» is a message
    purr = draw == "purr"
    if not purr and not from_owner and wave >= max_bot_turns:
        return ReplyDecision(False, reason="ambient-wave-limit")
    return ReplyDecision(True, delay(), "ambient-purr" if purr else "ambient-speak", purr=purr)


def pick_purr(event_id: str, localpart: str) -> str:
    return PURRS[int(uniform(event_id, "which:" + localpart) * len(PURRS))]


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
