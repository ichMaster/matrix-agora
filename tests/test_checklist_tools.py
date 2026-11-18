"""v9.2 (AGORA-283) — her own ways to keep her checklist: `plan_add` and `plan_mark` in a person's words, offered on
Gemini beside her recall in both memory modes, each set under its own cache key; her calls kept in the answer and
written only when her Gemini answer goes out; a past day plan's outcomes once its day has ended. nio and the model
mocked; made-up items only."""

import asyncio
import dataclasses
from datetime import date

from agents.checklist import fold, load
from agents.logic import BANNED_RE
from agents.memory_tools import (
    DAY_TALK,
    PLAN_ADD,
    PLAN_MARK,
    RECALL,
    TOOLS_KEY,
    TOOLS_KEY_ALL,
    TOOLS_KEY_PLANS,
    declarations,
    plan_declarations,
)
from tests.test_lumi_memory import lumi
from tests.test_lumi_memory import ms as kms


def with_checklist(agent):
    caps = agent.cfg.capabilities | {"checklist"}
    agent.cfg = dataclasses.replace(agent.cfg, capabilities=caps)
    agent.checklist_days, agent.checklist_n = 7, 20
    return agent


def names(toolset):
    return [d.name for tool in toolset.tools for d in tool.function_declarations]


# --- the declarations -----------------------------------------------------------------------------------------------
def test_her_two_ways_are_in_a_persons_words():
    add, mark = plan_declarations()
    assert (add.name, mark.name) == (PLAN_ADD, PLAN_MARK)
    assert set(add.parameters.properties) == {"what", "who", "ich", "date", "time"} and add.parameters.required == ["what"]
    assert mark.parameters.required == ["number", "status"]
    assert mark.parameters.properties["status"].enum == ["зроблено", "не вийшло", "скасовано", "перенесено"]
    for d in (add, mark):
        words = d.description + " ".join(p.description or "" for p in d.parameters.properties.values())
        assert not BANNED_RE.search(words)
        assert not any(w in words.lower() for w in ("інструмент", "функці", "модел", "tool"))
    assert [d.name for d in declarations()[0].function_declarations] == [RECALL, DAY_TALK]      # as before


def test_the_sets_by_mode_and_capability_each_with_its_key(tmp_path, monkeypatch):
    agent = lumi(tmp_path, monkeypatch)
    plain = agent._memory_tools("private")
    assert names(plain) == [RECALL, DAY_TALK] and plain.key == TOOLS_KEY                    # `lumi`, no checklist
    with_checklist(agent)
    both = agent._memory_tools("private")
    assert names(both) == [RECALL, DAY_TALK, PLAN_ADD, PLAN_MARK] and both.key == TOOLS_KEY_ALL
    monkeypatch.setenv("MEMORY_MODE", "layered")
    alone = agent._memory_tools("private_nudge")
    assert names(alone) == [PLAN_ADD, PLAN_MARK] and alone.key == TOOLS_KEY_PLANS              # `layered`: hers alone
    assert agent._memory_tools("reply") is None                                               # never in Agora
    assert len({TOOLS_KEY, TOOLS_KEY_ALL, TOOLS_KEY_PLANS}) == 3


# --- the runner -----------------------------------------------------------------------------------------------------
def test_her_calls_are_answered_in_words_and_wait_in_the_answer(tmp_path, monkeypatch, caplog):
    agent = with_checklist(lumi(tmp_path, monkeypatch))
    run = lambda name, args: asyncio.run(agent._run_memory_tool(name, args))
    caplog.set_level("INFO")
    assert run(PLAN_ADD, {"what": "сходити в кіно", "who": "Ich", "ich": True, "date": "2026-11-15",
                          "time": "19:00"}) == "Записала: №1."
    assert run(PLAN_ADD, {"what": "подзвонити мамі"}) == "Записала: №2."
    assert run(PLAN_MARK, {"number": 2.0, "status": "зроблено"}) == "Позначила №2: зроблено."  # a number as Gemini's float
    assert "немає" in run(PLAN_MARK, {"number": 9, "status": "зроблено"})
    assert "нова дата" in run(PLAN_MARK, {"number": 1, "status": "перенесено"})
    assert "Можна позначити лише" in run(PLAN_MARK, {"number": 1, "status": "може"})
    assert "що саме" in run(PLAN_ADD, {"what": "  "})
    assert not agent.checklist_file.exists()                                                 # nothing written yet
    items = fold(agent._checklist_pending)
    assert [(x.id, x.status, x.due, x.ich) for x in items] == [(1, "planned", "2026-11-15T19:00", True),
                                                               (2, "done", None, False)]
    assert "кіно" not in caplog.text and "мамі" not in caplog.text                            # never what it says
    monkeypatch.setattr(agent, "_checklist_entries", lambda: 1 / 0)
    assert "не вийшло" in run(PLAN_ADD, {"what": "x"})                                        # never a raise


def test_kept_only_with_her_gemini_answer_sent(tmp_path, monkeypatch):
    agent = with_checklist(lumi(tmp_path, monkeypatch))
    asyncio.run(agent._run_memory_tool(PLAN_ADD, {"what": "сходити в кіно"}))
    agent._commit_checklist("backup")                                                        # a blocked answer's
    assert not agent.checklist_file.exists() and agent._checklist_pending == []
    asyncio.run(agent._run_memory_tool(PLAN_ADD, {"what": "сходити в кіно"}))
    agent._commit_checklist(None)                                                            # silence
    assert not agent.checklist_file.exists()
    asyncio.run(agent._run_memory_tool(PLAN_ADD, {"what": "сходити в кіно"}))
    agent._commit_checklist("gemini")
    entries, _ = load(agent.checklist_file)
    assert [(e["op"], e["id"], e["what"]) for e in entries] == [("add", 1, "сходити в кіно")]


def test_her_private_answer_keeps_her_calls_and_a_new_answer_starts_clean(tmp_path, monkeypatch):
    agent = with_checklist(lumi(tmp_path, monkeypatch))
    agent._checklist_pending = [{"op": "add", "id": 99, "what": "старе з мовчазної відповіді"}]
    real = agent._compose

    async def compose(prompt, **kw):
        if kw.get("kind") in ("private", "private_nudge"):
            await agent._run_memory_tool(PLAN_ADD, {"what": "сходити в кіно", "ich": True})
        return await real(prompt, **kw)

    monkeypatch.setattr(agent, "_compose", compose)
    agent.private_line("Підемо в п'ятницю в кіно?", kms(2026, 11, 14, 17, 59), "telegram", "tg:1")
    asyncio.run(agent.private_reply())
    entries, _ = load(agent.checklist_file)
    assert [(e["id"], e["what"], e["ich"], e["from"]) for e in entries] == [(1, "сходити в кіно", True, "tg:1")]


# --- her life's day plan --------------------------------------------------------------------------------------------
def test_a_past_day_plans_outcomes_once_and_today_never(tmp_path, monkeypatch):
    agent = with_checklist(lumi(tmp_path, monkeypatch))
    today = date(2026, 11, 14)
    for d, text in ((date(2026, 11, 13), "- лекція\n- кава <!-- mutation: postponed -->\n"),
                    (date(2026, 11, 12), "- спортзал <!-- mutation: cancelled -->\n"),
                    (today, "- сьогоднішнє\n")):
        path = agent.plan_paths(d)["day"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    agent.ensure_plan_outcomes(today)
    agent.ensure_plan_outcomes(today)                                                        # a second tick: nothing
    items = fold(load(agent.checklist_file)[0])
    assert [(x.id, x.what, x.status, x.plan_day) for x in items] == [
        (1, "спортзал", "cancelled", "2026-11-12"), (2, "лекція", "done", "2026-11-13"),
        (3, "кава", "moved", "2026-11-13")]
    assert all(x.plan_day != today.isoformat() for x in items)
