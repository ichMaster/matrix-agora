import asyncio
import json
import os
import stat
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

import agents.llm as llm_mod
from agents.agent import Agent
from agents.usage import KINDS, Row, usage_line
from tests.test_chronicle import CFG, SeqLLM

META = SimpleNamespace(prompt_token_count=1200, candidates_token_count=80, total_token_count=1280)


# --- the line (contract) ---
def test_usage_line_shape_and_no_text():
    line = usage_line("2026-10-03T14:00:00+03:00", "ada", "reply", "gemini-2.5-flash", META, True)
    assert set(line) == {"ts", "agent", "kind", "model", "prompt_tokens", "output_tokens", "total_tokens", "ok",
                         "engine", "billing", "cache_read_tokens", "cache_write_tokens", "reported_cost_usd"}  # v2
    assert (line["engine"], line["billing"]) == ("gemini", "api")
    assert (line["prompt_tokens"], line["output_tokens"], line["total_tokens"], line["ok"]) == (1200, 80, 1280, True)


def test_missing_metadata_gives_nulls():
    assert usage_line("2026-10-03T14:00:00", "ada", "plan", "m", None, False)["prompt_tokens"] is None
    partial = SimpleNamespace(prompt_token_count=5, candidates_token_count=None, total_token_count=None)
    line = usage_line("2026-10-03T14:00:00", "ada", "plan", "m", partial, True)
    assert (line["prompt_tokens"], line["output_tokens"]) == (5, None)


def test_kind_list_is_the_contract():
    assert KINDS == ("reply", "summary", "plan", "day_memory", "digest", "today", "mood")


# --- the seam reports every call ---
class FakeModels:
    def __init__(self, behaviour):
        self.behaviour = behaviour

    async def generate_content(self, **kw):
        if self.behaviour == "raise":
            raise RuntimeError("boom")
        return SimpleNamespace(text="" if self.behaviour == "empty" else "текст", usage_metadata=META)


@pytest.mark.parametrize("behaviour,ok,result", [("ok", True, "текст"), ("empty", False, None), ("raise", False, None)])
def test_seam_reports_ok_empty_and_failed_calls(monkeypatch, behaviour, ok, result):
    monkeypatch.setattr(llm_mod.genai, "Client", lambda: SimpleNamespace(aio=SimpleNamespace(models=FakeModels(behaviour))))
    seen = []
    client = llm_mod.GeminiClient(sink=lambda *a: seen.append(a))
    out = asyncio.run(client.generate("c", "s", kind="digest"))
    assert out == result
    assert seen == [("digest", llm_mod.MODEL, None if behaviour == "raise" else META, ok)]


def test_a_failing_sink_never_breaks_the_call(monkeypatch):
    monkeypatch.setattr(llm_mod.genai, "Client", lambda: SimpleNamespace(aio=SimpleNamespace(models=FakeModels("ok"))))

    def bad_sink(*a):
        raise OSError("disk full")

    assert asyncio.run(llm_mod.GeminiClient(sink=bad_sink).generate("c", "s")) == "текст"


# --- the agent writes the line; every call site names its kind ---
class KindLLM(SeqLLM):
    def __init__(self, *texts):
        super().__init__(*texts)
        self.kinds = []

    async def generate(self, transcript, system_instruction, max_output_tokens=400, kind="reply"):
        self.kinds.append(kind)
        return await super().generate(transcript, system_instruction, max_output_tokens, kind)


def make(tmp_path, llm):
    agent = Agent(CFG, llm=llm)
    agent.client = SimpleNamespace(room_send=AsyncMock(), room_typing=AsyncMock())
    agent.memory_file = tmp_path / "ada.memory.md"
    agent.clock = lambda: int(datetime(2026, 10, 3, 9, tzinfo=ZoneInfo("Europe/Kyiv")).timestamp() * 1000)
    agent.rng = lambda: 0.99
    return agent


def test_record_usage_writes_a_private_jsonl_line(tmp_path):
    agent = make(tmp_path, KindLLM())
    agent.record_usage("summary", "gemini-2.5-flash", META, True)
    raw = agent.usage_file.read_text(encoding="utf-8")
    rec = json.loads(raw)
    assert rec["kind"] == "summary" and rec["agent"] == "ada" and rec["ts"].startswith("2026-10-03T09:00")
    assert stat.S_IMODE(agent.usage_file.stat().st_mode) == 0o600


def test_usage_file_is_private_from_birth(tmp_path, monkeypatch):
    agent = make(tmp_path, KindLLM())
    old = os.umask(0o022)
    monkeypatch.setattr(os, "chmod", lambda *a, **k: None)  # no after-the-fact chmod (code review #2)
    try:
        agent.record_usage("reply", "m", META, True)
    finally:
        os.umask(old)
    assert stat.S_IMODE(agent.usage_file.stat().st_mode) == 0o600


def test_a_loose_existing_usage_file_is_tightened(tmp_path):
    agent = make(tmp_path, KindLLM())
    agent.usage_file.write_text("", encoding="utf-8")
    agent.usage_file.chmod(0o644)
    agent.record_usage("reply", "m", META, True)
    agent.record_usage("plan", "m", None, False)
    assert stat.S_IMODE(agent.usage_file.stat().st_mode) == 0o600
    kinds = [json.loads(line)["kind"] for line in agent.usage_file.read_text(encoding="utf-8").splitlines()]
    assert kinds == ["reply", "plan"]


def test_every_call_site_names_its_kind(tmp_path):
    llm = KindLLM("НОТАТКА: н\nСЬОГОДНІ: с", "спогад", "дайджест")
    agent = make(tmp_path, llm)
    agent.session = [("Ich", "x")]
    asyncio.run(agent.summarize())
    asyncio.run(agent.ensure_day_memory(date(2026, 10, 2)))
    for d in range(14, 21):
        p = agent._memory_path("day", date(2026, 9, d))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("день", encoding="utf-8")
    asyncio.run(agent.ensure_digest("week", date(2026, 9, 14)))
    asyncio.run(agent.ensure_plans(date(2026, 10, 3)))
    asyncio.run(agent.ensure_today(datetime(2026, 10, 3, 9, tzinfo=ZoneInfo("Europe/Kyiv"))))
    assert llm.kinds[:3] == ["summary", "day_memory", "digest"]
    assert llm.kinds[3:7] == ["plan"] * 4 and llm.kinds[7] == "today"



def test_automatic_function_calling_is_off(monkeypatch):
    # no tools are passed, so AFC is pure log noise in the panel's view (v3.4 review #3)
    seen = {}

    class Capture(FakeModels):
        async def generate_content(self, **kw):
            seen.update(kw)
            return await super().generate_content(**kw)
    monkeypatch.setattr(llm_mod.genai, "Client", lambda: SimpleNamespace(aio=SimpleNamespace(models=Capture("ok"))))
    asyncio.run(llm_mod.GeminiClient().generate("c", "s"))
    assert seen["config"].automatic_function_calling.disable is True



# --- v4.4: usage line v2 ------------------------------------------------------------------------------------------------
def test_a_claude_sdk_line_is_always_subscription_and_carries_no_text():
    from agents.usage import sdk_usage_line
    line = sdk_usage_line("2026-10-10T20:00:00+03:00", "claude", "reply", "opus",
                          {"input_tokens": 900, "output_tokens": 60, "cache_read_input_tokens": 4000,
                           "cache_creation_input_tokens": 120}, True, reported_cost=0.0123)
    assert (line["engine"], line["billing"]) == ("claude-sdk", "subscription")
    assert (line["prompt_tokens"], line["output_tokens"], line["total_tokens"]) == (900, 60, 960)
    assert (line["cache_read_tokens"], line["cache_write_tokens"], line["reported_cost_usd"]) == (4000, 120, 0.0123)
    assert sdk_usage_line("2026-10-10T20:00:00", "claude", "reply", "opus", None, False)["total_tokens"] is None


def test_only_api_rows_are_priced_and_a_v1_line_is_gemini():
    from agents.usage import aggregate, cost, parse_lines, render, sdk_usage_line
    v1 = {"ts": "2026-10-10T10:00:00", "agent": "ada", "kind": "reply", "model": "m", "prompt_tokens": 1000,
          "output_tokens": 100, "total_tokens": 1100, "ok": True}
    claude = sdk_usage_line("2026-10-10T11:00:00", "claude", "reply", "opus",
                            {"input_tokens": 5000, "output_tokens": 500}, True, 0.5)
    recs, bad = parse_lines([json.dumps(v1), json.dumps(claude)])
    assert bad == 0
    rows = aggregate(recs)
    ada, cl = rows[("2026-10-10", "ada", "reply")], rows[("2026-10-10", "claude", "reply")]
    assert (ada.engine, ada.billing, cl.engine, cl.billing) == ("gemini", "api", "claude-sdk", "subscription")
    assert cost(ada, 0.30, 2.50) == pytest.approx(1000 / 1e6 * 0.30 + 100 / 1e6 * 2.50)
    assert cost(cl, 0.30, 2.50) is None                                   # the subscription is never priced
    total = Row()
    for r in rows.values():
        total.add(r)
    assert total.billing == "mixed" and cost(total, 0.30, 2.50) == pytest.approx(cost(ada, 0.30, 2.50))
    out = render(rows, 0.30, 2.50, markdown=True)
    assert "| subscription | — |" in out and "billing" in out
    assert parse_lines([json.dumps({**v1, "billing": "free"})])[1] == 1       # an unknown billing is corrupt
