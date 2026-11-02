"""v5.22 (the owner, 2026-11-02: «виключи бкап і включи щоб показувало все що приходить з джемені і інших мереж») —
`TRACE_CALLS`: every usage record of hers goes to the owner as one ⚙️ line in Telegram — the model, the kind, ok or
the block with its reason, the tokens and the time; never a text (a fake bot; no network)."""

import asyncio
import json
from types import SimpleNamespace

from agents.agent import TTS_MODEL
from agents.llm import LAST_BLOCK
from agents.settings import OVERRIDES_FILE, save_json
from agents.usage import fallback_usage_line, trace_line, tts_usage_line, usage_line, video_note_usage_line
from tests.test_telegram_runtime import kira, texts_sent

TS = "2026-11-02T17:00:00+02:00"
USAGE = SimpleNamespace(prompt_token_count=41218, candidates_token_count=140, thoughts_token_count=1000,
                        total_token_count=42358, cached_content_token_count=None)


def test_a_gemini_answer_names_the_model_the_kind_the_tokens_and_the_time():
    rec = usage_line(TS, "kira", "private", "gemini-3.1-pro-preview", USAGE, True, latency_ms=13_412)
    assert trace_line(rec) == "⚙️ gemini-3.1-pro-preview · private · ok · in 41 218 · out 1 140 · 13.4 с"


def test_a_block_names_its_stage_reason_and_category_when_it_is_this_records():
    rec = usage_line(TS, "kira", "private", "gemini-3.1-pro-preview", None, False, "prompt", 700)
    assert trace_line(rec, ("prompt", "prohibited_content", None)) == (
        "⚙️ gemini-3.1-pro-preview · private · БЛОК prompt prohibited_content · 0.7 с")
    assert "БЛОК answer safety HARM_CATEGORY_SEXUALLY_EXPLICIT" in trace_line(
        {**rec, "blocked": "answer"}, ("answer", "safety", "HARM_CATEGORY_SEXUALLY_EXPLICIT"))
    assert "БЛОК prompt ·" in trace_line(rec, ("refusal", "marker", None))   # another call's block: the stage alone


def test_other_networks_and_a_failure():
    assert trace_line(tts_usage_line(TS, "kira", "eleven_v3", 182, True, 2_100)) == (
        "⚙️ eleven_v3 · tts · ok · 182 симв. · 2.1 с")
    assert trace_line(video_note_usage_line(TS, "kira", "veed/fabric-1.0", 9_500, True, None, 81_000)).endswith(
        "video_note · ok · відео 9.5 с · 81.0 с")
    assert trace_line(fallback_usage_line(TS, "kira", "private", "glm-4-6", False, 5_000)) == (
        "⚙️ glm-4-6 · private · помилка · 5.0 с")


def run_record(agent):
    async def go():
        LAST_BLOCK.set(("prompt", "prohibited_content", None))
        agent.record_usage("private", "gemini-3.1-pro-preview", None, False, blocked="prompt", latency_ms=650)
        agent.record_tts(57, True, 1_200)
        await asyncio.gather(*list(agent._tasks))
    asyncio.run(go())


def test_on_each_record_goes_to_him_and_into_the_usage_file(tmp_path, monkeypatch):
    monkeypatch.setenv("TRACE_CALLS", "on")
    agent = kira(tmp_path, monkeypatch)
    agent.memory_file = tmp_path / "kira.memory.md"
    run_record(agent)
    assert texts_sent(agent) == ["⚙️ gemini-3.1-pro-preview · private · БЛОК prompt prohibited_content · 0.7 с",
                                 f"⚙️ {TTS_MODEL} · tts · ok · 57 симв. · 1.2 с"]
    lines = [json.loads(x) for x in agent.usage_file.read_text(encoding="utf-8").splitlines()]
    assert [x["kind"] for x in lines] == ["private", "tts"] and lines[0]["blocked"] == "prompt"


def test_off_by_default_and_without_telegram(tmp_path, monkeypatch):
    agent = kira(tmp_path, monkeypatch)
    agent.memory_file = tmp_path / "kira.memory.md"
    assert agent.trace_calls is False
    run_record(agent)
    assert texts_sent(agent) == [] and len(agent.usage_file.read_text(encoding="utf-8").splitlines()) == 2
    monkeypatch.setenv("TRACE_CALLS", "on")
    assert kira(tmp_path, monkeypatch, env=False).trace_calls is False             # no bot: nothing to send to


def test_the_panels_switch_works_at_once_without_a_restart(tmp_path, monkeypatch):
    """v5.22 (the owner, 2026-11-02: «зроби можливість такий трейс включати на адмін панелі»): the panel's override in
    `state/settings.json` is read at each record — on, her calls go to him; off again, they stop; she never restarts."""
    agent = kira(tmp_path, monkeypatch)
    agent.memory_file = tmp_path / "kira.memory.md"
    save_json(tmp_path / OVERRIDES_FILE, {"services": {}, "agents": {"kira": {"TRACE_CALLS": "on"}}})
    assert agent.trace_calls is True
    run_record(agent)
    assert len(texts_sent(agent)) == 2
    save_json(tmp_path / OVERRIDES_FILE, {"services": {}, "agents": {"kira": {"TRACE_CALLS": "off"}}})
    run_record(agent)
    assert len(texts_sent(agent)) == 2 and len(agent.usage_file.read_text(encoding="utf-8").splitlines()) == 4
