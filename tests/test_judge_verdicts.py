"""v5.15 — the judge's verdicts: a clean line of the backup's talk is Gemini's again (her history, the recall, the
facts, the embeddings), a flagged one is censored for good, an unrated one keeps its mark; the watcher rates what still
waits, bounded, backing off after a tick that rated nothing (nio, Gemini and the judge mocked; an injected clock)."""

import asyncio
import logging

from agents.facts import add_fact, facts_section, load_facts
from agents.judge import CLEAN, FLAGGED, Item
from agents.logic import ENTRY_MAX_CHARS, history_entry
from agents.route import load_route
from tests.test_private_route import her, marks
from tests.test_private_runtime import ms

SECRET = "таємниця-5152"


class FakeJudge:
    """Flags a text with «погане», leaves one with «збій» unrated, rates the rest clean; records each call."""

    def __init__(self):
        self.calls = []

    async def rate(self, texts):
        self.calls.append(list(texts))
        return [FLAGGED if "погане" in t else None if "збій" in t else CLEAN for t in texts]


def judged_agent(tmp_path, monkeypatch):
    agent = her(tmp_path, monkeypatch)
    agent.judge = FakeJudge()
    agent.facts_dir, agent.facts_in_prompt, agent.fact_max_chars = tmp_path / "kira.facts", 10, 240
    return agent


def waiting_line(agent, key, speaker, text, mark="waiting"):
    agent.archive.append(key, ms(17), "private", "telegram", speaker, text)
    agent.archive.mark([key], mark)
    agent.private_history.append((speaker, history_entry(text)))
    if mark == "waiting":
        agent.close_lines([(speaker, text)])


def test_a_clean_line_is_geminis_again_a_flagged_one_censored_an_unrated_one_waits(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    agent = judged_agent(tmp_path, monkeypatch)
    long_clean = f"гарний довгий рядок {SECRET} " + "слово " * (ENTRY_MAX_CHARS // 6)
    waiting_line(agent, "tg:1", "Ich", long_clean)
    waiting_line(agent, "own:1", "Кіра", f"погане {SECRET}")
    waiting_line(agent, "tg:2", "Ich", f"збій {SECRET}")
    assert agent.gemini_history() == []
    asyncio.run(agent.ensure_judged())
    assert marks(agent) == {"tg:1": "clean", "own:1": "censored", "tg:2": "waiting"}
    assert agent.gemini_history() == [("Ich", history_entry(long_clean))]          # the cut form reopened too
    assert agent.archive.search_words("гарний", ("private",)) != []                  # the recall reads it again
    assert agent.archive.search_words("погане", ("private",)) == []
    embedded = asyncio.run(agent.embed_tick())
    assert embedded >= 1 and agent.archive.unembedded(10) == []                     # the clean line got its vector
    r = load_route(agent.route_file)
    assert r.judged == {"rated": 2, "flagged": 1}
    assert "judge: 2 rated (1 flagged, 1 unrated) — waiting" in caplog.text and SECRET not in caplog.text


def test_a_waiting_fact_follows_its_verdict(tmp_path, monkeypatch):
    agent = judged_agent(tmp_path, monkeypatch)
    add_fact(agent.facts_dir, "Любить каву зранку", 1, "asked", "2026-10-30", 50, 240, mark="waiting")
    add_fact(agent.facts_dir, "погане про нього", 1, "asked", "2026-10-30", 50, 240, mark="waiting")
    assert facts_section(load_facts(agent.facts_dir), 10, 240) is None             # both closed to Gemini
    asyncio.run(agent.ensure_judged())
    by_text = {f.text: f.mark for f in load_facts(agent.facts_dir)}
    assert by_text == {"Любить каву зранку": "clean", "погане про нього": "censored"}
    section = agent.facts_now()
    assert "Любить каву зранку" in section and "погане" not in section
    mirrored = dict(agent.archive.db.execute("SELECT text, mark FROM lines WHERE place = 'facts'").fetchall())
    assert mirrored == by_text                                                     # the archive's mirror follows


def test_a_flagged_line_that_passed_through_gemini_is_closed_too(tmp_path, monkeypatch):
    agent = judged_agent(tmp_path, monkeypatch)
    waiting_line(agent, "tg:1", "Ich", "погане, що Gemini колись пропустив", mark="gemini")
    agent.session.append(("Ich (наодинці)", "погане, що Gemini колись пропустив"))
    assert agent.gemini_history() != []
    asyncio.run(agent.judge_items([Item("line", "tg:1", "Ich", "погане, що Gemini колись пропустив")], "block"))
    assert marks(agent) == {"tg:1": "censored"} and agent.gemini_history() == []


def test_a_line_rated_meanwhile_is_never_rated_twice(tmp_path, monkeypatch):
    agent = judged_agent(tmp_path, monkeypatch)
    waiting_line(agent, "tg:1", "Ich", "привіт")
    item = Item("line", "tg:1", "Ich", "привіт")
    assert asyncio.run(agent.judge_items([item], "window")) == 1
    assert asyncio.run(agent.judge_items([item], "waiting")) == 0 and len(agent.judge.calls) == 1
    assert load_route(agent.route_file).judged == {"rated": 1, "flagged": 0}


def test_the_watcher_rates_the_backlog_in_bounded_ticks_and_backs_off_after_a_tick_that_rated_nothing(tmp_path,
                                                                                                    monkeypatch):
    from agents import agent as agent_module
    monkeypatch.setattr(agent_module, "JUDGE_TICK_LINES", 3)
    agent = judged_agent(tmp_path, monkeypatch)
    asyncio.run(agent.ensure_judged())
    assert agent.judge.calls == [] and agent._judge_retry_ms == 0                 # nothing waits: nothing called
    for i in range(5):
        waiting_line(agent, f"tg:{i}", "Ich", f"рядок {i}")
    asyncio.run(agent.ensure_judged())
    assert agent.judge.calls == [["рядок 0", "рядок 1", "рядок 2"]]               # the oldest, bounded per tick
    asyncio.run(agent.ensure_judged())
    assert agent.judge.calls[-1] == ["рядок 3", "рядок 4"] and set(marks(agent).values()) == {"clean"}
    waiting_line(agent, "tg:9", "Ich", "збій")
    asyncio.run(agent.ensure_judged())
    assert agent._judge_retry_ms == ms(18) + 60_000 and not agent.judge_is_due()   # rated nothing: a minute
    agent.clock = lambda: ms(18, 1)
    asyncio.run(agent.ensure_judged())
    assert agent._judge_retry_ms == ms(18, 1) + 120_000                          # … doubling


def test_without_the_judge_nothing_is_rated_and_the_talk_waits(tmp_path, monkeypatch):
    agent = her(tmp_path, monkeypatch)
    assert agent.judge is None and not agent.judge_is_due()
    waiting_line(agent, "tg:1", "Ich", "привіт")
    asyncio.run(agent.ensure_judged())
    assert marks(agent) == {"tg:1": "waiting"}


def test_purge_keeps_a_line_the_judge_rated_clean(tmp_path, monkeypatch):
    """v5.15 — `/purge` deletes what is still the backup's talk (`waiting`, `censored`); a clean line is Gemini's."""
    agent = judged_agent(tmp_path, monkeypatch)
    waiting_line(agent, "tg:1", "Ich", "привіт")
    waiting_line(agent, "tg:2", "Ich", "погане")
    waiting_line(agent, "tg:3", "Ich", "збій")
    asyncio.run(agent.ensure_judged())
    assert agent.purge_backup_talk() == (2, 0)
    assert marks(agent) == {"tg:1": "clean"} and agent.private_history == [("Ich", "привіт")]
