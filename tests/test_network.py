"""v5.25 — her answer survives a bad network (the owner, 2026-11-04: «роби обидва»): the answer's call to Gemini is cut
at `REPLY_TIMEOUT_S` and tried once more; a send to Telegram that fails on the network is tried again after
`SEND_BACKOFF_S`, an HTTP error never is (fake clients; no network)."""

import asyncio
import logging
from types import SimpleNamespace

from agents import llm as llm_mod
from agents import telegram as tg_mod
from agents.llm import GeminiClient
from agents.telegram import Reply, TelegramBot
from tests.test_llm_block import answer_with


class Hanging:
    """Gemini whose first `hang` calls never answer in time; the next one answers."""

    def __init__(self, hang):
        self.hang, self.calls = hang, 0

    async def generate_content(self, model, contents, config):
        self.calls += 1
        if self.calls <= self.hang:
            await asyncio.sleep(5)
        return answer_with("STOP", text="Привіт!")


def pro(monkeypatch, models):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv("GEMINI_REPLY_MODEL", "gemini-3.1-pro-preview")
    monkeypatch.setattr(llm_mod.genai, "Client", lambda: SimpleNamespace(aio=SimpleNamespace(models=models)))
    monkeypatch.setattr(llm_mod, "REPLY_TIMEOUT_S", 0.05)
    seen = []
    return GeminiClient(sink=lambda kind, model, meta, ok, **kw: seen.append((kind, ok))), seen


def test_an_answer_that_hangs_is_asked_once_more(monkeypatch, caplog):
    llm, seen = pro(monkeypatch, models := Hanging(1))
    assert asyncio.run(llm.reply("Ich: привіт", "Ти — Кіра.", kind="private")) == ("Привіт!", "stop")
    assert models.calls == 2 and seen == [("private", True)]
    assert "gemini private timed out after" in caplog.text and "(try 1 of 2)" in caplog.text


def test_an_answer_that_hangs_twice_is_a_failure_never_a_third_call(monkeypatch, caplog):
    caplog.set_level(logging.ERROR)
    llm, seen = pro(monkeypatch, models := Hanging(5))
    assert asyncio.run(llm.reply("Ich: привіт", "Ти — Кіра.", kind="private")) is None
    assert models.calls == 2 and seen == [("private", False)] and "gemini reply failed: TimeoutError" in caplog.text


def test_a_thinking_call_that_hangs_is_asked_once_more_then_fails_never_holding_the_loop(monkeypatch, caplog):
    # 2026-11-10: Устина's session summary on Pro hung for three hours and held up her idle loop
    llm, seen = pro(monkeypatch, models := Hanging(1))
    monkeypatch.setattr(llm_mod, "THINK_TIMEOUT_S", 0.05)
    assert asyncio.run(llm.think("Ich: привіт", "Підсумуй.", kind="summary", level="low")) == "Привіт!"
    assert models.calls == 2 and seen == [("summary", True)] and "gemini summary timed out after" in caplog.text
    caplog.set_level(logging.ERROR)
    llm, seen = pro(monkeypatch, models := Hanging(5))
    assert asyncio.run(llm.think("Ich: привіт", "Підсумуй.", kind="summary")) is None
    assert models.calls == 2 and seen == [("summary", False)] and "gemini think failed: TimeoutError" in caplog.text


def bot(monkeypatch, replies):
    """A bot whose `_call` gives `replies` in turn and records each try's body."""
    monkeypatch.setattr(tg_mod, "SEND_BACKOFF_S", (0, 0))
    b, tries = TelegramBot("123:secret"), []

    async def call(method, timeout_s, json_body=None, data=None):
        tries.append((method, json_body, data))
        return replies[len(tries) - 1]

    b._call = call
    return b, tries


def test_a_send_that_fails_on_the_network_is_tried_again_until_it_goes(monkeypatch, caplog):
    b, tries = bot(monkeypatch, [Reply(False), Reply(False), Reply(True)])
    assert asyncio.run(b.send_message(1, "Привіт")) is True and len(tries) == 3
    assert "telegram: sendMessage tried again in 0 s (try 2)" in caplog.text and "Привіт" not in caplog.text
    b, tries = bot(monkeypatch, [Reply(False)] * 3)
    assert asyncio.run(b.send_message(1, "Привіт")) is False and len(tries) == 3          # never a fourth


def test_an_http_error_is_never_tried_again(monkeypatch):
    b, tries = bot(monkeypatch, [Reply(False, None, 400)])
    assert asyncio.run(b.send_message(1, "Привіт")) is False and len(tries) == 1


def test_a_voice_tried_again_is_sent_with_its_body_made_anew(monkeypatch):
    b, tries = bot(monkeypatch, [Reply(False), Reply(True)])
    assert asyncio.run(b.send_voice(1, b"OGG", 3)) is True
    assert [m for m, _, _ in tries] == ["sendVoice", "sendVoice"] and tries[0][2] is not tries[1][2]
