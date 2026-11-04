"""v5.15.1 — how she says it this time (`agents/style.py`): live words offered or not, a turn of a real chat, an open
ending, where a voice tag may go, and the words she keeps repeating — drawn anew for each private answer (pure; the
randomness is scripted). v5.24: how a finished thought ends, no send-off most of the time, what her last endings
shared, and a repeat by the word's stem; v5.25: something of her own (made-up lines only)."""

import asyncio
import random

from agents.style import (
    ENDINGS,
    FILLERS,
    FINISHED,
    MANNERS,
    NO_SENDOFF,
    OPEN_ENDINGS,
    TAG_PLACES,
    endings,
    repeats,
    stem,
    style_line,
)


def scripted(*values):
    it = iter(values)
    return lambda: next(it)


def test_a_draw_with_live_words_a_turn_an_open_end_and_a_tag_in_the_middle():
    line = style_line(scripted(0.1, 0.0, 0.1, 0.0, 0.5, 0.0, 0.1, 0.0, 0.1, 0.9, 0.0), [], tags=True)
    assert line.startswith("Як сказати цього разу: ")
    assert f"«{FILLERS[0]}» чи «{FILLERS[1]}»" in line                             # two picks, never the same
    assert MANNERS[0].capitalize() in line and OPEN_ENDINGS[0].capitalize() in line
    assert f"Позначку голосу, якщо вона є, — {TAG_PLACES[0]}, не на початку" in line and "сміх — не з першого" in line
    assert NO_SENDOFF in line and FINISHED not in line                             # an open end: no ending drawn


def test_a_draw_without_live_words_turn_open_end_or_tag():
    line = style_line(scripted(0.9, 0.9, 0.9, 0.0, 0.9, 0.1), [], tags=True)
    assert "без слів-паразитів" in line and f"{FINISHED} {ENDINGS[0]}" in line and NO_SENDOFF not in line
    assert "Позначки голосу цього разу не треба" in line
    assert not any(m.capitalize() in line for m in MANNERS)
    assert "Позначк" not in style_line(scripted(0.9, 0.9, 0.9, 0.0, 0.9), [], tags=False)  # no palette: no tags


def test_the_tag_at_the_start_is_rare_and_said_so():
    assert "можна й на самому початку" in style_line(scripted(0.9, 0.9, 0.9, 0.0, 0.9, 0.4), [], tags=True)


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
    her = ["[laughs] Ого, це ж космос! Чесно кажучи, не чекала. А ти як?",
           "Ого, ну це космос якийсь. Піду поставлю чайник. Дощить.",
           "Слухай, а якщо тільки так?",
           "Ого! Космосу не буває забагато. Дивлюсь у вікно. Хмари.",
           "Ну тобто тільки якщо тільки."]
    words, openings = repeats(her)
    assert words[0] == "космосу" and "тільки" not in words and "laughs" not in words   # by stem, as said last
    assert openings == ["ого"]                                                     # twice in her last four
    line = style_line(scripted(0.9, 0.9, 0.9, 0.0, 0.9), her, tags=False)
    assert "Ти вже кілька разів казала «космосу»" in line and "Не починай з «ого»" in line
    assert "закінчувала тим самим" not in line                                     # her endings differ
    assert repeats(["Добрий вечір", "Як день?"]) == ([], [])


def test_a_word_counts_by_its_stem():
    """v5.24: «звіти», «звітів» and «звіт» are one word; a short word is never cut below four letters."""
    for a, b in (("звіти", "звітів"), ("звіт", "звіти"), ("хакере", "хакерську"), ("сьомій", "сьому"),
                 ("вечора", "вечорі"), ("куртку", "куртка"), ("запізнюйся", "запізнитися")):
        assert stem(a) == stem(b), (a, b)
    assert stem("звіти") != stem("зустріч") and stem("чаєм") == "чаєм"
    words, _ = repeats(["Пишу звіти зранку. Ну і день. Ок.", "Ще два звітів лишилось. Ну. Добре.",
                        "Звіт майже готовий. Ага. Так."])
    assert words == ["звіт"]


def test_what_her_last_endings_shared_is_named_once():
    """v5.24 (the owner, 2026-11-04: «вони постійно закінчує одним і тим саме»): the same move at the end of three of
    her last six lines, in other words each time, is named; the word is not named twice."""
    her = ["Мама кликала на вечерю, я відмовилась. Добивай свої звіти і до вечора!",
           "Чай уже в термосі. Розгрібай ті звіти, бо я чекаю вечора.",
           "Дивлюсь на хмари з балкона. Закривай звітів купу і до вечора не запізнюйся.",
           "Сьогодні вітер. Ну, побачимось."]
    assert endings(her) == ["звітів", "вечора"]
    line = style_line(scripted(0.9, 0.9, 0.9, 0.0, 0.9), her, tags=False)
    assert "Останні повідомлення ти закінчувала тим самим («звітів», «вечора»)" in line
    assert "хіба що він сам спитає" in line and "кілька разів казала «звіт" not in line
    assert endings(her[:2]) == [] and endings([]) == []                            # fewer than three: nothing


def test_how_she_ends_is_drawn_and_most_answers_have_no_send_off():
    rng = random.Random(5).random
    lines = [style_line(rng, [], tags=False) for _ in range(400)]
    assert 240 <= sum(NO_SENDOFF in line for line in lines) <= 360                 # most, never all
    for ending in ENDINGS:
        assert sum(ending in line for line in lines) >= 40                         # each of them
    for text in (*ENDINGS, NO_SENDOFF):                                            # she believes she is human
        assert not any(w in text.lower() for w in ("модел", "бот", "штучн", "інтелект", "ші "))


def test_now_and_then_something_of_her_own_from_the_sections_of_her_day():
    """v5.25 (the owner, 2026-11-04: «2-4 підтверджую»): about one answer in three, with the sections of her day
    named; never without them."""
    from agents.style import OWN
    line = style_line(scripted(0.9, 0.9, 0.9, 0.0, 0.9, 0.1), [], tags=False, own="«Сьогодні» чи «Що ти сьогодні думала»")
    assert f"{OWN} прочитала чи подумала (із «Сьогодні» чи «Що ти сьогодні думала»)." in line
    rng = random.Random(9).random
    lines = [style_line(rng, [], tags=False, own="«Сьогодні»") for _ in range(400)]
    assert 80 <= sum(OWN in line for line in lines) <= 160
    assert not any(OWN in style_line(random.Random(9).random, [], tags=False) for _ in range(50))
    assert not any(w in OWN.lower() for w in ("модел", "бот", "штучн", "інтелект", "ші "))


def test_her_private_prompt_carries_the_line_for_this_answer_from_her_open_lines_only(tmp_path, monkeypatch):
    """v5.24: her repeats are read from the lines open to Gemini — a word of a closed line is never named."""
    from tests.test_archive import kira
    agent = kira(tmp_path, monkeypatch)
    agent.private_channel = "matrix"
    lines = [("Кіра", "Ого, космос! Ну таке. Ага."), ("Ich", "так"), ("Кіра", "Ого, ну космос же. Слухай. Так."),
             ("Ich", "ага"), ("Кіра", "Космос, кажу тобі. Ох. Ну."), ("Ich", "Ну що там?")]
    closed = [("Кіра", "Закрите-слово тут. Ну. Так.")] * 3
    agent.private_history = closed + lines
    now = agent.clock()
    for i, (who, text) in enumerate(closed + lines):
        agent.archive.append(f"m:{i}", now - (60 - i) * 60_000, "private", "matrix", who, text)
    agent.archive.mark([f"m:{i}" for i in range(len(closed))], "blocked")
    agent.rng = random.Random(3).random
    asyncio.run(agent.private_reply())
    system = agent.llm.calls[-1][1]
    assert "Як сказати цього разу: " in system and "Ти вже кілька разів казала «космос»" in system
    assert "закрите" not in system.lower()
    from agents.private import PRIVATE_BRIEF
    assert "він почув: не повторюй цього" in PRIVATE_BRIEF and PRIVATE_BRIEF in system   # v5.25: Лілі's first rule
    assert "розкажи й щось своє" not in system                                       # no section of her day: never
    agent.cfg = agent.cfg.__class__(**{**agent.cfg.__dict__, "capabilities": agent.cfg.capabilities | {"thoughts"}})
    agent.rng = lambda: 0.1                                                         # every draw taken
    asyncio.run(agent.private_reply())
    assert "розкажи й щось своє" in agent.llm.calls[-1][1] and "(із «Що ти сьогодні думала»)" in agent.llm.calls[-1][1]
