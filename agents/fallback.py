"""v5.14 — the backup model for Кіра's private chat: GLM-4.6 on NovelAI, a service that does not filter text.

When Gemini blocks or refuses her private answer (v5.13), the same prompt goes here. NovelAI's OpenAI-compatible chat
endpoint (verified with the owner's token, 2026-10-28) streams the answer in deltas only and reports no token counts;
Cloudflare refuses a client's default User-Agent (403 «error code: 1010»), so the request sends its own. Any failure
is None — silence, logged by type or status, never the token or a text. `backup_check` drops an answer that is not
her: Russian letters, a Latin majority, another script, a run of one symbol, or her calling herself a model.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable

import aiohttp

from agents.emotion import split_tags
from agents.llm import opening, refusal_marker

log = logging.getLogger("agent.fallback")

URL = "https://text.novelai.net/oa/v1/chat/completions"
TOKEN_VAR = "NOVELAI_API_TOKEN"
USER_AGENT = "matrix-agora/5.14"
TIMEOUT_S = 60          # the whole answer: a stream that hangs ends here
TEMPERATURE = 0.7       # the owner's choice, agreed as proposed (2026-10-28)
TOP_P = 0.9
THINK_RE = re.compile(r"<think>.*?(?:</think>|$)", re.DOTALL | re.IGNORECASE)
RUSSIAN_RE = re.compile(r"[ыэъёЫЭЪЁ]")
LATIN_RE = re.compile(r"[A-Za-z]")
CYRILLIC_RE = re.compile(r"[А-Яа-яІіЇїЄєҐґ]")
# Han, kana, Hangul, Arabic, Hebrew — a letter of another script means the model broke down
OTHER_SCRIPT_RE = re.compile(r"[֐-׿؀-ۿ぀-ヿ㐀-䶿一-鿿가-힯]")
RUN_RE = re.compile(r"(.)\1{10,}", re.DOTALL)
SELF_OPENINGS = ("я бот", "я чат бот", "я чатбот")  # with v5.13's refusal phrases: she never calls herself a model

UsageSink = Callable[[str, str, bool], None]  # (kind, model, ok)
ClientSession = aiohttp.ClientSession  # the seam: a test passes its own (tests/conftest.py guards the network)


def backup_check(text: str) -> str | None:
    """Why the backup's answer is not hers — `russian`, `latin`, `script`, `run` or `self` — or None. The audio tags
    are taken out first: `[laughs]` is Latin."""
    words, _ = split_tags(text)
    if RUSSIAN_RE.search(text):
        return "russian"
    if len(LATIN_RE.findall(words)) > len(CYRILLIC_RE.findall(words)):
        return "latin"
    if OTHER_SCRIPT_RE.search(text):
        return "script"
    if RUN_RE.search(text):
        return "run"
    if refusal_marker(words) or opening(words, SELF_OPENINGS):
        return "self"
    return None


def body(model: str, instruction: str | None, transcript: str, max_tokens: int) -> dict:
    """The request: the system instruction and the `Name: text` transcript, her token cap, the owner's sampling."""
    messages = ([{"role": "system", "content": instruction}] if instruction else []) + [
        {"role": "user", "content": transcript}]
    return {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": TEMPERATURE,
            "top_p": TOP_P, "stream": True}


def assemble(lines: list[str]) -> tuple[str, str]:
    """The streamed `data:` lines → (text, finish): the deltas put together until `[DONE]`, a `<think>` block cut;
    finish is `max_tokens` when the cap cut it (`length`), else `stop`."""
    parts, finish = [], None
    for line in lines:
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            break
        try:
            event = json.loads(payload)
        except ValueError:
            continue
        choices = event.get("choices") if isinstance(event, dict) else None
        for choice in choices if isinstance(choices, list) else []:
            if not isinstance(choice, dict):
                continue
            delta = choice.get("delta")
            content = delta.get("content") if isinstance(delta, dict) else None
            parts.append(content if isinstance(content, str) else "")
            finish = choice.get("finish_reason") or finish
    text = THINK_RE.sub("", "".join(parts)).strip()
    return text, "max_tokens" if finish == "length" else "stop"


class FallbackClient:
    """GLM-4.6 on NovelAI, one streamed call per answer; `reply` mirrors `GeminiClient.reply`."""

    def __init__(self, token: str, model: str, sink: UsageSink | None = None, timeout_s: float = TIMEOUT_S) -> None:
        self._token = token
        self.model = model
        self._sink = sink
        self.timeout_s = timeout_s

    def __repr__(self) -> str:  # never the token
        return f"FallbackClient(model={self.model!r})"

    def _report(self, kind: str, ok: bool) -> None:
        if self._sink is None:
            return
        try:
            self._sink(kind, self.model, ok)
        except Exception:
            log.exception("usage accounting failed")

    async def reply(self, transcript: str, system_instruction: str | None, max_output_tokens: int = 400,
                    kind: str = "private") -> tuple[str, str] | None:
        headers = {"Authorization": f"Bearer {self._token}", "User-Agent": USER_AGENT,
                   "Accept": "text/event-stream", "Content-Type": "application/json"}
        try:
            async with ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout_s)) as session, \
                    session.post(URL, json=body(self.model, system_instruction, transcript, max_output_tokens),
                                 headers=headers) as resp:
                if resp.status != 200:
                    log.error("backup: HTTP %s", resp.status)
                    self._report(kind, False)
                    return None
                lines = [raw.decode("utf-8", "replace") async for raw in resp.content]
        except Exception as exc:  # noqa: BLE001 — any failure is silence, named by its type only
            log.error("backup failed: %s", type(exc).__name__)
            self._report(kind, False)
            return None
        text, finish = assemble(lines)
        self._report(kind, bool(text))
        if not text:
            log.error("backup returned an empty answer")
            return None
        return text, finish
