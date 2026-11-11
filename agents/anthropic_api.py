"""v7.4 (AGORA-251) — `api-sonnet`: a companion's answer on Claude Sonnet 5.5 through Anthropic's Messages API, paid
by the token. Its key is `SONNET_API_KEY`, handed over explicitly — never named `ANTHROPIC_*`, which a Claude client
on the subscription refuses (v4.4) — and the `anthropic` SDK is imported in this module alone (v4.4 layer 6, widened
by v7.4). Her whole instruction as `system`, the transcript as the user's message, adaptive thinking at
`SONNET_EFFORT`, no tools. A `refusal` stop is a refusal (its category kept); `max_tokens` is the cut.
"""

from __future__ import annotations

from typing import Any

from agents.api_answers import ApiAnswers

MODEL = "claude-sonnet-5-5"
KEY_VAR = "SONNET_API_KEY"
EFFORTS = ("low", "medium", "high", "max")


def _usage(resp: Any) -> dict:
    """Her answer's tokens: the whole input (the fresh part, and the cache read and written), the output (the
    thinking counted in it)."""
    u = getattr(resp, "usage", None)
    if u is None:
        return {}
    fresh = getattr(u, "input_tokens", None)
    read = getattr(u, "cache_read_input_tokens", None) or 0
    written = getattr(u, "cache_creation_input_tokens", None) or 0
    return {"input_tokens": fresh + read + written if isinstance(fresh, int) else None,
            "cached_tokens": read or None, "output_tokens": getattr(u, "output_tokens", None)}


def text_of(resp: Any) -> str:
    return "".join(getattr(b, "text", "") or "" for b in getattr(resp, "content", None) or []
                   if getattr(b, "type", None) == "text")


class AnthropicAnswers(ApiAnswers):
    engine = "anthropic"

    def __init__(self, key: str, *, effort: str = "medium", client: Any = None, **kwargs: Any) -> None:
        super().__init__(model=MODEL, effort=effort if effort in EFFORTS else "medium", **kwargs)
        if client is None:
            # here alone; the key handed over, never read from the environment
            from anthropic import AsyncAnthropic
            client = AsyncAnthropic(api_key=key, max_retries=2, timeout=self.timeout_s)
        self._client = client

    def __repr__(self) -> str:  # never the key
        return f"AnthropicAnswers(model={self.reply_model!r}, effort={self.effort!r})"

    async def _call(self, system: str, message: str, cap: int) -> tuple[str, str, dict, tuple | None]:
        resp = await self._client.messages.create(
            model=self.reply_model, max_tokens=cap, system=system,
            messages=[{"role": "user", "content": message}],
            thinking={"type": "adaptive"}, output_config={"effort": self.effort})
        stop = getattr(resp, "stop_reason", None)
        refused = None
        if stop == "refusal":
            details = getattr(resp, "stop_details", None)
            refused = ("refusal", "refusal", getattr(details, "category", None))
        return text_of(resp), "max_tokens" if stop == "max_tokens" else "stop", _usage(resp), refused
