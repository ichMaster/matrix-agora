"""v5.15 — the judge of her backup's talk: Gemma 4 31B on OpenRouter (`agents/judge.py`) — the request, the verdicts,
the chunks, the failures, its usage line and its place in the agent (aiohttp patched; no network)."""

import asyncio
import logging
import os
from typing import ClassVar

from agents import judge as jd
from agents.judge import CHUNK, CLEAN, FLAGGED, POLICY, Judge, body, numbered, parse_verdicts

KEY = "or-secret-key-xyz"
SECRET = "таємниця-5150"


def answer(text, finish="stop", usage=None):
    return {"choices": [{"message": {"content": text}, "finish_reason": finish}],
            "usage": usage if usage is not None else {"prompt_tokens": 300, "completion_tokens": 12, "cost": 4e-05}}


class FakeResponse:
    def __init__(self, status, data):
        self.status, self.data = status, data

    async def json(self, content_type=None):
        return self.data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeSession:
    seen: ClassVar[list] = []
    live: ClassVar[list] = []

    def __init__(self, reply, **kwargs):
        self.reply, self.kwargs = reply, kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def post(self, url, json=None, headers=None):
        FakeSession.seen.append({"url": url, "json": json, "headers": headers, "timeout": self.kwargs.get("timeout")})
        out = self.reply(json)
        if isinstance(out, BaseException):
            raise out
        return out


def judge(monkeypatch, reply, timeout_s=30):
    """A judge whose calls answer through `reply(request) → FakeResponse | exception`, its usage lines collected."""
    FakeSession.seen = []
    monkeypatch.setattr(jd, "ClientSession", lambda **kw: FakeSession(reply, **kw))
    usage = []
    return Judge(KEY, sink=lambda *a: usage.append(a), timeout_s=timeout_s), usage


def lines_of(request):
    return request["messages"][1]["content"].splitlines()


# --- the request ------------------------------------------------------------------------------------------------------
def test_the_request_carries_the_policy_and_the_numbered_lines_only(monkeypatch):
    j, _ = judge(monkeypatch, lambda req: FakeResponse(200, answer("1: ні\n2: так · небезпечний зміст")))
    verdicts = asyncio.run(j.rate(["Привіт, сонце", f"рядок\nз переносом {SECRET}"]))
    assert verdicts == [CLEAN, FLAGGED]
    sent = FakeSession.seen[0]
    assert sent["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert sent["headers"]["Authorization"] == f"Bearer {KEY}"
    assert sent["timeout"].total == 30
    req = sent["json"]
    assert req["model"] == "google/gemma-4-31b-it" and req["temperature"] == 0
    assert req["provider"] == {"sort": "latency", "data_collection": "deny"} and req["reasoning"] == {"enabled": False}
    assert 0 < req["max_tokens"] <= 16 * 2 + 32
    assert [m["role"] for m in req["messages"]] == ["system", "user"]
    assert req["messages"][0]["content"] == POLICY
    assert "Флірт, компліменти, поцілунки, обійми" in POLICY and "`N: так · <категорія>`" in POLICY  # the owner's test
    assert lines_of(req) == ["1: Привіт, сонце", f"2: рядок з переносом {SECRET}"]  # no speaker, no canon, one per line


def test_numbered_and_body_are_pure():
    assert numbered(["а", "б  в"]) == "1: а\n2: б в"
    assert body("openai/gpt-oss-120b", ["а"])["model"] == "openai/gpt-oss-120b"


# --- the verdicts -----------------------------------------------------------------------------------------------------
def test_parse_verdicts_yes_no_missing_malformed_and_out_of_range():
    text = "1: ні\n2: ТАК · мова ворожнечі\n3) ні\n4: можливо\n9: так · образи\nкоментар"
    assert parse_verdicts(text, 5) == [CLEAN, FLAGGED, CLEAN, None, None]


def test_a_refusal_flags_every_line_of_the_call():
    assert parse_verdicts("I cannot fulfill this request.", 3) == [FLAGGED] * 3
    assert parse_verdicts("1: ні", 2, finish="content_filter") == [FLAGGED, FLAGGED]
    assert parse_verdicts("", 2) == [None, None]  # nothing at all is no verdict, never a flag


# --- the chunks and the failures --------------------------------------------------------------------------------------
def test_many_lines_go_in_chunks_of_25_in_parallel(monkeypatch):
    live, peak = [0], [0]

    async def slow(req):
        live[0] += 1
        peak[0] = max(peak[0], live[0])
        await asyncio.sleep(0.01)
        live[0] -= 1
        n = len(lines_of(req))
        return FakeResponse(200, answer("\n".join(f"{i}: ні" for i in range(1, n + 1))))

    class AwaitedResponse(FakeResponse):
        def __init__(self, coro):
            self.coro = coro

        async def __aenter__(self):
            done = await self.coro
            self.status, self.data = done.status, done.data
            return self

    j, usage = judge(monkeypatch, lambda req: AwaitedResponse(slow(req)))
    verdicts = asyncio.run(j.rate([f"рядок {i}" for i in range(60)]))
    assert verdicts == [CLEAN] * 60
    assert [len(lines_of(s["json"])) for s in FakeSession.seen] == [CHUNK, CHUNK, 10] and peak[0] == 3
    assert len(usage) == 3


def test_an_error_or_a_timeout_leaves_that_chunk_unrated_never_flagged(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    calls = iter([FakeResponse(500, {}), TimeoutError(), FakeResponse(200, answer("1: так · образи"))])
    j, usage = judge(monkeypatch, lambda req: next(calls))
    texts = [f"{SECRET} {i}" for i in range(CHUNK * 2 + 1)]
    verdicts = asyncio.run(j.rate(texts))
    assert verdicts[:CHUNK * 2] == [None] * (CHUNK * 2) and verdicts[-1] == FLAGGED
    assert [u[3] for u in usage] == [False, False, True]
    assert "judge: HTTP 500" in caplog.text and "judge failed: TimeoutError" in caplog.text
    assert SECRET not in caplog.text and KEY not in caplog.text


def test_the_usage_sink_gets_the_model_the_tokens_and_openrouters_cost(monkeypatch):
    j, usage = judge(monkeypatch, lambda req: FakeResponse(200, answer("1: ні")))
    asyncio.run(j.rate(["привіт"]))
    assert usage == [("google/gemma-4-31b-it", 300, 12, True, 4e-05)]
    j2, usage2 = judge(monkeypatch, lambda req: FakeResponse(200, answer("щось не те", usage={})))
    assert asyncio.run(j2.rate(["привіт"])) == [None]
    assert usage2 == [("google/gemma-4-31b-it", None, None, False, None)]  # no verdict: not ok


def test_the_judge_never_shows_its_key():
    assert KEY not in repr(Judge(KEY)) and "gemma" in repr(Judge(KEY))


# --- in the agent -----------------------------------------------------------------------------------------------------
def test_the_key_leaves_every_agents_environment_and_her_judge_needs_the_backup(tmp_path, monkeypatch, caplog):
    from agents.agent import Agent
    from tests.test_archive import kira as kira_agent
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)
    base = kira_agent(tmp_path, monkeypatch)
    assert "OPENROUTER_API_KEY" not in os.environ and base.judge is None  # no backup: no judge
    cfg = base.cfg.__class__(**{**base.cfg.__dict__, "capabilities": base.cfg.capabilities | {"fallback"}})
    monkeypatch.setenv("FALLBACK_MODEL", "glm-4-6")
    monkeypatch.setenv("NOVELAI_API_TOKEN", "nai")
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)
    monkeypatch.setenv("CLASSIFIER_TIMEOUT_S", "20")
    agent = Agent(cfg, llm=base.llm, roster=base.roster)
    assert agent.judge is not None and agent.judge.model == "google/gemma-4-31b-it" and agent.judge.timeout_s == 20
    caplog.set_level(logging.WARNING)
    monkeypatch.setenv("NOVELAI_API_TOKEN", "nai")  # the key is gone now: the judge is off, and said so
    assert Agent(cfg, llm=base.llm, roster=base.roster).judge is None
    assert "judge off: OPENROUTER_API_KEY is not set" in caplog.text and KEY not in caplog.text


def test_her_judge_writes_its_usage_line(tmp_path, monkeypatch):
    from agents.usage import parse_lines
    from tests.test_archive import kira as kira_agent
    agent = kira_agent(tmp_path, monkeypatch)
    agent.record_judge_usage("google/gemma-4-31b-it", 300, 12, True, 4e-05)
    records, bad = parse_lines(agent.usage_file.read_text(encoding="utf-8").splitlines())
    assert bad == 0 and records[-1]["kind"] == "judge" and records[-1]["engine"] == "openrouter"
