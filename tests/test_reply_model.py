"""v5.8 — two models: the agent's answers on `GEMINI_REPLY_MODEL` (a thinking model through the thinking path), every
other call on `GEMINI_MODEL` (google-genai mocked)."""

import asyncio
from types import SimpleNamespace

import pytest
from google.genai import types

from agents import llm as llm_mod
from agents.llm import THINKING_MODELS, GeminiClient
from agents.responder import ANSWER_KINDS, GeminiResponder, Turn
from agents.settings import BY_NAME, validate

PRO = "gemini-3.1-pro-preview"


class Models:
    def __init__(self, resp=None, fail=None):
        self.resp, self.fail, self.seen = resp, fail, []

    async def generate_content(self, model, contents, config):
        self.seen.append({"model": model, "config": config})
        if self.fail:
            raise self.fail
        return self.resp


def response(*parts, finish="STOP"):
    return SimpleNamespace(text=None, usage_metadata=SimpleNamespace(prompt_token_count=10),
                           candidates=[SimpleNamespace(content=SimpleNamespace(parts=list(parts)),
                                                       finish_reason=SimpleNamespace(name=finish))])


def client(monkeypatch, models, reply_model="", level=None):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv("GEMINI_REPLY_MODEL", reply_model)
    if level:
        monkeypatch.setenv("GEMINI_THINKING_LEVEL", level)
    else:
        monkeypatch.delenv("GEMINI_THINKING_LEVEL", raising=False)
    monkeypatch.setattr(llm_mod.genai, "Client", lambda: SimpleNamespace(aio=SimpleNamespace(models=models)))
    usage = []
    return GeminiClient(sink=lambda kind, model, meta, ok: usage.append((kind, model, ok))), usage


def flash_response(text="Привіт."):
    return SimpleNamespace(text=text, usage_metadata=None,
                           candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name="STOP"))])


def test_an_answer_on_a_thinking_model_thinks_and_returns_only_the_answer(monkeypatch):
    models = Models(response(SimpleNamespace(text="думаю…", thought=True), SimpleNamespace(text="Ось.", thought=None)))
    llm, usage = client(monkeypatch, models, PRO)
    assert asyncio.run(llm.reply("Ich: привіт", "КАНОН", 4096, "private")) == ("Ось.", "stop")
    seen = models.seen[0]
    assert seen["model"] == PRO and seen["config"].max_output_tokens == 4096
    assert seen["config"].thinking_config.thinking_budget is None                 # never a zero budget
    assert seen["config"].thinking_config.thinking_level == types.ThinkingLevel.LOW
    assert usage == [("private", PRO, True)]


def test_a_cut_thinking_answer_says_so_and_the_level_is_tunable(monkeypatch):
    models = Models(response(SimpleNamespace(text="Перше речення. Друге обірв", thought=None), finish="MAX_TOKENS"))
    llm, _ = client(monkeypatch, models, PRO, level="high")
    assert asyncio.run(llm.reply("c", "s", 4096, "reply")) == ("Перше речення. Друге обірв", "max_tokens")
    assert models.seen[0]["config"].thinking_config.thinking_level == types.ThinkingLevel.HIGH


@pytest.mark.parametrize("fail", [RuntimeError("boom"), None])
def test_a_failed_or_empty_thinking_answer_is_none_reported_under_its_model(monkeypatch, fail):
    models = Models(response(SimpleNamespace(text="лише думка", thought=True)), fail=fail)
    llm, usage = client(monkeypatch, models, PRO)
    assert asyncio.run(llm.reply("c", "s", 4096, "reply")) is None
    assert usage == [("reply", PRO, False)]


def test_a_reply_model_with_thinking_off_goes_through_the_plain_call(monkeypatch):
    models = Models(flash_response())
    llm, usage = client(monkeypatch, models, "gemini-2.5-flash-lite")
    assert asyncio.run(llm.reply("c", "s", 200, "reply")) == ("Привіт.", "stop")
    assert models.seen[0]["model"] == "gemini-2.5-flash-lite"
    assert models.seen[0]["config"].thinking_config.thinking_budget == 0
    assert usage == [("reply", "gemini-2.5-flash-lite", True)]


def test_an_empty_reply_model_is_gemini_model(monkeypatch):
    models = Models(flash_response())
    llm, usage = client(monkeypatch, models, "")
    assert llm.reply_model == "gemini-2.5-flash"
    asyncio.run(llm.reply("c", "s", 200, "reply"))
    assert models.seen[0]["model"] == "gemini-2.5-flash" and usage == [("reply", "gemini-2.5-flash", True)]


@pytest.mark.parametrize(("kind", "model"), [
    ("reply", PRO), ("private", PRO), ("private_nudge", PRO),
    ("summary", "gemini-2.5-flash"), ("day_memory", "gemini-2.5-flash"), ("plan", "gemini-2.5-flash"),
    ("today", "gemini-2.5-flash"), ("digest", "gemini-2.5-flash"),
])
def test_the_responder_routes_answers_to_the_reply_model_and_the_rest_to_gemini_model(monkeypatch, kind, model):
    models = Models(response(SimpleNamespace(text="Так.", thought=None)))
    models.resp.text = "Так."
    llm, usage = client(monkeypatch, models, PRO)
    asyncio.run(GeminiResponder(llm).respond(Turn([("Ich", "привіт")], "КАНОН", 400, kind)))
    assert models.seen[0]["model"] == model and usage[0][:2] == (kind, model)


def test_the_answer_kinds_and_the_thinking_models():
    assert ANSWER_KINDS == ("reply", "private", "private_nudge")
    assert PRO in THINKING_MODELS and "gemini-2.5-flash" not in THINKING_MODELS


def test_the_settings():
    assert BY_NAME["GEMINI_REPLY_MODEL"].choices == ("", "gemini-2.5-flash", "gemini-2.5-flash-lite", PRO)
    assert BY_NAME["GEMINI_REPLY_MODEL"].default == "" and BY_NAME["GEMINI_REPLY_MODEL"].scope == "engine:gemini"
    assert validate("GEMINI_REPLY_MODEL", PRO) == (PRO, None) and validate("GEMINI_REPLY_MODEL", "")[1] is None
    assert validate("GEMINI_REPLY_MODEL", "gemini-2.5-pro")[0] is None
    assert validate("GEMINI_THINKING_LEVEL", "medium") == ("medium", None)
    assert validate("REPLY_THINK_MAX_TOKENS", "512")[0] is None and BY_NAME["REPLY_THINK_MAX_TOKENS"].default == "4096"
    assert BY_NAME["GEMINI_MODEL"].choices == ("gemini-2.5-flash", "gemini-2.5-flash-lite")  # still thinking-off only


def test_a_thinking_reply_model_raises_the_agents_reply_cap(monkeypatch):
    from agents.agent import Agent
    from agents.config import AgentConfig
    monkeypatch.setenv("REPLY_MAX_TOKENS", "200")
    monkeypatch.setenv("REPLY_THINK_MAX_TOKENS", "4096")
    cfg = AgentConfig(name="Кіра", user_id="@kira:agora.lan", canon="К.", homeserver="http://hs", room_id="!room",
                      owner="@ich:agora.lan", password="pw")
    thinking = SimpleNamespace(reply_model=PRO, model="gemini-2.5-flash")
    assert Agent(cfg, llm=thinking).reply_max_tokens == 4096
    plain = SimpleNamespace(reply_model="gemini-2.5-flash", model="gemini-2.5-flash")
    assert Agent(cfg, llm=plain).reply_max_tokens == 200
