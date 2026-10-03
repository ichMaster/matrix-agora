import asyncio
import re
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agents.agent import Agent
from agents.plans import (
    KIND_ORDER,
    parse_items,
    plan_request,
    render_plan,
    roll_mutations,
    split_summary,
    strip_tags,
)
from tests.test_first_sync import CFG, FakeLLM
from tests.test_memory import BANNED


def seq(*values):
    it = iter(values)
    return lambda: next(it)


# --- mutation dice ---
def test_rate_zero_never_mutates():
    assert roll_mutations(5, 0.0, lambda: 0.0) == [None] * 5


def test_rate_one_always_mutates():
    out = roll_mutations(3, 1.0, lambda: 0.5)
    assert all(k in KIND_ORDER for k in out)


def test_dice_pick_items_and_kinds_deterministically():
    # item1: 0.1<0.3 → kind index int(0.0*5)=0; item2: 0.9 → none; item3: 0.2<0.3 → kind int(0.99*5)=4
    out = roll_mutations(3, 0.3, seq(0.1, 0.0, 0.9, 0.2, 0.99))
    assert out == [KIND_ORDER[0], None, KIND_ORDER[4]]


# --- items, tags, rendering ---
def test_parse_items_from_varied_output():
    assert parse_items("- а\n• б\n1. в\n2) г\nнотатка") == ["а", "б", "в", "г"]
    assert parse_items("просто рядок\nще один") == ["просто рядок", "ще один"]


def test_tags_are_stored_and_stripped():
    plan = render_plan(["Ринок", "Жовква"], [None, "spontaneous"], 120)
    assert "<!-- mutation: spontaneous -->" in plan
    clean = strip_tags(plan)
    assert "mutation" not in clean and "<!--" not in clean
    assert clean == "- Ринок\n- Жовква"


def test_render_respects_the_word_budget():
    plan = render_plan(["один два три", "чотири пʼять шість", "сім"], [None] * 3, 4)
    assert plan == "- один два три"


# --- the request ---
def test_plan_request_bends_exactly_the_rolled_items_and_hides_the_future():
    system, contents = plan_request(
        "day", "Ада", "Канон.", "субота, 3 жовтня", "Розділ зараз.", "Есеїстика виходить книжкою.",
        [("на тиждень", "- басейн")], "- вчорашній план", "вчора дощ",
        [None, "spontaneous", None, "cancelled", None], 120,
    )
    assert "пункт №2" in contents and "пункт №4" in contents and "пункт №1 " not in contents
    assert "не називай цього" in contents  # the next chapter is a silent direction
    assert "рівно 5 пунктів" in contents
    assert not BANNED.search(system + contents)


# --- the summary split feeding the journal ---
@pytest.mark.parametrize("raw,note,today", [
    ("НОТАТКА: довга нотатка\nСЬОГОДНІ: говорили про каву", "довга нотатка", "говорили про каву"),
    ("просто текст без міток", "просто текст без міток", None),
    ("НОТАТКА: тільки нотатка", "тільки нотатка", None),
])
def test_split_summary(raw, note, today):
    assert split_summary(raw) == (note, today)


# --- the agent: plans on four horizons, never rewritten, tags hidden ---
def make(tmp_path, llm):
    agent = Agent(CFG, llm=llm)
    agent.client = SimpleNamespace(room_send=AsyncMock(), room_typing=AsyncMock())
    agent.memory_file = tmp_path / "ada.memory.md"
    agent.rng = lambda: 0.0  # every item mutates (rate 0.3) with kind index 0
    return agent


def test_ensure_plans_writes_four_horizons_with_hidden_tags(tmp_path):
    agent = make(tmp_path, FakeLLM("- перше\n- друге\n- третє\n- четверте\n- пʼяте\n- шосте"))
    today = date(2026, 10, 3)
    asyncio.run(agent.ensure_plans(today))
    paths = agent.plan_paths(today)
    for horizon in ("year", "month", "week", "day"):
        assert paths[horizon].exists(), horizon
        assert "<!-- mutation:" in paths[horizon].read_text(encoding="utf-8")
    assert paths["week"].name == "week-2026-09-28.md"
    from datetime import datetime
    from zoneinfo import ZoneInfo
    section = agent.plans_section(datetime(2026, 10, 3, 12, tzinfo=ZoneInfo("Europe/Kyiv")))
    assert section.startswith("Твої плани:") and "<!--" not in section and "mutation" not in section


def test_existing_plans_are_never_rewritten(tmp_path):
    agent = make(tmp_path, FakeLLM("- нове"))
    today = date(2026, 10, 3)
    day = agent.plan_paths(today)["day"]
    day.parent.mkdir(parents=True)
    day.write_text("- старий план\n", encoding="utf-8")
    asyncio.run(agent.ensure_plans(today))
    assert day.read_text(encoding="utf-8") == "- старий план\n"


def test_summary_journal_gets_the_session_only_part(tmp_path):
    agent = make(tmp_path, FakeLLM("НОТАТКА: усе разом\nСЬОГОДНІ: лише сьогоднішнє"))
    agent.clock = lambda: 1_759_500_000_000  # fixed instant
    agent.session = [("Ich", "привіт")]
    asyncio.run(agent.summarize())
    assert agent.summary == "усе разом"
    journals = list((tmp_path / "ada.days").glob("*.talk.md"))
    assert len(journals) == 1
    assert re.fullmatch(r"\[\d\d:\d\d\] лише сьогоднішнє\n", journals[0].read_text(encoding="utf-8"))
