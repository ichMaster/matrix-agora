"""v5.24 — the scan: the hours that make her private prompt block, softened (ROADMAP §v5.24, ARCHITECTURE §The
owner's commands).

The owner, 2026-11-05 (AGORA-212): «перероби сканування. і визначай проблемні години і роби для них самарізейшинг
по агормту від мягкого до строгого. тоді не треба буде і закривати рядки». After a block of her private prompt at the
prompt stage, once her answer is out, and at `/scan`: Gemini itself (`probe` on her reply model) finds the hours of
her window that make the prompt block — the shortest run of hours at the end that blocks, then its shortest head —
and those hours go one step stricter: her summary of the hour (`talk.TALK_GENTLE` 0), stricter (1), the strictest
(2), then left out (3). The whole prompt is checked again, up to `ROUNDS` times; only a prompt that passes is kept.
Nothing closes: the lines stay open, and her window shows a softened span as she remembers it. On 11-05 a run of 39
messages blocked only together — no line alone — which v5.24's Opus judge, line by line, could not see; the judge
and `/scan yes` went with it.

Pure: plain data in, plain data out (the run search takes its check injected); the agent builds the prompt and calls
Gemini. Never a text in a log or an answer — times, levels and counts.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from agents.world import local_now

HOUR_MS = 3_600_000
ROUNDS = 4          # how many times a scan goes one step stricter before it gives up
STRICT_MAX = 3      # 0–2: a summary (`talk.TALK_GENTLE`); 3: the span left out
SOFT_KEEP_MS = 30 * 86_400_000  # how long a softened span's lines stay out of her recall
LEVEL_NAMES = ("підсумок", "суворіший підсумок", "найсуворіший підсумок", "без підсумку")
NEUTRAL = "Ich: Привіт"  # the history of a check that asks whether the rest of the prompt blocks on its own

# why a scan changed nothing — the ⚙️ answer's words
WHY = {
    "passes": "Промпт проходить — нічого не треба",
    "empty": "Розмови для перевірки немає — нічого не змінено",
    "tail": "Блокує повідомлення, на яке вона ще не відповіла: пом'якшувати нічого, відповідає backup",
    "rest": "Блокує не розмова, а решта промпту (підсумки, згадки, факти чи думки): години не допоможуть, нічого не "
            "змінено",
    "rounds": "Промпт блокує й після пом'якшення: нічого не змінено",
    "cap": "Перевірок забагато: нічого не змінено",
    "failed": "Gemini не відповів на перевірку: нічого не змінено",
    "write": "Підсумок не написався: нічого не змінено",
}


class ScanStop(Exception):
    """A scan ends early: its reason is a key of `WHY`."""


def hour_spans(times: list[int], cut_ms: int) -> list[tuple[int, int]]:
    """The spans a scan may soften (pure): each hour of the clock (Kyiv's offsets are whole hours) holding a line
    before `cut_ms` — his first line she has not answered yet, which is never softened —, as [the hour's start,
    min(its end, `cut_ms`)), oldest first."""
    starts = sorted({(t // HOUR_MS) * HOUR_MS for t in times if t < cut_ms})
    return [(s, min(s + HOUR_MS, cut_ms)) for s in starts]


def soften(lines: list[tuple[int, Any]], rows: list) -> list[tuple[int, Any]]:
    """Her window with the softened spans (pure): `lines` are (ts_ms, line), oldest first; a line inside a row's
    [start_ms, end_ms) is left out and the row itself stands at its first line's place — none for a row at
    `STRICT_MAX` or with no text. (ts_ms, the line or the row)."""
    out: list[tuple[int, Any]] = []
    shown: set[int] = set()
    for ts, line in lines:
        row = next((r for r in rows if r.start_ms <= ts < r.end_ms), None)
        if row is None:
            out.append((ts, line))
        elif row.start_ms not in shown:
            shown.add(row.start_ms)
            if row.strict < STRICT_MAX and row.text:
                out.append((ts, row))
    return out


def next_level(row) -> int:
    """A span's next step (pure): 0 for one never softened, else one stricter than its row, at most `STRICT_MAX`."""
    return 0 if row is None else min(row.strict + 1, STRICT_MAX)


async def minimal_run(n: int, blocks: Callable[[int, int], Awaitable[bool]]) -> tuple[int, int] | None:
    """The run [a, b) of `n` spans to soften: the shortest run at the end that blocks, then its shortest head that
    still blocks (`blocks(a, b)`: does the history of spans a..b-1 alone block?). None when all `n` together pass.
    Two halvings: about 2·log2(n) checks."""
    if n <= 0 or not await blocks(0, n):
        return None
    lo, hi = 1, n
    while lo < hi:
        mid = (lo + hi) // 2
        if await blocks(n - mid, n):
            hi = mid
        else:
            lo = mid + 1
    start = n - lo
    lo, hi = 1, n - start
    while lo < hi:
        mid = (lo + hi) // 2
        if await blocks(start, start + mid):
            hi = mid
        else:
            lo = mid + 1
    return start, start + lo


def _span_label(start_ms: int, end_ms: int, now_ms: int, tz: str) -> str:
    start, end, now = local_now(start_ms, tz), local_now(end_ms, tz), local_now(now_ms, tz)
    day = "" if start.date() == now.date() else f"{start:%d.%m} "
    return f"{day}{start:%H:%M}–{end:%H:%M}"


def scan_line(why: str, changed: list[tuple[int, int, int]], checks: int, now_ms: int, tz: str) -> str:
    """The ⚙️ answer (pure): the spans softened, each with its step, or why nothing changed; the checks made. Times
    and steps only, never a text."""
    if why == "softened":
        spans = "; ".join(f"{_span_label(s, e, now_ms, tz)} — {LEVEL_NAMES[k]}" for s, e, k in sorted(changed))
        return f"⚙️ Пом'якшено: {spans}. Промпт проходить — далі gemini (перевірок: {checks})"
    return f"⚙️ {WHY.get(why, WHY['failed'])} (перевірок: {checks})"
