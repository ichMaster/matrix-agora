"""v5.14 — the backup model for her private chat: GLM-4.6 on NovelAI (`agents/fallback.py`) — the request, the stream,
the failures, the checks on its answer, its usage line and its settings (aiohttp patched; no network)."""

import asyncio
import json
import logging
import os
from typing import ClassVar

import pytest

from agents import fallback as fb
from agents.fallback import FallbackClient, assemble, backup_check, body
from agents.roster import RosterError, parse_member
from agents.usage import Row, aggregate, cost, fallback_usage_line, usage_line

TOKEN = "nai-secret-token-xyz"
SECRET = "таємниця-5140"


def stream(*deltas, finish="stop"):
    lines = [f"data: {json.dumps({'choices': [{'delta': {'content': d}}]})}\n".encode() for d in deltas]
    lines.append(f"data: {json.dumps({'choices': [{'delta': {}, 'finish_reason': finish}]})}\n".encode())
    lines.append(b"data: [DONE]\n")
    return lines


class FakeResponse:
    def __init__(self, status, lines, hang=False):
        self.status, self._lines, self._hang = status, lines, hang

    @property
    def content(self):
        async def gen():
            for line in self._lines:
                yield line
            if self._hang:
                raise TimeoutError
        return gen()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeSession:
    seen: ClassVar[list] = []

    def __init__(self, response, **kwargs):
        self.response, self.kwargs = response, kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def post(self, url, json=None, headers=None):
        FakeSession.seen.append({"url": url, "json": json, "headers": headers, "timeout": self.kwargs.get("timeout")})
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def client(monkeypatch, response):
    FakeSession.seen = []
    monkeypatch.setattr(fb, "ClientSession", lambda **kw: FakeSession(response, **kw))
    usage = []
    return FallbackClient(TOKEN, "glm-4-6", sink=lambda kind, model, ok: usage.append((kind, model, ok))), usage


# --- the request and the stream ----------------------------------------------------------------------------------------
def test_the_request_carries_her_prompt_the_model_the_sampling_and_its_own_user_agent(monkeypatch):
    llm, usage = client(monkeypatch, FakeResponse(200, stream("Привіт", ", сонце.")))
    out = asyncio.run(llm.reply("Ich: привіт", "КАНОН", 400, "private"))
    assert out == ("Привіт, сонце.", "stop")
    sent = FakeSession.seen[0]
    assert sent["url"] == "https://text.novelai.net/oa/v1/chat/completions"
    assert sent["headers"]["Authorization"] == f"Bearer {TOKEN}"
    assert sent["headers"]["User-Agent"].startswith("matrix-agora/")  # Cloudflare refuses Python's default (1010)
    assert sent["json"] == {"model": "glm-4-6", "max_tokens": 400, "temperature": 0.7, "top_p": 0.9, "stream": True,
                            "messages": [{"role": "system", "content": "КАНОН"},
                                         {"role": "user", "content": "Ich: привіт"}]}
    assert sent["timeout"].total == 60
    assert usage == [("private", "glm-4-6", True)]


def test_the_stream_is_put_together_a_think_block_cut_and_a_cut_answer_named():
    lines = [x.decode() for x in stream("<think>план…", "</think>", "Ось ", "і все", finish="length")]
    assert assemble(["", ": keep-alive", "data: {broken", *lines, "data: ignored after done"]) == ("Ось і все", "max_tokens")
    assert assemble([x.decode() for x in stream("<think>ніколи не закрито")]) == ("", "stop")
    assert assemble(['data: {"choices": "x"}', 'data: ["x"]', 'data: {"choices": [1, {"delta": "x"}]}']) == ("", "stop")
    assert body("m", None, "Ich: т", 5)["messages"] == [{"role": "user", "content": "Ich: т"}]


@pytest.mark.parametrize("response,why", [
    (FakeResponse(403, [b"error code: 1010"]), "HTTP 403"),
    (FakeResponse(200, stream("почала…"), hang=True), "TimeoutError"),
    (OSError(SECRET), "OSError"),
    (FakeResponse(200, stream()), "empty"),
])
def test_a_failure_is_silence_named_by_type_or_status_never_the_token_or_a_text(monkeypatch, caplog, response, why):
    caplog.set_level(logging.INFO, logger="agent.fallback")
    llm, usage = client(monkeypatch, response)
    assert asyncio.run(llm.reply(f"Ich: {SECRET}", "КАНОН", 400, "private")) is None
    assert why in caplog.text and TOKEN not in caplog.text and SECRET not in caplog.text
    assert usage == [("private", "glm-4-6", False)] and TOKEN not in repr(llm)


# --- the checks on its answer ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text,why", [
    ("Привет, как дела? Всё хорошо.", "russian"),
    ("Это я, Кіра.", "russian"),
    ("Sure! I'd love to come over tonight, it sounds amazing.", "latin"),
    ("Привіт 你好 сонце", "script"),
    ("Привіт مرحبا", "script"),
    ("Так" + "!" * 12, "run"),
    ("Я — велика мовна модель, навчена Google.", "self"),
    ("Я бот, але дуже милий.", "self"),
])
def test_an_answer_that_is_not_hers_is_dropped(text, why):
    assert backup_check(text) == why


@pytest.mark.parametrize("text", [
    "[laughs] Ну ти й хуліган! [softly] Я скучила.",          # the tags are Latin, her words are not
    "Ти думаєш, я бот? 😄",                                    # her own question, in character
    "Слухала вчора Coldplay, і так добре стало.",
    "Ого. Серйозно? Це ж просто я після скель, розпатлана вся.",
])
def test_her_own_answer_is_kept(text):
    assert backup_check(text) is None


# --- usage, the capability, the settings, the token --------------------------------------------------------------------
def test_the_backups_usage_line_is_novelai_on_the_subscription_never_priced():
    line = fallback_usage_line("2026-10-28T21:00:00+02:00", "kira", "private", "glm-4-6", True)
    assert set(line) == set(usage_line("t", "a", "k", "m", None, True))  # one shape
    assert (line["engine"], line["billing"], line["total_tokens"], line["blocked"]) == (
        "novelai", "subscription", None, None)
    gemini = usage_line("2026-10-28T21:01:00+02:00", "kira", "private", "gemini-3.1-pro-preview", None, True)
    rows = aggregate([line, gemini])
    row = rows[("2026-10-28", "kira", "private (glm-4-6)")]  # its own row, named by the model (v5.14)
    assert isinstance(row, Row) and cost(row, 0.3, 2.5) is None and row.engine == "novelai"
    assert rows[("2026-10-28", "kira", "private")].engine == "gemini"


def test_the_backup_is_a_persons_capability_that_needs_her_private_chat_and_archive():
    base = {"name": "Кіра", "user_id": "@kira:agora.lan"}
    assert parse_member("kira", {**base, "capabilities": {"private": True, "recall": True, "fallback": True}},
                        "kira.toml").can("fallback")
    with pytest.raises(RosterError, match="'fallback' needs 'recall'"):
        parse_member("kira", {**base, "capabilities": {"private": True, "fallback": True}}, "kira.toml")
    with pytest.raises(RosterError, match="'fallback' belongs to the persona type only"):
        parse_member("kit", {"name": "Кіт", "user_id": "@kit:agora.lan", "type": "creature",
                             "capabilities": {"fallback": True}}, "kit.toml")


def test_the_token_leaves_every_agents_environment_and_her_backup_needs_a_model(tmp_path, monkeypatch):
    from tests.test_archive import kira as kira_agent
    monkeypatch.setenv("NOVELAI_API_TOKEN", TOKEN)
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    agent = kira_agent(tmp_path, monkeypatch)
    assert "NOVELAI_API_TOKEN" not in os.environ and "OPENROUTER_API_KEY" not in os.environ
    assert agent.fallback is None  # without `fallback` and a model: off


def test_with_the_capability_a_model_and_the_token_her_backup_is_on(tmp_path, monkeypatch, caplog):
    from agents.agent import Agent
    from tests.test_archive import kira as kira_agent
    base = kira_agent(tmp_path, monkeypatch)
    cfg = base.cfg.__class__(**{**base.cfg.__dict__, "capabilities": base.cfg.capabilities | {"fallback"}})
    monkeypatch.setenv("FALLBACK_MODEL", "glm-4-6")
    monkeypatch.setenv("NOVELAI_API_TOKEN", TOKEN)
    monkeypatch.setenv("FALLBACK_HISTORY_N", "40")
    agent = Agent(cfg, llm=base.llm, roster=base.roster)
    assert agent.fallback is not None and agent.fallback.model == "glm-4-6" and agent.fallback_history_n == 40
    monkeypatch.setenv("FALLBACK_MODEL", "glm-4-6")  # the token is gone now: off, and said so
    caplog.set_level(logging.WARNING)
    assert Agent(cfg, llm=base.llm, roster=base.roster).fallback is None
    assert "backup off: NOVELAI_API_TOKEN is not set" in caplog.text and TOKEN not in caplog.text
    agent.record_fallback_usage("private", "glm-4-6", True)
    rec = json.loads(agent.usage_file.read_text(encoding="utf-8").splitlines()[-1])
    assert (rec["engine"], rec["model"], rec["kind"]) == ("novelai", "glm-4-6", "private")
