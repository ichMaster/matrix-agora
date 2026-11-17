"""v6.5.1 — a person's own character alone with the owner (the owner, 2026-11-10, of Устина: «дуже приторно солодка …
щоб вона не була настільки піддатлива і мала свій характер»; «додай їй більше слів паразитів»; «хай не починається на
"ой"»): her TOML's `fillers`, `never_open` and `private_lead`; Кіра's prompts unchanged (made-up lines only)."""

import asyncio
import random
import tomllib
from pathlib import Path

import pytest

from agents.config import AgentConfig, ConfigError, load_config
from agents.logic import cut_openings
from agents.private import PRIVATE_AS_FELT, PRIVATE_BRIEF, PRIVATE_BRIEF_LEAD, PRIVATE_WARM, private_brief
from agents.style import (
    DETAIL_ENDING,
    FILLERS,
    MANNERS,
    SLANG,
    SLANG_MANNERS,
    SPOKEN,
    filler_repeats,
    style_line,
)
from agents.topics import TOPICS_CHOOSE, TOPICS_CHOOSE_LEAD, TOPICS_HELD, TOPICS_LED, topics_section
from tests.test_config import ENV
from tests.test_topics import talking

ROOT = Path(__file__).resolve().parent.parent


# --- the pure parts ---------------------------------------------------------------------------------------------------
def test_her_lead_brief_differs_from_the_warm_one_only_by_how_she_speaks():
    assert PRIVATE_WARM in PRIVATE_BRIEF and PRIVATE_BRIEF_LEAD == PRIVATE_BRIEF.replace(PRIVATE_WARM, PRIVATE_AS_FELT)
    assert "тепло" not in PRIVATE_BRIEF_LEAD and "так, як ти зараз почуваєшся" in PRIVATE_BRIEF_LEAD
    assert "він почув: не повторюй цього" in PRIVATE_BRIEF_LEAD                      # v5.25's rule stays
    assert private_brief(False) == PRIVATE_BRIEF and private_brief(True) == PRIVATE_BRIEF_LEAD


def test_with_the_lead_she_may_turn_the_topic_herself_still_one_topic_a_message():
    assert TOPICS_HELD in TOPICS_CHOOSE and TOPICS_HELD not in TOPICS_CHOOSE_LEAD and TOPICS_LED in TOPICS_CHOOSE_LEAD
    assert "доки він сам не змінить тему" not in TOPICS_CHOOSE_LEAD
    assert "одне повідомлення — одна тема" in TOPICS_CHOOSE_LEAD and "сама поверни розмову" in TOPICS_CHOOSE_LEAD
    topics = [("наш флірт і ніжність", 3, 2)]
    assert topics_section(topics, 20).endswith("\n\n" + TOPICS_CHOOSE)
    assert topics_section(topics, 20, lead=True).endswith("\n\n" + TOPICS_CHOOSE_LEAD)


def test_her_own_words_of_live_speech_are_offered_never_the_shared_ones():
    own = ("ади", "капець", "прикинь")
    lines = [style_line(random.Random(i).random, [], tags=False, fillers=own) for i in range(60)]
    offered = {w for line in lines for w in (*FILLERS, *own) if f"«{w}»" in line}
    assert offered == set(own)
    one = [style_line(random.Random(i).random, [], tags=False, fillers=("ади",)) for i in range(30)]
    assert any("«ади»" in line for line in one) and not any("«ади» чи «ади»" in line for line in one)
    same = [style_line(random.Random(5).random, [], False, fillers=f) for f in ((), FILLERS)]
    assert same[0] == same[1] == style_line(random.Random(5).random, [], False)      # none named: the shared ones


def _woven_words(line: str) -> list[str]:
    """The words a line's `woven` part offers (between «з цих слів:» and `SPOKEN`)."""
    part = line.split("з цих слів: ", 1)[1].split(SPOKEN, 1)[0]
    return [w.strip("«» .,") for w in part.split(",")]


def test_with_fillers_each_every_answer_weaves_her_words_into_spoken_talk():
    own = ("ади", "капець", "прикинь", "файно", "ніц")
    lines = [style_line(random.Random(i).random, [], tags=False, fillers=own, each=2) for i in range(60)]
    for line in lines:
        assert "вплети щонайменше два з цих слів: " in line and SPOKEN in line
        assert "можеш (але не мусиш)" not in line and "без слів-паразитів" not in line
        words = _woven_words(line)
        assert len(words) == len(set(words)) == 3 and set(words) <= set(own)        # each + 1 offered, all hers
    assert len({w for line in lines for w in _woven_words(line)}) == len(own)       # drawn, not always the same
    short = style_line(random.Random(1).random, [], tags=False, fillers=("ади",), each=2)
    assert "вплети щонайменше одне з цих слів: «ади»." in short                       # never more than she has


def test_a_word_she_keeps_repeating_is_never_one_she_must_weave_in():
    own = ("капець", "ади", "прикинь", "файно")
    her = ["капець, ну й день. миші не спали. кава скінчилась.",                    # «капець» in three of them,
           "та капець просто. професорка злиться. дощ ллє.",                         # never in their endings
           "оце капець! плівка засвітилась. гітара розстроєна.", "ага."]
    for i in range(30):
        line = style_line(random.Random(i).random, her, tags=False, fillers=own, each=2)
        assert "капець" not in _woven_words(line) and "казала «капець»" in line     # named to leave out instead


def test_without_fillers_each_the_line_is_as_before():
    own = ("ади", "капець", "прикинь")
    for i in range(20):
        assert (style_line(random.Random(i).random, [], False, fillers=own)
                == style_line(random.Random(i).random, [], False, fillers=own, each=0))
        assert SPOKEN not in style_line(random.Random(i).random, [], False, fillers=own)


def test_with_slang_every_answer_asks_slang_and_never_a_turn_that_corrects_herself():
    own = ("ади", "рофл", "баг", "файно")
    lines = [style_line(random.Random(i).random, [], tags=False, fillers=own, each=3, slang=True) for i in range(80)]
    for line in lines:
        assert SLANG in line and DETAIL_ENDING not in line
        assert not any(m.capitalize() in line for m in MANNERS if m not in SLANG_MANNERS)
    assert any(m.capitalize() in line for line in lines for m in SLANG_MANNERS)     # a plain turn, drawn
    assert any(DETAIL_ENDING in style_line(random.Random(i).random, [], False, fillers=own, each=3)
               for i in range(80))                                                  # off: the ending as before


class _Counted:
    def __init__(self, seed: int):
        self.rng, self.n = random.Random(seed), 0

    def __call__(self) -> float:
        self.n += 1
        return self.rng.random()


def test_slang_takes_as_many_draws_so_off_it_the_line_is_as_before():
    own = ("ади", "рофл", "баг")
    for i in range(20):
        on, off = _Counted(i), _Counted(i)
        style_line(on, [], True, fillers=own, each=3, slang=True)
        style_line(off, [], True, fillers=own, each=3)
        assert on.n == off.n
        assert (style_line(random.Random(i).random, [], True, fillers=own, each=3)
                == style_line(random.Random(i).random, [], True, fillers=own, each=3, slang=False))
        assert SLANG not in style_line(random.Random(i).random, [], True, fillers=own, each=3)


def test_her_own_short_word_said_twice_lately_is_named_and_never_offered():
    own = ("топ", "ади", "файно", "ніц", "лол", "шо", "та ну")
    her = ["шо, це просто топ.", "ну шо. миші спали.", "та ну, реально топ!", "шо далі?"]   # «топ» in two of four
    assert filler_repeats(her, own) == ["топ"]                                        # «шо»: two letters, never
    assert filler_repeats(her[:-2] + ["ага.", "ну."], own) == []                      # once in the last four: not yet
    assert filler_repeats(["топіться!", "топити", "ага"], own) == []                 # a whole word only
    for i in range(30):
        line = style_line(random.Random(i).random, her, tags=False, fillers=own, each=3)
        assert "топ" not in _woven_words(line) and "казала «топ»" in line
        assert "«шо»" not in line.split("цих слів:")[0] and "казала «шо»" not in line
    kira = style_line(random.Random(1).random, her, tags=False, fillers=own)          # without fillers_each: as before
    assert "казала «топ»" not in kira


def test_with_her_it_words_half_the_words_offered_are_it():
    own, it = ("ади", "рофл", "жиза", "файно", "ніц"), ("баг", "асап", "пофіксити", "таска")
    lines = [style_line(random.Random(i).random, [], tags=False, fillers=own, each=3, half=it) for i in range(60)]
    for line in lines:
        assert "вплети щонайменше три з цих слів: " in line
        words = _woven_words(line)
        assert len(words) == len(set(words)) == 4
        assert words[0] in it and words[1] in own and words[2] in it and words[3] in own   # two of each, in turn
    assert {w for line in lines for w in _woven_words(line)} == set(own) | set(it)    # drawn, not always the same
    odd = _woven_words(style_line(random.Random(2).random, [], False, fillers=own, each=2, half=it))
    assert len(odd) == 3 and sum(w in it for w in odd) == 1                           # half of three: one


def test_without_her_it_words_the_words_offered_are_as_before():
    own = ("ади", "рофл", "жиза", "файно", "ніц")
    for i in range(20):
        assert (style_line(random.Random(i).random, [], True, fillers=own, each=3, slang=True)
                == style_line(random.Random(i).random, [], True, fillers=own, each=3, slang=True, half=()))


def test_an_it_word_she_said_twice_lately_is_named_and_never_offered():
    own, it = ("ади", "рофл", "жиза"), ("баг", "асап", "таска")
    her = ["ну це баг.", "ага.", "знов баг!", "ок."]
    for i in range(20):
        line = style_line(random.Random(i).random, her, tags=False, fillers=own, each=3, half=it)
        assert "баг" not in _woven_words(line) and "казала «баг»" in line


@pytest.mark.parametrize("text,out", [
    ("ой, слухай, ти де?", "слухай, ти де?"),
    ("Ой! Віталіку, привіт.", "Віталіку, привіт."),                                  # the capital stays
    ("[giggles] оййй, ну ти даєш!", "[giggles] ну ти даєш!"),                          # past her voice tags
    ("ой-ой-ой. серйозно?", "серйозно?"),
    ("ой.\nну все, я спати.", "ну все, я спати."),                                   # a line left empty: dropped
    ("ну все.\nОй, забула!", "ну все.\nЗабула!"),                                     # every line
    ("ойкнула я, коли побачила.", "ойкнула я, коли побачила."),                      # a whole word only
    ("слухай, ой, ну ти даєш.", "слухай, ой, ну ти даєш."),                          # the opening only
    ("ой!", "ой!"),                                                                   # nothing else: never silence
])
def test_no_line_of_hers_opens_with_a_word_she_never_opens_with(text, out):
    assert cut_openings(text, ["ой"]) == out
    assert cut_openings(text, []) == text


# --- her TOML ---------------------------------------------------------------------------------------------------------
def _toml(tmp_path, extra: str, private: bool = True):
    toml = tmp_path / "x.toml"
    toml.write_text('name = "X"\nuser_id = "@x:agora.lan"\ncanon = "c.md"\nlife = "l.md"\nsimulation = "agora"\n'
                    + extra + ("[capabilities]\nprivate = true\n" if private else ""))
    return str(toml)


@pytest.mark.parametrize("extra,error", [
    ('fillers = ["ну"]\n', "'fillers' needs 'private'"),
    ("private_lead = true\n", "'private_lead' needs 'private'"),
    ('fillers = ["ну"]\nfillers_each = 2\n', "needs 'private'"),                     # her words come first
    ("slang = true\n", "'slang' needs 'private'"),                                    # v8.3.3
])
def test_her_words_and_her_lead_need_the_private_chat(tmp_path, extra, error):
    with pytest.raises(ConfigError, match=error):
        load_config(_toml(tmp_path, extra, private=False), env={**ENV, "X_PASSWORD": "pw-x"})


@pytest.mark.parametrize("extra,error", [
    ('fillers = "ну"\n', "'fillers' must be a list of non-empty strings"),
    ('never_open = ["ой", " "]\n', "'never_open' must be a list of non-empty strings"),
    ('private_lead = "так"\n', "'private_lead' must be true or false"),
    ('fillers_each = "2"\n', "'fillers_each' must be a whole number from 0 to 5"),
    ("fillers_each = true\n", "'fillers_each' must be a whole number from 0 to 5"),
    ("fillers_each = -1\n", "'fillers_each' must be a whole number from 0 to 5"),
    ("fillers_each = 6\n", "'fillers_each' must be a whole number from 0 to 5"),
    ("fillers_each = 1.5\n", "'fillers_each' must be a whole number from 0 to 5"),
    ("fillers_each = 2\n", "'fillers_each' needs her own 'fillers'"),               # never «ой» and its kin
    ('slang = "так"\n', "'slang' must be true or false"),                             # v8.3.3
    ("slang = 1\n", "'slang' must be true or false"),
    ('fillers_it = "баг"\n', "'fillers_it' must be a list of non-empty strings"),     # v8.3.4
    ('fillers = ["ну"]\nfillers_it = ["баг"]\n', "'fillers_it' needs 'fillers_each'"),
    ('fillers = ["ну", "баг"]\nfillers_each = 2\nfillers_it = ["баг"]\n', "'fillers_it' and 'fillers' must not share"),
])
def test_a_malformed_word_list_or_lead_is_refused(tmp_path, extra, error):
    with pytest.raises(ConfigError, match=error):
        load_config(_toml(tmp_path, extra), env={**ENV, "X_PASSWORD": "pw-x"})


def test_ustynas_toml_names_her_words_and_her_lead_and_kiras_names_none():
    ustyna = tomllib.loads((ROOT / "agents" / "ustyna.toml").read_text(encoding="utf-8"))
    kira = tomllib.loads((ROOT / "agents" / "kira.toml").read_text(encoding="utf-8"))
    assert ustyna["private_lead"] is True and ustyna["never_open"] == ["ой"]
    words = ustyna["fillers"]
    assert len(words) == len(set(words)) > len(FILLERS)                              # more than the shared ones
    assert not {"ой", "ммм", "ніби", "наче", "до речі", "уяви", "між іншим"} & set(words)
    assert ustyna["fillers_each"] == 3 and {"шось", "ніц", "файно", "крінж"} <= set(words)   # v8.3.1; v8.3.3: 3
    assert ustyna["slang"] is True and {"рофл", "жиза", "імба", "рілі"} <= set(words)
    it = ustyna["fillers_it"]                                                         # v8.3.4: her IT words apart
    assert {"баг", "пофіксити", "асап", "задеплоїти"} <= set(it) and not set(it) & set(words)
    assert "го" not in words                                                          # it would push invitations
    assert not {"ая", "коротше", "ваще", "канєшно"} & set(words)                   # v8.3.2: the owner took them out
    assert not {"fillers", "never_open", "private_lead", "fillers_each", "slang", "fillers_it"} & set(kira)  # Кіра


@pytest.mark.canon
def test_ustynas_config_carries_them_and_kiras_does_not():
    cfg = load_config("agents/ustyna.toml", env={**ENV, "USTYNA_PASSWORD": "pw-ustyna"})
    kira = load_config("agents/kira.toml", env={**ENV, "KIRA_PASSWORD": "pw-kira"})
    assert cfg.private_lead and cfg.never_open == ("ой",) and "капець" in cfg.fillers and cfg.fillers_each == 3
    assert cfg.slang and not kira.slang                                               # v8.3.3
    assert "баг" in cfg.fillers_it and "баг" not in cfg.fillers and kira.fillers_it == ()   # v8.3.4
    assert (kira.fillers, kira.never_open, kira.private_lead, kira.fillers_each) == ((), (), False, 0)


# --- the agent --------------------------------------------------------------------------------------------------------
def test_her_answer_gets_her_brief_her_words_and_her_topic_turns_and_never_opens_with_oi(tmp_path, monkeypatch):
    agent = talking(tmp_path, monkeypatch)
    agent.cfg = AgentConfig(**{**agent.cfg.__dict__, "fillers": ("капець",), "never_open": ("ой",),
                               "private_lead": True})
    agent.llm.text = "Ой, привіт! А ти де?"
    agent.private_channel = "matrix"
    agent.private_history = [("Ich", "Привіт")]
    agent._topics = ([("його звіти", 3, 1)], 4)
    agent.rng = lambda: 0.1                                                          # every draw taken
    asyncio.run(agent.private_reply())
    system = agent.llm.calls[-1][1]
    assert PRIVATE_BRIEF_LEAD in system and PRIVATE_BRIEF not in system
    assert "«капець»" in system and not any(f"«{w}»" in system for w in FILLERS)
    assert TOPICS_CHOOSE_LEAD in system and TOPICS_CHOOSE not in system
    assert agent.private_history[-1] == ("Кіра", "Привіт! А ти де?")               # «ой» cut before her history


def test_with_fillers_each_her_answer_asks_for_her_words_in_spoken_talk(tmp_path, monkeypatch):
    agent = talking(tmp_path, monkeypatch)
    agent.cfg = AgentConfig(**{**agent.cfg.__dict__, "fillers": ("капець", "ади", "файно"), "fillers_each": 2})
    agent.llm.text = "Привіт!"
    agent.private_channel = "matrix"
    agent.private_history = [("Ich", "Привіт")]
    agent.rng = lambda: 0.9                                                          # no draw would offer words
    asyncio.run(agent.private_reply())
    system = agent.llm.calls[-1][1]
    assert "вплети щонайменше два з цих слів: " in system and SPOKEN in system
    assert not any(f"«{w}»" in system for w in FILLERS if w not in ("капець", "ади", "файно"))


def test_with_slang_her_answer_asks_for_slang(tmp_path, monkeypatch):
    agent = talking(tmp_path, monkeypatch)
    agent.cfg = AgentConfig(**{**agent.cfg.__dict__, "fillers": ("рофл", "баг", "файно", "ади"), "fillers_each": 3,
                               "slang": True})
    agent.llm.text = "Привіт!"
    agent.private_channel = "matrix"
    agent.private_history = [("Ich", "Привіт")]
    agent.rng = lambda: 0.1                                                          # every draw taken
    asyncio.run(agent.private_reply())
    system = agent.llm.calls[-1][1]
    assert SLANG in system and "вплети щонайменше три з цих слів: " in system
    assert DETAIL_ENDING not in system


def test_with_her_it_words_her_answer_offers_two_of_them(tmp_path, monkeypatch):
    agent = talking(tmp_path, monkeypatch)
    it = ("баг", "асап", "таска")
    agent.cfg = AgentConfig(**{**agent.cfg.__dict__, "fillers": ("рофл", "файно", "ади"), "fillers_each": 3,
                               "fillers_it": it})
    agent.llm.text = "Привіт!"
    agent.private_channel = "matrix"
    agent.private_history = [("Ich", "Привіт")]
    agent.rng = lambda: 0.1
    asyncio.run(agent.private_reply())
    assert sum(w in it for w in _woven_words(agent.llm.calls[-1][1])) == 2


def test_without_them_kiras_answer_is_as_before(tmp_path, monkeypatch):
    agent = talking(tmp_path, monkeypatch)
    agent.llm.text = "Ой, привіт!"
    agent.private_channel = "matrix"
    agent.private_history = [("Ich", "Привіт")]
    agent._topics = ([("його звіти", 3, 1)], 4)
    asyncio.run(agent.private_reply())
    system = agent.llm.calls[-1][1]
    assert PRIVATE_BRIEF in system and TOPICS_CHOOSE in system and TOPICS_CHOOSE_LEAD not in system
    assert SPOKEN not in system and "вплети щонайменше" not in system                # v8.3.1: hers alone
    assert SLANG not in system                                                        # v8.3.3: hers alone
    assert agent.private_history[-1] == ("Кіра", "Ой, привіт!")
