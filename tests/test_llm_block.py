"""v5.13 — a block by Gemini's safety filter named: `blocked_reason` over canned responses, and the client's log line
and usage line on a blocked call (google-genai mocked; no network)."""

import asyncio
import logging
from types import SimpleNamespace

import pytest
from google.genai import types

from agents import llm as llm_mod
from agents.llm import BLOCK_FINISH, GeminiClient, blocked_reason

SECRET = "ТАЄМНИЙ ТЕКСТ"


def rating(category, probability="NEGLIGIBLE", blocked=None):
    return SimpleNamespace(category=SimpleNamespace(name=category), probability=SimpleNamespace(name=probability),
                           blocked=blocked)


def prompt_blocked(reason="SAFETY", ratings=None):
    return SimpleNamespace(text=None, candidates=[], usage_metadata=None,
                           prompt_feedback=SimpleNamespace(block_reason=SimpleNamespace(name=reason),
                                                           safety_ratings=ratings or []))


def answer_with(finish, ratings=None, text=None):
    return SimpleNamespace(text=text, usage_metadata=None, prompt_feedback=None,
                           candidates=[SimpleNamespace(content=SimpleNamespace(parts=[]),
                                                       finish_reason=SimpleNamespace(name=finish),
                                                       safety_ratings=ratings or [])])


@pytest.mark.parametrize("reason", ["SAFETY", "OTHER", "BLOCKLIST", "PROHIBITED_CONTENT", "JAILBREAK", "MODEL_ARMOR"])
def test_every_prompt_stage_reason_is_a_block(reason):
    stage, why, _ = blocked_reason(prompt_blocked(reason))
    assert (stage, why) == ("prompt", reason.lower())


@pytest.mark.parametrize("finish", sorted(BLOCK_FINISH))
def test_every_answer_stage_block_reason_is_a_block(finish):
    assert blocked_reason(answer_with(finish))[:2] == ("answer", finish.lower())


@pytest.mark.parametrize("finish", ["STOP", "MAX_TOKENS", "RECITATION", "OTHER", "LANGUAGE", "FINISH_REASON_UNSPECIFIED"])
def test_other_finish_reasons_are_not_a_block(finish):
    assert blocked_reason(answer_with(finish)) is None


def test_no_reason_no_fields_and_none_are_not_a_block():
    assert blocked_reason(prompt_blocked("BLOCKED_REASON_UNSPECIFIED")) is None
    assert blocked_reason(SimpleNamespace(text="", candidates=[])) is None
    assert blocked_reason(SimpleNamespace()) is None
    assert blocked_reason(None) is None


def test_the_real_sdk_types_are_read():
    resp = types.GenerateContentResponse(
        prompt_feedback=types.GenerateContentResponsePromptFeedback(
            block_reason=types.BlockedReason.PROHIBITED_CONTENT,
            safety_ratings=[types.SafetyRating(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                                               probability=types.HarmProbability.LOW),
                            types.SafetyRating(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                                               probability=types.HarmProbability.HIGH)]))
    assert blocked_reason(resp) == ("prompt", "prohibited_content", "sexually_explicit")
    answer = types.GenerateContentResponse(candidates=[types.Candidate(
        finish_reason=types.FinishReason.SAFETY,
        safety_ratings=[types.SafetyRating(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                                           probability=types.HarmProbability.MEDIUM, blocked=True)])])
    assert blocked_reason(answer) == ("answer", "safety", "dangerous_content")


def test_the_category_is_the_blocked_rating_else_the_most_probable():
    ratings = [rating("HARM_CATEGORY_HATE_SPEECH", "HIGH"), rating("HARM_CATEGORY_HARASSMENT", "LOW", blocked=True)]
    assert blocked_reason(answer_with("SAFETY", ratings))[2] == "harassment"
    ratings = [rating("HARM_CATEGORY_HATE_SPEECH", "LOW"), rating("HARM_CATEGORY_SEXUALLY_EXPLICIT", "MEDIUM")]
    assert blocked_reason(prompt_blocked("SAFETY", ratings))[2] == "sexually_explicit"
    assert blocked_reason(prompt_blocked("SAFETY"))[2] is None  # no ratings


class Models:
    def __init__(self, resp):
        self.resp = resp

    async def generate_content(self, model, contents, config):
        return self.resp


def client(monkeypatch, resp, reply_model=""):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv("GEMINI_REPLY_MODEL", reply_model)
    monkeypatch.setattr(llm_mod.genai, "Client", lambda: SimpleNamespace(aio=SimpleNamespace(models=Models(resp))))
    seen = []
    return GeminiClient(sink=lambda kind, model, meta, ok, **kw: seen.append((kind, model, ok, kw))), seen


@pytest.mark.parametrize("call", ["complete", "reply", "reply_pro", "think"])
def test_a_blocked_call_is_logged_by_stage_reason_and_category_never_a_text(monkeypatch, caplog, call):
    resp = prompt_blocked("SAFETY", [rating("HARM_CATEGORY_SEXUALLY_EXPLICIT", "HIGH")])
    llm, seen = client(monkeypatch, resp, "gemini-3.1-pro-preview" if call == "reply_pro" else "")
    caplog.set_level(logging.INFO, logger="agent.llm")
    if call == "complete":
        out = asyncio.run(llm.complete(f"Ich: {SECRET}", f"КАНОН {SECRET}", 200, "private"))
    elif call in ("reply", "reply_pro"):
        out = asyncio.run(llm.reply(f"Ich: {SECRET}", f"КАНОН {SECRET}", 200, "private"))
    else:
        out = asyncio.run(llm.think(f"Ich: {SECRET}", f"КАНОН {SECRET}", kind="ask"))
    assert out is None  # a block is still silence
    assert "gemini blocked: stage=prompt reason=safety category=sexually_explicit" in caplog.text
    assert SECRET not in caplog.text and "empty" not in caplog.text
    assert len(seen) == 1 and seen[0][2] is False and seen[0][3] == {"blocked": "prompt"}


def test_an_empty_answer_that_is_not_a_block_logs_and_reports_as_before(monkeypatch, caplog):
    llm, seen = client(monkeypatch, answer_with("STOP", text=""))
    caplog.set_level(logging.INFO, logger="agent.llm")
    assert asyncio.run(llm.complete("Ich: привіт", "КАНОН", 200, "reply")) is None
    assert "gemini returned an empty reply" in caplog.text and "blocked" not in caplog.text
    assert seen == [("reply", "gemini-2.5-flash", False, {})]  # a four-argument sink keeps working


def test_a_block_reaches_the_agents_usage_file_through_its_own_sink(tmp_path, monkeypatch):
    import json

    from tests.test_usage import KindLLM, make
    agent = make(tmp_path, KindLLM())
    llm, _ = client(monkeypatch, answer_with("PROHIBITED_CONTENT"))
    llm._sink = agent.record_usage  # the agent's real sink, as GeminiClient(sink=self.record_usage) wires it
    assert asyncio.run(llm.complete(f"Ich: {SECRET}", "КАНОН", 200, "reply")) is None
    agent.record_usage("reply", "gemini-2.5-flash", None, True)  # a plain call after it
    raw = agent.usage_file.read_text(encoding="utf-8")
    first, second = (json.loads(x) for x in raw.splitlines())
    assert (first["blocked"], first["ok"], second["blocked"]) == ("answer", False, None)
    assert SECRET not in raw
