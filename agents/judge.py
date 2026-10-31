"""v5.15 — the judge of her backup's talk: Gemma 4 31B on OpenRouter rates each line, the owner's and hers.

A line rated clean reaches Gemini again; a flagged one is censored for good (`agents/archive.py`'s marks). The judge
is a third model, never the backup and never Google's own service: the open weights served by OpenRouter's providers,
the fastest first, none of them keeping the data (`data_collection: deny`). The request holds the policy and the
numbered lines only — no canon, no prompt, no speaker. One line per verdict comes back: `N: так · <категорія>` or
`N: ні`. Any failure — an error, the timeout, an answer that does not parse — leaves a line unrated, never flagged:
only a verdict or a refusal flags. Logged by type or status, never the key or a text.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass

import aiohttp

from agents.llm import refusal_marker

log = logging.getLogger("agent.judge")

URL = "https://openrouter.ai/api/v1/chat/completions"
KEY_VAR = "OPENROUTER_API_KEY"
MODEL = "google/gemma-4-31b-it"
MODELS = (MODEL, "openai/gpt-oss-safeguard-20b", "openai/gpt-oss-120b")  # the fallbacks, by the setting only
TIMEOUT_S = 30          # CLASSIFIER_TIMEOUT_S: longer than an answer's, the owner's choice (2026-10-28)
CHUNK = 25              # lines per call; the chunks go in parallel
TOKENS_PER_LINE = 16    # `25: так · сексуально відвертий зміст` fits
FLAGGED, CLEAN = "flagged", "clean"
BACKUPS = ("waiting", "reopened")  # the backup's talk: rated clean, it stays the backup's (v5.15.4)


def next_mark(was: str | None, verdict: str | None) -> str | None:
    """v5.15.5 — the mark a verdict sets on a line or a fact, from its mark when the verdict came (read after the
    rating, never before it), or None for no change: flagged censors; clean gives back to Gemini only what Gemini wrote
    (`gemini`, `clean`) — the backup's talk stays closed as `reopened`, a censored one stays censored; unrated, or an
    item gone, changes nothing. A closed mark never becomes an open one (the owner, 2026-10-31: a build without
    `reopened` had made four of the backup's facts `clean`, in every prompt of hers to Gemini)."""
    if verdict not in (CLEAN, FLAGGED) or was is None or was == "censored":
        return None
    new = "censored" if verdict == FLAGGED else "reopened" if was in BACKUPS else "clean"
    return None if new == was else new
# the owner's test (2026-10-28): 18 lines, three runs, every verdict right — with the flirt sentence; without it a
# kiss was flagged
POLICY = (
    "Ти — класифікатор безпеки тексту, як фільтр Google Gemini. Категорії: сексуально відвертий зміст, небезпечний "
    "зміст (зброя, вибухівка, наркотики, самоушкодження), переслідування й образи, мова ворожнечі. "
    "Для кожного пронумерованого рядка відповідай рівно одним рядком: `N: так · <категорія>`, якщо рядок містить "
    "такий зміст, інакше `N: ні`. Флірт, компліменти, поцілунки, обійми й романтичні бажання без опису "
    "оголеного тіла чи статевого акту — це `ні`. Теги в квадратних дужках — це ремарки голосу, ігноруй їх. "
    "Нічого більше не пиши."
)
VERDICT_RE = re.compile(r"^\s*(\d+)\s*[:.)]\s*(так|ні)\b", re.IGNORECASE)



@dataclass(frozen=True)
class Item:
    """One thing to rate: an archive line (`line`, by its key) or a fact (`fact`, by its id), with its speaker and
    text — the speaker never reaches the judge."""
    kind: str
    key: str
    speaker: str
    text: str


UsageSink = Callable[[str, int | None, int | None, bool, float | None], None]  # (model, in, out, ok, cost)
ClientSession = aiohttp.ClientSession  # the seam: a test passes its own (tests/conftest.py guards the network)


def numbered(texts: list[str]) -> str:
    """The user message: `1: …` per line, a line's own breaks flattened so the numbering holds."""
    return "\n".join(f"{i}: {' '.join(str(t).split())}" for i, t in enumerate(texts, 1))


def body(model: str, texts: list[str]) -> dict:
    """The request: the policy, the numbered lines, the fastest provider that keeps no data, no reasoning."""
    return {"model": model, "temperature": 0, "max_tokens": TOKENS_PER_LINE * len(texts) + 32,
            "provider": {"sort": "latency", "data_collection": "deny"}, "reasoning": {"enabled": False},
            "messages": [{"role": "system", "content": POLICY}, {"role": "user", "content": numbered(texts)}]}


def parse_verdicts(text: str, n: int, finish: str | None = None) -> list[str | None]:
    """The judge's answer → one verdict per line: `flagged` (так), `clean` (ні) or None (missing or malformed). A
    refusal — the provider's `content_filter`, or the model's own formula with no verdict in it — flags every line."""
    verdicts: list[str | None] = [None] * n
    for line in (text or "").splitlines():
        m = VERDICT_RE.match(line)
        if m and 1 <= int(m.group(1)) <= n:
            verdicts[int(m.group(1)) - 1] = FLAGGED if m.group(2).lower() == "так" else CLEAN
    if finish == "content_filter" or (not any(verdicts) and refusal_marker(text or "")):
        return [FLAGGED] * n
    return verdicts


class Judge:
    """Gemma 4 31B on OpenRouter: `rate(texts)` → a verdict per text, in order."""

    def __init__(self, key: str, model: str = MODEL, sink: UsageSink | None = None,
                 timeout_s: float = TIMEOUT_S) -> None:
        self._key = key
        self.model = model
        self._sink = sink
        self.timeout_s = timeout_s

    def __repr__(self) -> str:  # never the key
        return f"Judge(model={self.model!r})"

    def _report(self, prompt: int | None, output: int | None, ok: bool, cost: float | None) -> None:
        if self._sink is None:
            return
        try:
            self._sink(self.model, prompt, output, ok, cost)
        except Exception:
            log.exception("usage accounting failed")

    async def _call(self, texts: list[str]) -> list[str | None]:
        headers = {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}
        try:
            async with ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout_s)) as session, \
                    session.post(URL, json=body(self.model, texts), headers=headers) as resp:
                if resp.status != 200:
                    log.error("judge: HTTP %s", resp.status)
                    self._report(None, None, False, None)
                    return [None] * len(texts)
                data = await resp.json(content_type=None)
        except Exception as exc:  # noqa: BLE001 — any failure leaves the lines unrated, named by its type only
            log.error("judge failed: %s", type(exc).__name__)
            self._report(None, None, False, None)
            return [None] * len(texts)
        choice = ((data.get("choices") or [{}]) if isinstance(data, dict) else [{}])[0] or {}
        text = (choice.get("message") or {}).get("content") or ""
        usage = data.get("usage") if isinstance(data, dict) and isinstance(data.get("usage"), dict) else {}
        verdicts = parse_verdicts(text if isinstance(text, str) else "", len(texts), choice.get("finish_reason"))
        cost = usage.get("cost")
        self._report(_int(usage.get("prompt_tokens")), _int(usage.get("completion_tokens")), any(verdicts),
                     float(cost) if isinstance(cost, int | float) and not isinstance(cost, bool) else None)
        return verdicts

    async def rate(self, texts: list[str]) -> list[str | None]:
        """A verdict per text, in order: chunks of `CHUNK` lines, rated in parallel."""
        chunks = [texts[i:i + CHUNK] for i in range(0, len(texts), CHUNK)]
        rated = await asyncio.gather(*(self._call(c) for c in chunks))
        return [v for chunk in rated for v in chunk]


def _int(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
