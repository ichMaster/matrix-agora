"""v5.16 — Gemini checks the parts of a blocked prompt, in her private answer: after a prompt-stage block the backup
answers as before; once her line is sent, the same model gets that prompt in parts, and what it blocks is closed
`censored` — a recalled line, a fact, a thought — gone from her next prompt to Gemini; a fixed layer is only named; the
judge leaves the blocked prompt's older lines to the probe; the caps per block and per day (nio, Gemini, NovelAI and
the judge mocked; an injected clock; made-up lines only)."""

import asyncio
import logging

import pytest

from agents.facts import add_fact, load_facts
from agents.llm import LAST_BLOCK
from agents.private import PRIVATE_BRIEF
from agents.route import Route, load_route, save_route
from agents.thoughts import Thought, archive_key
from agents.world import local_now
from tests.test_archive import EmbedLLM
from tests.test_judge_verdicts import FakeJudge
from tests.test_private_route import her
from tests.test_private_runtime import ms

MARK = "заборонене-5161"  # what Gemini's filter will not take, in a made-up line
YESTERDAY = 86_400_000


class Filtered(EmbedLLM):
    """Gemini whose filter blocks any prompt holding one of `marks` at the prompt stage — an answer and a probe the
    same way; `stage` makes the answer's block another stage."""

    def __init__(self, marks=(MARK,), stage="prompt", probe=True):
        super().__init__()
        self.marks, self.stage, self.events = marks, stage, []
        if not probe:
            self.probe = None

    def _holds(self, *texts):
        return any(m in t for m in self.marks for t in texts)

    async def generate(self, transcript, system_instruction, max_output_tokens=400, kind="reply"):
        if self._holds(transcript, system_instruction):
            self.events.append("blocked")
            LAST_BLOCK.set((self.stage, "prohibited_content", None) if self.stage != "refusal"
                           else ("refusal", "виконати цей запит", None))
            return None
        self.events.append("answer")
        return "Від Gemini."

    async def probe(self, transcript, system_instruction, kind="probe"):
        self.events.append("probe")
        return self._holds(transcript, system_instruction)


def probing(tmp_path, monkeypatch, gemini=None):
    agent = her(tmp_path, monkeypatch, gemini or Filtered())
    agent.judge = FakeJudge()
    agent.probe_calls, agent.probe_day_calls = 12, 60
    agent.facts_dir, agent.facts_in_prompt, agent.fact_max_chars = tmp_path / "kira.facts", 10, 240
    agent.spawned = []

    def spawn(coro):  # the probe and the judge, with how many lines of hers were kept by then; nothing else here
        if coro.__name__ not in ("probe_later", "judge_later"):
            coro.close()
            return
        sent = sum(1 for x in agent.archive.latest("private", 50, gemini=False) if x.speaker == "Кіра")
        agent.spawned.append((coro.__name__, coro, sent))

    agent._spawn = spawn
    AGENTS.append(agent)
    return agent


AGENTS: list = []


@pytest.fixture(autouse=True)
def _close_what_was_not_run():
    yield
    while AGENTS:
        drop_rest(AGENTS.pop())


def run(agent, name):
    for kind, coro, _ in list(agent.spawned):
        if kind == name:
            asyncio.run(coro)
    agent.spawned = [s for s in agent.spawned if s[0] != name]


def drop_rest(agent):
    for _, coro, _ in agent.spawned:
        coro.close()
    agent.spawned = []


def mark_of(agent, key):
    return agent.archive.db.execute("SELECT mark FROM lines WHERE key = ?", (key,)).fetchone()[0]


def test_a_blocking_recalled_line_is_closed_once_she_has_sent_and_never_reaches_gemini_again(tmp_path, monkeypatch,
                                                                                              caplog):
    caplog.set_level(logging.INFO)
    agent = probing(tmp_path, monkeypatch)
    agent.archive.append("$a1", ms(10) - YESTERDAY, "agora", "matrix", "Бруно", f"Бачив телескоп {MARK}")
    agent.archive.append("$a2", ms(11) - YESTERDAY, "agora", "matrix", "Ада", "Принесла каву.")
    agent.private_line("Як там телескоп?", ms(17), "telegram", "tg:1")
    assert asyncio.run(agent.private_reply()) is True
    assert agent.llm.events == ["blocked"]                                         # nothing probed on the reply path
    names = [(name, sent) for name, _, sent in agent.spawned]
    assert ("probe_later", 1) in names                                             # spawned once her line was kept
    run(agent, "probe_later")
    assert agent.llm.events[0] == "blocked" and set(agent.llm.events[1:]) == {"probe"}
    assert mark_of(agent, "$a1") == "censored" and mark_of(agent, "$a2") == "gemini"
    assert agent.archive.unembedded(10) == [(x[0], x[1]) for x in agent.archive.unembedded(10)]  # no vector for it
    assert MARK not in asyncio.run(agent._gemini_private_prompt(PRIVATE_BRIEF))    # gone from her next prompt
    assert "probe:" in caplog.text and "closed 1 lines, 0 facts, 0 thoughts" in caplog.text
    assert MARK not in caplog.text and "$a1" not in caplog.text
    r = load_route(agent.route_file)
    assert r.probed["calls"] == len(agent.llm.events) - 1 and r.probed["closed"] == 1
    run(agent, "judge_later")                                                      # the judge: his line and her answer
    rated = [t for call in agent.judge.calls for t in call]
    assert rated and not any(MARK in t for t in rated) and len(rated) == 2


def test_a_blocking_fact_and_a_blocking_thought_are_closed(tmp_path, monkeypatch):
    agent = probing(tmp_path, monkeypatch)
    agent.cfg = agent.cfg.__class__(**{**agent.cfg.__dict__, "capabilities": agent.cfg.capabilities | {"thoughts"}})
    agent.thoughts_in_prompt = 3
    add_fact(agent.facts_dir, f"Любить чай {MARK}", 1, "private", "2026-10-19", 50, 240)
    add_fact(agent.facts_dir, "Любить гори", 1, "private", "2026-10-19", 50, 240)
    now = local_now(agent.clock(), agent.tz)
    morning = Thought("09:00", "news", "thought", "zaxid", f"Ранок у куполі {MARK}")
    agent.keep_thought(now.replace(hour=9), morning)
    agent.private_line("Добрий вечір", ms(17), "telegram", "tg:1")
    assert asyncio.run(agent.private_reply()) is True
    run(agent, "probe_later")
    assert {f.text: f.mark for f in load_facts(agent.facts_dir)} == {f"Любить чай {MARK}": "censored",
                                                                       "Любить гори": "gemini"}
    assert mark_of(agent, archive_key(now.date().isoformat(), morning, 0)) == "censored"
    assert agent.day_thoughts(now.date()) == [] and MARK not in (agent.facts_now() or "")
    mirrored = dict(agent.archive.db.execute("SELECT text, mark FROM lines WHERE place = 'facts'").fetchall())
    assert mirrored[f"Любить чай {MARK}"] == "censored"
    prompt = asyncio.run(agent._gemini_private_prompt(PRIVATE_BRIEF))
    assert MARK not in prompt and "Любить гори" in prompt


def test_a_blocking_layer_is_named_and_nothing_is_closed(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    agent = probing(tmp_path, monkeypatch, Filtered(marks=("Канон.",)))
    agent.private_line("Добрий вечір", ms(17), "telegram", "tg:1")
    assert asyncio.run(agent.private_reply()) is True
    run(agent, "probe_later")
    assert "probe: the base blocks — layers canon" in caplog.text
    assert load_route(agent.route_file).probed["closed"] == 0
    assert set(dict(agent.archive.db.execute("SELECT key, mark FROM lines WHERE place = 'private' "
                                             "AND speaker = 'Ich'").fetchall()).values()) == {"waiting"}


@pytest.mark.parametrize("stage", ["answer", "refusal"])
def test_no_probe_after_an_answer_stage_block_or_a_refusal_and_the_judge_rates_as_before(tmp_path, monkeypatch,
                                                                                          stage):
    agent = probing(tmp_path, monkeypatch, Filtered(stage=stage))
    agent.archive.append("$a1", ms(10) - YESTERDAY, "agora", "matrix", "Бруно", f"Бачив телескоп {MARK}")
    agent.private_line("Як там телескоп?", ms(17), "telegram", "tg:1")
    assert asyncio.run(agent.private_reply()) is True
    assert "probe_later" not in [name for name, _, _ in agent.spawned]
    run(agent, "judge_later")
    assert any(MARK in t for call in agent.judge.calls for t in call)          # the older lines: still the judge's


def blocked_once(agent, spent=0):
    if spent:
        day = local_now(agent.clock(), agent.tz).date().isoformat()
        save_route(agent.route_file, Route(day=day, probed={"calls": spent, "closed": 0}))
    for i in range(30):
        agent.archive.append(f"tg:{i}", ms(9, i), "private", "telegram", "Ich", f"рядок {i}")
    agent.archive.append("tg:x", ms(16), "private", "telegram", "Ich", f"і ще {MARK}")
    agent.private_line("Добрий вечір", ms(17), "telegram", "tg:y")
    assert asyncio.run(agent.private_reply()) is True
    return agent


@pytest.mark.parametrize(("calls", "day_calls", "spent", "probes"), [(3, 60, 0, 3), (12, 60, 58, 2), (12, 60, 60, 0)])
def test_the_caps_per_block_and_per_day(tmp_path, monkeypatch, caplog, calls, day_calls, spent, probes):
    caplog.set_level(logging.INFO)
    agent = probing(tmp_path, monkeypatch)
    agent.probe_calls, agent.probe_day_calls = calls, day_calls
    blocked_once(agent, spent)
    run(agent, "probe_later")
    assert agent.llm.events.count("probe") == probes
    assert load_route(agent.route_file).probed["calls"] == spent + probes      # counted in the file, across a restart
    if probes == 0:
        assert "probe: off — the day's calls are spent" in caplog.text


@pytest.mark.parametrize(("calls", "day_calls"), [(0, 60), (12, 0)])
def test_zero_turns_the_probe_off_and_the_judge_rates_as_before(tmp_path, monkeypatch, calls, day_calls):
    agent = probing(tmp_path, monkeypatch)
    agent.probe_calls, agent.probe_day_calls = calls, day_calls
    blocked_once(agent)
    assert "probe_later" not in [name for name, _, _ in agent.spawned]
    run(agent, "judge_later")
    assert any(MARK in t for call in agent.judge.calls for t in call)


def test_a_failed_probe_closes_nothing(tmp_path, monkeypatch):
    agent = probing(tmp_path, monkeypatch)

    async def broken(transcript, system_instruction, kind="probe"):
        return None

    agent.llm.probe = broken
    agent.archive.append("$a1", ms(10) - YESTERDAY, "agora", "matrix", "Бруно", f"Бачив телескоп {MARK}")
    agent.private_line("Як там телескоп?", ms(17), "telegram", "tg:1")
    asyncio.run(agent.private_reply())
    run(agent, "probe_later")
    assert mark_of(agent, "$a1") == "gemini" and load_route(agent.route_file).probed["closed"] == 0


def test_a_line_she_writes_first_is_probed_too(tmp_path, monkeypatch):
    agent = probing(tmp_path, monkeypatch)
    agent.archive.append("tg:0", ms(16), "private", "telegram", "Ich", f"старе {MARK}")
    agent.last_private_ms = ms(16)
    assert asyncio.run(agent.private_reply(nudge=True)) is True
    run(agent, "probe_later")
    assert mark_of(agent, "tg:0") == "censored" and ("Ich", f"старе {MARK}") in agent._closed
    drop_rest(agent)
