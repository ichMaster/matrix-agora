"""The LLM seam: one async call to Gemini, injectable and silent on failure.

Any error or empty reply returns None — the agent then stays silent (never
crashes, never apologizes in the room). No prompts, replies or keys in logs.
Every call — ok, empty or failed — is reported to the usage sink (v3.1).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from google import genai
from google.genai import types

log = logging.getLogger("agent.llm")

MODEL = "gemini-2.5-flash"

UsageSink = Callable[[str, str, Any, bool], None]  # (kind, model, usage_metadata | None, ok)


class GeminiClient:
    def __init__(self, sink: UsageSink | None = None) -> None:
        self._client = genai.Client()  # reads GEMINI_API_KEY from the environment
        self._sink = sink

    def _report(self, kind: str, usage: Any, ok: bool) -> None:
        if self._sink is None:
            return
        try:
            self._sink(kind, MODEL, usage, ok)
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
                model=MODEL,
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


def finish_of(resp: Any) -> str:
    """The candidate's finish reason, mapped to the responder's vocabulary."""
    candidates = getattr(resp, "candidates", None) or []
    reason = getattr(candidates[0], "finish_reason", None) if candidates else None
    return "max_tokens" if "MAX_TOKENS" in str(getattr(reason, "name", reason) or "") else "stop"
