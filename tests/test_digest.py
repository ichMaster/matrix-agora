"""v5.1 — Hermes's digest core: the schedule, the collection, the length, the prompts, «підсумок», the state, and the
Pro call with thinking (Gemini mocked)."""

import asyncio
import json
import os
import stat
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

import agents.llm as llm_mod
from agents.digest import (
    ASK_DAYS,
    CHAT_BRIEF,
    DIGEST_BRIEF,
    NOTHING_NEW,
    DigestState,
    Message,
    ask_window,
    asks_digest,
    chat_request,
    collect,
    dialogue_lines,
    digest_due,
    digest_lines,
    digest_request,
    load_digest_state,
    period,
    plural_messages,
    record_sent,
    save_digest_state,
    since_point,
    target_chars,
    text_header,
    today_count,
    trim_digest,
)
from agents.logic import BANNED_RE
from agents.nudge import parse_hours

TZ = "Europe/Kyiv"
H = 3_600_000
EVERY = 4 * H


def ms(day: int, hour: int, minute: int = 0) -> int:
    return int(datetime(2026, 10, day, hour, minute, tzinfo=ZoneInfo(TZ)).timestamp() * 1000)


# --- the schedule -----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("hour,had_one,new,expect", [
    (12, False, 5, True),                   # the first run: at once, with enough talk
    (12, False, 4, False),                  # below the minimum
    (12, True, 5, True),                    # exactly the interval since the last one
    (8, False, 50, False),                  # before 09:00
    (23, False, 50, False),                 # the end hour is exclusive
    (22, False, 50, True),
])
def test_digest_due(hour, had_one, new, expect):
    now = ms(17, hour)
    last_ms = now - EVERY if had_one else None
    assert digest_due(now, hour, last_ms, EVERY, parse_hours("09-23"), new, 5) is expect


def test_digest_due_waits_for_the_interval_and_wraps_past_midnight():
    hours = parse_hours("09-23")
    assert not digest_due(ms(17, 14), 14, ms(17, 14) - EVERY + 1, EVERY, hours, 50, 5)
    assert digest_due(ms(17, 14), 14, ms(17, 14) - EVERY, EVERY, hours, 50, 5)
    wrap = parse_hours("20-02")
    assert digest_due(ms(17, 1), 1, None, EVERY, wrap, 5, 5)
    assert not digest_due(ms(17, 3), 3, None, EVERY, wrap, 5, 5)
    assert not digest_due(ms(17, 12), 12, None, EVERY, hours, 0, 0)  # never an empty digest


# --- the collection -----------------------------------------------------------------------------------------------
def msg(i: int, t: int, text: str = "слово", sender: str = "@ada:agora.lan") -> Message:
    return Message(f"$e{i}", sender, t, text)


def test_since_the_point_oldest_first_without_purrs():
    room = [msg(5, ms(17, 14), "п'ять"), msg(4, ms(17, 13), "Мрррр."), msg(3, ms(17, 12), "три"),
            msg(2, ms(17, 11), "два"), msg(1, ms(17, 10), "один")]
    state = DigestState(point_event="$e2", point_ts=ms(17, 11))
    assert [m.text for m in since_point(room, state, ms(17, 15), EVERY)] == ["три", "п'ять"]


def test_a_vanished_point_stops_at_its_time_and_the_first_run_takes_the_last_interval():
    room = [msg(3, ms(17, 14)), msg(2, ms(17, 11)), msg(1, ms(17, 9))]
    gone = DigestState(point_event="$gone", point_ts=ms(17, 10))
    assert [m.event_id for m in since_point(room, gone, ms(17, 15), EVERY)] == ["$e2", "$e3"]
    assert [m.event_id for m in since_point(room, DigestState(), ms(17, 15), EVERY)] == ["$e2", "$e3"]


def test_the_collection_is_bounded_to_the_newest():
    room = [msg(i, ms(17, 12) - i) for i in range(10)]
    assert [m.event_id for m in collect(room, limit=3)] == ["$e2", "$e1", "$e0"]


def test_the_ask_window_reads_the_last_days():
    assert ask_window(ms(17, 12)) == ms(17, 12) - ASK_DAYS * 86_400_000


# --- lines, period, header, length ---------------------------------------------------------------------------------
NAMES = {"@ich:agora.lan": "Ich", "@ada:agora.lan": "Ада"}


def test_the_lines_name_the_owner_ich_in_local_time():
    room = [msg(1, ms(17, 10, 5), "привіт", "@ich:agora.lan"), msg(2, ms(17, 10, 7), "вітаю")]
    assert digest_lines(room, NAMES, TZ) == ["10:05 Ich: привіт", "10:07 Ада: вітаю"]
    assert digest_lines(room, NAMES, TZ, with_date=True)[0] == "17.10 10:05 Ich: привіт"
    assert period(room, TZ) == "10:05–10:07"
    assert period([msg(1, ms(16, 22, 10)), msg(2, ms(17, 9, 5))], TZ) == "16.10 22:10 – 17.10 09:05"
    assert text_header(room, TZ) == "Агора, 10:05–10:07 · 2 повідомлення"


@pytest.mark.parametrize("n,word", [(1, "повідомлення"), (3, "повідомлення"), (5, "повідомлень"),
                                    (11, "повідомлень"), (12, "повідомлень"), (21, "повідомлення"),
                                    (24, "повідомлення"), (25, "повідомлень")])
def test_plural(n, word):
    assert plural_messages(n) == f"{n} {word}"


def test_the_length_follows_the_talk_up_to_the_cap():
    assert target_chars(5, 1500) == 500        # a few lines: about half a minute
    assert target_chars(30, 1500) == 1500      # a lively stretch: the cap
    assert target_chars(100, 1500) == 1500


def test_an_overlong_digest_is_cut_to_its_last_full_sentence():
    text = "Перше речення. Друге речення! Третє речення, дуже довге і нескінченне"
    assert trim_digest(text, 1500) == text
    assert trim_digest(text, 40) == "Перше речення. Друге речення!"
    assert trim_digest("без крапки взагалі і довге", 10) == ""


@pytest.mark.parametrize("text,expect", [
    ("Підсумок!", True), ("дай підсумок", True), ("Гермесе, підсумок", True), ("підсумуй", True),
    ("Що Бруно казав учора про подорож і чи був там якийсь підсумок?", False),
    ("привіт", False), ("", False),
])
def test_asks_digest(text, expect):
    assert asks_digest(text) is expect


# --- the prompts --------------------------------------------------------------------------------------------------
def test_the_briefs_never_hold_a_banned_word_and_name_the_members():
    for brief in (DIGEST_BRIEF, CHAT_BRIEF, NOTHING_NEW):
        assert not BANNED_RE.search(brief), brief
    system, contents = digest_request("КАНОН", ["10:05 Ада: так"], "10:05–10:07", 2, 380, 1500,
                                      ["Ich", "Ада", "Бруно"])
    assert system.startswith("КАНОН\n\n") and "Ich, Ада, Бруно" in system and "близько 380 знаків" in system
    assert "не обговорюй, хто вони і яка їхня природа" in system and contents == "10:05 Ада: так"
    system, contents = chat_request("КАНОН", ["17.10 10:05 Ада: так"], ["Ich: привіт", "Гермес: вітаю"],
                                    "що казала Ада?", ["Ich", "Ада"])
    assert "не обговорюй, хто вони і яка їхня природа" in system and "це розмова, а не підсумок" in system
    assert contents == ("Агора за останні дні:\n17.10 10:05 Ада: так\n\nВаша недавня розмова:\nIch: привіт\n"
                        "Гермес: вітаю\n\nIch: що казала Ада?")
    assert chat_request("К", [], [], "привіт", ["Ich"])[1] == "Агора за останні дні:\n(тиша)\n\nIch: привіт"
    long = Message("$d", "@hermes:agora.lan", 1, "в" * 2000)
    assert dialogue_lines([long], {"@hermes:agora.lan": "Гермес"}) == ["Гермес: " + "в" * 1500 + "…"]


# --- the state ----------------------------------------------------------------------------------------------------
def test_the_state_is_private_atomic_and_a_corrupt_one_starts_fresh(tmp_path):
    path = tmp_path / "hermes.digest.json"
    assert load_digest_state(path) == DigestState()
    state = DigestState(room="!dm", point_event="$e9", point_ts=5, last_ms=7, day="2026-10-17", count=2)
    save_digest_state(path, state)
    assert load_digest_state(path) == state
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600 and not path.with_suffix(".json.tmp").exists()
    assert set(json.loads(path.read_text())) == {"room", "point_event", "point_ts", "last_ms", "day", "count"}
    path.write_text("{not json")
    assert load_digest_state(path) == DigestState()


def test_a_sent_digest_moves_the_point_and_counts_the_day():
    s = record_sent(DigestState(room="!dm", day="2026-10-16", count=3), 100, "2026-10-17", msg(9, 50))
    assert (s.room, s.point_event, s.point_ts, s.last_ms, s.day, s.count) == ("!dm", "$e9", 50, 100, "2026-10-17", 1)
    s = record_sent(s, 200, "2026-10-17", None)  # nothing collected (never sent so) keeps the point
    assert (s.point_event, s.count, today_count(s, "2026-10-17"), today_count(s, "2026-10-18")) == ("$e9", 2, 2, 0)


# --- the Pro call with thinking ------------------------------------------------------------------------------------
def thinking_response(*parts):
    return SimpleNamespace(
        text="".join(p.text for p in parts if not getattr(p, "thought", False)), usage_metadata="META",
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=list(parts)), finish_reason=None)])


class Models:
    def __init__(self, resp=None, fail=False):
        self.resp, self.fail, self.seen = resp, fail, {}

    async def generate_content(self, **kw):
        self.seen.update(kw)
        if self.fail:
            raise RuntimeError("boom")
        return self.resp


def client_with(monkeypatch, models):
    monkeypatch.setattr(llm_mod.genai, "Client", lambda: SimpleNamespace(aio=SimpleNamespace(models=models)))
    usage = []
    return llm_mod.GeminiClient(sink=lambda *a: usage.append(a)), usage


def test_think_keeps_thinking_on_and_returns_only_the_answer(monkeypatch):
    models = Models(thinking_response(SimpleNamespace(text="я думаю…", thought=True),
                                      SimpleNamespace(text=" Вісті з Агори. ", thought=None)))
    client, usage = client_with(monkeypatch, models)
    out = asyncio.run(client.think("рядки", "канон"))
    assert out == "Вісті з Агори."
    cfg = models.seen["config"]
    assert models.seen["model"] == llm_mod.DIGEST_MODEL == "gemini-3.1-pro-preview"
    assert cfg.thinking_config.thinking_budget is None and cfg.thinking_config.include_thoughts is False
    assert cfg.max_output_tokens == llm_mod.THINK_MAX_TOKENS
    assert usage == [("digest_voice", "gemini-3.1-pro-preview", "META", True)]


def test_think_reports_a_failure_or_an_empty_answer_under_its_model(monkeypatch):
    client, usage = client_with(monkeypatch, Models(fail=True))
    assert asyncio.run(client.think("рядки", "канон", kind="ask")) is None
    assert usage == [("ask", llm_mod.DIGEST_MODEL, None, False)]
    client, usage = client_with(monkeypatch, Models(thinking_response(SimpleNamespace(text="лише думка", thought=True))))
    assert asyncio.run(client.think("рядки", "канон")) is None
    assert usage == [("digest_voice", llm_mod.DIGEST_MODEL, "META", False)]


def test_think_can_bound_the_thinking_for_a_chat(monkeypatch):
    """The chat with the owner thinks `low` (seconds, not a minute); the digest keeps the model's default."""
    from google.genai import types
    models = Models(thinking_response(SimpleNamespace(text="Вітаю.", thought=None)))
    client, _ = client_with(monkeypatch, models)
    assert asyncio.run(client.think("рядки", "канон", kind="ask", level="low")) == "Вітаю."
    assert models.seen["config"].thinking_config.thinking_level == types.ThinkingLevel.LOW
    asyncio.run(client.think("рядки", "канон"))
    assert models.seen["config"].thinking_config.thinking_level is None
