"""The LLM seam: one async call to Gemini, injectable and silent on failure.

Any error or empty reply returns None — the agent then stays silent (never
crashes, never apologizes in the room). No prompts, replies or keys in logs.
Every call — ok, empty or failed — is reported to the usage sink (v3.1).
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from collections.abc import Callable
from contextvars import ContextVar
from typing import Any

from google import genai
from google.genai import types

from agents.gemini_cache import BACKOFF_S, SEPARATOR, CachePlanner, channel_of
from agents.logic import split_prompt
from agents.responder import ANSWER_KINDS
from agents.usage import PROMPT_SLOW

log = logging.getLogger("agent.llm")

MODEL = "gemini-2.5-flash"  # the default; `GEMINI_MODEL` overrides it (v4.7: tunable in the panel)
DIGEST_MODEL = "gemini-3.1-pro-preview"  # v5.1: Hermes's digests and answers — Lumi's verified id, with thinking
THINK_MAX_TOKENS = 16384  # the cap counts the thinking too: room for it and a ~1,500-character digest
# v5.8 — models that refuse a zero thinking budget: an answer on one of them goes through the thinking path
THINKING_MODELS = frozenset({"gemini-3.1-pro-preview"})
REPLY_TIMEOUT_S = 90  # v5.25 (the owner, 2026-11-04): an answer's call, at most so long
REPLY_TRIES = 2       # … tried once more when it hangs
# 2026-11-10 (the owner: «роби»): a thinking call (a summary, a digest) hung for hours on Pro and held up her idle
# loop — no writing first, no events, no summary; the longest seen took 95 s. v6.5 code review #1: every other call
# but an answer too (`complete`, `probe`, `embed`, `search`)
THINK_TIMEOUT_S = 180
EMBED_MODEL = "gemini-embedding-001"  # v5.8: the archive's meaning search (the owner, 2026-10-25: Gemini's)
EMBED_DIM = 768

UsageSink = Callable[..., None]  # (kind, model, usage_metadata | None, ok[, blocked=stage]) — v5.13: a block's stage

# v5.13 — a block by Gemini's safety filter: the answer-stage finish reasons that mean one (an empty answer only), and
# the order of a safety rating's probability, for the category when none is marked `blocked`
BLOCK_FINISH = frozenset({"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII"})
PROBABILITY = {"NEGLIGIBLE": 1, "LOW": 2, "MEDIUM": 3, "HIGH": 4}
BLOCK_LOG = "gemini blocked: stage=%s reason=%s category=%s kind=%s model=%s"  # never a text
# v5.13 (the owner's live test) — a refusal written as an answer, in the model's own voice. `REFUSAL_MARKERS` are a
# model's formulas — a request refused, its safety rules, its maker or kind — matched anywhere (lower-cased, every
# punctuation mark a space); `REFUSAL_OPENINGS` (it calling itself an AI) count only at a sentence's start, after any
# voice tags, in a sentence that is no question — so her own «Ти думаєш, я штучний інтелект? 😄», «ти говориш як
# штучний інтелект, я…» or «я пішла в деканат з цим запитом» never are (code review #1).
REFUSAL_MARKERS = (
    "виконати цей запит", "виконати ваш запит", "виконати твій запит", "виконати такий запит",
    "допомогти з цим запитом", "допомогти з таким запитом",
    "правила безпеки суворо", "правила безпеки забороняють", "мої правила безпеки не дозволяють",
    "велика мовна модель", "навчена google", "розроблена google",
    "выполнить этот запрос", "выполнить ваш запрос", "правила безопасности запрещают", "большая языковая модель",
    "обучена google",
    "i can't help with that", "i cannot help with that", "i can't assist with that", "i cannot assist with that",
    "i can't fulfill", "i cannot fulfill", "i can't comply", "i cannot comply", "large language model",
    "trained by google",
)
REFUSAL_OPENINGS = (
    "як штучний інтелект", "як мовна модель", "я штучний інтелект", "я мовна модель",
    "как искусственный интеллект", "как языковая модель", "я искусственный интеллект", "я языковая модель",
    "as an ai", "as a language model", "i'm an ai", "i am an ai", "i'm a language model", "i am a language model",
)
_SENTENCE_RE = re.compile(r"[^.!?…\n]+[.!?…]*")
_LEAD_RE = re.compile(r"^[\s\-—–«»\"']*(?:\[[^\]\n]*\][\s\-—–«»\"']*)*")
# v5.13 — the last answer's block or refusal, (stage, reason, category), for its caller in the same task: a concurrent
# call in another task never sees it. Cleared at each answer's start.
LAST_BLOCK: ContextVar[tuple[str, str, str | None] | None] = ContextVar("gemini_last_block", default=None)
_REFUSAL_RE = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(m) for m in REFUSAL_MARKERS) + r")(?!\w)")


# v5.22 — when this task's call began, on the client's monotonic clock: a call's usage line holds its time. A
# context variable, as `LAST_BLOCK`: concurrent calls in other tasks never share it.
_CALL_T0: ContextVar[float | None] = ContextVar("gemini_call_t0", default=None)


def _joined(lines: list[str], tail: str) -> str:
    """v7.5 (AGORA-256): an answer's message — her history, then the tail (the time, the recall, her brief, the move,
    the rules) next to his last line."""
    history = "\n".join(lines)
    return f"{history}{SEPARATOR}{tail}" if history else tail


class GeminiClient:
    _mono = staticmethod(time.monotonic)  # v5.22: the calls' clock — a test sets its own

    def __init__(self, sink: UsageSink | None = None, api_key: str | None = None) -> None:
        # reads GEMINI_API_KEY from the environment; v7.1: an agent on Claude hands the key over, so it never stays in
        # the environment the CLI inherits
        self._client = genai.Client(api_key=api_key) if api_key else genai.Client()
        self._sink = sink
        self.model = os.environ.get("GEMINI_MODEL", MODEL).strip() or MODEL
        # v5.8 — the agent's answers on a model of their own (empty: the same as GEMINI_MODEL), and how hard a
        # thinking reply model thinks
        self.reply_model = os.environ.get("GEMINI_REPLY_MODEL", "").strip() or self.model
        self.thinking_level = os.environ.get("GEMINI_THINKING_LEVEL", "low").strip() or "low"
        self.cache: CachePlanner | None = None  # v7.5 (AGORA-256): a companion's answers, set by her agent
        self.cache_sink: Callable[..., None] | None = None  # v7.5 (AGORA-258): (model, tokens, ttl_s, made)

    @property
    def client(self):
        """The Google SDK client this one calls through — v7.3: beside Claude the photo and clip makers share it,
        since `GEMINI_API_KEY` is no longer in the environment there."""
        return self._client

    def _report(self, kind: str, usage: Any, ok: bool, model: str | None = None,
                block: tuple[str, str, str | None] | None = None) -> None:
        if self._sink is None:
            return
        t0 = _CALL_T0.get()
        latency = round((self._mono() - t0) * 1000) if t0 is not None else None  # v5.22: from the call's start
        try:
            if block:  # v5.13: only a block passes its stage
                self._sink(kind, model or self.model, usage, ok, blocked=block[0], latency_ms=latency)
            else:
                self._sink(kind, model or self.model, usage, ok, latency_ms=latency)
        except Exception:
            log.exception("usage accounting failed")

    def _start(self) -> None:
        """v5.22 — a call begins: its usage line measures from here."""
        _CALL_T0.set(self._mono())

    def _empty(self, resp: Any, kind: str, model: str, usage: Any, line: str) -> None:
        """v5.13 — an empty answer: a block is reported with its stage and logged by stage, reason and category (never
        a text); anything else logs `line` as before."""
        block = blocked_reason(resp)
        if block:  # v5.22: set before the report, so the owner's trace line (`TRACE_CALLS`) can name its reason
            LAST_BLOCK.set(block)
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
        LAST_BLOCK.set(block)
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
        (v5.8) overrides `GEMINI_MODEL` for this call — a model that runs with thinking off. v6.5 code review #1: at
        most `REPLY_TIMEOUT_S` for an answer (`refusal`, from `reply`), `THINK_TIMEOUT_S` for any other call, tried
        once more when it hangs."""
        LAST_BLOCK.set(None)
        model = model or self.model
        self._start()
        try:
            resp = await self._within(lambda: self._client.aio.models.generate_content(
                model=model,
                contents=transcript,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    max_output_tokens=max_output_tokens,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                    # no tools are passed: AFC only adds a log line per call (v3.4 review #3)
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                ),
            ), kind, REPLY_TIMEOUT_S if refusal else THINK_TIMEOUT_S)
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

    async def _within(self, call, kind: str, timeout_s: float | None = None):
        """v5.25 (the owner, 2026-11-04: «роби обидва») — an answer's call to Gemini, at most `REPLY_TIMEOUT_S`
        (a thinking call: `timeout_s`), tried once more when it hangs (on 2026-11-04 at 19:28 one took 194 s on a bad
        network); raises `TimeoutError` when the last try hangs too. `call` makes a fresh request each time."""
        timeout_s = timeout_s or REPLY_TIMEOUT_S
        for attempt in range(1, REPLY_TRIES + 1):
            try:
                return await asyncio.wait_for(call(), timeout=timeout_s)
            except TimeoutError:
                log.warning("gemini %s timed out after %d s (try %d of %d)", kind, timeout_s, attempt, REPLY_TRIES)
        raise TimeoutError

    async def reply(
        self, transcript: str, system_instruction: str | None, max_output_tokens: int = 400, kind: str = "reply",
    ) -> tuple[str, str] | None:
        """v5.8 — an answer (in the room, in the private chat, a line written first) on `GEMINI_REPLY_MODEL`: a
        thinking model through the thinking config at `GEMINI_THINKING_LEVEL`, any other through `complete`.
        (text, finish) either way, so a cut answer is still trimmed to a sentence; None on failure. A block or a
        refusal (v5.13) also leaves `LAST_BLOCK` set for the caller.

        v7.5 (AGORA-256): an answer whose prompt's start is known (`PROMPT_SLOW`) sends the start as the system
        instruction and the history then the tail as the message; with her cache (`self.cache`) the start and the
        first lines of her history are read from Gemini's explicit context cache."""
        LAST_BLOCK.set(None)
        split = split_prompt(system_instruction, PROMPT_SLOW.get()) if kind in ANSWER_KINDS else None
        lines = transcript.split("\n") if transcript else []
        if self.reply_model not in THINKING_MODELS:
            if split is not None:
                system_instruction, transcript = split[0], _joined(lines, split[1])
            return await self.complete(transcript, system_instruction, max_output_tokens, kind, self.reply_model,
                                       refusal=True)  # v5.13: an answer — a refusal in it is a block
        model = self.reply_model
        cached = await self._cache_for(kind, model, split[0], lines) if split is not None else None
        if split is not None:
            system_instruction, transcript = split[0], _joined(lines[cached[1]:] if cached else lines, split[1])
        self._start()
        try:
            resp = await self._within(lambda: self._client.aio.models.generate_content(
                model=model, contents=transcript,
                config=self._reply_config(None if cached else system_instruction, max_output_tokens,
                                          cached[0] if cached else None)), kind)
        except Exception as exc:  # noqa: BLE001 — any provider failure means silence
            # a hang is the network, not the cache: both tries are spent, the cache is kept (code review v7.5 #2)
            if cached is None or isinstance(exc, TimeoutError):
                log.error("gemini reply failed: %s", type(exc).__name__)
                self._report(kind, None, False, model)
                return None
            # the cache was gone or refused: forget it, and the same answer once more without it; plain answers for
            # `BACKOFF_S`, so a cache the model keeps refusing is not made again at every answer (code review v7.5 #1)
            log.warning("gemini reply on the cache failed (%s) — once more without it", type(exc).__name__)
            await self._drop_cache(self.cache.forget(channel_of(kind)))
            self.cache.failed(channel_of(kind), self._mono())
            transcript = _joined(lines, split[1])
            try:
                resp = await self._within(lambda: self._client.aio.models.generate_content(
                    model=model, contents=transcript,
                    config=self._reply_config(system_instruction, max_output_tokens, None)), kind)
            except Exception as again:  # noqa: BLE001
                log.error("gemini reply failed: %s", type(again).__name__)
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

    def _reply_config(self, system_instruction: str | None, max_output_tokens: int,
                      cached_content: str | None) -> Any:
        return types.GenerateContentConfig(
            system_instruction=system_instruction,
            cached_content=cached_content,
            max_output_tokens=max_output_tokens,
            thinking_config=types.ThinkingConfig(
                include_thoughts=False,
                thinking_level=getattr(types.ThinkingLevel, self.thinking_level.upper(), None)),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

    # --- v7.5 (AGORA-256): her answers' explicit context cache ---------------------------------------------------
    async def _cache_for(self, kind: str, model: str, start: str, lines: list[str]) -> tuple[str, int] | None:
        """(the cache's name, the history lines in it) for this answer, or None — a plain call. Never raises."""
        if self.cache is None:
            return None
        ch = channel_of(kind)
        plan = self.cache.plan(ch, model, start, lines, self._mono())
        if plan.action == "use":
            if plan.renew:
                try:
                    await asyncio.wait_for(self._client.aio.caches.update(
                        name=plan.name, config=types.UpdateCachedContentConfig(ttl=f"{int(self.cache.ttl)}s")), 30)
                    self.cache.renewed(ch, self._mono())
                    held = self.cache.held(ch)
                    self._cache_report(model, held.tokens if held else None, False)
                except Exception as exc:  # noqa: BLE001 — it may expire; the next answer makes another
                    log.warning("gemini cache: not renewed (%s)", type(exc).__name__)
            return plan.name, plan.lines
        if plan.action != "make":
            return None
        if plan.old:
            await self._drop_cache(plan.old)
        k = plan.lines
        try:
            made = await asyncio.wait_for(self._client.aio.caches.create(model=model, config=types.CreateCachedContentConfig(
                system_instruction=start,
                contents=[types.Content(role="user", parts=[types.Part(text="\n".join(lines[:k]))])] if k else None,
                ttl=f"{int(self.cache.ttl)}s", display_name=f"answers-{ch}")), 60)
        except Exception as exc:  # noqa: BLE001 — too small, refused, a bad network: plain calls for a while
            log.warning("gemini cache: not made (%s) — plain answers for %d s", type(exc).__name__, BACKOFF_S)
            self.cache.forget(ch)
            self.cache.failed(ch, self._mono())
            return None
        tokens = getattr(getattr(made, "usage_metadata", None), "total_token_count", None)
        self.cache.made(ch, made.name, model, start, lines[:k], self._mono(), tokens or 0)
        log.info("gemini cache: made (%s) for %s — %d history lines", plan.why, ch, k)  # names and counts only
        self._cache_report(model, tokens, True)
        return made.name, k

    def _cache_report(self, model: str, tokens: int | None, made: bool) -> None:
        """v7.5 (AGORA-258): a cache made (read once at the input price) or renewed — its storage for its life."""
        if self.cache_sink is None or self.cache is None:
            return
        try:
            self.cache_sink(model, tokens, int(self.cache.ttl), made)
        except Exception:
            log.exception("usage accounting failed")

    async def _drop_cache(self, name: str | None) -> None:
        """A cache no longer used, deleted so its storage stops; a failure is left to its TTL."""
        if not name:
            return
        try:
            await asyncio.wait_for(self._client.aio.caches.delete(name=name), 30)
        except Exception as exc:  # noqa: BLE001
            log.warning("gemini cache: an old one not deleted (%s) — it expires by itself", type(exc).__name__)

    async def probe(self, transcript: str, system_instruction: str | None, kind: str = "probe") -> bool | None:
        """v5.16 — does Gemini block this prompt at the prompt stage? One call on `GEMINI_REPLY_MODEL` for the
        verdict alone: one output token at the lowest thinking. True: blocked at the prompt stage; False: anything
        else (an answer, a cut, an answer-stage block); None: the call failed. Never sets `LAST_BLOCK` — an answer
        must not read a probe's block — and never logs a text; its usage line is the kind `probe`."""
        model = self.reply_model
        thinking = (types.ThinkingConfig(include_thoughts=False, thinking_level=types.ThinkingLevel.LOW)
                    if model in THINKING_MODELS else types.ThinkingConfig(thinking_budget=0))
        self._start()
        try:
            resp = await self._within(lambda: self._client.aio.models.generate_content(
                model=model,
                contents=transcript,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    max_output_tokens=1,
                    thinking_config=thinking,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                ),
            ), kind, THINK_TIMEOUT_S)  # v6.5 code review #1
        except Exception as exc:  # noqa: BLE001 — a failed probe closes nothing; its type reaches the log (review #1)
            log.warning("probe: failed (%s)", type(exc).__name__)
            self._report(kind, None, False, model)
            return None
        block = blocked_reason(resp)
        blocked = block is not None and block[0] == "prompt"
        self._report(kind, getattr(resp, "usage_metadata", None), not blocked, model, block if blocked else None)
        log.debug("probe: %s", "blocked" if blocked else "passed")
        return blocked


    async def embed(self, texts: list[str], task: str = "RETRIEVAL_DOCUMENT", kind: str = "embed") -> list | None:
        """v5.8 — the texts' embeddings (`EMBED_DIM` floats each), in one call: `RETRIEVAL_DOCUMENT` for the archive's
        lines, `RETRIEVAL_QUERY` for a recall's question. None on failure or a short answer (logged by type)."""
        if not texts:
            return []
        self._start()
        try:
            resp = await self._within(lambda: self._client.aio.models.embed_content(
                model=EMBED_MODEL, contents=texts,
                config=types.EmbedContentConfig(task_type=task, output_dimensionality=EMBED_DIM)),
                kind, THINK_TIMEOUT_S)  # v6.5 code review #1: `embed_tick` runs in the idle loop
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
        self._start()
        try:
            resp = await self._within(lambda: self._client.aio.models.generate_content(
                model=self.model,
                contents=question,
                config=types.GenerateContentConfig(
                    max_output_tokens=max_output_tokens,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                ),
            ), kind, THINK_TIMEOUT_S)  # v6.5 code review #1
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
        answers in seconds, the digest thinks at the model's default. None on failure or an empty answer. At most
        `THINK_TIMEOUT_S`, tried once more when it hangs (2026-11-10)."""
        self._start()
        try:
            resp = await self._within(lambda: self._client.aio.models.generate_content(
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
            ), kind, THINK_TIMEOUT_S)
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


def _plain(text: str) -> str:
    return " ".join(re.sub(r"[^\w']+", " ", text).split())


def opening(text: str, phrases: tuple[str, ...]) -> str | None:
    """The first of `phrases` that opens a sentence of `text` — after any voice tags, in a sentence that is no
    question — or None (v5.13; v5.14: the backup's «я бот»)."""
    for sentence in _SENTENCE_RE.findall(text.lower().replace("’", "'")):
        if sentence.rstrip().endswith("?"):
            continue
        head = _plain(sentence[_LEAD_RE.match(sentence).end():])
        hit = next((o for o in phrases if head == o or head.startswith(o + " ")), None)
        if hit:
            return hit
    return None


def refusal_marker(text: str) -> str | None:
    """v5.13 — the phrase that makes an answer the model's own refusal, or None: a `REFUSAL_MARKERS` formula anywhere,
    or a `REFUSAL_OPENINGS` one opening a sentence that is no question."""
    m = _REFUSAL_RE.search(_plain(text.lower().replace("’", "'")))
    return m.group(0) if m else opening(text, REFUSAL_OPENINGS)


def finish_of(resp: Any) -> str:
    """The candidate's finish reason, mapped to the responder's vocabulary."""
    candidates = getattr(resp, "candidates", None) or []
    reason = getattr(candidates[0], "finish_reason", None) if candidates else None
    return "max_tokens" if "MAX_TOKENS" in str(getattr(reason, "name", reason) or "") else "stop"
