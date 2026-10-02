"""The LLM seam: one async call to Gemini, injectable and silent on failure.

Any error or empty reply returns None — the agent then stays silent (never
crashes, never apologizes in the room). No prompts, replies or keys in logs.
"""

from __future__ import annotations

import logging

from google import genai
from google.genai import types

log = logging.getLogger("agent.llm")

MODEL = "gemini-2.5-flash"


class GeminiClient:
    def __init__(self) -> None:
        self._client = genai.Client()  # reads GEMINI_API_KEY from the environment

    async def generate(
        self, transcript: str, system_instruction: str, max_output_tokens: int = 400,
    ) -> str | None:
        try:
            resp = await self._client.aio.models.generate_content(
                model=MODEL,
                contents=transcript,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    max_output_tokens=max_output_tokens,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
        except Exception as exc:  # noqa: BLE001 — any provider failure means silence
            log.error("gemini call failed: %s", type(exc).__name__)
            return None
        text = (resp.text or "").strip() if resp is not None else ""
        if not text:
            log.error("gemini returned an empty reply")
            return None
        return text
