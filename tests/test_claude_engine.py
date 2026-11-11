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
    assert (agent.llm.thinking, agent.llm.effort) == ("off", "low")  # the defaults: no thinking
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
    env = {"CLAUDE_CODE_OAUTH_TOKEN": "oat", "CLAUDE_LIMIT_FALLBACK": "maybe", "CLAUDE_CONCURRENCY": "many",
           "CLAUDE_THINKING": "deep", "CLAUDE_EFFORT": "huge"}
    c = claude_client_for(env, status_file=tmp_path / "s.json", sink=None, gemini_sink=None, clock=lambda: 0,
                          recall=False, gemini=object())
    assert c.limit_fallback == "gemini" and c._gate._value == 2 and (c.thinking, c.effort) == ("off", "low")
    assert "CLAUDE_THINKING is not one of off, adaptive" in caplog.text


def test_her_thinking_comes_from_her_settings(tmp_path):
    env = {"CLAUDE_CODE_OAUTH_TOKEN": "oat", "CLAUDE_THINKING": "adaptive", "CLAUDE_EFFORT": "medium"}
    c = claude_client_for(env, status_file=tmp_path / "s.json", sink=None, gemini_sink=None, clock=lambda: 0,
                          recall=False, gemini=object())
    assert (c.thinking, c.effort, c.effort_for("private"), c.effort_for("summary")) == \
        ("adaptive", "medium", "medium", "low")
    assert c.thinks("private") and not c.thinks("summary")


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


# --- code review v7.1 #1: her talk summaries on Claude are kept, the scan is off ----------------------------------
def test_her_talk_summaries_on_claude_are_written_and_kept_and_the_scan_is_off(tmp_path, monkeypatch):
    from tests.test_archive import EmbedLLM
    from tests.test_talk_writer import drain, ms, say, talking
    sdk = FakeSDK([INIT_OK, result("Пам'ятаю, як ми гуляли.")])
    llm = ClaudeClient(reply_model="sonnet", background_model="haiku", config_dir=str(tmp_path / "cfg"),
                       status_file=tmp_path / "kira.ratelimit.json", sink=None, embedder=EmbedLLM(),
                       query=sdk.query, options=lambda **kw: SimpleNamespace(**kw))
    agent = talking(tmp_path, monkeypatch, llm)
    say(agent, "tg:1", ms(2026, 11, 2, 10, 1), "Ich", "Привіт")
    say(agent, "tg:2", ms(2026, 11, 2, 10, 2), "Кіра", "Привіт!")
    drain(agent)
    rows = agent.llm and agent.archive.talk_rows("hour")
    assert rows and rows[0].text == "Пам'ятаю, як ми гуляли." and rows[0].left_out == 0
    assert all(o.model == "haiku" for _, o in sdk.calls)  # the background model, no check call
    assert agent._scan_open() is False


# --- v7.3 (AGORA-246): Gemini beside Claude for her media and her fallback ------------------------------------------
def test_on_claude_her_photos_and_clips_are_made_on_the_gemini_beside_it(tmp_path, monkeypatch, caplog):
    """v7.1 code review #10: the makers read GEMINI_API_KEY, which the Claude client takes out of the environment."""
    import agents.agent as agent_mod
    from tests.test_photo_route import telegram_kira
    built = []
    monkeypatch.setattr(agent_mod, "photo_maker", lambda *a, **k: built.append(("photo", k)) or object())
    monkeypatch.setattr(agent_mod, "clip_maker", lambda *a, **k: built.append(("clip", k)) or object())
    monkeypatch.setattr(agent_mod, "load_faces", lambda folder: [("kira.png", b"x", "image/png")])
    monkeypatch.setattr(agent_mod, "load_look", lambda path: "Її очі світлі.")
    cfg = telegram_kira(tmp_path, monkeypatch).cfg
    cfg = replace(cfg, engine="claude-sdk", capabilities=cfg.capabilities | {"photos", "videos"})
    beside = SimpleNamespace(client="the google sdk client")
    agent_mod.Agent(cfg, llm=ClaudeClient(reply_model="sonnet", background_model="haiku", config_dir=str(tmp_path),
                                          status_file=tmp_path / "k.json", sink=None, gemini=beside))
    assert ("photo", {"client": "the google sdk client"}) in built and ("clip", {"client": "the google sdk client"}) in built
    built.clear()
    agent = agent_mod.Agent(cfg, llm=ClaudeClient(reply_model="sonnet", background_model="haiku",
                                                  config_dir=str(tmp_path), status_file=tmp_path / "k.json", sink=None))
    assert built == [] and agent.photos is None and agent.clips is None
    assert "photos: no Gemini beside Claude (GEMINI_API_KEY) — no photos" in caplog.text


def test_media_alone_brings_gemini_beside_claude_and_takes_its_key_out_of_the_environment(tmp_path, caplog):
    env = {"CLAUDE_CODE_OAUTH_TOKEN": "oat", "GEMINI_API_KEY": "gem-key", "CLAUDE_LIMIT_FALLBACK": "silent"}
    c = claude_client_for(env, status_file=tmp_path / "s.json", sink=None, gemini_sink=None, clock=lambda: 0,
                          recall=False, media=True)
    assert isinstance(c.gemini, GeminiClient) and c.fallback is None and c.embedder is None
    assert "GEMINI_API_KEY" not in env
    bare = {"CLAUDE_CODE_OAUTH_TOKEN": "oat", "CLAUDE_LIMIT_FALLBACK": "silent"}
    none = claude_client_for(bare, status_file=tmp_path / "s.json", sink=None, gemini_sink=None, clock=lambda: 0,
                             recall=False, media=True)
    assert none.gemini is None and "no GEMINI_API_KEY on claude: no photos or clips" in caplog.text


@pytest.mark.parametrize("reply_model,expected", [("gemini-3.1-pro-preview", 4096), ("gemini-2.5-flash", 200)])
def test_the_gemini_fallback_answers_at_its_own_models_cap(tmp_path, reply_model, expected):
    """v7.2 code review #6: the Claude reply's cap (200) on 3.1 Pro would be eaten by its thinking."""
    from tests.test_claude_client import FakeGemini
    gemini = FakeGemini()
    gemini.reply_model = reply_model
    c = ClaudeClient(reply_model="sonnet", background_model="haiku", config_dir=str(tmp_path),
                     status_file=tmp_path / "k.json", sink=None, fallback=gemini, fallback_think_cap=4096,
                     clock=lambda: 1_000_000 * 1000)
    c.status.muted_until = 1_000_000 + 600                    # at the limit: the fallback answers
    asyncio.run(c.reply("Ich: привіт", "S", 200, kind="private"))
    asyncio.run(c.complete("x", "S", 300, kind="summary"))   # the background keeps its own cap
    assert gemini.calls[0] == ("reply", ("Ich: привіт", "S", expected, "private"))
    assert gemini.calls[1][1][2] == 300
