"""Claude on the subscription (v4.4): the responder against a fake SDK, and every no-API-key layer."""

import asyncio
import json
import os
import re
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from agents.claude_sdk import (
    DISALLOWED_TOOLS,
    AuthRefused,
    ClaudeSdkResponder,
    check_startup,
    forbidden_vars,
    scrub,
    sdk_options,
)
from agents.responder import Turn


# --- fake SDK messages: the responder matches them by class name, as it does the real ones ---------------------------
class SystemMessage(SimpleNamespace):
    pass


class AssistantMessage(SimpleNamespace):
    pass


class TextBlock(SimpleNamespace):
    pass


class RateLimitEvent(SimpleNamespace):
    pass


class ResultMessage(SimpleNamespace):
    pass


INIT_OK = SystemMessage(subtype="init", data={"apiKeySource": "none", "tools": [], "model": "claude-opus"})


def result(text="Так, це працює.", **kw):
    return ResultMessage(**{"subtype": "success", "is_error": False, "result": text, "stop_reason": "end_turn",
                            "usage": {"input_tokens": 900, "output_tokens": 40}, "total_cost_usd": 0.01, **kw})


class FakeSDK:
    def __init__(self, *messages, raises=None):
        self.messages = messages
        self.raises = raises
        self.calls = []

    def query(self, *, prompt, options):
        self.calls.append((prompt, options))

        async def gen():
            if self.raises:
                raise self.raises
            for m in self.messages:
                yield m
        return gen()


def responder(tmp_path, sdk, now_s=1_000_000):
    usage = []
    r = ClaudeSdkResponder(model="opus", max_output_tokens=300, config_dir="/tmp/claude",
                           status_file=tmp_path / "claude.ratelimit.json",
                           usage_sink=lambda *a: usage.append(a), clock=lambda: now_s * 1000,
                           query=sdk.query, options=lambda **kw: SimpleNamespace(**kw))
    return r, usage


TURN = Turn([("Ich", "Клоде, котра година в Токіо?")], "BRIEF", 200)


def run(r, turn=TURN):
    return asyncio.run(r.respond(turn))


# --- layer 2: startup refuses; layer 3: the environment is scrubbed --------------------------------------------------
@pytest.mark.parametrize("var", ["ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
                                 "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY",
                                 "CLAUDE_CODE_SIMPLE"])
def test_startup_refuses_every_forbidden_variable_and_names_only_the_variable(var):
    secret = "sk-ant-should-never-be-printed"
    with pytest.raises(AuthRefused) as exc:
        check_startup({var: secret, "CLAUDE_CODE_OAUTH_TOKEN": "oat"})
    assert var in str(exc.value) and secret not in str(exc.value)


def test_startup_refuses_without_the_oauth_token():
    for env in ({}, {"CLAUDE_CODE_OAUTH_TOKEN": "  "}):
        with pytest.raises(AuthRefused, match="CLAUDE_CODE_OAUTH_TOKEN"):
            check_startup(env)
    check_startup({"CLAUDE_CODE_OAUTH_TOKEN": "oat", "CLAUDE_MODEL": "opus"})  # the subscription alone passes


def test_the_forbidden_names_leave_the_environment():
    env = {"ANTHROPIC_API_KEY": "x", "CLAUDE_CODE_USE_VERTEX": "1", "CLAUDE_CODE_OAUTH_TOKEN": "oat", "HOME": "/h"}
    assert scrub(env) == ["ANTHROPIC_API_KEY", "CLAUDE_CODE_USE_VERTEX"]
    assert forbidden_vars(env) == [] and env == {"CLAUDE_CODE_OAUTH_TOKEN": "oat", "HOME": "/h"}


# --- the options: a chat turn, nothing else --------------------------------------------------------------------------
def test_the_options_turn_off_tools_settings_and_memory():
    o = sdk_options("BRIEF", model="opus", max_output_tokens=300, config_dir="/tmp/claude")
    assert (o["tools"], o["setting_sources"], o["mcp_servers"], o["max_turns"]) == ([], [], {}, 1)
    assert o["permission_mode"] == "dontAsk" and {"Bash", "Read", "WebFetch", "Agent"} <= set(o["disallowed_tools"])
    assert o["system_prompt"] == "BRIEF" and o["model"] == "opus" and o["cwd"] == "/tmp/claude"
    assert o["env"] == {"CLAUDE_CODE_MAX_OUTPUT_TOKENS": "300", "CLAUDE_CODE_SKIP_PROMPT_HISTORY": "1",
                        "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1", "CLAUDE_CONFIG_DIR": "/tmp/claude",
                        "MAX_THINKING_TOKENS": "0"}
    assert o["thinking"] == {"type": "disabled"}                     # review #1: thinking ate the cap
    uncapped = sdk_options("B", model="opus", max_output_tokens=0, config_dir="/c")
    assert "CLAUDE_CODE_MAX_OUTPUT_TOKENS" not in uncapped["env"]    # 0 = no cap (the owner, 2026-10-11)
    assert not any(k.startswith(("ANTHROPIC_", "CLAUDE_CODE_USE_")) for k in o["env"])
    assert "effort" not in o and sdk_options("B", model="opus", max_output_tokens=1, config_dir="/c",
                                             effort="high")["effort"] == "high"
    assert "Bash" in DISALLOWED_TOOLS


# --- the responder -------------------------------------------------------------------------------------------------
def test_a_reply_is_the_result_text_and_a_subscription_usage_row(tmp_path):
    sdk = FakeSDK(INIT_OK, AssistantMessage(content=[TextBlock(text="Так, це працює.")]), result())
    r, usage = responder(tmp_path, sdk)
    reply = run(r)
    assert (reply.text, reply.finish) == ("Так, це працює.", "stop")
    prompt, options = sdk.calls[0]
    assert prompt == "Ich: Клоде, котра година в Токіо?" and options.system_prompt == "BRIEF" and options.tools == []
    assert usage == [("reply", "opus", {"input_tokens": 900, "output_tokens": 40}, True, 0.01)]
    assert json.loads((tmp_path / "claude.ratelimit.json").read_text())["auth"] == "oauth"


def test_an_error_result_or_a_failed_query_is_silence(tmp_path):
    r, usage = responder(tmp_path, FakeSDK(INIT_OK, result(is_error=True, result=None, api_error_status=529)))
    assert run(r) is None and usage[-1][3] is False
    r, usage = responder(tmp_path, FakeSDK(raises=RuntimeError("cli died")))
    assert run(r) is None and usage == [("reply", "opus", None, False, None)]


def test_a_reply_cut_by_the_cap_reports_max_tokens(tmp_path):
    r, _ = responder(tmp_path, FakeSDK(INIT_OK, result("Перше речення. Друге обірв", stop_reason="max_tokens")))
    assert run(r).finish == "max_tokens"


@pytest.mark.parametrize("data,why", [
    ({"apiKeySource": "ANTHROPIC_API_KEY", "tools": []}, "apiKeySource='ANTHROPIC_API_KEY'"),
    ({"apiKeySource": "apiKeyHelper", "tools": []}, "apiKeySource='apiKeyHelper'"),
    ({"tools": []}, "apiKeySource=None"),                      # not reported: fail closed
    ({"apiKeySource": "none", "tools": ["Bash"]}, "tools=Bash"),
])
def test_the_init_check_blocks_any_api_key_or_tool_for_good(tmp_path, data, why):
    sdk = FakeSDK(SystemMessage(subtype="init", data=data), result())
    r, usage = responder(tmp_path, sdk)
    assert run(r) is None and r.blocked == why
    assert usage[-1][3] is False                                # the call happened; it counts, never as ok
    assert json.loads((tmp_path / "claude.ratelimit.json").read_text())["auth"] == f"blocked: {why}"
    assert run(r) is None and len(sdk.calls) == 1               # no later call at all


@pytest.mark.parametrize("status", ["allowed_warning", "rejected"])
def test_a_limit_mutes_him_until_it_resets(tmp_path, status):
    info = SimpleNamespace(status=status, resets_at=1_000_600, rate_limit_type="seven_day_opus", utilization=0.91)
    sdk = FakeSDK(INIT_OK, RateLimitEvent(rate_limit_info=info), result())
    r, _ = responder(tmp_path, sdk)
    run(r)
    saved = json.loads((tmp_path / "claude.ratelimit.json").read_text())
    assert (saved["status"], saved["muted_until"], saved["rate_limit_type"]) == (status, 1_000_600, "seven_day_opus")
    assert set(saved) == {"status", "utilization", "resets_at", "rate_limit_type", "muted_until", "auth", "model",
                          "updated_at"}                         # no text, no token
    assert stat.S_IMODE(os.stat(tmp_path / "claude.ratelimit.json").st_mode) == 0o600
    assert run(r) is None and len(sdk.calls) == 1               # muted: no call before the reset
    r.clock = lambda: 1_000_600 * 1000
    run(r)
    assert len(sdk.calls) == 2                                  # the window reset


def test_an_allowed_event_lifts_the_mute(tmp_path):
    warn = SimpleNamespace(status="allowed_warning", resets_at=None, rate_limit_type="five_hour", utilization=0.8)
    r, _ = responder(tmp_path, FakeSDK(INIT_OK, RateLimitEvent(rate_limit_info=warn), result()))
    run(r)
    assert r.muted() and r.status.muted_until == 1_000_000 + 3600       # no reset time: an hour
    r._rate_limit(SimpleNamespace(status="allowed", resets_at=None, rate_limit_type="five_hour", utilization=0.1))
    assert not r.muted()


# --- layer 6: no API client in the code ------------------------------------------------------------------------------
def test_nothing_imports_anthropic_and_only_the_responder_imports_the_sdk():
    for path in Path("agents").rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        assert not re.search(r"^\s*(import|from)\s+anthropic\b", src, re.MULTILINE), path
        if path.name != "claude_sdk.py":
            assert "claude_agent_sdk" not in src, path


# --- the agent: refuses first, scrubs, builds no Gemini client --------------------------------------------------------
def claude_cfg():
    from agents.config import AgentConfig
    from tests.test_first_sync import CFG
    return AgentConfig(**{**CFG.__dict__, "name": "Клод", "user_id": "@claude:agora.lan", "type": "assistant",
                          "engine": "claude-sdk", "capabilities": frozenset(), "canon": ""})


def test_the_agent_refuses_to_start_with_a_forbidden_variable(monkeypatch):
    from agents.agent import Agent
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oat")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    with pytest.raises(AuthRefused, match="ANTHROPIC_API_KEY"):
        Agent(claude_cfg())


def test_the_agent_starts_without_a_gemini_key_and_scrubs_its_environment(monkeypatch):
    from agents.agent import Agent
    for k in [k for k in os.environ if k.startswith(("ANTHROPIC_", "CLAUDE_CODE_USE_"))]:
        monkeypatch.delenv(k)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oat")
    agent = Agent(claude_cfg())
    assert isinstance(agent.responder, ClaudeSdkResponder) and agent.llm is None
    assert agent.responder.model == "opus" and agent.responder.max_output_tokens == 0


def test_the_agent_writes_a_subscription_usage_line(tmp_path, monkeypatch):
    from agents.agent import Agent
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oat")
    agent = Agent(claude_cfg())
    agent.memory_file = tmp_path / "claude.memory.md"
    agent.record_sdk_usage("reply", "opus", {"input_tokens": 10, "output_tokens": 2}, True, 0.001)
    line = json.loads(agent.usage_file.read_text().splitlines()[-1])
    assert (line["engine"], line["billing"], line["total_tokens"]) == ("claude-sdk", "subscription", 12)



def test_without_an_init_message_he_stays_silent(tmp_path):
    """Review #2: the auth source unverified — the reply is not sent (the call is counted, never as ok)."""
    r, usage = responder(tmp_path, FakeSDK(result()))
    assert run(r) is None and usage[-1][3] is False                          # counted, never as ok
    assert not r.blocked                                                     # one unchecked call, not a block


def test_an_init_subclass_with_an_api_key_is_still_caught_and_the_stream_closed(tmp_path):
    """Review #2: init is matched by its subtype, whatever the class; a bad init stops reading at once."""
    class TaskStartedMessage(SystemMessage):
        pass
    closed = []

    class ClosingSDK(FakeSDK):
        def query(self, *, prompt, options):
            self.calls.append((prompt, options))

            async def gen():
                try:
                    yield TaskStartedMessage(subtype="init", data={"apiKeySource": "ANTHROPIC_API_KEY", "tools": []})
                    yield AssistantMessage(content=[TextBlock(text="billed to a key")])
                    yield result("billed to a key")
                finally:
                    closed.append(True)
            return gen()

    r, _ = responder(tmp_path, ClosingSDK())
    assert run(r) is None and r.blocked == "apiKeySource='ANTHROPIC_API_KEY'" and closed == [True]
