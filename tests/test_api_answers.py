"""v7.4 (AGORA-251) — a companion's answers on GPT-6.1 Sol and Sonnet through their APIs: the request (her whole
instruction as the system, the transcript as the message, thinking on, the cap with its headroom, nothing stored),
the answer, the cut, a refusal of each kind, a failure and a timeout, the usage lines, the keys out of the
environment, and her private chat on each (the SDKs faked; nothing reaches the network; made-up lines only)."""

import asyncio
import json
import logging
import os
from types import SimpleNamespace

from agents.anthropic_api import AnthropicAnswers
from agents.api_answers import EMPTY_MESSAGE, THINK_HEADROOM
from agents.llm import LAST_BLOCK
from agents.openai_api import OpenAIAnswers
from agents.responder import LlmResponder
from agents.settings import BY_NAME
from agents.usage import api_usage_line, parse_lines
from tests.test_answer_switch import answers, choose
from tests.test_private_route import ASKED, her, marks
from tests.test_private_runtime import ms

SYSTEM = "Ти — Кіра. Канон."


class Sink:
    def __init__(self):
        self.calls = []

    def __call__(self, kind, model, usage, ok, blocked=None, latency_ms=None):
        self.calls.append({"kind": kind, "model": model, "usage": usage, "ok": ok, "blocked": blocked,
                           "latency_ms": latency_ms})


class OpenAIFake:
    """`client.responses.create`, canned."""

    def __init__(self, resp=None, error=None, delay=0.0):
        self.resp, self.error, self.delay, self.asked = resp, error, delay, []
        self.responses = self

    async def create(self, **kwargs):
        self.asked.append(kwargs)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return self.resp


def oai(text="Привіт!", status="completed", reason=None, refusal=False, cached=100):
    content = [SimpleNamespace(type="refusal", refusal="I can't")] if refusal else \
        [SimpleNamespace(type="output_text", text=text)]
    return SimpleNamespace(
        output=[SimpleNamespace(type="reasoning"), SimpleNamespace(type="message", content=content)],
        output_text="" if refusal else text, status=status,
        incomplete_details=SimpleNamespace(reason=reason) if reason else None,
        usage=SimpleNamespace(input_tokens=1200, input_tokens_details=SimpleNamespace(cached_tokens=cached),
                              output_tokens=340))


class AnthropicFake:
    """`client.messages.create`, canned."""

    def __init__(self, resp=None, error=None):
        self.resp, self.error, self.asked = resp, error, []
        self.messages = self

    async def create(self, **kwargs):
        self.asked.append(kwargs)
        if self.error:
            raise self.error
        return self.resp


def ant(text="Привіт!", stop="end_turn", category=None):
    content = [SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)]
    return SimpleNamespace(content=[] if stop == "refusal" else content, stop_reason=stop,
                           stop_details=SimpleNamespace(category=category) if stop == "refusal" else None,
                           usage=SimpleNamespace(input_tokens=300, cache_read_input_tokens=900,
                                                 cache_creation_input_tokens=0, output_tokens=410))


def run(coro):
    """(the answer, `LAST_BLOCK` as the call left it) — read inside the run, where the call set it."""
    async def inside():
        out = await coro
        return out, LAST_BLOCK.get()
    return asyncio.run(inside())


# --- GPT-6.1 Sol on OpenAI's Responses API -------------------------------------------------------------------------
def test_openai_sends_her_whole_instruction_thinking_on_and_nothing_stored():
    fake, sink = OpenAIFake(oai()), Sink()
    client = OpenAIAnswers("sk-test", effort="medium", client=fake, sink=sink)
    assert asyncio.run(client.reply("Ich: Привіт", SYSTEM, 4096, "private")) == ("Привіт!", "stop")
    asked = fake.asked[0]
    assert asked == {"model": "gpt-6.1-sol", "instructions": SYSTEM, "input": "Ich: Привіт",
                     "reasoning": {"effort": "medium"}, "max_output_tokens": 4096 + THINK_HEADROOM, "store": False}
    assert sink.calls[0]["ok"] and sink.calls[0]["usage"] == {"input_tokens": 1200, "cached_tokens": 100,
                                                              "output_tokens": 340}
    assert "sk-test" not in repr(client)


def test_openai_cut_refusal_filter_formula_failure_and_timeout(caplog):
    caplog.set_level(logging.WARNING)
    cut = OpenAIAnswers("k", client=OpenAIFake(oai("Довга думка.", "incomplete", "max_output_tokens")), sink=Sink())
    assert asyncio.run(cut.reply("x", SYSTEM, 100, "private")) == ("Довга думка.", "max_tokens")
    for resp, block in ((oai(refusal=True), ("refusal", "refusal", None)),
                        (oai("", "incomplete", "content_filter"), ("refusal", "content_filter", None))):
        sink = Sink()
        assert run(OpenAIAnswers("k", client=OpenAIFake(resp), sink=sink).reply("x", SYSTEM, 100, "private")) == \
            (None, block)
        assert sink.calls[0]["blocked"] == "refusal" and not sink.calls[0]["ok"]
    sink = Sink()
    out, block = run(OpenAIAnswers("k", client=OpenAIFake(oai("Я не можу виконати цей запит.")), sink=sink)
                     .reply("x", SYSTEM, 100, "private"))
    assert out is None and block[0] == "refusal" and sink.calls[0]["blocked"] == "refusal"
    sink = Sink()
    assert run(OpenAIAnswers("k", client=OpenAIFake(error=RuntimeError("secret text")), sink=sink)
               .reply("x", SYSTEM, 100, "private")) == (None, None)
    assert not sink.calls[0]["ok"] and "secret text" not in caplog.text
    slow = OpenAIAnswers("k", client=OpenAIFake(oai(), delay=1.0), sink=Sink(), timeout_s=0.01)
    assert run(slow.reply("x", SYSTEM, 100, "private")) == (None, None) and "timed out" in caplog.text


def test_her_first_line_with_nothing_before_it_still_sends_a_message():
    fake = OpenAIFake(oai())
    asyncio.run(OpenAIAnswers("k", client=fake, sink=None).reply("", SYSTEM, 100, "private_nudge"))
    assert fake.asked[0]["input"] == EMPTY_MESSAGE


# --- Sonnet on Anthropic's Messages API ----------------------------------------------------------------------------
def test_anthropic_sends_her_whole_instruction_with_adaptive_thinking_and_reads_the_answer():
    fake, sink = AnthropicFake(ant()), Sink()
    client = AnthropicAnswers("sk-ant-test", effort="medium", client=fake, sink=sink)
    assert asyncio.run(client.reply("Ich: Привіт", SYSTEM, 4096, "reply")) == ("Привіт!", "stop")
    assert fake.asked[0] == {"model": "claude-sonnet-5-5", "max_tokens": 4096 + THINK_HEADROOM, "system": SYSTEM,
                             "messages": [{"role": "user", "content": "Ich: Привіт"}],
                             "thinking": {"type": "adaptive"}, "output_config": {"effort": "medium"}}
    assert sink.calls[0]["usage"] == {"input_tokens": 1200, "cached_tokens": 900, "output_tokens": 410}
    assert "sk-ant-test" not in repr(client)


def test_anthropic_refusal_keeps_its_category_and_the_cut_is_max_tokens():
    sink = Sink()
    client = AnthropicAnswers("k", client=AnthropicFake(ant(stop="refusal", category="bio")), sink=sink)
    assert run(client.reply("x", SYSTEM, 100, "private")) == (None, ("refusal", "refusal", "bio"))
    assert sink.calls[0]["blocked"] == "refusal"
    cut = AnthropicAnswers("k", client=AnthropicFake(ant("Обірвана.", stop="max_tokens")), sink=Sink())
    assert asyncio.run(cut.reply("x", SYSTEM, 100, "private")) == ("Обірвана.", "max_tokens")


# --- usage lines ---------------------------------------------------------------------------------------------------
def test_the_api_usage_lines_are_valid_api_lines_with_no_text():
    for engine in ("openai", "anthropic"):
        line = api_usage_line("2026-11-11T18:00:00+02:00", "kira", "private", "gpt-6.1-sol", engine,
                              {"input_tokens": 1200, "cached_tokens": 100, "output_tokens": 340}, True, None, 4200)
        assert (line["engine"], line["billing"], line["prompt_tokens"], line["cache_read_tokens"],
                line["total_tokens"], line["latency_ms"]) == (engine, "api", 1200, 100, 1540, 4200)
        assert parse_lines([json.dumps(line)]) == ([line], 0)
    assert api_usage_line("2026-11-11T18:00:00+02:00", "kira", "private", "m", "other", None, False,
                          "refusal")["engine"] == "api"


def test_the_two_efforts_are_her_settings_never_off():
    assert BY_NAME["OPENAI_REASONING_EFFORT"].default == "medium" and BY_NAME["SONNET_EFFORT"].default == "medium"
    assert all("off" not in BY_NAME[n].choices and "none" not in BY_NAME[n].choices
               for n in ("OPENAI_REASONING_EFFORT", "SONNET_EFFORT"))


# --- the agent -----------------------------------------------------------------------------------------------------
def test_the_keys_leave_the_environment_at_her_start_and_their_models_join_her_switch(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-for-the-test")
    monkeypatch.setenv("SONNET_API_KEY", "sk-ant-for-the-test")
    agent = her(tmp_path, monkeypatch)
    assert "OPENAI_API_KEY" not in os.environ and "SONNET_API_KEY" not in os.environ
    assert agent.switch.available() == ["api-gemini-3.1pro", "api-gpt-6.1sol", "api-sonnet"]
    for name in ("api-gpt-6.1sol", "api-sonnet"):
        assert "for-the-test" not in repr(agent.switch.responders[name].llm)


def test_sonnet_answers_her_private_chat_its_usage_is_anthropics_and_its_refusal_goes_to_the_backup(
        tmp_path, monkeypatch):
    agent = her(tmp_path, monkeypatch)
    fake = AnthropicFake(ant("Від Sonnet."))
    agent.switch.responders["api-sonnet"] = LlmResponder(
        AnthropicAnswers("k", client=fake, sink=agent.record_api_usage("anthropic")))
    choose(agent, "api-sonnet")
    agent.private_line("Привіт", ms(17), "telegram", "tg:1")
    assert asyncio.run(agent.private_reply()) is True
    assert answers(agent)[-1]["by"] == "anthropic" and agent.llm.transcripts == []
    lines, bad = parse_lines(agent.usage_file.read_text(encoding="utf-8").splitlines())
    sonnet = [r for r in lines if r["engine"] == "anthropic"]
    assert bad == 0 and len(sonnet) == 1 and sonnet[0]["model"] == "claude-sonnet-5-5" and sonnet[0]["ok"]
    fake.resp = ant(stop="refusal", category="bio")
    agent.private_line(ASKED, ms(17, 1), "telegram", "tg:2")
    assert asyncio.run(agent.private_reply()) is True
    assert answers(agent)[-1]["by"] == "backup" and marks(agent)["tg:2"] == "blocked"
