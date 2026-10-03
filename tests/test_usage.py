import asyncio
import json
import stat
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

import agents.llm as llm_mod
from agents.agent import Agent
from agents.usage import KINDS, usage_line
from tests.test_chronicle import CFG, SeqLLM

META = SimpleNamespace(prompt_token_count=1200, candidates_token_count=80, total_token_count=1280)


# --- the line (contract) ---
def test_usage_line_shape_and_no_text():
    line = usage_line("2026-10-03T14:00:00+03:00", "ada", "reply", "gemini-2.5-flash", META, True)
    assert set(line) == {"ts", "agent", "kind", "model", "prompt_tokens", "output_tokens", "total_tokens", "ok"}
    assert (line["prompt_tokens"], line["output_tokens"], line["total_tokens"], line["ok"]) == (1200, 80, 1280, True)


def test_missing_metadata_gives_nulls():
    assert usage_line("2026-10-03T14:00:00", "ada", "plan", "m", None, False)["prompt_tokens"] is None
    partial = SimpleNamespace(prompt_token_count=5, candidates_token_count=None, total_token_count=None)
    line = usage_line("2026-10-03T14:00:00", "ada", "plan", "m", partial, True)
    assert (line["prompt_tokens"], line["output_tokens"]) == (5, None)


def test_kind_list_is_the_contract():
    assert KINDS == ("reply", "summary", "plan", "day_memory", "digest", "today")


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
