"""v5.16 — her private prompt for Gemini kept in parts (`PromptParts`): the fixed layers and the closable items by id
— her history's lines, the recall's groups, the facts the section shows, today's thoughts — drawn whole it is the
very prompt Gemini got, and any part left out is gone from it (Gemini mocked; an injected clock; made-up lines)."""

import asyncio

from agents.facts import add_fact
from agents.private import PRIVATE_BRIEF
from agents.thoughts import Thought, archive_key
from agents.world import local_now
from tests.test_archive import EmbedLLM
from tests.test_private_runtime import ms
from tests.test_thoughts import thinking_kira


class Capture(EmbedLLM):
    """Gemini: answers, and keeps each call's instruction and transcript."""

    def __init__(self):
        super().__init__()
        self.seen = []

    async def generate(self, transcript, system_instruction, max_output_tokens=400, kind="reply"):
        self.seen.append((system_instruction, transcript))
        return "Від Gemini."


def her(tmp_path, monkeypatch):
    agent = thinking_kira(tmp_path, monkeypatch)
    agent.llm = Capture()
    agent.responder.llm = agent.llm
    agent.thoughts_in_prompt = 3
    agent.facts_dir, agent.facts_in_prompt, agent.fact_max_chars = tmp_path / "kira.facts", 10, 240
    now = local_now(agent.clock(), agent.tz)
    for i, text in enumerate(("Ада принесла зорі.", "Бруно бачив телескоп на даху.", "Леон пив каву.")):
        agent.archive.append(f"$a{i}", ms(10, i) - 86_400_000, "agora", "matrix", "Ада", text)  # yesterday
    add_fact(agent.facts_dir, "Любить чай із чебрецем", 1, "private", "2026-10-19", 50, 240)
    add_fact(agent.facts_dir, "Мріє про власний телескоп", 0, "private", "2026-10-19", 50, 240)  # recalled only
    agent.keep_thought(now.replace(day=now.day - 1, hour=21), Thought("21:00", "reflection", "thought_private",
                                                                      "private", "Про телескоп він питав двічі."))
    agent.keep_thought(now.replace(hour=9), Thought("09:00", "news", "thought", "zaxid", "Ранок у куполі."))
    agent.private_line("Добрий вечір", ms(16), "telegram", "tg:1")
    agent.private_line("Як там телескоп?", ms(17), "telegram", "tg:2")
    return agent


def capture(agent):
    parts: list = []
    text, block = asyncio.run(agent._gemini_text(PRIVATE_BRIEF, "private", [], parts))
    assert text is not None and block is None and len(parts) == 1
    return parts[0]


def test_drawn_whole_the_parts_are_the_prompt_gemini_got_and_the_same_as_before(tmp_path, monkeypatch):
    agent = her(tmp_path, monkeypatch)
    parts = capture(agent)
    assert parts.render() == agent.llm.seen[-1]                                   # byte for byte, both
    assert asyncio.run(agent._gemini_private_prompt(PRIVATE_BRIEF)) == parts.render()[0]  # as `build_prompt` drew it
    ids = parts.item_ids()
    assert {"line:tg:1", "line:tg:2", "line:$a1"} <= set(ids)                     # history, a recalled Agora line
    assert any(i.startswith("fact:") for i in ids) and any(i.startswith("thought:") for i in ids)
    assert {"canon", "world", "private"} <= set(parts.layer_names()) and "name" not in parts.layer_names()
    assert not {"recalled", "facts", "thoughts"} & set(parts.layers)               # drawn from the items, never layers


def test_a_part_left_out_is_gone_and_nothing_else(tmp_path, monkeypatch):
    agent = her(tmp_path, monkeypatch)
    parts = capture(agent)
    system, transcript = parts.render()
    everything = set(parts.item_ids())

    def without(*ids):
        return parts.render(everything - set(ids))

    s, t = without("line:tg:1")                                                   # a history line
    assert "Добрий вечір" in transcript and "Добрий вечір" not in t and s == system
    s, _ = without("line:$a1")                                                    # a recalled line: its group stays
    assert "телескоп на даху" in system and "телескоп на даху" not in s
    assert "Ада принесла зорі." in s and "Леон пив каву." in s
    pinned = next(i for i, f in parts.facts if f.text == "Любить чай із чебрецем")
    s, _ = without(pinned)                                                        # a fact the section shows
    assert "чебрецем" in system and "чебрецем" not in s
    day = local_now(agent.clock(), agent.tz).date()
    morning = archive_key(day.isoformat(), Thought("09:00", "news", "thought", "zaxid", "Ранок у куполі."), 0)
    s, _ = without(morning)                                                       # today's thought
    assert "Ранок у куполі." in system and "Ранок у куполі." not in s
    s, _ = parts.render(keep_layers=set(parts.layer_names()) - {"canon"})         # a layer
    assert "Канон." in system and "Канон." not in s and "Добрий вечір" in parts.render()[1]
    s, t = parts.render(set(), set())                                             # nothing at all: the rules alone
    assert t == "" and s.strip().startswith("Ти — Кіра.")


def test_without_her_archive_the_history_has_no_closable_line(tmp_path, monkeypatch):
    agent = her(tmp_path, monkeypatch)
    agent.archive = None
    parts = capture(agent)
    assert all(i is None for i, _ in parts.history) and parts.groups == []
    assert parts.render(set(), set(parts.layer_names()))[1] == parts.render()[1]  # never left out
