"""v7.4 — a companion's answers on the model the owner picks in her panel settings (`ANSWER_MODEL`).

The owner, 2026-11-11: «щоб Кіру можна було перемикати між 4ма моделями api-gemini-3.1pro, api-gtp-6.1sol,
api-sonet, claudemax-opus всі моделі мають мати включений thinking», then a fifth, «codex-gpt-6.1sol», and «те саме
треба буде потім для Устини». Only her answers follow the switch (the private chat, writing first, Agora: the
`ANSWER_KINDS`); her background stays on Gemini, the agent's own client. The switch is live: read at each answer, so
the panel's change works at once and restarts nobody.

Each answer client has `reply(transcript, system, max_output_tokens, kind)` → `(text, finish)` or None, a refusal
being None with `LAST_BLOCK` set — as `GeminiClient` and `ClaudeClient` have. The whole instruction goes as its
system prompt (the order for the cache is v7.5's). A choice whose client is missing (no key, not signed in, no SDK)
answers nothing and is said by name; its answer is never handed to another model.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping

from agents.answer_models import CHOICES, ENGINE_OF
from agents.claude_sdk import LAST_SERVED
from agents.llm import LAST_BLOCK
from agents.responder import ANSWER_KINDS, Reply, Responder, Turn

log = logging.getLogger("agent.answers")

MISSING_LOG_S = 60  # a missing choice is said at most once a minute


class SwitchedResponder:
    """Her answers on the chosen model's responder (an `LlmResponder` over its client), every other kind on `base`
    (Gemini, as ever); the Gemini choice is `base` itself, so on it nothing differs from before v7.4."""

    def __init__(self, choice: Callable[[], str], responders: Mapping[str, Responder], base: Responder,
                 mono: Callable[[], float] = time.monotonic) -> None:
        self._choice = choice
        self.responders = dict(responders)
        self.base = base
        self._mono = mono
        self._said: dict[str, float] = {}

    def chosen(self) -> str:
        """The choice now — an unknown value (a hand edit) is the default's."""
        value = self._choice()
        return value if value in ENGINE_OF else CHOICES[0]

    def available(self) -> list[str]:
        return [name for name in CHOICES if name in self.responders]

    def _missing(self, name: str) -> None:
        now = self._mono()
        if now - self._said.get(name, float("-inf")) >= MISSING_LOG_S:
            self._said[name] = now
            log.warning("answers: %s is not available — no answer", name)

    async def respond(self, turn: Turn) -> Reply | None:
        if turn.kind not in ANSWER_KINDS:
            return await self.base.respond(turn)
        name = self.chosen()
        LAST_SERVED.set(ENGINE_OF[name])  # the client's own fallback at a limit says `gemini` in its turn
        LAST_BLOCK.set(None)
        responder = self.responders.get(name)
        if responder is None:
            self._missing(name)
            return None
        return await responder.respond(turn)
