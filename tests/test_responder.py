"""The reply engine seam and reply length (v4.1): Responder, the finish reason, trimming to a sentence."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import agents.llm as llm_mod
from agents.agent import Agent
from agents.responder import GeminiResponder, Reply, Turn, responder_for, trim_to_sentence
from tests.test_first_sync import CFG


@pytest.mark.parametrize("text,kept", [
    ("Перше речення. Друге обірва", "Перше речення."),
    ("Так! А ще я думаю, що", "Так!"),
    ("Справді? Ну… а може", "Справді? Ну…"),
    ("Він сказав «так». А потім", "Він сказав «так»."),
    ("Ціле речення.", "Ціле речення."),
    ("без жодної крапки і ще", None),
    ("версія 2.5 була б", None),  # a dot inside a number is no sentence end
])
def test_trim_to_sentence(text, kept):
    assert trim_to_sentence(text) == kept


class CompleteLLM:
    def __init__(self, text, finish="stop"):
        self.out = (text, finish)
        self.calls = []

    async def complete(self, transcript, system_instruction, max_output_tokens=400, kind="reply"):
        self.calls.append((transcript, system_instruction, max_output_tokens, kind))
        return self.out

    async def generate(self, transcript, system_instruction, max_output_tokens=400, kind="reply"):
        self.calls.append((transcript, system_instruction, max_output_tokens, kind))
        return self.out[0]


class GenerateOnlyLLM:
    async def generate(self, transcript, system_instruction, max_output_tokens=400, kind="reply"):
        return "текст"


def test_gemini_responder_keeps_the_transcript_contract_and_reports_the_finish():
    llm = CompleteLLM("відповідь", "max_tokens")
    reply = asyncio.run(GeminiResponder(llm).respond(Turn([("Ich", "привіт"), ("Бруно", "о")], "SYS", 200)))
    assert reply == Reply("відповідь", "max_tokens")
    assert llm.calls == [("Ich: привіт\nБруно: о", "SYS", 200, "reply")]


def test_a_generate_only_seam_is_never_cut():
    reply = asyncio.run(GeminiResponder(GenerateOnlyLLM()).respond(Turn([], "SYS", 200)))
    assert reply == Reply("текст", "stop")


def test_only_the_gemini_engine_exists_in_v4_1():
    assert isinstance(responder_for("gemini", GenerateOnlyLLM()), GeminiResponder)
    with pytest.raises(ValueError):
        responder_for("claude-sdk", GenerateOnlyLLM())


@pytest.mark.parametrize("reason,finish", [("MAX_TOKENS", "max_tokens"), ("STOP", "stop"), (None, "stop")])
def test_the_gemini_finish_reason_is_mapped(monkeypatch, reason, finish):
    resp = SimpleNamespace(text="текст", usage_metadata=None,
                           candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name=reason) if reason else None)])
    models = SimpleNamespace(generate_content=AsyncMock(return_value=resp))
    monkeypatch.setattr(llm_mod.genai, "Client", lambda: SimpleNamespace(aio=SimpleNamespace(models=models)))
    client = llm_mod.GeminiClient()
    assert asyncio.run(client.complete("c", "s")) == ("текст", finish)
    assert asyncio.run(client.generate("c", "s")) == "текст"


def _agent(llm):
    agent = Agent(CFG, llm=llm)
    agent.client = SimpleNamespace(room_send=AsyncMock(), room_typing=AsyncMock())
    agent.ensure_today = AsyncMock()
    return agent


def test_a_cut_reply_is_sent_up_to_its_last_sentence():
    agent = _agent(CompleteLLM("Перше речення. Друге обірва", "max_tokens"))
    asyncio.run(agent.reply("!room"))
    assert agent.client.room_send.await_args.kwargs["content"]["body"] == "Перше речення."


def test_a_reply_cut_before_any_sentence_ends_is_silence():
    agent = _agent(CompleteLLM("без жодної крапки і ще", "max_tokens"))
    asyncio.run(agent.reply("!room"))
    agent.client.room_send.assert_not_awaited()


def test_an_uncut_reply_is_sent_whole():
    agent = _agent(CompleteLLM("без крапки, але повна", "stop"))
    asyncio.run(agent.reply("!room"))
    assert agent.client.room_send.await_args.kwargs["content"]["body"] == "без крапки, але повна"


def test_reply_max_tokens_reaches_the_reply_call_and_other_kinds_keep_their_caps(monkeypatch):
    monkeypatch.setenv("REPLY_MAX_TOKENS", "123")
    llm = CompleteLLM("Так.")
    agent = _agent(llm)
    asyncio.run(agent.reply("!room"))
    assert llm.calls[-1][2:] == (123, "reply")
    agent.session = [("Ich", "привіт")]
    asyncio.run(agent.summarize())
    assert llm.calls[-1][2:] == (agent.summary_max_words * 3, "summary")


def test_the_defaults_are_chat_sized(monkeypatch):
    monkeypatch.delenv("REPLY_MAX_TOKENS", raising=False)
    monkeypatch.delenv("HISTORY_N", raising=False)
    agent = Agent(CFG, llm=GenerateOnlyLLM())
    assert agent.reply_max_tokens == 200 and agent.history_n == 40


def test_the_common_canon_asks_for_one_to_three_sentences():
    from pathlib import Path
    assert "Пиши 1–3 речення" in Path("agents/canon/common.md").read_text(encoding="utf-8")
