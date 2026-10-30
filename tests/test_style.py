"""v5.15.1 — how she says it this time (`agents/style.py`): live words offered or not, a turn of a real chat, an open
ending, where a voice tag may go, and the words she keeps repeating — drawn anew for each private answer (pure; the
randomness is scripted)."""

import asyncio
import random

from agents.style import FILLERS, FINISHED, MANNERS, OPEN_ENDINGS, TAG_PLACES, repeats, style_line


def scripted(*values):
    it = iter(values)
    return lambda: next(it)


def test_a_draw_with_live_words_a_turn_an_open_end_and_a_tag_in_the_middle():
    line = style_line(scripted(0.1, 0.0, 0.1, 0.0, 0.5, 0.0, 0.1, 0.0, 0.9, 0.0), [], tags=True)
    assert line.startswith("Як сказати цього разу: ")
    assert f"«{FILLERS[0]}» чи «{FILLERS[1]}»" in line                             # two picks, never the same
    assert MANNERS[0].capitalize() in line and OPEN_ENDINGS[0].capitalize() in line
    assert f"Позначку голосу, якщо вона є, — {TAG_PLACES[0]}, не на початку" in line and "сміх — не з першого" in line


def test_a_draw_without_live_words_turn_open_end_or_tag():
    line = style_line(scripted(0.9, 0.9, 0.9, 0.1), [], tags=True)
    assert "без слів-паразитів" in line and FINISHED in line
    assert "Позначки голосу цього разу не треба" in line
    assert not any(m.capitalize() in line for m in MANNERS)
    assert "Позначк" not in style_line(scripted(0.9, 0.9, 0.9), [], tags=False)    # no palette: no word of tags


def test_the_tag_at_the_start_is_rare_and_said_so():
    assert "можна й на самому початку" in style_line(scripted(0.9, 0.9, 0.9, 0.4), [], tags=True)


def test_over_many_draws_the_live_words_vary_and_some_answers_have_none():
    rng = random.Random(7).random
    lines = [style_line(rng, [], tags=True) for _ in range(200)]
    offered = {f for line in lines for f in FILLERS if f"«{f}»" in line}
    assert len(offered) >= len(FILLERS) * 2 // 3                                   # many different words
    assert 40 <= sum("без слів-паразитів" in line for line in lines) <= 120       # and often none
    starts = sum("на самому початку" in line for line in lines)
    assert starts < 40                                                             # the start: rare
    for line in lines:                                                             # she believes she is human
        assert not any(w in line.lower() for w in ("модел", "бот", "штучн", "інтелект", "ші "))


def test_an_open_end_is_rare_and_soft_and_a_thought_breaks_off_only_mid_message():
    # v5.15.2 (the owner, 2026-10-31): her messages broke off at the end too often and too hard
    rng = random.Random(11).random
    lines = [style_line(rng, [], tags=False) for _ in range(200)]
    open_ends = sum(any(e.capitalize() in line for e in OPEN_ENDINGS) for line in lines)
    assert 15 <= open_ends <= 65 and sum(FINISHED in line for line in lines) == 200 - open_ends
    for ending in OPEN_ENDINGS:                                                    # soft: never a cut
        assert "обірви" not in ending and "півслов" not in ending
    for manner in MANNERS:                                                         # a cut: mid-message only
        assert "обірви" not in manner or manner.startswith("посеред")
        assert "«…»" not in manner or manner.startswith("посеред")


def test_her_repeats_are_named_and_function_words_never():
    her = ["[laughs] Ого, це ж космос, чесно!", "Ого, ну це космос якийсь.", "Слухай, а якщо тільки так?",
           "Ого! Космос просто.", "Ну тобто тільки якщо тільки."]
    words, openings = repeats(her)
    assert words[0] == "космос" and "тільки" not in words and "laughs" not in words
    assert openings == ["ого"]                                                     # twice in her last four
    line = style_line(scripted(0.9, 0.9, 0.9), her, tags=False)
    assert "Ти вже кілька разів казала «космос»" in line and "Не починай з «ого»" in line
    assert repeats(["Добрий вечір", "Як день?"]) == ([], [])


def test_her_private_prompt_carries_the_line_for_this_answer(tmp_path, monkeypatch):
    from tests.test_archive import kira
    agent = kira(tmp_path, monkeypatch)
    agent.private_channel = "matrix"
    agent.private_history = [("Кіра", "Ого, космос!"), ("Ich", "так"), ("Кіра", "Ого, ну космос же."),
                             ("Ich", "ага"), ("Кіра", "Космос, кажу тобі."), ("Ich", "Ну що там?")]
    agent.rng = random.Random(3).random
    asyncio.run(agent.private_reply())
    system = agent.llm.calls[-1][1]
    assert "Як сказати цього разу: " in system and "Ти вже кілька разів казала «космос»" in system
