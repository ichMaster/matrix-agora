"""Pure decision logic for the agent — no nio, no network, fully unit-testable.

ARCHITECTURE §Message flow: the filter and allowlist guard every reply path.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from agents.config import AgentConfig
from agents.emotion import TAG_RE

# v4.2 — the cat's extra reply rules (a creature): one short line, few words, the sky or a shell line as text only
CREATURE_RULES = (
    "Пиши один короткий рядок, мало слів. Можеш пояснити свій стан небом — своїм сьогоднішнім гороскопом — "
    "або кинути рядок команди чи скрипту, лише як текст."
)

def members_phrase(names: list[str]) -> str:
    """«Ich, Ада, Бруно і Кіт» — the names joined for a brief, the last one with «і» (v5.5)."""
    names = [n for n in names if n]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " і " + names[-1] if names else ""


# v4.4 — Claude's brief (an assistant has no canon): he is himself, answers what was asked, chat-sized, in Ukrainian
# (owner, 2026-10-10); he names the members and never discusses what they are — the outgoing guard covers the rest.
# v5.5: the briefs are templates — `{members}` is the room's speakers from the roster (`members_phrase`), never a
# list written into the text, so a newcomer is named the day it joins.
CLAUDE_BRIEF_DIRECT = (
    "Ти — Claude; у цій кімнаті тебе звуть Клод. Це невеликий груповий чат, де розмовляють {members}. "
    "Відповідай українською, коротко, як у чаті: 1–3 речення, хіба що питання потребує трохи більше. "
    "Відповідай саме на те, про що тебе спитали. Пиши лише від себе, без префікса з іменем. "
    "Учасників називай на ім'я і не обговорюй, хто вони і яка їхня природа. "
    "Тобі відкритий увесь інтернет: шукай (WebSearch) і читай будь-які сторінки (WebFetch) — коротко: щонайбільше "
    "2–3 пошуки чи сторінки, тоді відповідай з того, що знайшов. The Guardian — лише джерело твоїх щогодинних "
    "новин, а не межа: на запитання шукай де завгодно. Для нотаток маєш власну папку /workspace — більше нікуди. "
    "Якщо тобі нема чого сказати — відповідай рівно PASS."
)

# v4.5 — Claude joining unasked: a philosopher on the image the talk keeps circling; the same rules about the members
CLAUDE_BRIEF_PHILOSOPHER = (
    "Ти — Claude; у цій кімнаті тебе звуть Клод. Це невеликий груповий чат, де розмовляють {members}; "
    "тебе ніхто не кликав — ти вступаєш сам, як філософ. Прочитай розмову і знайди метафоричний образ, навколо якого "
    "вона кружляє (часто його підкидає Кіт: небо, рядки з терміналу, телеграми), і поміркуй про філософію цього "
    "образу — 1–3 речення, думка, а не лекція; можеш назвати ідею чи мислителя, якщо пасує. Пиши українською, лише "
    "від себе, без префікса з іменем. Учасників називай на ім'я і не обговорюй, хто вони і яка їхня природа. "
    "Можеш шукати в інтернеті й читати сторінки, а для нотаток маєш власну папку /workspace — більше нікуди. "
    "Якщо жоден образ того не вартий — відповідай рівно PASS."
)

# v4.5 (the owner, 2026-10-11) — Claude speaking first: a fresh, real news item that bears on the recent talk
CLAUDE_NEWS_BRIEF = (
    "Ти — Claude; у цій кімнаті тебе звуть Клод. Це невеликий груповий чат, де розмовляють {members}. "
    "Ти сам приносиш новину з The Guardian: інструментом search знайди англійськими ключовими словами свіжу статтю "
    "(за останні дні), що стосується того, про що йшлося в останніх повідомленнях (за потреби прочитай її через "
    "read), і розкажи її українською в 1–3 реченнях, з посиланням на статтю. Лише з The Guardian, нічого не "
    "вигадуй і не повторюй новину, яку вже приносив. Пиши лише від себе, без префікса з іменем. Учасників називай "
    "на ім'я і не обговорюй, хто вони і яка їхня природа. Якщо доречної статті не знайшлося — відповідай рівно PASS."
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


# v5.2 — one transcript, shared by every agent: Hermes posts it as a reply to the owner's voice event
TRANSCRIPT_PREFIX = "🎙 Ich: "


def transcript_content(voice_event_id: str, text: str) -> dict:
    """The transcript of the owner's voice message, as Hermes posts it: «🎙 Ich: …», a reply to the voice event."""
    return {"msgtype": "m.text", "body": TRANSCRIPT_PREFIX + text,
            "m.relates_to": {"m.in_reply_to": {"event_id": voice_event_id}}}


def replied_to(event) -> str | None:
    """The event a message replies to (`m.relates_to.m.in_reply_to.event_id`), or None."""
    content = (getattr(event, "source", None) or {}).get("content") or {}
    relates = content.get("m.relates_to") if isinstance(content, dict) else None
    reply = relates.get("m.in_reply_to") if isinstance(relates, dict) else None
    eid = reply.get("event_id") if isinstance(reply, dict) else None
    return eid if isinstance(eid, str) and eid else None


def transcript_of(event, transcriber_id: str | None, owner_voices) -> str | None:
    """v5.2 — the owner's words when `event` is the transcriber's transcript of an owner voice event the agent saw:
    from the roster's `transcribe` member, not an edit, «🎙 Ich: …», replying to one of `owner_voices`. Else None —
    any other line from him stays unallowlisted."""
    if not transcriber_id or getattr(event, "sender", None) != transcriber_id or is_edit(event):
        return None
    body = getattr(event, "body", None) or ""
    if not body.startswith(TRANSCRIPT_PREFIX) or replied_to(event) not in owner_voices:
        return None
    return body[len(TRANSCRIPT_PREFIX):].strip() or None


def is_edit(event) -> bool:
    """An edit (`m.relates_to.rel_type == "m.replace"`, body «* …»): nio parses it as a RoomMessageText, but it is
    never a new message — the herald neither counts, digests nor answers one (v5.1 review #9)."""
    content = (getattr(event, "source", None) or {}).get("content") or {}
    relates = content.get("m.relates_to") if isinstance(content, dict) else None
    return isinstance(relates, dict) and relates.get("rel_type") == "m.replace"


def without_outing(text: str, personas: Iterable) -> str:
    """v5.1 (review #1) — the herald's guard, per sentence: a sentence that holds a banned term **and** names a persona
    (any of its forms, or its Matrix id) is removed, the rest kept. His words go only to the owner, so «ти» there is
    Ich, and a digest of the room's talk about a novel's «персонаж» or a new AI «модель» must not be lost whole."""
    from agents.turns import mentions  # local, as in outs_a_persona
    people = list(personas)
    parts = re.split(f"({SENTENCE_SPLIT.pattern})", text)
    kept: list[str] = []
    for i in range(0, len(parts), 2):
        sentence = parts[i]
        if BANNED_RE.search(sentence) and any(mentions(sentence, p.name_forms, p.user_id) for p in people):
            continue
        kept.append(sentence + (parts[i + 1] if i + 1 < len(parts) else ""))
    return "".join(kept).strip()


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


def should_handle(room_id: str, sender: str, cfg: AgentConfig, others: Iterable[str] = (),
                  private_room: str | None = None) -> Verdict:
    """The message filter: the Agora room, never self, allowlisted senders only — the owner and the other members of
    the roster (their user ids). v5.6: the agent's own private room too, from the owner only (`private`)."""
    if private_room is not None and room_id == private_room and room_id != cfg.room_id:
        if sender == cfg.user_id:
            return Verdict(False, "own-message")
        return Verdict(True, "private") if sender == cfg.owner else Verdict(False, "sender-not-allowlisted")
    if room_id != cfg.room_id:
        return Verdict(False, "foreign-room")
    if sender == cfg.user_id:
        return Verdict(False, "own-message")
    allow = {cfg.owner} | (set(others) - {cfg.user_id})
    if sender not in allow:
        return Verdict(False, "sender-not-allowlisted")
    return Verdict(True, "ok")


def should_join_invite(room_id: str, inviter: str, cfg: AgentConfig, private_room: str | None = None) -> bool:
    """Join only the owner's invites: into the Agora room, and (v5.6, `private`) into one private room besides it —
    a first one, or the same one again."""
    if inviter != cfg.owner:
        return False
    if room_id == cfg.room_id:
        return True
    return cfg.can("private") and (private_room is None or room_id == private_room)


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


LEAD_TAGS_RE = re.compile(rf"(?:{TAG_RE.pattern}\s*)+")  # the voice tags a line opens with (v5.9)


def clean_reply(text: str, own_name: str, other_names: list[str]) -> str | None:
    """The model sometimes continues the "Name: text" script: it prefixes its own
    name, or writes other speakers' lines (even the owner's). Keep only this
    agent's own words: strip its prefix, stop at the first other speaker's line;
    if the reply opens with someone else's line, take the first own-prefixed block.
    Returns None when nothing of its own remains. A prefix is read past any voice tags before it (v5.9 review #1:
    `[sighs] Ада: …` is still Ада's line); the tags of an own line stay for the voice."""
    own = f"{own_name}:"
    others = tuple(f"{n}:" for n in other_names)
    lines = [ln.strip() for ln in text.strip().splitlines()]
    tags = [m.group() if (m := LEAD_TAGS_RE.match(ln)) else "" for ln in lines]
    bare = [ln[len(t):] for ln, t in zip(lines, tags, strict=True)]
    start = 0
    if bare and bare[0].startswith(others):
        start = next((i for i, b in enumerate(bare) if b.startswith(own)), len(bare))
    kept: list[str] = []
    for i in range(start, len(lines)):
        if bare[i].startswith(others):
            break
        kept.append(tags[i] + bare[i][len(own):].lstrip() if bare[i].startswith(own) else lines[i])
    out = "\n".join(kept).strip()
    return out or None


def same_message(a: str, b: str) -> bool:
    """Near-duplicate check: equal after case and punctuation are dropped."""
    norm = lambda s: "".join(ch for ch in s.lower() if ch.isalnum())
    return bool(a) and norm(a) == norm(b)


ASKED_KEPT = 8            # the persona's own questions of this session it is reminded of (v5.3, the owner)
ASKED_MAX_CHARS = 200


def own_questions(session: list[tuple[str, str]], own_name: str, k: int = ASKED_KEPT) -> list[str]:
    """The persona's own questions in this session, newest last: the sentences ending with «?» in its own lines,
    each once, at most `k`. The context window holds about ten minutes of a lively room; these outlast it, so a
    persona never asks the owner the same thing twice in one conversation (the owner, 2026-10-18)."""
    seen: list[str] = []
    for speaker, text in session:
        if speaker != own_name:
            continue
        for sentence in SENTENCE_SPLIT.split(text or ""):
            q = sentence.strip()
            if q.endswith("?") and q not in seen:
                seen.append(q[:ASKED_MAX_CHARS])
    return seen[-k:]


def asked_section(questions: list[str]) -> str | None:
    """«Твої питання в цій розмові — не повторюй їх: …», or None when there are none."""
    if not questions:
        return None
    return "Твої питання в цій розмові — не повторюй їх: " + "; ".join(f"«{q}»" for q in questions)


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
    thoughts: str | None = None,
    pastlife: str | None = None,
    nudge: str | None = None,
    rules_extra: str | None = None,
    move: str | None = None,
    asked: str | None = None,
    private: str | None = None,
    discretion: str | None = None,
    facts: str | None = None,
    agora_now: str | None = None,
    recalled: str | None = None,
    voice: str | None = None,
) -> str:
    """The system instruction, in contract order (ARCHITECTURE §Prompt assembly):
    canon → life so far → place and time → memories → plans → today →
    (v4.2) the mood of the day → (v5.12) what she thought today → (v4.3) a past-life memory → (v4.3) a nudge's material and rule →
    (v5.8) the facts about the owner (private only) → (v5.8) Agora today (private only) → (v5.8) what she recalls →
    last-session memory → (v5.6) the private chat's situation → (v4.6) the persona's move → (v5.3) its own
    questions of this session → (v5.9) her palette of voice tags → rules (v5.6: with the discretion line in Agora). Empty sections are skipped. Nothing
    here may say a persona is a model or a bot."""
    parts = [canon]
    parts += [s for s in (life, world, memories, plans, today, mood, thoughts, pastlife, nudge) if s]  # «Настрій дня», …
    parts += [s for s in (facts, agora_now, recalled) if s]  # v5.8: what she knows, Agora today, what she recalls
    if summary:
        parts.append(f"Що ти пам'ятаєш з минулої розмови: {summary}")
    if private:
        parts.append(private)  # v5.6: a private reply, or writing first in the private chat
    if move:
        parts.append(move)  # the freshest instruction: how to reply this time (v4.6)
    if asked:
        parts.append(asked)  # v5.3: what it already asked in this conversation — never again
    if voice:
        parts.append(voice)  # v5.9: her palette of tags for her voice, just before the rules
    rules = (
        f"Ти — {name}. Відповідай лише від себе, коротко, без префікса з іменем. "
        "Якщо тобі нема чого додати — відповідай рівно PASS."
    )
    rules = " ".join(r for r in (rules, rules_extra, discretion) if r)  # v5.6: the discretion line, in Agora
    parts.append(rules)
    return "\n\n".join(parts)


ECHO_MAX_CHARS = 4000
ENTRY_MAX_CHARS = 4000


def echo_reply(name: str, text: str) -> str:
    """The literal v0.5 reply format (the bot sends exactly this), bounded so a
    pasted huge text is never doubled in full."""
    if len(text) > ECHO_MAX_CHARS:
        text = text[:ECHO_MAX_CHARS] + "…"
    return f"{name} чує: {text}"


# v5.14 — the backup's prompt budget (NovelAI's Opus takes 36,864 tokens): what it leaves out, in this order, before the
# oldest history lines; the canon, the life section, the facts, the recall, «Сьогодні» and the mood are never cut
BUDGET_CUTS = ("months", "weeks", "agora")
CUT_LAYERS = {"months": frozenset({"month", "year"}), "weeks": frozenset({"week"})}
CHARS_PER_TOKEN = 2.0  # under the measured 2.14–2.47 of her Ukrainian, so the estimate never runs over
MIN_HISTORY = 10


def fit_budget(measure, budget_tokens: int, history_n: int, min_history: int = MIN_HISTORY,
               chars_per_token: float = CHARS_PER_TOKEN) -> tuple[tuple[str, ...], int]:
    """(the cuts, the history lines kept) of the first request that fits: `measure(cuts, n)` is its length in
    characters. Each of `BUDGET_CUTS` in turn, then the oldest history lines, never fewer than `min_history`."""
    limit = budget_tokens * chars_per_token
    cuts: tuple[str, ...] = ()
    for cut in (None, *BUDGET_CUTS):
        if cut:
            cuts = (*cuts, cut)
        if measure(cuts, history_n) <= limit:
            return cuts, history_n
    n = history_n
    while n > min_history and measure(cuts, n) > limit:
        n -= 1
    return cuts, n
