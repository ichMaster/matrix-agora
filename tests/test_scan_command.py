"""v5.24 — the owner's `/scan`, `/scan yes` and `/scan all` in Кіра's Telegram chat: what Gemini can read since the
last scan goes to a fake judge in a task of its own, the counts come back as one ⚙️ line, and the kept list is closed
through her own code — once, within its TTL, never opening anything (a fake bot and judge; made-up lines only)."""

import asyncio
import json
import logging
import os

from agents.archive import Archive
from agents.facts import add_fact, load_facts
from agents.scan import Found, fact_hash, load_scan
from agents.telegram import COMMANDS
from tests.test_telegram_runtime import kira, ms, texts_sent

SECRET = "закритий-рядок-524"   # made-up text of a closed line: it must never reach the judge
NOW = ms(18, 0)


class FakeJudge:
    """Finds every item whose text holds «сцена» (S) and puts «натяк» in the borderline (I); records what it read."""

    def __init__(self, fail=False):
        self.read, self.fail = [], fail

    async def judge(self, items, tz):
        self.read.append(list(items))
        if self.fail:
            return None
        found = Found()
        for i in items:
            if "сцена" in i.text:
                found.candidates[i.ref] = "S"
            elif "натяк" in i.text:
                found.borderline[i.ref] = "I"
        return found


def scanning(tmp_path, monkeypatch, judge=None):
    agent = kira(tmp_path, monkeypatch)
    agent.archive = Archive(tmp_path / "kira.archive.db")
    agent.facts_dir = tmp_path / "kira.facts"
    agent.facts_dir.mkdir()
    agent.scan_judge = judge or FakeJudge()
    agent.scan_days, agent.scan_ttl_s = 7, 1800
    agent.clock = lambda: NOW
    arc = agent.archive
    for n, (who, text, mark) in enumerate((("Ich", "звичайне питання", "gemini"), ("Кіра", "сцена у стіни", "gemini"),
                                           ("Ich", "легкий натяк", "clean"), ("Кіра", SECRET, "blocked"))):
        arc.append(f"k{n}", ms(16, n), "private", "telegram", who, text)
        arc.mark([f"k{n}"], mark)
        agent.private_history.append((who, text))
    agent.session.extend([("Ich (наодинці)", "звичайне питання"), ("Кіра (наодинці)", "сцена у стіни")])
    arc.append("t1", ms(16, 10), "thought_private", "", "Кіра", "думка: сцена вчора")
    arc.append("t2", ms(16, 11), "thought_private", "", "Кіра", SECRET)
    arc.mark(["t2"], "blocked")
    add_fact(agent.facts_dir, "він любить каву", 1, "asked", "2026-10-20", 100, 240)
    add_fact(agent.facts_dir, "сцена з йогуртом", 1, "asked", "2026-10-20", 100, 240)
    add_fact(agent.facts_dir, SECRET + " факт", 1, "asked", "2026-10-20", 100, 240, mark="blocked")
    arc.talk_put("hour", ms(15, 0), ms(16, 0), "сцена в підсумку", 3, 0, 0, ms(16, 0) + 30_000)
    arc.talk_put("hour", ms(14, 0), ms(15, 0), "про роботу", 3, 0, 0, ms(15, 0) + 30_000)
    return agent


def scan(agent, text="/scan"):
    spawned = []
    agent._spawn = lambda coro: spawned.append(coro)
    asyncio.run(agent.telegram_command(text))
    for coro in spawned:
        asyncio.run(coro)
    return spawned


def test_scan_is_a_command():
    assert ("scan", "Знайти, що може блокувати gemini") in COMMANDS


def test_without_a_key_the_scan_is_off(tmp_path, monkeypatch):
    agent = kira(tmp_path, monkeypatch)
    assert agent.scan_judge is None                                  # no OPUS_JUDGE_KEY, no `recall`
    scan(agent)
    assert texts_sent(agent)[-1] == "⚙️ Сканування вимкнене: немає ключа"


def test_the_key_leaves_the_environment_and_makes_the_judge_for_a_person_with_private_and_recall(tmp_path,
                                                                                                    monkeypatch):
    from agents.agent import Agent
    from agents.config import AgentConfig
    from tests.test_private_runtime import KIRA, OWNER, KindLLM
    monkeypatch.setenv("OPUS_JUDGE_KEY", "sk-ant-test-524")
    agent = kira(tmp_path, monkeypatch)                                # her test caps hold no `recall`
    assert "OPUS_JUDGE_KEY" not in os.environ and agent.scan_judge is None
    monkeypatch.setenv("OPUS_JUDGE_KEY", "sk-ant-test-524")
    monkeypatch.setenv("SCAN_EFFORT", "high")
    caps = frozenset({"canon", "summary", "world", "private", "recall"})
    cfg = AgentConfig(**{**AgentConfig(name="Кіра", user_id=KIRA, canon="Канон.", homeserver="http://hs",
                                       room_id="!room", owner=OWNER, password="pw").__dict__, "capabilities": caps})
    agent = Agent(cfg, llm=KindLLM())
    assert "OPUS_JUDGE_KEY" not in os.environ
    assert (agent.scan_judge.key, agent.scan_judge.model, agent.scan_judge.effort) == (
        "sk-ant-test-524", "claude-opus-5-5", "high")


def test_scan_answers_at_once_runs_apart_and_sends_the_counts(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    agent = scanning(tmp_path, monkeypatch)
    spawned = []
    agent._spawn = lambda coro: spawned.append(coro)
    asyncio.run(agent.telegram_command("/scan"))
    assert texts_sent(agent) == ["⚙️ Сканую…"] and len(spawned) == 1   # the command returns before Opus
    asyncio.run(agent.telegram_command("/scan"))
    assert texts_sent(agent)[-1] == "⚙️ Сканування вже йде" and len(spawned) == 1
    asyncio.run(spawned[0])
    answer = texts_sent(agent)[-1]
    assert answer.startswith("⚙️ Знайдено 1 рядків (сцени 1), 1 фактів, 1 думок, 1 підсумків; межових: 1. "
                             "/scan yes — закрити знайдене, /scan all — разом з межовими\n\nПо днях — закриє")
    assert SECRET not in answer and "сцена" not in answer                   # v5.24: by day, counts only
    assert agent._scan_running is False and agent.telegram.send_voice.await_count == 0
    assert "сцена" not in caplog.text and "натяк" not in caplog.text and SECRET not in caplog.text


def test_a_closed_line_thought_or_fact_never_reaches_the_judge(tmp_path, monkeypatch):
    agent = scanning(tmp_path, monkeypatch)
    scan(agent)
    read = agent.scan_judge.read[0]
    assert all(SECRET not in i.text for i in read)
    assert sorted(i.kind for i in read) == ["fact", "fact", "line", "line", "line", "summary", "summary", "thought"]


def test_the_list_holds_refs_codes_hashes_and_times_never_a_text(tmp_path, monkeypatch):
    agent = scanning(tmp_path, monkeypatch)
    scan(agent)
    raw = agent.scan_file.read_text(encoding="utf-8")
    data = json.loads(raw)
    assert oct(agent.scan_file.stat().st_mode & 0o777) == "0o600"
    assert {"made_ms", "start_ms", "end_ms", "candidates", "borderline", "facts", "summaries"} <= set(data)
    assert "сцена" not in raw and "натяк" not in raw and "йогурт" not in raw and "кав" not in raw
    fact = next(f for f in load_facts(agent.facts_dir) if "йогурт" in f.text)
    assert fact_hash(fact.id) in data["facts"].values()
    assert data["end_ms"] == NOW and data["start_ms"] == NOW - 7 * 86_400_000


def test_scan_yes_closes_the_candidates_through_her_own_code(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    agent = scanning(tmp_path, monkeypatch)
    scan(agent)
    scan(agent, "/scan yes")
    assert texts_sent(agent)[-1] == "⚙️ Закрито: 1 рядків, 1 фактів, 1 думок, 1 підсумків"
    marks = dict(agent.archive.db.execute("SELECT key, mark FROM lines WHERE place != 'facts'").fetchall())
    assert marks["k1"] == "blocked" and marks["k2"] == "clean" and marks["k0"] == "gemini" and marks["t1"] == "blocked"
    assert ("Кіра (наодинці)", "сцена у стіни") not in agent.session and ("Кіра", "сцена у стіни") in agent._closed
    assert {f.text: f.mark for f in load_facts(agent.facts_dir)}["сцена з йогуртом"] == "blocked"
    assert [r.text for r in agent.archive.talk_rows("hour")] == ["про роботу"]                 # deleted
    assert agent.archive.talk_put("hour", ms(15, 0), ms(16, 0), "заново", 3, 0, 0, NOW)           # written again
    assert "scan: closed 1 lines, 1 facts, 1 thoughts, 1 summaries" in caplog.text
    assert "сцена" not in caplog.text


def test_scan_all_closes_the_borderline_too(tmp_path, monkeypatch):
    agent = scanning(tmp_path, monkeypatch)
    scan(agent)
    scan(agent, "/scan all")
    assert texts_sent(agent)[-1] == "⚙️ Закрито: 2 рядків, 1 фактів, 1 думок, 1 підсумків"
    marks = dict(agent.archive.db.execute("SELECT key, mark FROM lines WHERE place = 'private'").fetchall())
    assert marks["k2"] == "blocked" and marks["k0"] == "gemini"


def test_a_spent_list_never_closes_twice_and_an_old_one_never_closes(tmp_path, monkeypatch):
    agent = scanning(tmp_path, monkeypatch)
    scan(agent, "/scan yes")                                          # no scan yet
    assert texts_sent(agent)[-1] == "⚙️ Немає свіжого сканування: спершу /scan"
    scan(agent)
    agent.clock = lambda: NOW + 1801 * 1000                           # past SCAN_TTL_S
    scan(agent, "/scan yes")
    assert texts_sent(agent)[-1] == "⚙️ Немає свіжого сканування: спершу /scan"
    assert agent.archive.closed_count() == 1                          # only the line closed before
    agent.clock = lambda: NOW
    scan(agent)
    scan(agent, "/scan yes")
    scan(agent, "/scan yes")
    assert texts_sent(agent)[-1] == "⚙️ Немає свіжого сканування: спершу /scan"


def test_the_next_scan_starts_where_a_used_or_empty_one_ended_never_after_an_unused_one(tmp_path, monkeypatch):
    agent = scanning(tmp_path, monkeypatch)
    scan(agent)
    assert load_scan(agent.scan_file)["last_end_ms"] is None          # unused: the next one reads the same lines
    agent.clock = lambda: NOW + 60_000
    scan(agent)
    assert len(agent.scan_judge.read) == 2 and len(agent.scan_judge.read[1]) == len(agent.scan_judge.read[0])
    scan(agent, "/scan yes")
    assert load_scan(agent.scan_file)["last_end_ms"] == NOW + 60_000  # used: the next one starts there
    agent.clock = lambda: NOW + 120_000
    scan(agent)
    assert texts_sent(agent)[-1] == "⚙️ Нічого не знайдено" and len(agent.scan_judge.read) == 2  # nothing new to read
    assert load_scan(agent.scan_file)["last_end_ms"] == NOW + 120_000
    assert len(load_scan(agent.scan_file)["facts_seen"]) == 2       # a fact has only its day: read once, by hash


def test_a_scan_that_finds_nothing_moves_the_start(tmp_path, monkeypatch):
    agent = scanning(tmp_path, monkeypatch)

    class Nothing(FakeJudge):
        async def judge(self, items, tz):
            self.read.append(list(items))
            return Found()

    agent.scan_judge = Nothing()
    scan(agent)
    assert texts_sent(agent)[-1] == "⚙️ Нічого не знайдено"
    data = load_scan(agent.scan_file)
    assert data["last_end_ms"] == NOW and len(data["facts_seen"]) == 2 and "candidates" not in data


def test_a_failed_scan_closes_nothing_and_keeps_the_start(tmp_path, monkeypatch):
    agent = scanning(tmp_path, monkeypatch, FakeJudge(fail=True))
    scan(agent)
    assert texts_sent(agent)[-1] == "⚙️ Opus не відповів: нічого не знайдено і не закрито"
    assert not agent.scan_file.exists() and agent.archive.closed_count() == 1
    assert agent._scan_running is False


def test_closing_never_opens_and_skips_what_is_closed_already(tmp_path, monkeypatch):
    agent = scanning(tmp_path, monkeypatch)
    scan(agent)
    agent.archive.mark(["k1"], "blocked")                             # closed by hand in between
    scan(agent, "/scan yes")
    assert texts_sent(agent)[-1].startswith("⚙️ Закрито: 0 рядків")
    assert agent.archive.mark(["k1"], "gemini") == 0                  # a closed mark never becomes an open one


def probing(agent, blocks):
    """Gemini for the scan's check: `blocks(text)` says whether a group blocks; each check recorded with its kind."""
    agent.llm.checked = []

    async def probe(transcript, system_instruction, kind="probe"):
        agent.llm.checked.append((kind, transcript))
        return blocks(transcript)

    agent.llm.probe = probe
    return agent


def test_what_gemini_lets_through_stays_open(tmp_path, monkeypatch):
    """v5.24 (the owner, 2026-11-04: «не просто чи є там тема … а чи вона буде блокувати промпт»): Opus found four
    and one borderline; Gemini passes every group — nothing to close, and the answer says so."""
    agent = probing(scanning(tmp_path, monkeypatch), lambda text: False)
    scan(agent)
    answer = texts_sent(agent)[-1]
    assert answer.startswith("⚙️ Нічого не знайдено") and "Знайдене Opus, яке Gemini пропускає, лишається відкритим: 5" in answer
    assert {k for k, _ in agent.llm.checked} == {"scan_check"}
    assert all(SECRET not in t for _, t in agent.llm.checked)                   # a closed line is never checked
    assert load_scan(agent.scan_file).get("candidates") is None                 # nothing kept to close


def test_what_gemini_blocks_closes_and_the_borderline_only_when_needed(tmp_path, monkeypatch):
    agent = probing(scanning(tmp_path, monkeypatch), lambda text: "сцена" in text)
    scan(agent)
    answer = texts_sent(agent)[-1]
    assert answer.startswith("⚙️ Знайдено 1 рядків (сцени 1), 1 фактів, 1 думок, 1 підсумків; межових: 0.")
    assert "— Gemini блокує" in answer and "Gemini (Pro): блокує —" in answer
    kept = load_scan(agent.scan_file)
    assert len(kept["candidates"]) == 4 and kept["borderline"] == []            # «натяк» was not needed


def test_a_block_of_two_days_together_keeps_the_candidates_in_her_window(tmp_path, monkeypatch):
    """Each day passes alone, her window of both blocks: the candidates in it stay (the 16:34 block of 2026-11-04)."""
    agent = scanning(tmp_path, monkeypatch)
    agent.archive.append("y1", ms(23, 0) - 86_400_000, "private", "telegram", "Кіра", "сцена вчора ввечері")
    agent.private_history_hours, agent.private_history_min = 24, 0
    probing(agent, lambda text: "вчора ввечері" in text and "у стіни" in text)
    scan(agent)
    answer = texts_sent(agent)[-1]
    assert "Gemini (Pro): блокує — вікно доби" in answer and "пропускає" in answer
    kept = dict(load_scan(agent.scan_file)["candidates"])
    assert len([r for r in kept if r.startswith("L")]) == 2                     # both days' candidates, in the window
