"""The LLM seam: one async call to Gemini, injectable and silent on failure.

Any error or empty reply returns None — the agent then stays silent (never
crashes, never apologizes in the room). No prompts, replies or keys in logs.
Every call — ok, empty or failed — is reported to the usage sink (v3.1).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Any

from google import genai
from google.genai import types

log = logging.getLogger("agent.llm")

MODEL = "gemini-2.5-flash"  # the default; `GEMINI_MODEL` overrides it (v4.7: tunable in the panel)
DIGEST_MODEL = "gemini-3.1-pro-preview"  # v5.1: Hermes's digests and answers — Lumi's verified id, with thinking
THINK_MAX_TOKENS = 16384  # the cap counts the thinking too: room for it and a ~1,500-character digest

UsageSink = Callable[[str, str, Any, bool], None]  # (kind, model, usage_metadata | None, ok)


class GeminiClient:
    def __init__(self, sink: UsageSink | None = None) -> None:
        self._client = genai.Client()  # reads GEMINI_API_KEY from the environment
        self._sink = sink
        self.model = os.environ.get("GEMINI_MODEL", MODEL).strip() or MODEL

    def _report(self, kind: str, usage: Any, ok: bool, model: str | None = None) -> None:
        if self._sink is None:
            return
        try:
            self._sink(kind, model or self.model, usage, ok)
        except Exception:
            log.exception("usage accounting failed")

    async def generate(
        self, transcript: str, system_instruction: str, max_output_tokens: int = 400, kind: str = "reply",
    ) -> str | None:
        out = await self.complete(transcript, system_instruction, max_output_tokens, kind)
        return out[0] if out else None

    async def complete(
        self, transcript: str, system_instruction: str | None, max_output_tokens: int = 400, kind: str = "reply",
    ) -> tuple[str, str] | None:
        """(text, finish) — finish is "max_tokens" when the cap cut the reply, else "stop"; None on failure."""
        try:
            resp = await self._client.aio.models.generate_content(
                model=self.model,
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
            self._report(kind, None, False)
            return None
        text = (resp.text or "").strip() if resp is not None else ""
        self._report(kind, getattr(resp, "usage_metadata", None), bool(text))
        if not text:
            log.error("gemini returned an empty reply")
            return None
        return text, finish_of(resp)


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
                    max_output_tokens: int = THINK_MAX_TOKENS, kind: str = "digest_voice") -> str | None:
        """v5.1 — one call with thinking on (a Pro model rejects a zero budget): the answer is the non-thought text;
        the usage line names this call's model. None on failure or an empty answer (logged by type)."""
        try:
            resp = await self._client.aio.models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    max_output_tokens=max_output_tokens,
                    thinking_config=types.ThinkingConfig(include_thoughts=False),
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                ),
            )
        except Exception as exc:  # noqa: BLE001 — any provider failure means silence
            log.error("gemini think failed: %s", type(exc).__name__)
            self._report(kind, None, False, model)
            return None
        text = answer_text(resp)
        self._report(kind, getattr(resp, "usage_metadata", None), bool(text), model)
        if not text:
            log.error("gemini think returned no answer (finish %s)", finish_of(resp))
            return None
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


def finish_of(resp: Any) -> str:
    """The candidate's finish reason, mapped to the responder's vocabulary."""
    candidates = getattr(resp, "candidates", None) or []
    reason = getattr(candidates[0], "finish_reason", None) if candidates else None
    return "max_tokens" if "MAX_TOKENS" in str(getattr(reason, "name", reason) or "") else "stop"
