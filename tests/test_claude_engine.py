"""v7.1 — the engine per agent: a persona, the cat or Hermes on Claude (`engine = "claude-sdk"`), Claude himself as
before, and an agent on Gemini untouched. nio is never reached; the SDK is a fake."""

import asyncio
import logging
import os
from dataclasses import replace
from types import SimpleNamespace

import pytest

from agents.claude_sdk import AuthRefused, ClaudeClient, ClaudeSdkResponder, claude_client_for, secret_vars
from agents.config import AgentConfig
from agents.llm import GeminiClient
from agents.responder import LlmResponder, Turn
from agents.roster import TYPES, parse_member
from tests.test_claude_client import INIT_OK, FakeSDK, result
from tests.test_first_sync import CFG, v44_room

SECRETS = {"ADA_PASSWORD": "pw-a", "BRUNO_PASSWORD": "pw-b", "REGISTRATION_TOKEN": "reg", "PANEL_TOKEN": "panel",
           "GEMINI_API_KEY": "gem-key", "GUARDIAN_API_KEY": "g"}


@pytest.fixture
def subscription(monkeypatch):
    for k in [k for k in os.environ if k.startswith(("ANTHROPIC_", "CLAUDE_CODE_USE_"))]:
        monkeypatch.delenv(k)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oat")
    for k, v in SECRETS.items():
        monkeypatch.setenv(k, v)
    return monkeypatch


def persona(**kw):
    return replace(CFG, engine="claude-sdk", **kw)


def on_claude(sdk, tmp_path):
    return ClaudeClient(reply_model="sonnet", background_model="haiku", config_dir=str(tmp_path / "cfg"),
                        status_file=tmp_path / "ada.ratelimit.json", sink=None, query=sdk.query,
                        options=lambda **kw: SimpleNamespace(**kw))


# --- who gets which engine --------------------------------------------------------------------------------------
def test_a_persona_on_claude_gets_the_claude_client_and_the_shared_responder(subscription):
    from agents.agent import Agent
    agent = Agent(persona(), roster=v44_room())
    assert isinstance(agent.llm, ClaudeClient) and isinstance(agent.responder, LlmResponder)
    assert (agent.llm.reply_model, agent.llm.model, agent.llm.limit_fallback) == ("sonnet", "haiku", "gemini")
    assert agent.llm.status_file.name == "ada.ratelimit.json"
    assert isinstance(agent.llm.fallback, GeminiClient) and agent.llm.embedder is None  # no recall: no embeddings


def test_her_settings_pick_the_models_the_bound_and_the_limit(subscription):
    from agents.agent import Agent
    for k, v in {"CLAUDE_REPLY_MODEL": "haiku", "CLAUDE_BACKGROUND_MODEL": "sonnet", "CLAUDE_CONCURRENCY": "3",
                 "CLAUDE_LIMIT_FALLBACK": "silent"}.items():
        subscription.setenv(k, v)
    agent = Agent(replace(CFG, name="Кіт", user_id="@kit:agora.lan", type="creature", engine="claude-sdk",
                          capabilities=TYPES["creature"]), roster=v44_room())
    assert (agent.llm.reply_model, agent.llm.model, agent.llm.limit_fallback) == ("haiku", "sonnet", "silent")
    assert agent.llm.fallback is None and agent.llm._gate._value == 3


def test_claude_himself_keeps_his_own_responder(subscription):
    from agents.agent import Agent
    cfg = AgentConfig(**{**CFG.__dict__, "name": "Клод", "user_id": "@claude:agora.lan", "type": "assistant",
                         "engine": "claude-sdk", "capabilities": frozenset(), "canon": ""})
    agent = Agent(cfg)
    assert isinstance(agent.responder, ClaudeSdkResponder) and agent.llm is None


def test_an_agent_on_gemini_is_untouched(subscription):
    from agents.agent import Agent
    agent = Agent(CFG, roster=v44_room())
    assert isinstance(agent.llm, GeminiClient) and isinstance(agent.responder, LlmResponder)
    assert os.environ["GEMINI_API_KEY"] == "gem-key" and os.environ["ADA_PASSWORD"] == "pw-a"


def test_a_forbidden_variable_or_no_token_refuses_her_start(subscription):
    from agents.agent import Agent
    subscription.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    with pytest.raises(AuthRefused, match="ANTHROPIC_API_KEY"):
        Agent(persona(), roster=v44_room())
    subscription.delenv("ANTHROPIC_API_KEY")
    subscription.delenv("CLAUDE_CODE_OAUTH_TOKEN")
    with pytest.raises(AuthRefused, match="CLAUDE_CODE_OAUTH_TOKEN"):
        Agent(persona(), roster=v44_room())


# --- no secret for the CLI --------------------------------------------------------------------------------------
def test_secret_vars_names_every_secret_but_the_oauth_token():
    env = {**SECRETS, "CLAUDE_CODE_OAUTH_TOKEN": "oat", "TELEGRAM_BOT_TOKEN": "t", "FAL_KEY": "f",
           "REPLY_MAX_TOKENS": "200", "CLAUDE_CODE_MAX_OUTPUT_TOKENS": "0", "ADA_VOICE_ID": "v", "ROOM_ID": "!r"}
    assert secret_vars(env) == sorted([*SECRETS, "TELEGRAM_BOT_TOKEN", "FAL_KEY"])


def test_after_her_start_no_secret_is_left_for_the_cli(subscription):
    from agents.agent import Agent
    agent = Agent(persona(), roster=v44_room())
    assert not [k for k in SECRETS if k in os.environ] and os.environ["CLAUDE_CODE_OAUTH_TOKEN"] == "oat"
    assert agent.cfg.password == "pw"  # her own was read before


# --- Gemini beside Claude, only when needed ---------------------------------------------------------------------
@pytest.mark.parametrize("recall,fallback,has_fallback,has_embedder", [
    (False, "gemini", True, False), (False, "silent", False, False),
    (True, "silent", False, True), (True, "gemini", True, True)])
def test_gemini_is_built_for_the_embeddings_or_the_limit_alone(tmp_path, recall, fallback, has_fallback,
                                                                 has_embedder):
    env = {"CLAUDE_CODE_OAUTH_TOKEN": "oat", "GEMINI_API_KEY": "gem-key", "CLAUDE_LIMIT_FALLBACK": fallback}
    c = claude_client_for(env, status_file=tmp_path / "s.json", sink=None, gemini_sink=None, clock=lambda: 0,
                          recall=recall)
    assert (c.fallback is not None, c.embedder is not None) == (has_fallback, has_embedder)
    assert "GEMINI_API_KEY" not in env  # handed over, never left behind


def test_without_a_gemini_key_she_says_what_she_loses(tmp_path, caplog):
    env = {"CLAUDE_CODE_OAUTH_TOKEN": "oat"}
    c = claude_client_for(env, status_file=tmp_path / "s.json", sink=None, gemini_sink=None, clock=lambda: 0,
                          recall=True)
    assert c.fallback is None and c.embedder is None
    assert "no GEMINI_API_KEY on claude: no meaning search in recall, silent at the limit" in caplog.text


def test_a_bad_fallback_or_bound_falls_back_to_the_defaults(tmp_path, caplog):
    caplog.set_level(logging.WARNING)
    env = {"CLAUDE_CODE_OAUTH_TOKEN": "oat", "CLAUDE_LIMIT_FALLBACK": "maybe", "CLAUDE_CONCURRENCY": "many"}
    c = claude_client_for(env, status_file=tmp_path / "s.json", sink=None, gemini_sink=None, clock=lambda: 0,
                          recall=False, gemini=object())
    assert c.limit_fallback == "gemini" and c._gate._value == 2


# --- her calls through the client, on their models --------------------------------------------------------------
def test_her_answer_and_her_summary_go_through_claude_on_their_models(subscription, tmp_path):
    from agents.agent import Agent
    sdk = FakeSDK([INIT_OK, result("Привіт, я тут.")],
                  [INIT_OK, result("Нотатка: говорили про Карпати.\n\nСесія: Ich питав про гори.")])
    agent = Agent(persona(), llm=on_claude(sdk, tmp_path), roster=v44_room())
    reply = asyncio.run(agent.responder.respond(Turn([("Ich", "привіт")], "КАНОН", 200)))
    assert reply.text == "Привіт, я тут."
    agent.session = [("Ich", "підемо в гори?"), ("Ада", "так!")]
    assert asyncio.run(agent.summarize()) is True
    assert [o.model for _, o in sdk.calls] == ["sonnet", "haiku"]


def test_a_decline_in_agora_is_silence(subscription, tmp_path, caplog):
    from agents.agent import Agent
    sdk = FakeSDK([INIT_OK, result("Вибач, ні.", stop_reason="refusal")])
    agent = Agent(persona(), llm=on_claude(sdk, tmp_path), roster=v44_room())
    assert asyncio.run(agent._compose("КАНОН")) is None
    assert "claude declined: reason=stop kind=reply" in caplog.text and "Вибач" not in caplog.text


def test_hermes_on_claude_writes_his_digest_on_the_reply_model(subscription, tmp_path):
    from agents.herald import Herald
    from tests.test_herald import CFG as HERMES
    from tests.test_herald import ROSTER
    h = Herald(replace(HERMES, engine="claude-sdk"), roster=ROSTER, client=SimpleNamespace(), state_dir=tmp_path)
    assert isinstance(h.llm, ClaudeClient) and h.llm.embedder is None
    assert h.llm.status_file == tmp_path / "hermes.ratelimit.json"
    assert not [k for k in SECRETS if k in os.environ]
    sdk = FakeSDK([INIT_OK, result("Сьогодні в кімнаті говорили про гори.")])
    h.llm._query_fn, h.llm._options = sdk.query, (lambda **kw: SimpleNamespace(**kw))
    out = asyncio.run(h.llm.think("розмова", "БРИФ", kind="digest_voice"))
    assert out.startswith("Сьогодні") and sdk.calls[-1][1].model == "sonnet"
    h.record_sdk_usage("digest_voice", "claude-sonnet-5-5", {"input_tokens": 5, "output_tokens": 2}, True, None,
                       latency_ms=900)
    line = (tmp_path / "hermes.usage.jsonl").read_text(encoding="utf-8")
    assert '"engine": "claude-sdk"' in line and '"billing": "subscription"' in line


# --- the roster: the engine on every type -----------------------------------------------------------------------
@pytest.mark.parametrize("kind", ["persona", "creature", "herald", "assistant"])
def test_claude_sdk_is_an_engine_of_every_type(kind):
    m = parse_member("x", {"name": "X", "user_id": "@x:agora.lan", "type": kind, "engine": "claude-sdk"})
    assert m.engine == "claude-sdk"
