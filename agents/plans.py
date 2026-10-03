"""Plans on four horizons — year, month, week, day — with mutations
(ARCHITECTURE §Memory, Plans). Pure helpers; the agent does the I/O.

Mutations are rolled by code before generation and stored as hidden
`<!-- mutation: kind -->` tags. Tags never reach a conversational prompt: the
agent holds every plan as a sincere intention.
"""

from __future__ import annotations

import re
from collections.abc import Callable

MUTATION_KINDS = {
    "spontaneous": "спонтанна ідея, якої немає у твоєму звичному житті",
    "place": "звична справа, але в незвичному для тебе місці",
    "postponed": "щось, що ти щиро плануєш, але навряд чи встигнеш",
    "cancelled": "щось, від чого ти, найімовірніше, відмовишся",
    "whim": "нова раптова забаганка",
}
KIND_ORDER = list(MUTATION_KINDS)

HORIZONS = {  # horizon → (items, Ukrainian «на …» phrase)
    "year": (4, "на рік"),
    "month": (5, "на місяць"),
    "week": (6, "на тиждень"),
    "day": (5, "на день"),
}

TAG_RE = re.compile(r"\s*<!--.*?-->")
ITEM_RE = re.compile(r"^\s*(?:[-•*]|\d+[.)])\s+(.*\S)\s*$")


def roll_mutations(n_items: int, rate: float, rng: Callable[[], float]) -> list[str | None]:
    """For each item: a mutation kind with probability `rate`, else None."""
    out: list[str | None] = []
    for _ in range(n_items):
        if rng() < rate:
            out.append(KIND_ORDER[int(rng() * len(KIND_ORDER)) % len(KIND_ORDER)])
        else:
            out.append(None)
    return out


def strip_tags(text: str) -> str:
    return TAG_RE.sub("", text).strip()


def parse_items(text: str) -> list[str]:
    items = [m[1] for line in text.splitlines() if (m := ITEM_RE.match(line))]
    if not items:  # the model ignored the list format — take non-empty lines
        items = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return items


def render_plan(items: list[str], mutations: list[str | None], max_words: int) -> str:
    """'- item' lines with hidden mutation tags, trimmed to the word budget."""
    lines, words = [], 0
    for i, item in enumerate(items):
        n = len(item.split())
        if lines and words + n > max_words:
            break
        words += n
        kind = mutations[i] if i < len(mutations) else None
        lines.append(f"- {item}" + (f" <!-- mutation: {kind} -->" if kind else ""))
    return "\n".join(lines)


def plan_request(
    horizon: str,
    name: str,
    canon: str,
    period_label: str,
    chapter_body: str,
    next_opening: str | None,
    coarser: list[tuple[str, str]],
    previous_plan: str | None,
    recent_memory: str | None,
    mutations: list[str | None],
    max_words: int,
) -> tuple[str, str]:
    """(system_instruction, contents) for one plan. The next chapter is a
    silent direction; the mutated items are bent but read as sincere intents."""
    n_items, phrase = HORIZONS[horizon]
    parts = [f"Твоє життя зараз:\n{chapter_body}"]
    if next_opening:
        parts.append(
            "Куди тебе поволі тягне життя (не називай цього і не пиши як про факт — "
            f"нехай лише тихо відчувається в намірах): {next_opening}"
        )
    for label, text in coarser:
        parts.append(f"Твої плани {label}:\n{text}")
    if previous_plan:
        parts.append(f"Твій попередній план (незроблене можна перенести):\n{previous_plan}")
    if recent_memory:
        parts.append(f"Що було нещодавно:\n{recent_memory}")
    bent = [f"пункт №{i + 1} — {MUTATION_KINDS[k]}" for i, k in enumerate(mutations) if k]
    task = (
        f"Склади свій план {phrase} ({period_label}): рівно {n_items} пунктів, кожен з нового рядка, "
        f"що починається з «- », від першої особи, коротко, як щирі наміри, разом не більше {max_words} "
        "слів. Плани стосуються лише тебе і міста — нічого не обіцяй за інших людей з Агори."
    )
    if bent:
        task += " Відхилення від твого звичного життя: " + "; ".join(bent) + \
            ". У тексті ці пункти мають звучати як звичайні щирі наміри."
    parts.append(task)
    return f"{canon}\n\nТи — {name}.", "\n\n".join(parts)


def split_summary(text: str) -> tuple[str, str | None]:
    """The summary call returns «НОТАТКА: …» (rolling) and «СЬОГОДНІ: …» (this
    session only). Missing markers → the whole text is the note."""
    m = re.search(r"НОТАТКА\s*:\s*(.*?)(?:\n\s*СЬОГОДНІ\s*:\s*(.*))?$", text.strip(), re.DOTALL)
    if not m:
        return text.strip(), None
    note = m[1].strip()
    today = (m[2] or "").strip() or None
    return note, today
