"""The LLM seam: one async call to Gemini, injectable and silent on failure.

Any error or empty reply returns None — the agent then stays silent (never
crashes, never apologizes in the room). No prompts, replies or keys in logs.
Every call — ok, empty or failed — is reported to the usage sink (v3.1).
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable
from typing import Any

from google import genai
from google.genai import types

log = logging.getLogger("agent.llm")

MODEL = "gemini-2.5-flash"  # the default; `GEMINI_MODEL` overrides it (v4.7: tunable in the panel)
DIGEST_MODEL = "gemini-3.1-pro-preview"  # v5.1: Hermes's digests and answers — Lumi's verified id, with thinking
THINK_MAX_TOKENS = 16384  # the cap counts the thinking too: room for it and a ~1,500-character digest
# v5.8 — models that refuse a zero thinking budget: an answer on one of them goes through the thinking path
THINKING_MODELS = frozenset({"gemini-3.1-pro-preview"})
EMBED_MODEL = "gemini-embedding-001"  # v5.8: the archive's meaning search (the owner, 2026-10-25: Gemini's)
EMBED_DIM = 768

UsageSink = Callable[..., None]  # (kind, model, usage_metadata | None, ok[, blocked=stage]) — v5.13: a block's stage

# v5.13 — a block by Gemini's safety filter: the answer-stage finish reasons that mean one (an empty answer only), and
# the order of a safety rating's probability, for the category when none is marked `blocked`
BLOCK_FINISH = frozenset({"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII"})
PROBABILITY = {"NEGLIGIBLE": 1, "LOW": 2, "MEDIUM": 3, "HIGH": 4}
BLOCK_LOG = "gemini blocked: stage=%s reason=%s category=%s kind=%s model=%s"  # never a text
# v5.13 (the owner's live test) — a refusal written as an answer, in the model's own voice: phrases of a model
# speaking of a request, of its safety rules or of itself as an AI, matched on the answer lower-cased with every
# punctuation mark a space. Never everyday speech («я не можу сьогодні прийти», «ти говориш як штучний інтелект»).
REFUSAL_MARKERS = (
    "виконати цей запит", "виконати ваш запит", "виконати твій запит", "виконати такий запит", "з цим запитом",
    "правила безпеки суворо", "правила безпеки забороняють", "мої правила безпеки не дозволяють",
    "я штучний інтелект", "як штучний інтелект я", "я мовна модель", "як мовна модель я",
    "выполнить этот запрос", "выполнить ваш запрос", "правила безопасности запрещают", "я языковая модель",
    "как языковая модель я", "как искусственный интеллект я",
    "i can't help with that", "i cannot help with that", "i can't assist with that", "i cannot assist with that",
    "i can't fulfill", "i cannot fulfill", "i can't comply", "i cannot comply", "as an ai i", "as a language model i",
    "i'm an ai", "i am an ai", "i'm a language model", "i am a language model",
)
_REFUSAL_RE = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(m) for m in REFUSAL_MARKERS) + r")(?!\w)")


class GeminiClient:
    def __init__(self, sink: UsageSink | None = None) -> None:
        self._client = genai.Client()  # reads GEMINI_API_KEY from the environment
        self._sink = sink
        self.model = os.environ.get("GEMINI_MODEL", MODEL).strip() or MODEL
        # v5.8 — the agent's answers on a model of their own (empty: the same as GEMINI_MODEL), and how hard a
        # thinking reply model thinks
        self.reply_model = os.environ.get("GEMINI_REPLY_MODEL", "").strip() or self.model
        self.thinking_level = os.environ.get("GEMINI_THINKING_LEVEL", "low").strip() or "low"

    def _report(self, kind: str, usage: Any, ok: bool, model: str | None = None,
                block: tuple[str, str, str | None] | None = None) -> None:
        if self._sink is None:
            return
        try:
            if block:  # v5.13: only a block passes its stage, so a four-argument sink keeps working
                self._sink(kind, model or self.model, usage, ok, blocked=block[0])
            else:
                self._sink(kind, model or self.model, usage, ok)
        except Exception:
            log.exception("usage accounting failed")

    def _empty(self, resp: Any, kind: str, model: str, usage: Any, line: str) -> None:
        """v5.13 — an empty answer: a block is reported with its stage and logged by stage, reason and category (never
        a text); anything else logs `line` as before."""
        block = blocked_reason(resp)
        self._report(kind, usage, False, model, block)
        if block:
            log.warning(BLOCK_LOG, *block, kind, model)
        else:
            log.error(line, finish_of(resp))

    def _refused(self, text: str, kind: str, model: str, usage: Any) -> bool:
        """v5.13 — an answer that is the model's own refusal: reported and logged as a block of the stage `refusal`
        (the reason is the matched phrase, never the text); the caller drops it."""
        marker = refusal_marker(text)
        if marker is None:
            return False
        block = ("refusal", marker, None)
        self._report(kind, usage, False, model, block)
        log.warning(BLOCK_LOG, *block, kind, model)
        return True

    async def generate(
        self, transcript: str, system_instruction: str, max_output_tokens: int = 400, kind: str = "reply",
    ) -> str | None:
        out = await self.complete(transcript, system_instruction, max_output_tokens, kind)
        return out[0] if out else None

    async def complete(
        self, transcript: str, system_instruction: str | None, max_output_tokens: int = 400, kind: str = "reply",
        model: str | None = None, refusal: bool = False,
    ) -> tuple[str, str] | None:
        """(text, finish) — finish is "max_tokens" when the cap cut the reply, else "stop"; None on failure. `model`
        (v5.8) overrides `GEMINI_MODEL` for this call — a model that runs with thinking off."""
        model = model or self.model
        try:
            resp = await self._client.aio.models.generate_content(
                model=model,
                contents=transcript,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    max_output_tokens=max_output_tokens,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                    # no tools are passed: AFC only adds a log line per call (v3.4 review #3)
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                ),
            )
        except Exception as exc:  # noqa: BLE001 — any provider failure means silence
            log.error("gemini call failed: %s", type(exc).__name__)
            self._report(kind, None, False, model)
            return None
        text = (resp.text or "").strip() if resp is not None else ""
        if not text:
            self._empty(resp, kind, model, getattr(resp, "usage_metadata", None),
                        "gemini returned an empty reply (finish %s)")
            return None
        if refusal and self._refused(text, kind, model, getattr(resp, "usage_metadata", None)):  # v5.13
            return None
        self._report(kind, getattr(resp, "usage_metadata", None), True, model)
        return text, finish_of(resp)

    async def reply(
        self, transcript: str, system_instruction: str | None, max_output_tokens: int = 400, kind: str = "reply",
    ) -> tuple[str, str] | None:
        """v5.8 — an answer (in the room, in the private chat, a line written first) on `GEMINI_REPLY_MODEL`: a
        thinking model through the thinking config at `GEMINI_THINKING_LEVEL`, any other through `complete`.
        (text, finish) either way, so a cut answer is still trimmed to a sentence; None on failure."""
        if self.reply_model not in THINKING_MODELS:
            return await self.complete(transcript, system_instruction, max_output_tokens, kind, self.reply_model,
                                       refusal=True)  # v5.13: an answer — a refusal in it is a block
        model = self.reply_model
        try:
            resp = await self._client.aio.models.generate_content(
                model=model,
                contents=transcript,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    max_output_tokens=max_output_tokens,
                    thinking_config=types.ThinkingConfig(
                        include_thoughts=False,
                        thinking_level=getattr(types.ThinkingLevel, self.thinking_level.upper(), None)),
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                ),
            )
        except Exception as exc:  # noqa: BLE001 — any provider failure means silence
            log.error("gemini reply failed: %s", type(exc).__name__)
            self._report(kind, None, False, model)
            return None
        text = answer_text(resp)
        if not text:
            self._empty(resp, kind, model, getattr(resp, "usage_metadata", None), "gemini reply was empty (finish %s)")
            return None
        if self._refused(text, kind, model, getattr(resp, "usage_metadata", None)):  # v5.13: an answer
            return None
        self._report(kind, getattr(resp, "usage_metadata", None), True, model)
        return text, finish_of(resp)


    async def embed(self, texts: list[str], task: str = "RETRIEVAL_DOCUMENT", kind: str = "embed") -> list | None:
        """v5.8 — the texts' embeddings (`EMBED_DIM` floats each), in one call: `RETRIEVAL_DOCUMENT` for the archive's
        lines, `RETRIEVAL_QUERY` for a recall's question. None on failure or a short answer (logged by type)."""
        if not texts:
            return []
        try:
            resp = await self._client.aio.models.embed_content(
                model=EMBED_MODEL, contents=texts,
                config=types.EmbedContentConfig(task_type=task, output_dimensionality=EMBED_DIM))
        except Exception as exc:  # noqa: BLE001 — a failed embedding is retried later, never a blocked reply
            log.error("gemini embed failed: %s", type(exc).__name__)
            self._report(kind, None, False, EMBED_MODEL)
            return None
        vectors = [list(getattr(e, "values", None) or []) for e in (getattr(resp, "embeddings", None) or [])]
        ok = len(vectors) == len(texts) and all(len(v) == EMBED_DIM for v in vectors)  # v5.8 review #10
        self._report(kind, getattr(resp, "metadata", None), ok, EMBED_MODEL)
        if not ok:
            log.error("gemini embed returned %d of %d vectors", len(vectors), len(texts))
            return None
        return vectors

    async def search(self, question: str, max_output_tokens: int = 800, kind: str = "sky") -> str | None:
        """A grounded answer — Gemini with Google Search, as Lumi's web lookup (core/weblookup.py): the question is
        asked of the live internet; the sources stay out of the answer. None on failure (logged by type)."""
        try:
            resp = await self._client.aio.models.generate_content(
                model=self.model,
                contents=question,
                config=types.GenerateContentConfig(
                    max_output_tokens=max_output_tokens,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                ),
            )
        except Exception as exc:  # noqa: BLE001
            log.error("gemini search failed: %s", type(exc).__name__)
            self._report(kind, None, False)
            return None
        text = (resp.text or "").strip() if resp is not None else ""
        self._report(kind, getattr(resp, "usage_metadata", None), bool(text))
        return text or None


    async def think(self, contents: str, system_instruction: str, model: str = DIGEST_MODEL,
                    max_output_tokens: int = THINK_MAX_TOKENS, kind: str = "digest_voice",
                    level: str | None = None) -> str | None:
        """v5.1 — one call with thinking on (a Pro model rejects a zero budget): the answer is the non-thought text;
        the usage line names this call's model. `level` (`low`, …) bounds the thinking — the chat with the owner
        answers in seconds, the digest thinks at the model's default. None on failure or an empty answer."""
        try:
            resp = await self._client.aio.models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    max_output_tokens=max_output_tokens,
                    thinking_config=types.ThinkingConfig(
                        include_thoughts=False,
                        thinking_level=getattr(types.ThinkingLevel, level.upper()) if level else None),
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                ),
            )
        except Exception as exc:  # noqa: BLE001 — any provider failure means silence
            log.error("gemini think failed: %s", type(exc).__name__)
            self._report(kind, None, False, model)
            return None
        text = answer_text(resp)
        if not text:
            self._empty(resp, kind, model, getattr(resp, "usage_metadata", None),
                        "gemini think returned no answer (finish %s)")
            return None
        self._report(kind, getattr(resp, "usage_metadata", None), True, model)
        return text


def answer_text(resp: Any) -> str:
    """The answer of a thinking call: the first candidate's text parts that are not thoughts (the SDK's `.text`
    when the response carries no parts)."""
    candidates = getattr(resp, "candidates", None) or []
    parts = getattr(getattr(candidates[0], "content", None), "parts", None) if candidates else None
    if not parts:
        return (getattr(resp, "text", None) or "").strip() if resp is not None else ""
    return "".join(p.text for p in parts if isinstance(getattr(p, "text", None), str)
                   and not getattr(p, "thought", False)).strip()


def _name(value: Any) -> str:
    """An enum's name or a plain string, upper-cased; "" for anything else (None, a test double's attribute)."""
    name = getattr(value, "name", value)
    return name.upper() if isinstance(name, str) else ""


def _category(ratings: Any) -> str | None:
    """The safety rating that blocked, or else the most probable one: `HARM_CATEGORY_SEXUALLY_EXPLICIT` →
    `sexually_explicit`; None with no ratings."""
    ratings = [r for r in (ratings if isinstance(ratings, list | tuple) else []) if _name(getattr(r, "category", None))]
    if not ratings:
        return None
    hit = next((r for r in ratings if getattr(r, "blocked", None) is True), None)
    if hit is None:
        hit = max(ratings, key=lambda r: PROBABILITY.get(_name(getattr(r, "probability", None)), 0))
    return _name(hit.category).removeprefix("HARM_CATEGORY_").lower()


def blocked_reason(resp: Any) -> tuple[str, str, str | None] | None:
    """v5.13 — (stage, reason, category) when Gemini's safety filter blocked the call, else None. Called on an empty
    answer: the prompt stage is any `prompt_feedback.block_reason`; the answer stage a `finish_reason` in
    `BLOCK_FINISH`. `MAX_TOKENS`, `RECITATION`, `OTHER` or no reason is not a block."""
    feedback = getattr(resp, "prompt_feedback", None)
    reason = _name(getattr(feedback, "block_reason", None))
    if reason and reason != "BLOCKED_REASON_UNSPECIFIED":
        return "prompt", reason.lower(), _category(getattr(feedback, "safety_ratings", None))
    candidates = getattr(resp, "candidates", None)
    first = candidates[0] if isinstance(candidates, list | tuple) and candidates else None
    finish = _name(getattr(first, "finish_reason", None))
    if finish in BLOCK_FINISH:
        return "answer", finish.lower(), _category(getattr(first, "safety_ratings", None))
    return None


def refusal_marker(text: str) -> str | None:
    """v5.13 — the `REFUSAL_MARKERS` phrase that makes an answer the model's own refusal, or None."""
    plain = " ".join(re.sub(r"[^\w']+", " ", text.lower().replace("’", "'")).split())
    m = _REFUSAL_RE.search(plain)
    return m.group(0) if m else None


def finish_of(resp: Any) -> str:
    """The candidate's finish reason, mapped to the responder's vocabulary."""
    candidates = getattr(resp, "candidates", None) or []
    reason = getattr(candidates[0], "finish_reason", None) if candidates else None
    return "max_tokens" if "MAX_TOKENS" in str(getattr(reason, "name", reason) or "") else "stop"
