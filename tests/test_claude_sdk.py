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
                                 "CLAUDE_CODE_SIMPLE", "CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR",
                                 "CLAUDE_CODE_MANAGED_SETTINGS_PATH", "CLAUDE_CODE_API_BASE_URL",
                                 "CLAUDE_CODE_HOST_CREDS_FILE"])  # review #10: the gaps
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
    assert o["strict_mcp_config"] is True and o["env"]["ENABLE_CLAUDEAI_MCP_SERVERS"] == "false"  # review #10
    assert o["permission_mode"] == "dontAsk" and {"Bash", "Read", "WebFetch", "Agent"} <= set(o["disallowed_tools"])
    assert o["system_prompt"] == "BRIEF" and o["model"] == "opus" and o["cwd"] == "/tmp/claude"
    assert o["env"] == {"CLAUDE_CODE_MAX_OUTPUT_TOKENS": "300", "CLAUDE_CODE_SKIP_PROMPT_HISTORY": "1",
                        "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1", "CLAUDE_CONFIG_DIR": "/tmp/claude",
                        "MAX_THINKING_TOKENS": "0", "CLAUDE_CODE_MAX_RETRIES": "2",
                        "ENABLE_CLAUDEAI_MCP_SERVERS": "false"}
    assert o["thinking"] == {"type": "disabled"}                     # review #1: thinking ate the cap
    assert o["extra_args"] == {"no-session-persistence": None}       # review #7: no session transcript
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
    ({"apiKeySource": "none", "tools": [], "mcp_servers": [{"name": "gmail"}]}, "mcp_servers=1"),  # review #10
])
def test_the_init_check_blocks_any_api_key_or_tool_for_good(tmp_path, data, why):
    sdk = FakeSDK(SystemMessage(subtype="init", data=data), result())
    r, usage = responder(tmp_path, sdk)
    assert run(r) is None and r.blocked == why
    assert usage[-1][3] is False                                # the call happened; it counts, never as ok
    assert json.loads((tmp_path / "claude.ratelimit.json").read_text())["auth"] == f"blocked: {why}"
    assert run(r) is None and len(sdk.calls) == 1               # no later call at all


@pytest.mark.parametrize("status,until", [("allowed_warning", 1_000_000 + 3600), ("rejected", 1_000_600)])
def test_a_limit_mutes_him_until_it_resets(tmp_path, status, until):
    """A rejection waits for the reset; a warning mutes for an hour and re-checks (review #9: a weekly window's
    warning would otherwise mute him for days)."""
    info = SimpleNamespace(status=status, resets_at=1_000_600, rate_limit_type="seven_day_opus", utilization=0.91)
    sdk = FakeSDK(INIT_OK, RateLimitEvent(rate_limit_info=info), result())
    r, _ = responder(tmp_path, sdk)
    run(r)
    saved = json.loads((tmp_path / "claude.ratelimit.json").read_text())
    assert (saved["status"], saved["muted_until"], saved["rate_limit_type"]) == (status, until, "seven_day_opus")
    assert set(saved) == {"status", "utilization", "resets_at", "rate_limit_type", "muted_until", "auth", "model",
                          "last_error", "updated_at"}           # no text, no token
    assert stat.S_IMODE(os.stat(tmp_path / "claude.ratelimit.json").st_mode) == 0o600
    assert run(r) is None and len(sdk.calls) == 1               # muted: no call before the reset
    r.clock = lambda: until * 1000
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



def test_the_clis_error_text_never_reaches_the_room(tmp_path):
    """Review #3: an assistant message with `error` set carries the CLI's own text, e.g. "API Error: …"."""
    err = AssistantMessage(content=[TextBlock(text="API Error: Claude's response exceeded the 300 output token maximum.")],
                           error="max_output_tokens")
    r, _ = responder(tmp_path, FakeSDK(INIT_OK, err, result(result=None, stop_reason="max_tokens")))
    assert run(r) is None
    ok = AssistantMessage(content=[TextBlock(text="Перше.")], error=None)
    more = AssistantMessage(content=[TextBlock(text="Друге.")], error=None)
    r, _ = responder(tmp_path, FakeSDK(INIT_OK, ok, more, result(result=None)))
    assert run(r).text == "Перше.\nДруге."                                   # parts joined, not glued



@pytest.mark.parametrize("info", [
    SimpleNamespace(status="rejected", resets_at=1_000_600, rate_limit_type="five_hour", utilization=1.0, raw={}),
    SimpleNamespace(status="allowed_warning", resets_at=None, rate_limit_type="five_hour", utilization=0.9,
                    raw={"isUsingOverage": True}),
])
def test_a_reply_billed_as_extra_usage_is_never_sent(tmp_path, info):
    """Review #4: a rejected window answered anyway is overage — dropped, counted, never ok."""
    r, usage = responder(tmp_path, FakeSDK(INIT_OK, RateLimitEvent(rate_limit_info=info), result()))
    assert run(r) is None and usage[-1][3] is False and r.muted()


def test_a_429_result_mutes_him(tmp_path):
    r, _ = responder(tmp_path, FakeSDK(INIT_OK, result(is_error=True, result=None, api_error_status=429)))
    assert run(r) is None and r.muted()



def test_a_hung_query_is_bounded_and_closed(tmp_path):
    """Review #11: the CLI's retries could hold a reply (and typing) for minutes."""
    closed = []

    class HangingSDK(FakeSDK):
        def query(self, *, prompt, options):
            self.calls.append((prompt, options))

            async def gen():
                try:
                    yield INIT_OK
                    await asyncio.sleep(3600)
                    yield result()
                finally:
                    closed.append(True)
            return gen()

    r, usage = responder(tmp_path, HangingSDK())
    r.timeout_s = 0.05
    assert run(r) is None and usage == [("reply", "opus", None, False, None)] and closed == [True]



def test_a_failing_call_is_on_the_card_until_one_succeeds(tmp_path):
    """Review #14: a dead token fails every call; the status says so, and a good call clears it."""
    sdk = FakeSDK(INIT_OK, result(is_error=True, result=None, subtype="success", api_error_status=401))
    r, _ = responder(tmp_path, sdk)
    run(r)
    assert json.loads((tmp_path / "claude.ratelimit.json").read_text())["last_error"] == "success (http 401)"
    sdk.messages = (INIT_OK, result())
    run(r)
    assert json.loads((tmp_path / "claude.ratelimit.json").read_text())["last_error"] is None



def test_the_agent_really_scrubs_its_environment(monkeypatch):
    """Review #10: the scrub is a layer of its own — with the startup check bypassed, the names still leave."""
    import agents.agent as agent_mod
    from agents.agent import Agent
    monkeypatch.setattr(agent_mod, "check_startup", lambda env: None)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oat")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    monkeypatch.setenv("CLAUDE_CODE_MANAGED_SETTINGS_PATH", "/etc/x.json")
    Agent(claude_cfg())
    assert "ANTHROPIC_API_KEY" not in os.environ and "CLAUDE_CODE_MANAGED_SETTINGS_PATH" not in os.environ



def test_a_restart_refreshes_the_card_and_keeps_a_running_mute(tmp_path):
    """Review #6: a fixed refusal no longer shows after a start; a mute still running survives a restart."""
    path = tmp_path / "claude.ratelimit.json"
    path.write_text(json.dumps({"status": "rejected", "resets_at": 1_000_900, "muted_until": 1_000_900,
                                "auth": "refused: forbidden variables set: ANTHROPIC_API_KEY",
                                "last_error": "timeout", "model": "old", "updated_at": 1}), encoding="utf-8")
    sdk = FakeSDK(INIT_OK, result())
    r, _ = responder(tmp_path, sdk)
    r.resume_status()                                                                         # at the agent's start
    saved = json.loads(path.read_text())
    assert (saved["auth"], saved["last_error"], saved["model"]) == (None, None, "opus")       # fresh
    assert saved["muted_until"] == 1_000_900 and r.muted()                                    # still running
    assert run(r) is None and sdk.calls == []                                                 # no call meanwhile
    path.write_text(json.dumps({"muted_until": 999_000, "auth": "oauth"}), encoding="utf-8")
    r2, _ = responder(tmp_path, sdk)
    r2.resume_status()
    assert not r2.muted()                                                                     # an old mute is gone
