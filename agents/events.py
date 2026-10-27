"""Events of her life (v5.11; the owner, 2026-10-26) — things that happen to a person that she did not plan.

Three sources fill one append-only file a day, `state/<name>.events/YYYY-MM-DD.md`:
- her life story's dated events (`agents/life.py`), entered on their date — `known` ahead or a `surprise`;
- an hourly roll in her waking hours: at `EVENT_P` an event of a weighted kind (everyday, joyful, inspiring, heavy),
  written by one call inside her life's frame;
- Lviv's news, woven in rarely (`agents/citynews.py`).

A block is `## HH:MM · <kind> · <source>` and its text; hidden `<!-- … -->` lines record the rolled hours, the
rolled news items and a news item's link. Only `events_for_prompt` reaches a prompt: the time and the text, never
the kind, the source, a marker or a link. An event involves only her, her people outside the room and the city —
never Ich's or a member's words or deeds (`event_ok`). Everything here is pure; the agent owns the clock, the rng,
the call and the file.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime

KINDS = ("everyday", "joyful", "inspiring", "heavy")
DEFAULT_WEIGHTS = "everyday:6,joyful:2,inspiring:2,heavy:1"
SOURCES = ("known", "surprise", "rolled", "news")
# what the event call asks for, by kind
KIND_ASK = {
    "everyday": "звичайна подія дня — невелика, але справжня: зустріч, дзвінок чи новина від когось із твоїх людей, "
                "щось на роботі чи в місті",
    "joyful": "радісна подія — щось хороше, що сталося з тобою чи з кимось із твоїх людей",
    "inspiring": "подія, що надихнула: ідея, відкриття, зустріч чи слово, від якого з'явилися сили",
    "heavy": "важка подія — хвороба, втрата, справжня невдача чи погана новина; без мелодрами, як буває в житті",
}
EVENT_MAX_WORDS = 60

_BLOCK_RE = re.compile(r"^## (\d{2}:\d{2}) · (\w+) · (\w+)\s*$", re.MULTILINE)
_ROLLED_RE = re.compile(r"<!-- rolled (\d{2}) -->")
_NEWS_RE = re.compile(r"<!-- news-rolled (\S+) -->")
_LINK_RE = re.compile(r"<!-- link: (\S+) -->")
_TAG_RE = re.compile(r"\s*<!--.*?-->\s*", re.DOTALL)
# Ich, in any case and either alphabet
_ICH_RE = r"ich\w*|іч(?:а|у|ем|еві|е)?"


@dataclass(frozen=True)
class Event:
    time: str              # HH:MM, local
    kind: str              # KINDS, `story` for her life story's dated events, a way of `agents.citynews.WAYS`
    source: str            # SOURCES
    text: str
    link: str | None = None


@dataclass(frozen=True)
class DayLog:
    events: tuple[Event, ...] = ()
    rolled: frozenset[int] = field(default_factory=frozenset)    # the hours already rolled
    news: frozenset[str] = field(default_factory=frozenset)      # the links of the news items already rolled


def parse_weights(spec: str) -> dict[str, float]:
    """`everyday:6,joyful:2,inspiring:2,heavy:1` → the kinds' weights; a kind left out weighs 0. An unknown or
    repeated kind, a negative or non-numeric weight, or all of them zero is a ValueError."""
    weights: dict[str, float] = {}
    for part in str(spec).split(","):
        kind, sep, value = part.strip().partition(":")
        kind = kind.strip()
        if not sep or kind not in KINDS or kind in weights:
            raise ValueError(f"not kind:weight of {', '.join(KINDS)}, each once: {part.strip()!r}")
        try:
            weight = float(value)
        except ValueError:
            raise ValueError(f"not a number: {part.strip()!r}") from None
        if not weight >= 0 or weight == float("inf"):
            raise ValueError(f"not a weight ≥ 0: {part.strip()!r}")
        weights[kind] = weight
    if not any(weights.values()):
        raise ValueError("every weight is zero")
    return {k: weights.get(k, 0.0) for k in KINDS}


def format_weights(weights: dict[str, float]) -> str:
    return ",".join(f"{k}:{weights[k]:g}" for k in KINDS if k in weights)


def roll_event(rng: Callable[[], float], p: float, weights: dict[str, float]) -> str | None:
    """One hourly roll: None at 1 − p, else a kind drawn by its weight."""
    if rng() >= p:
        return None
    total = sum(weights.values())
    x = rng() * total
    for kind in KINDS:
        x -= weights.get(kind, 0.0)
        if x < 0:
            return kind
    return next(k for k in reversed(KINDS) if weights.get(k, 0.0) > 0)  # x landed exactly on the total


def hour_due(now: datetime, in_window: bool, rolled: Iterable[int]) -> bool:
    """Once per local hour inside her waking hours; an hour she was not running for is never caught up."""
    return in_window and now.hour not in set(rolled)


def parse_day(text: str | None) -> DayLog:
    """The day file → its events (oldest first), the rolled hours and the rolled news links."""
    text = text or ""
    heads = list(_BLOCK_RE.finditer(text))
    events = []
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        chunk = text[m.end():end]
        link = _LINK_RE.search(chunk)
        body = _TAG_RE.sub("\n", chunk).strip()
        if body:
            events.append(Event(m[1], m[2], m[3], " ".join(body.split()), link[1] if link else None))
    return DayLog(tuple(events), frozenset(int(h) for h in _ROLLED_RE.findall(text)),
                  frozenset(_NEWS_RE.findall(text)))


def block(event: Event) -> str:
    """One event as appended to the day file."""
    link = f"<!-- link: {event.link} -->\n" if event.link else ""
    return f"\n## {event.time} · {event.kind} · {event.source}\n{link}{event.text.strip()}\n"


def rolled_marker(hour: int) -> str:
    return f"<!-- rolled {hour:02d} -->\n"


def news_marker(link: str) -> str:
    return f"<!-- news-rolled {link} -->\n"


def events_for_prompt(events: Iterable[Event]) -> str:
    """`[HH:MM] text` a line — all a prompt ever sees of an event."""
    return "\n".join(f"[{e.time}] {e.text}" for e in events)


def forbidden_re(names: Iterable[str]) -> re.Pattern:
    """Ich and the room's members, as whole words in any case — an event never names them."""
    forms = sorted({n.strip().lower() for n in names if n and n.strip()}, key=len, reverse=True)
    alts = [_ICH_RE, *(re.escape(f) for f in forms)]
    return re.compile(r"(?<!\w)(?:" + "|".join(alts) + r")(?!\w)", re.IGNORECASE)


def event_ok(text: str | None, forbidden: re.Pattern) -> bool:
    """An event to keep: not empty, naming neither Ich nor a member, with no word the persons are never called."""
    from agents.logic import BANNED_RE  # the human-belief rule's own list

    text = (text or "").strip()
    return bool(text) and not forbidden.search(text) and not BANNED_RE.search(text)


EVENT_RULES = (
    "Подія стосується лише тебе, твоїх людей поза Агорою і міста. Ich і люди з Агори в ній не з'являються: нічого "
    "не вигадуй про їхні слова чи вчинки. Без дат, без заголовків і без вступу."
)


def event_request(name: str, canon: str, kind: str, now: datetime, chapter_body: str, next_opening: str | None,
                  plan: str | None, mood: str | None, recent: str | None) -> tuple[str, str]:
    """(system, contents) for one event of `kind`, inside her life's frame; the next chapter is a silent direction."""
    parts = [f"Твоє життя зараз:\n{chapter_body}"]
    if next_opening:
        parts.append("Куди тебе поволі тягне життя (не називай цього і не пиши як про факт — нехай лише тихо "
                     f"відчувається): {next_opening}")
    if plan:
        parts.append(f"Твій план на сьогодні:\n{plan}")
    if mood:
        parts.append(f"Настрій дня: {mood}")
    if recent:
        parts.append(f"Що з тобою сталося останнім часом:\n{recent}")
    parts.append(
        f"Зараз {now:%H:%M}. Щойно з тобою трапилося те, чого ти не планував(-ла): {KIND_ASK[kind]}. Розкажи про це "
        f"одним-двома реченнями від першої особи, у минулому часі, не більше {EVENT_MAX_WORDS} слів — що саме "
        "сталося, з ким і де. Нехай воно рухає одну з ниточок твого життя на крок і не повторює того, що вже "
        f"сталося. {EVENT_RULES}"
    )
    return f"{canon}\n\nТи — {name}.", "\n\n".join(parts)
