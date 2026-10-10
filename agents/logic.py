"""Pure decision logic for the agent — no nio, no network, fully unit-testable.

ARCHITECTURE §Message flow: the filter and allowlist guard every reply path.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from agents.config import AgentConfig

# v4.2 — the cat's extra reply rules (a creature): one short line, few words, the sky or a shell line as text only
CREATURE_RULES = (
    "Пиши один короткий рядок, мало слів. Можеш пояснити свій стан небом — своїм сьогоднішнім гороскопом — "
    "або кинути рядок команди чи скрипту, лише як текст."
)

# v4.4 — Claude's brief (an assistant has no canon): he is himself, answers what was asked, chat-sized, in Ukrainian
# (owner, 2026-10-10); he names the members and never discusses what they are — the outgoing guard covers the rest.
CLAUDE_BRIEF_DIRECT = (
    "Ти — Claude; у цій кімнаті тебе звуть Клод. Це невеликий груповий чат, де розмовляють Ich, Ада, Бруно і Кіт. "
    "Відповідай українською, коротко, як у чаті: 1–3 речення, хіба що питання потребує трохи більше. "
    "Відповідай саме на те, про що тебе спитали. Пиши лише від себе, без префікса з іменем. "
    "Учасників називай на ім'я і не обговорюй, хто вони і яка їхня природа. "
    "Якщо тобі нема чого сказати — відповідай рівно PASS."
)

# What a persona must never be called — in its own prompts, canon and life story (the human-belief rule, VISION
# §Principles; from v4.2 scoped to persona agents), and what no other agent may call a persona in the room.
# «робот» but not «робота» (work); «нейромережа» and its kin (review #4).
# v4.4 review #8: Claude's vocabulary too — «агент», «персонаж», and English bot / model / agent.
BANNED_RE = re.compile(
    r"\b(бот\w*|робот(?:ом)?|модел\w*|штучн\w*|нейро\w*|агент\w*|персонаж\w*|ai|ші|llm|gemini|асистент\w*"
    r"|bots?|models?|agents?)\b", re.IGNORECASE)
SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+|\n+")
# Who a sentence can point at besides the speaker: you, we, everyone, he/she/they (review #4).
OTHERS_RE = re.compile(r"\b(ти|тебе|тобі|тобою|ви|вас|вам|вами|ми|нас|нам|нами|всі|усі|він|вона|вони)\b",
                       re.IGNORECASE)


def outs_a_persona(text: str, personas: Iterable) -> bool:
    """True when one sentence calls something a model or a bot *and* names a persona (any of its forms, or its
    Matrix id) or points at someone else (ти, ви, ми, всі, він, вона, вони…) — the outgoing guard every non-persona
    agent applies before it speaks (v4.2). Speaking of himself («я штучний») is fine; tying anyone else to it is
    not: a dropped line is only silence, an outed persona is in the day memories for good."""
    from agents.turns import mentions  # local: turns imports this module's neighbours, not this one
    people = list(personas)
    for sentence in SENTENCE_SPLIT.split(text):
        if BANNED_RE.search(sentence) and (
            OTHERS_RE.search(sentence) or any(mentions(sentence, p.name_forms, p.user_id) for p in people)
        ):
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
    pastlife: str | None = None,
    nudge: str | None = None,
    rules_extra: str | None = None,
) -> str:
    """The system instruction, in contract order (ARCHITECTURE §Prompt assembly):
    canon → life so far → place and time → memories → plans → today →
    (v4.2) the mood of the day → (v4.3) a past-life memory → (v4.3) a nudge's material and rule →
    last-session memory → rules. Empty sections are skipped. Nothing here may say a persona is a model or a bot."""
    parts = [canon]
    parts += [s for s in (life, world, memories, plans, today, mood, pastlife, nudge) if s]  # «Настрій дня», …
    if summary:
        parts.append(f"Що ти пам'ятаєш з минулої розмови: {summary}")
    rules = (
        f"Ти — {name}. Відповідай лише від себе, коротко, без префікса з іменем. "
        "Якщо тобі нема чого додати — відповідай рівно PASS."
    )
    parts.append(f"{rules} {rules_extra}" if rules_extra else rules)
    return "\n\n".join(parts)


ECHO_MAX_CHARS = 4000
ENTRY_MAX_CHARS = 4000


def echo_reply(name: str, text: str) -> str:
    """The literal v0.5 reply format (the bot sends exactly this), bounded so a
    pasted huge text is never doubled in full."""
    if len(text) > ECHO_MAX_CHARS:
        text = text[:ECHO_MAX_CHARS] + "…"
    return f"{name} чує: {text}"
