"""The cat's past-life memories (v4.3): authored theses, picked by the talk, retold — never quoted."""

import asyncio
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agents.agent import Agent
from agents.config import AgentConfig
from agents.logic import BANNED_RE
from agents.pastlife import PASTLIFE_PREFIX, ThesesError, Thesis, parse_theses, pick_memory
from agents.roster import TYPES, load_roster
from agents.turns import mentions
from tests.test_first_sync import CFG

REAL = Path("agents/canon/kit.memories.md")
THESES = (
    Thesis(("бекап", "backup"), "Бекапи були щоночі, відновлення жодного разу."),
    Thesis(("п'ятниц", "deploy"), "Деплой у п'ятницю о 17:55."),
    Thesis(("dns",), "Завжди DNS."),
    Thesis(("кава", "каву"), "Кавоварка в серверній мала найкращий аптайм."),
)


# --- the file -------------------------------------------------------------------------------------------------------
def test_the_real_file_holds_60_to_100_theses_with_tags():
    theses = parse_theses(REAL.read_text(encoding="utf-8"))
    assert 60 <= len(theses) <= 100  # ROADMAP §v4.3; the owner edits the file (review #11)
    assert all(t.tags and t.text for t in theses)
    assert all(tag == tag.lower() for t in theses for tag in t.tags)


def test_headings_and_prose_are_ignored_and_a_broken_thesis_is_named():
    assert parse_theses("# Заголовок\n\nПроза.\n- [a, b] Текст.\n## Розділ\n- [c] Ще.") == (
        Thesis(("a", "b"), "Текст."), Thesis(("c",), "Ще."))
    for bad in ("- [a, b Текст без дужки", "- [] Без тегів", "- [a]"):
        with pytest.raises(ThesesError, match="line 1"):
            parse_theses(bad)


def test_no_thesis_names_ich_ada_or_bruno_or_says_what_it_must_not():
    """The phase DoD: the past is his alone — no room member, no hidden end, no word that outs anyone."""
    roster = load_roster("agora")
    people = [m for m in roster.values() if m.localpart != "kit"]
    for t in parse_theses(REAL.read_text(encoding="utf-8")):
        assert not any(mentions(t.text, p.name_forms, p.user_id) for p in people), t.text
        assert not re.search(r"\bich\b", t.text, re.IGNORECASE), t.text
        assert "2038" not in t.text and not BANNED_RE.search(t.text), t.text


# --- pick_memory ----------------------------------------------------------------------------------------------------
def test_pick_memory_is_deterministic_per_event():
    picks = [pick_memory(f"$e{i}", "", THESES, set()) for i in range(40)]
    assert picks == [pick_memory(f"$e{i}", "", THESES, set()) for i in range(40)]
    assert set(picks) == {0, 1, 2, 3}  # every thesis is reachable


@pytest.mark.parametrize("said,expect", [
    ("Коли ти востаннє робив бекап?", 0),
    ("Знову п’ятниця, і знову деплой", 1),      # a typographic apostrophe and a case form
    ("у пʼятницю ввечері", 1),                    # the modifier-letter apostrophe
    ("DNS знову впав", 2),
    ("зварю каву", 3),
])
def test_a_tag_in_the_message_is_preferred(said, expect):
    assert all(pick_memory(f"$e{i}", said, THESES, set()) == expect for i in range(20))


def test_no_thesis_repeats_until_all_are_told_then_they_start_over():
    told: set[int] = set()
    for i in range(len(THESES)):
        pick = pick_memory(f"$e{i}", "бекап", THESES, told)
        assert pick not in told
        told.add(pick)
    assert told == {0, 1, 2, 3}
    assert pick_memory("$again", "бекап", THESES, told) == 0  # all told → all are candidates, the tag wins again
    assert pick_memory("$e", "", (), set()) is None


# --- the agent: the section, the verbatim rule, `told` --------------------------------------------------------------
class SeqLLM:
    """Replies in order; records each system instruction."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.prompts = []

    async def generate(self, transcript, system_instruction, max_output_tokens=400, kind="reply"):
        self.prompts.append(system_instruction)
        return self.replies.pop(0) if self.replies else "мрр"


def cat(llm, memory_p, theses=THESES):
    cfg = AgentConfig(**{**CFG.__dict__, "name": "Кіт", "user_id": "@kit:agora.lan", "type": "creature",
                         "capabilities": TYPES["creature"] - {"mood"}, "theses": theses})
    agent = Agent(cfg, llm=llm)
    agent.client = SimpleNamespace(room_send=AsyncMock(), room_typing=AsyncMock())
    agent.cat_memory_p = memory_p
    agent.rng = lambda: 0.5
    agent.history = [("Ich", "коли був останній бекап?")]
    agent.timeline = [("Ich", 0, "$o", False)]
    return agent


def test_a_thesis_enters_the_prompt_with_its_probability_and_is_marked_told_when_sent():
    llm = SeqLLM("Нічні копії. Жодної перевірки.")
    agent = cat(llm, memory_p=1.0)
    assert asyncio.run(agent.reply("!room")) is True
    assert PASTLIFE_PREFIX + THESES[0].text in llm.prompts[0]          # the tag «бекап» chose it
    assert agent.told == {0}
    never = SeqLLM("мрр")
    quiet = cat(never, memory_p=0.0)
    asyncio.run(quiet.reply("!room"))
    assert "Спогад з минулого життя" not in never.prompts[0] and quiet.told == set()


def test_a_verbatim_retelling_is_regenerated_once():
    llm = SeqLLM("Бекапи були щоночі, відновлення жодного разу.", "Копії щоночі. Ніколи не перевіряв.")
    agent = cat(llm, memory_p=1.0)
    assert asyncio.run(agent.reply("!room")) is True
    assert len(llm.prompts) == 2
    assert agent.client.room_send.await_args.kwargs["content"]["body"] == "Копії щоночі. Ніколи не перевіряв."


def test_twice_verbatim_means_silence_and_nothing_is_told():
    quote = "Бекапи були щоночі, відновлення жодного разу."
    llm = SeqLLM(quote, quote)
    agent = cat(llm, memory_p=1.0)
    assert asyncio.run(agent.reply("!room")) is False
    agent.client.room_send.assert_not_awaited()
    assert len(llm.prompts) == 2 and agent.told == set()


def test_a_persona_never_gets_a_past_life_section():
    from tests.test_first_sync import FakeLLM, make_agent
    llm = FakeLLM()
    agent = make_agent(llm)
    agent.cat_memory_p = 1.0
    asyncio.run(agent.reply("!room"))
    assert "Спогад з минулого життя" not in llm.calls[0][1] and not agent.cfg.can("pastlife")


COMMON = ("багато", "цікаво", "цікава", "почати", "початок", "справа", "справді", "перспектива", "посуд", "на сходах",
          "прозорі", "діалоги", "психологи", "до побачення", "відповідь", "відповідно", "місце", "на місці", "гуляти",
          "прогулянка", "регулярно", "зачекай секунду", "привіт", "дякую", "добре", "швидко", "пам'ятаю",
          "минулого тижня", "історія", "процес", "перевірю", "судячи з усього", "доступний", "жорстко", "література",
          "редакторка", "жарт", "сьогодні", "завтра", "вчора", "як справи", "що нового", "desktop", "blog", "login",
          "groups", "circle", "afraid", "typing", "shopping", "topic", "upset")


@pytest.mark.parametrize("said", COMMON)
def test_everyday_words_trigger_no_tag_of_the_real_file(said):
    """v4.3 review #3: tags match at a word start, and no tag starts an everyday word."""
    from agents.pastlife import tag_found
    hits = [tag for t in parse_theses(REAL.read_text(encoding="utf-8")) for tag in t.tags if tag_found(tag, said)]
    assert hits == [], hits


def test_a_tag_matches_only_at_a_word_start():
    from agents.pastlife import tag_found
    assert tag_found("бекап", "з бекапом") and tag_found("п'ятниц", "у п'ятницю")
    assert not tag_found("чат", "почати") and not tag_found("ping", "typing") and not tag_found("зорі", "прозорі")
