"""v7.4 (AGORA-251) — a companion's answer on a model paid by the token: what the OpenAI and the Anthropic clients
share. One call per answer — the whole instruction as the system prompt, the transcript as the message, thinking
on — bounded by `REPLY_TIMEOUT_S`; `(text, finish)`, or None with `LAST_BLOCK` set on a refusal (the model's own
refusal stop, a content filter, or v5.13's refusal formulas in the text), or None on any failure. One usage line a
call (`sink`), never a text in a log or a line. The SDKs are the subclasses' own (`agents/openai_api.py`,
`agents/anthropic_api.py`), each handed its key explicitly — never read from the environment.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

from agents.gemini_cache import SEPARATOR
from agents.llm import LAST_BLOCK, REPLY_TIMEOUT_S, refusal_marker
from agents.logic import split_prompt
from agents.responder import ANSWER_KINDS
from agents.usage import PROMPT_SLOW

log = logging.getLogger("agent.api")

THINK_HEADROOM = 4096  # added to the answer's cap: the thinking counts in it and never eats the answer (as on Claude)
EMPTY_MESSAGE = "…"    # an answer with no line before it (she writes first) still sends a message
API_BLOCK_LOG = "%s blocked: stage=%s reason=%s category=%s kind=%s model=%s"  # never a text


class ApiAnswers:
    """The shared call: `_call(system, message, cap)` → (text, finish, usage, refused) is the subclass's."""

    engine = "api"

    def __init__(self, *, model: str, effort: str, sink: Callable[..., None] | None,
                 timeout_s: float = REPLY_TIMEOUT_S, mono: Callable[[], float] = time.monotonic) -> None:
        self.reply_model = model
        self.effort = effort
        self._sink = sink
        self.timeout_s = timeout_s
        self._mono = mono

    async def _call(self, system: str, message: str, cap: int) -> tuple[str, str, dict, tuple | None]:
        raise NotImplementedError

    def _report(self, kind: str, usage: dict | None, ok: bool, started: float, blocked: str | None = None) -> None:
        if self._sink is None:
            return
        try:
            self._sink(kind, self.reply_model, usage, ok, blocked=blocked,
                       latency_ms=round((self._mono() - started) * 1000))
        except Exception:
            log.exception("usage accounting failed")

    def _block(self, kind: str, usage: dict | None, started: float, block: tuple) -> None:
        LAST_BLOCK.set(block)
        self._report(kind, usage, False, started, "refusal")
        log.warning(API_BLOCK_LOG, self.engine, *block, kind, self.reply_model)

    async def reply(self, transcript: str, system_instruction: str | None, max_output_tokens: int = 400,
                    kind: str = "reply") -> tuple[str, str] | None:
        LAST_BLOCK.set(None)
        cap = max_output_tokens + THINK_HEADROOM if max_output_tokens > 0 else max_output_tokens
        # v7.5 (AGORA-257): the start as the system prompt, the history then the tail as the message
        split = split_prompt(system_instruction, PROMPT_SLOW.get()) if kind in ANSWER_KINDS else None
        if split is not None:
            system_instruction = split[0]
            transcript = f"{transcript}{SEPARATOR}{split[1]}" if transcript.strip() else split[1]
        started = self._mono()
        try:
            text, finish, usage, refused = await asyncio.wait_for(
                self._call(system_instruction or "", transcript if transcript.strip() else EMPTY_MESSAGE, cap),
                self.timeout_s)
        except TimeoutError:
            log.warning("%s %s timed out after %d s", self.engine, kind, self.timeout_s)
            self._report(kind, None, False, started)
            return None
        except Exception as exc:  # noqa: BLE001 — any provider failure means silence
            log.error("%s %s failed: %s", self.engine, kind, type(exc).__name__)
            self._report(kind, None, False, started)
            return None
        if refused is not None:
            self._block(kind, usage, started, refused)
            return None
        if not text.strip():
            log.error("%s %s was empty (finish %s)", self.engine, kind, finish)
            self._report(kind, usage, False, started)
            return None
        marker = refusal_marker(text)  # v5.13: an answer that is the model's own refusal is a block
        if marker is not None:
            self._block(kind, usage, started, ("refusal", marker, None))
            return None
        self._report(kind, usage, True, started)
        return text, finish

    # the background never comes here (her switch sends only her answers); a stray call is an answer all the same
    async def complete(self, transcript: str, system_instruction: str | None, max_output_tokens: int = 400,
                       kind: str = "reply", *_: Any, **__: Any) -> tuple[str, str] | None:
        return await self.reply(transcript, system_instruction, max_output_tokens, kind)
