"""v7.6 (AGORA-262) — her own recall on Gemini in `lumi` mode (ROADMAP §v7.6, ARCHITECTURE §Memory).

The owner, 2026-11-12: «також в Люмі … вона сама може шукати в РАГ через тул». In `lumi` mode her prompt holds a short
window, her day's digest and a line a day and a week. For the rest she looks herself: Gemini's function calling with
two declarations — `recall` (her archive by meaning and words, as the recall before an answer searches it) and
`day_talk` (what they talked about on a given day: its gist and its summaries, today her day's digest). At most
`RECALL_TOOL_ROUNDS` rounds an answer; the declarations live in her explicit cache with the start, so every round reads
the start from it.

The words are a person's: «згадати», «пригадати» — never a model, a bot, a tool or an AI. A result never holds a
closed line or fact (the archive's open lines and the summaries, written from open lines alone), a softened span's
line, or her future (a day not yet come is nothing).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date

from google.genai import types

RECALL = "recall"
DAY_TALK = "day_talk"
TOOLS_KEY = "recall+day_talk/1"  # in her cache's fingerprint: a cache with the tools never serves one without them
NOTHING = "Нічого не згадується."
NO_MORE = "Більше нічого не згадується — відповідай з того, що пам'ятаєш."
DAY_RESULT_WORDS = 300
RECALL_TOOL_N = 5
RECALL_TOOL_ROUNDS = 3
LUMI_RECALL_N = 4


def declarations() -> list[types.Tool]:
    """Her two ways to look back, as Gemini's function declarations."""
    return [types.Tool(function_declarations=[
        types.FunctionDeclaration(
            name=RECALL,
            description=("Згадати, що ти пам'ятаєш про щось — з ваших розмов, свого життя, своїх думок і того, що ти "
                         "знаєш про Ich. Скажи кількома словами, про що саме."),
            parameters=types.Schema(type=types.Type.OBJECT, properties={
                "query": types.Schema(type=types.Type.STRING, description="Про що згадати, кількома словами")},
                required=["query"])),
        types.FunctionDeclaration(
            name=DAY_TALK,
            description="Пригадати, про що ви з Ich говорили певного дня.",
            parameters=types.Schema(type=types.Type.OBJECT, properties={
                "date": types.Schema(type=types.Type.STRING, description="День: РРРР-ММ-ДД")},
                required=["date"])),
    ])]


@dataclass
class ToolSet:
    """What her answer's call offers and runs: the declarations, the runner (never raises: a failure is `NOTHING`),
    the rounds' cap, and the key her cache's fingerprint takes."""
    tools: list
    run: Callable[[str, dict], Awaitable[str]]
    rounds: int = RECALL_TOOL_ROUNDS
    key: str = TOOLS_KEY


def parse_day(raw: object) -> date | None:
    """The `day_talk` argument as a date; anything else none."""
    try:
        return date.fromisoformat(str(raw).strip()[:10])
    except ValueError:
        return None


def day_result(day: date | None, today: date, label: str, gist: str | None, summaries: list[str],
               digest: str | None, max_words: int = DAY_RESULT_WORDS) -> str:
    """What she recalls of a day (pure): a day not yet come or none — nothing; today — her day's digest; an earlier
    day — its gist, then its summaries, at most `max_words` words, labelled as she remembers it, never a date."""
    if day is None or day > today:
        return NOTHING
    if day == today:
        return f"Сьогодні: {digest.strip()}" if digest and digest.strip() else NOTHING
    parts = [x.strip() for x in ([gist] if gist else []) + summaries if x and x.strip()]
    if not parts:
        return NOTHING
    words, out = 0, []
    for part in parts:
        n = len(part.split())
        if out and words + n > max_words:
            break
        out.append(part)
        words += n
    return f"{label}:\n" + "\n".join(f"- {x}" for x in out)
