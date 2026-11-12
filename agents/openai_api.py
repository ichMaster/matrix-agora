"""v7.4 (AGORA-251) — `api-gpt-6.1sol`: a companion's answer on GPT-6.1 Sol through OpenAI's Responses API, paid by
the token (`OPENAI_API_KEY`, handed over explicitly). Her whole instruction as `instructions`, the transcript as the
input, reasoning at `OPENAI_REASONING_EFFORT`, nothing stored on OpenAI's side, no tools. A refusal part or a
content-filter end is a refusal; an answer cut by the cap is `max_tokens`.
"""

from __future__ import annotations

from typing import Any

from agents.api_answers import ApiAnswers

MODEL = "gpt-6.1-sol"
EFFORTS = ("low", "medium", "high")  # never `none` or `minimal`: her answers always think


def _usage(resp: Any) -> dict:
    """Her answer's tokens: the input (the cached part counted in it, kept apart too) and the output (the reasoning
    counted in it)."""
    u = getattr(resp, "usage", None)
    if u is None:
        return {}
    details = getattr(u, "input_tokens_details", None)
    return {"input_tokens": getattr(u, "input_tokens", None),
            "cached_tokens": getattr(details, "cached_tokens", None),
            "output_tokens": getattr(u, "output_tokens", None)}


def refusal_of(resp: Any) -> tuple | None:
    """The model's own refusal (a `refusal` part of its message) or a content filter's end — never the refusal's text."""
    for item in getattr(resp, "output", None) or []:
        if getattr(item, "type", None) != "message":
            continue
        for part in getattr(item, "content", None) or []:
            if getattr(part, "type", None) == "refusal":
                return ("refusal", "refusal", None)
    details = getattr(resp, "incomplete_details", None)
    if getattr(resp, "status", None) == "incomplete" and getattr(details, "reason", None) == "content_filter":
        return ("refusal", "content_filter", None)
    return None


class OpenAIAnswers(ApiAnswers):
    engine = "openai"

    def __init__(self, key: str, *, effort: str = "medium", client: Any = None, cache_key: str = "answers",
                 **kwargs: Any) -> None:
        super().__init__(model=MODEL, effort=effort if effort in EFFORTS else "medium", **kwargs)
        self.cache_key = cache_key  # v7.5 (AGORA-257): her answers' prefix cache on OpenAI's side
        if client is None:
            from openai import AsyncOpenAI  # here alone; the key handed over, never read from the environment
            client = AsyncOpenAI(api_key=key, max_retries=2, timeout=self.timeout_s)
        self._client = client

    def __repr__(self) -> str:  # never the key
        return f"OpenAIAnswers(model={self.reply_model!r}, effort={self.effort!r})"

    async def _call(self, system: str, message: str, cap: int) -> tuple[str, str, dict, tuple | None]:
        resp = await self._client.responses.create(
            model=self.reply_model, instructions=system, input=message, reasoning={"effort": self.effort},
            max_output_tokens=cap, store=False, prompt_cache_key=self.cache_key)
        refused = refusal_of(resp)
        details = getattr(resp, "incomplete_details", None)
        cut = getattr(resp, "status", None) == "incomplete" and getattr(details, "reason", None) == "max_output_tokens"
        return (getattr(resp, "output_text", "") or "", "max_tokens" if cut else "stop", _usage(resp), refused)
