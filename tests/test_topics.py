"""v5.25 — her topics (`agents/topics.py`): after each of her private answers one Flash call lists what their last
`TOPICS_LINES` messages are about, and her next prompt holds the list and the line that she picks which to go on with
(pure parts with plain data; the agent with a fake `generate`; made-up lines only)."""

import asyncio
import json
import logging

from agents.logic import BANNED_RE
from agents.topics import TOPICS_CHOOSE, TOPICS_MAX, parse_topics, topics_request, topics_section
from tests.test_archive import EmbedLLM, kira

ANSWER = json.dumps({"topics": [{"topic": "його звіти", "her": 3, "his": 1},
                                {"topic": "вечір на Замку", "her": 2, "his": 1}]}, ensure_ascii=False)


class TopicsLLM(EmbedLLM):
    """Flash for the list: `answer` for the kind `topics` (None: a failure), each request recorded."""

    def __init__(self, answer=ANSWER):
        super().__init__()
        self.answer, self.asked = answer, []

    async def generate(self, transcript, system_instruction, max_output_tokens=400, kind="reply"):
        if kind == "topics":
            self.asked.append((transcript, system_instruction))
            return self.answer
        return await super().generate(transcript, system_instruction, max_output_tokens, kind)


def test_the_request_is_both_sides_as_two_people_and_their_closeness_in_fixed_words():
    system, contents = topics_request("Кіра", [("Ich", "Привіт"), ("Кіра", "Привіт!")])
    assert contents == "Переписка:\nIch: Привіт\nКіра: Привіт!"
    assert "двох людей, Кіра та Ich" in system and f"не більше {TOPICS_MAX} тем" in system
    assert "«наш флірт і ніжність» — без подробиць" in system and '"her"' in system and '"his"' in system
    assert not BANNED_RE.search(system) and "бот" not in system.lower()


def test_the_answer_is_bounded_and_a_bad_one_is_none():
    assert parse_topics(ANSWER, 20) == [("його звіти", 3, 1), ("вечір на Замку", 2, 1)]
    assert parse_topics(f"```json\n{ANSWER}\n```", 20) == parse_topics(ANSWER, 20)          # fenced: still read
    bad = json.dumps({"topics": [
        {"topic": "забагато", "her": 30, "his": 1},          # more than the lines read: cut to them
        {"topic": "мінус", "her": -1, "his": 1},
        {"topic": "не число", "her": "3", "his": 1},
        {"topic": "так", "her": True, "his": 1},
        {"topic": "нікого", "her": 0, "his": 0},             # nobody touched it
        {"topic": "х" * 61, "her": 1, "his": 1},             # too long
        {"topic": "що вона модель", "her": 1, "his": 1},     # names what she is
        {"topic": "  мій сценарій.  ", "her": 3, "his": 1},
    ]}, ensure_ascii=False)
    assert parse_topics(bad, 20) == [("забагато", 20, 1), ("мій сценарій", 3, 1)]
    many = json.dumps({"topics": [{"topic": f"тема {i}", "her": 1, "his": 1} for i in range(9)]})
    assert len(parse_topics(many, 20)) == TOPICS_MAX
    for raw in ("", "нема", "{не json}", '{"topics": "так"}', "[1, 2]"):
        assert parse_topics(raw, 20) is None, raw
    assert parse_topics('{"topics": []}', 20) == []


def test_the_section_counts_in_ukrainian_and_ends_with_her_choice():
    section = topics_section([("його звіти", 7, 1), ("вечір на Замку", 2, 21), ("кіно", 0, 11)], 20)
    assert section.startswith("Про що ваша розмова (з останніх 20 повідомлень):\n")
    assert "- його звіти — ти 7 разів, він 1 раз;" in section
    assert "- вечір на Замку — ти 2 рази, він 21 раз;" in section and "- кіно — ти 0 разів, він 11 разів;" in section
    assert section.endswith("\n\n" + TOPICS_CHOOSE) and topics_section([], 20) is None
    assert not BANNED_RE.search(TOPICS_CHOOSE)
    # the owner, 2026-11-05: one topic a message, never a jump in the middle of one
    assert "одне повідомлення — одна тема" in TOPICS_CHOOSE and "а далі говори" not in TOPICS_CHOOSE
    # the same day: her interest decides — on the two of them she stays; from a dull topic she may slip away
    assert "Поки ви про те, що тобі з ним найцікавіше" in TOPICS_CHOOSE
    assert "без «хоча…» чи «хотя…», «до речі» чи «кстаті»" in TOPICS_CHOOSE         # … and her surzhyk's words
    assert "Тема, яка тобі не цікава, — інша справа" in TOPICS_CHOOSE
    assert "«наш флірт і ніжність» — без подробиць" in topics_request("Кіра", [("Ich", "Привіт")])[0]


def talking(tmp_path, monkeypatch, llm=None):
    agent = kira(tmp_path, monkeypatch, llm or TopicsLLM())
    agent.topics_lines = 4
    now = agent.clock()
    lines = [("Ich", "Як день?"), ("Кіра", "Пишу сценарій"), ("Ich", "закрите-слово"), ("Кіра", "А в тебе звіти?"),
             ("Ich", "Так, звіти"), ("Кіра", "Тоді до вечора")]
    for i, (who, text) in enumerate(lines):
        agent.archive.append(f"tg:{i}", now - (60 - i) * 60_000, "private", "telegram", who, text)
    agent.archive.mark(["tg:2"], "blocked")
    return agent


def test_the_list_reads_the_last_open_lines_both_sides_and_the_log_holds_no_topic(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    agent = talking(tmp_path, monkeypatch)
    asyncio.run(agent.ensure_topics())
    contents, system = agent.llm.asked[-1]
    assert system.startswith("Перед тобою кінець переписки двох людей, Кіра та Ich")
    assert contents == "Переписка:\nКіра: Пишу сценарій\nКіра: А в тебе звіти?\nIch: Так, звіти\nКіра: Тоді до вечора"
    assert "закрите" not in contents and "Як день" not in contents                  # closed; past `TOPICS_LINES`
    assert agent._topics == ([("його звіти", 3, 1), ("вечір на Замку", 2, 1)], 4)
    assert "topics: 2 from 4 lines" in caplog.text and "звіти" not in caplog.text and "Замку" not in caplog.text


def test_a_failure_or_a_bad_answer_keeps_the_list_before_it(tmp_path, monkeypatch, caplog):
    agent = talking(tmp_path, monkeypatch)
    asyncio.run(agent.ensure_topics())
    before = agent._topics
    for answer in (None, "не json"):
        agent.llm.answer = answer
        asyncio.run(agent.ensure_topics())
        assert agent._topics == before
    assert "the list before kept" in caplog.text


def test_with_no_lines_to_read_nothing_is_asked(tmp_path, monkeypatch):
    agent = talking(tmp_path, monkeypatch)
    agent.topics_lines = 0                                                          # the owner's switch
    asyncio.run(agent.ensure_topics())
    agent.topics_lines = 4
    agent.archive.mark([f"tg:{i}" for i in range(6)], "blocked")                    # nothing open to Gemini
    asyncio.run(agent.ensure_topics())
    assert agent.llm.asked == [] and agent._topics is None


def test_her_private_prompt_holds_the_list_and_her_choice_and_her_answer_asks_for_the_next(tmp_path, monkeypatch):
    agent = talking(tmp_path, monkeypatch)
    agent.private_channel = "matrix"
    agent.private_history = [("Ich", "Привіт")]
    spawned = []
    agent._spawn = spawned.append
    asyncio.run(agent.private_reply())                                              # before the first list: none
    assert TOPICS_CHOOSE not in agent.llm.calls[-1][1]
    assert [c.__qualname__ for c in spawned] == ["Agent.ensure_topics"]             # her answer asks for the list
    for coro in spawned:
        asyncio.run(coro)
    agent.private_history.append(("Ich", "Ну що?"))
    asyncio.run(agent.private_reply())
    system = agent.llm.calls[-1][1]
    assert "Про що ваша розмова (з останніх 4 повідомлень):" in system and TOPICS_CHOOSE in system
    assert system.index("Як сказати цього разу") < system.index("Про що ваша розмова")   # after the style line
    agent.private_history.append(("Ich", "А на резерві?"))                          # the backup: never the list
    prompt, _ = asyncio.run(agent._backup_private_prompt("brief"))
    assert TOPICS_CHOOSE not in prompt and "Про що ваша розмова" not in prompt
    agent.topics_lines = 0                                                          # the owner's switch: no list
    agent.private_history.append(("Ich", "А тепер?"))
    asyncio.run(agent.private_reply())
    assert TOPICS_CHOOSE not in agent.llm.calls[-1][1]
    for coro in spawned[1:]:
        coro.close()
