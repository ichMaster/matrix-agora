"""v7.1 — the Claude client: `GeminiClient`'s calls over the Agent SDK, against a fake SDK (no CLI, no network)."""

import asyncio
import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from agents.claude_sdk import (
    DISALLOWED_TOOLS,
    SEARCH_MAX_TURNS,
    VOICE_KINDS,
    WARN_MUTE_S,
    ClaudeClient,
    client_options,
)
from agents.llm import LAST_BLOCK
from agents.usage import sdk_usage_line


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


INIT_OK = SystemMessage(subtype="init", data={"apiKeySource": "none", "tools": []})
INIT_SEARCH = SystemMessage(subtype="init", data={"apiKeySource": "none", "tools": ["WebSearch"]})


def result(text="так, я тут.", **kw):
    return ResultMessage(**{"subtype": "success", "is_error": False, "result": text, "stop_reason": "end_turn",
                            "usage": {"input_tokens": 800, "output_tokens": 30}, "total_cost_usd": 0.002,
                            "model_usage": {"claude-sonnet-5-5": {}}, **kw})


class FakeSDK:
    """Each call takes the next script (a list of messages, or "hang"); the last script repeats."""

    def __init__(self, *scripts):
        self.scripts = list(scripts) or [[INIT_OK, result()]]
        self.calls = []
        self.prompt_files = []  # what the system prompt file held while the call ran, and its mode
        self.running = self.peak = 0

    def query(self, *, prompt, options):
        self.calls.append((prompt, options))
        script = self.scripts.pop(0) if len(self.scripts) > 1 else self.scripts[0]
        sp = options.system_prompt
        if isinstance(sp, dict):
            path = Path(sp["path"])
            self.prompt_files.append((path.read_text(encoding="utf-8"), stat.S_IMODE(os.stat(path).st_mode)))

        async def gen():
            self.running += 1
            self.peak = max(self.peak, self.running)
            try:
                if script == "hang":
                    await asyncio.sleep(3600)
                await asyncio.sleep(0.01)
                for m in script:
                    yield m
            finally:
                self.running -= 1
        return gen()


class FakeGemini:
    reply_model = "gemini-3.1-pro-preview"

    def __init__(self):
        self.calls = []

    async def complete(self, *a, **k):
        self.calls.append(("complete", a))
        return "gemini", "stop"

    async def reply(self, *a, **k):
        self.calls.append(("reply", a))
        return "gemini answer", "stop"

    async def think(self, *a, **k):
        self.calls.append(("think", k.get("model")))
        return "gemini thought"

    async def search(self, *a, **k):
        self.calls.append(("search", a))
        return "gemini sky"

    async def embed(self, texts, task="RETRIEVAL_DOCUMENT", kind="embed"):
        self.calls.append(("embed", task))
        return [[0.1] * 3 for _ in texts]


def client(tmp_path, sdk, *, now_s=1_000_000, limit_fallback="gemini", fallback=None, embedder=None, concurrency=2):
    usage = []
    c = ClaudeClient(reply_model="sonnet", background_model="haiku", config_dir=str(tmp_path / "cfg"),
                     status_file=tmp_path / "ustyna.ratelimit.json",
                     sink=lambda *a, **k: usage.append((a, k)), clock=lambda: now_s * 1000,
                     concurrency=concurrency, limit_fallback=limit_fallback, fallback=fallback, embedder=embedder,
                     query=sdk.query, options=lambda **kw: SimpleNamespace(**kw))
    return c, usage


def run(coro):
    return asyncio.run(coro)


# --- the options: one stateless call, nothing else ------------------------------------------------------------------
def test_the_options_have_no_tools_no_settings_no_thinking_and_the_calls_cap():
    o = client_options("/tmp/claude/prompts/x.md", model="haiku", max_output_tokens=300, config_dir="/tmp/claude")
    assert (o["tools"], o["allowed_tools"], o["setting_sources"], o["mcp_servers"], o["max_turns"]) == \
        ([], [], [], {}, 1)
    assert o["strict_mcp_config"] is True and o["permission_mode"] == "dontAsk"
    assert o["thinking"] == {"type": "disabled"} and o["disallowed_tools"] == DISALLOWED_TOOLS
    assert o["system_prompt"] == {"type": "file", "path": "/tmp/claude/prompts/x.md"}  # never on a command line
    assert o["env"]["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] == "300" and o["env"]["CLAUDE_CONFIG_DIR"] == "/tmp/claude"
    assert o["extra_args"] == {"no-session-persistence": None} and o["model"] == "haiku"
    assert client_options(None, model="haiku", max_output_tokens=0, config_dir="/c")["system_prompt"] is None


def test_a_search_has_the_web_search_alone_and_a_few_turns():
    o = client_options(None, model="haiku", max_output_tokens=800, config_dir="/c", toolset="search")
    assert o["tools"] == o["allowed_tools"] == ["WebSearch"] and o["max_turns"] == SEARCH_MAX_TURNS


# --- the model by the kind ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("kind", sorted(VOICE_KINDS))
def test_the_agents_voice_goes_to_the_reply_model(tmp_path, kind):
    sdk = FakeSDK()
    c, _ = client(tmp_path, sdk)
    run(c.complete("Ich: привіт", "BRIEF", 200, kind=kind))
    assert sdk.calls[-1][1].model == "sonnet"


@pytest.mark.parametrize("kind", ["summary", "day_memory", "plan", "today", "event", "mood", "topics", "facts",
                                  "talk_summary", "reading", "thought"])
def test_every_other_kind_goes_to_the_background_model_whatever_gemini_model_is_named(tmp_path, kind):
    sdk = FakeSDK()
    c, _ = client(tmp_path, sdk)
    run(c.complete("x", "S", 300, kind=kind, model="gemini-3.1-pro-preview"))
    run(c.think("x", "S", model="gemini-3.1-pro-preview", kind=kind, level="low"))
    assert [o.model for _, o in sdk.calls] == ["haiku", "haiku"]


def test_the_calls_return_what_geminis_do(tmp_path):
    sdk = FakeSDK([INIT_OK, result("перше.")], [INIT_OK, result("друге.", stop_reason="max_tokens")],
                  [INIT_OK, result("третє.")], [INIT_OK, result("четверте.")], [INIT_SEARCH, result("Луна в Тельці.")])
    c, _ = client(tmp_path, sdk)
    assert run(c.generate("t", "s", kind="summary")) == "перше."
    assert run(c.complete("t", "s", kind="today")) == ("друге.", "max_tokens")   # the cap cut it
    assert run(c.reply("t", "s", kind="private")) == ("третє.", "stop")
    assert run(c.think("t", "s", kind="digest_voice")) == "четверте."
    assert run(c.search("the moon today", 800, "sky")) == "Луна в Тельці."
    _, options = sdk.calls[-1]
    assert options.tools == ["WebSearch"] and options.system_prompt is None and options.model == "haiku"
    assert sdk.calls[0][0] == "t"  # the transcript is the prompt (stdin), never an argument


def test_the_system_prompt_is_a_private_file_for_the_call_alone(tmp_path):
    sdk = FakeSDK()
    c, _ = client(tmp_path, sdk)
    run(c.reply("Ich: привіт", "Ти — Устина. Пам'ять: …"))
    assert sdk.prompt_files == [("Ти — Устина. Пам'ять: …", 0o600)]
    assert list((tmp_path / "cfg" / "prompts").iterdir()) == []  # removed after the call


def test_embed_is_geminis_and_probe_is_none(tmp_path):
    gemini = FakeGemini()
    c, _ = client(tmp_path, FakeSDK(), embedder=gemini)
    assert run(c.embed(["a", "b"], task="RETRIEVAL_QUERY")) == [[0.1] * 3, [0.1] * 3]
    assert gemini.calls == [("embed", "RETRIEVAL_QUERY")]
    assert run(c.probe("t", "s", kind="scan_check")) is None
    c2, _ = client(tmp_path, FakeSDK())
    assert run(c2.embed(["a"])) is None


# --- bounded: the timeout, the second try, the processes at once ----------------------------------------------------
def test_a_hung_call_is_tried_once_more(tmp_path, monkeypatch):
    monkeypatch.setattr("agents.claude_sdk.THINK_TIMEOUT_S", 0.05)
    sdk = FakeSDK("hang", [INIT_OK, result("нарешті.")])
    c, usage = client(tmp_path, sdk)
    assert run(c.generate("t", "s", kind="summary")) == "нарешті."
    assert [a[3] for a, _ in usage] == [False, True]  # one usage line a try


def test_a_call_that_hangs_twice_is_none_and_the_card_says_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr("agents.claude_sdk.REPLY_TIMEOUT_S", 0.05)
    c, usage = client(tmp_path, FakeSDK("hang"))
    assert run(c.reply("t", "s")) is None and len(usage) == 2
    assert json.loads((tmp_path / "ustyna.ratelimit.json").read_text())["last_error"] == "timeout"


def test_at_most_concurrency_cli_processes_at_once(tmp_path):
    sdk = FakeSDK()
    c, _ = client(tmp_path, sdk, concurrency=2)

    async def many():
        return await asyncio.gather(*(c.generate("t", "s", kind="summary") for _ in range(6)))
    assert run(many()) == ["так, я тут."] * 6 and sdk.peak == 2


# --- failures -------------------------------------------------------------------------------------------------------
def test_an_error_result_is_none_and_named_on_the_card(tmp_path):
    c, usage = client(tmp_path, FakeSDK([INIT_OK, result(is_error=True, subtype="error_during_execution",
                                                         api_error_status=500)]))
    assert run(c.reply("t", "s")) is None and usage[-1][0][3] is False
    assert json.loads((tmp_path / "ustyna.ratelimit.json").read_text())["last_error"] == \
        "error_during_execution (http 500)"


def test_no_init_message_means_no_answer(tmp_path):
    c, _ = client(tmp_path, FakeSDK([result()]))
    assert run(c.reply("t", "s")) is None


def test_an_api_key_source_blocks_every_later_call(tmp_path):
    bad = SystemMessage(subtype="init", data={"apiKeySource": "ANTHROPIC_API_KEY", "tools": []})
    sdk = FakeSDK([bad, result()], [INIT_OK, result()])
    c, _ = client(tmp_path, sdk, limit_fallback="silent")
    assert run(c.reply("t", "s")) is None and c.blocked
    assert run(c.reply("t", "s")) is None and len(sdk.calls) == 1  # never called again
    assert json.loads((tmp_path / "ustyna.ratelimit.json").read_text())["auth"].startswith("blocked: ")


def test_an_extra_tool_refuses_that_call_only(tmp_path):
    extra = SystemMessage(subtype="init", data={"apiKeySource": "none", "tools": ["Bash"]})
    sdk = FakeSDK([extra, result()], [INIT_OK, result("далі.")])
    c, _ = client(tmp_path, sdk)
    assert run(c.reply("t", "s")) is None and c.blocked is None
    assert run(c.reply("t", "s")) == ("далі.", "stop")
    web = SystemMessage(subtype="init", data={"apiKeySource": "none", "tools": ["WebSearch"]})
    c2, _ = client(tmp_path, FakeSDK([web, result()]))
    assert run(c2.reply("t", "s")) is None  # the web only where a search asks for it


# --- the limit: decision 1 ------------------------------------------------------------------------------------------
def rejected(resets_at=1_003_600, **raw):
    return RateLimitEvent(rate_limit_info=SimpleNamespace(status="rejected", resets_at=resets_at, utilization=1.0,
                                                          rate_limit_type="five_hour", raw=raw))


def test_a_rejection_is_kept_and_the_call_goes_to_gemini_until_the_reset(tmp_path):
    gemini = FakeGemini()
    sdk = FakeSDK([INIT_OK, rejected(), result()])
    c, _ = client(tmp_path, sdk, fallback=gemini)
    assert run(c.reply("t", "s", kind="private")) == ("gemini answer", "stop")  # this very call, on Gemini
    status = json.loads((tmp_path / "ustyna.ratelimit.json").read_text())
    assert (status["status"], status["muted_until"], status["rate_limit_type"]) == ("rejected", 1_003_600, "five_hour")
    assert run(c.think("t", "s", model="sonnet", kind="talk_summary")) == "gemini thought"
    assert run(c.search("q", 800, "sky")) == "gemini sky"
    assert len(sdk.calls) == 1  # no Claude call while muted
    assert gemini.calls[1] == ("think", "gemini-3.1-pro-preview")  # a Claude alias never reaches Gemini


def test_silent_at_the_limit_makes_no_call_at_all(tmp_path):
    gemini = FakeGemini()
    sdk = FakeSDK([INIT_OK, rejected(), result()])
    c, _ = client(tmp_path, sdk, limit_fallback="silent", fallback=gemini)
    assert run(c.reply("t", "s")) is None and run(c.generate("t", "s", kind="today")) is None
    assert len(sdk.calls) == 1 and gemini.calls == []


def test_a_warning_mutes_for_an_hour_and_the_reset_brings_claude_back(tmp_path):
    now = [1_000_000]
    usage = []
    warn = RateLimitEvent(rate_limit_info=SimpleNamespace(status="allowed_warning", resets_at=1_500_000,
                                                          utilization=0.9, rate_limit_type="seven_day", raw={}))
    sdk = FakeSDK([INIT_OK, warn, result("ще можу.")], [INIT_OK, result("знову.")])
    c = ClaudeClient(reply_model="sonnet", background_model="haiku", config_dir=str(tmp_path / "cfg"),
                     status_file=tmp_path / "s.json", sink=lambda *a, **k: usage.append(a),
                     clock=lambda: now[0] * 1000, limit_fallback="silent", query=sdk.query,
                     options=lambda **kw: SimpleNamespace(**kw))
    assert run(c.reply("t", "s")) == ("ще можу.", "stop")  # the warned call itself is kept
    assert c.status.muted_until == 1_000_000 + WARN_MUTE_S and run(c.reply("t", "s")) is None
    now[0] += WARN_MUTE_S
    assert run(c.reply("t", "s")) == ("знову.", "stop")


def test_an_overage_answer_or_a_429_is_never_used(tmp_path):
    gemini = FakeGemini()
    over = RateLimitEvent(rate_limit_info=SimpleNamespace(status="allowed", resets_at=None, utilization=0.5,
                                                          rate_limit_type="overage", raw={"isUsingOverage": True}))
    c, usage = client(tmp_path, FakeSDK([INIT_OK, over, result("платна відповідь.")]), fallback=gemini)
    assert run(c.reply("t", "s")) == ("gemini answer", "stop") and usage[-1][0][3] is False
    c2, _ = client(tmp_path, FakeSDK([INIT_OK, result(is_error=True, api_error_status=429)]),
                   limit_fallback="silent")
    assert run(c2.reply("t", "s")) is None and c2.muted()


# --- a decline ------------------------------------------------------------------------------------------------------
def test_the_refusal_stop_is_a_decline_with_its_reason_never_its_text(tmp_path, caplog):
    c, usage = client(tmp_path, FakeSDK([INIT_OK, result("Вибач, не можу.", stop_reason="refusal")]))
    LAST_BLOCK.set(None)

    async def go():
        out = await c.reply("t", "s", kind="private")
        return out, LAST_BLOCK.get()
    out, block = run(go())
    assert out is None and block == ("refusal", "stop", None)
    args, kw = usage[-1]
    assert args[3] is False and kw["blocked"] == "refusal"
    assert "claude declined: reason=stop kind=private" in caplog.text and "не можу" not in caplog.text


def test_a_refusal_formula_in_an_answer_is_a_decline_but_not_in_a_summary(tmp_path):
    text = "Я не можу виконати цей запит."
    c, _ = client(tmp_path, FakeSDK([INIT_OK, result(text)]))

    async def go(call):
        out = await call
        return out, LAST_BLOCK.get()
    out, block = run(go(c.reply("t", "s")))
    assert out is None and block == ("refusal", "виконати цей запит", None)
    out, block = run(go(c.complete("t", "s", kind="summary")))
    assert out == (text, "stop") and block is None


# --- the usage line -------------------------------------------------------------------------------------------------
def test_one_usage_line_a_call_with_the_model_the_cli_ran_and_its_time(tmp_path):
    sdk = FakeSDK([INIT_OK, result(model_usage={"claude-haiku-5-5": {}})])
    c, usage = client(tmp_path, sdk)
    ticks = iter([10.0, 12.5])
    c._mono = lambda: next(ticks)
    run(c.generate("t", "s", kind="today"))
    (kind, model, tokens, ok, cost), kw = usage[-1]
    assert (kind, model, ok, kw) == ("today", "claude-haiku-5-5", True, {"latency_ms": 2500})
    line = sdk_usage_line("2026-11-10T12:00:00+02:00", "ustyna", kind, model, tokens, ok, cost, **kw)
    assert (line["engine"], line["billing"], line["prompt_tokens"], line["blocked"]) == \
        ("claude-sdk", "subscription", 800, None)
    assert sdk_usage_line("t", "a", "private", "m", None, False, blocked="refusal")["blocked"] == "refusal"
    assert sdk_usage_line("t", "a", "private", "m", None, False, blocked="prompt")["blocked"] is None
