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
from agents.style import FILLERS, style_line
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
])
def test_her_words_and_her_lead_need_the_private_chat(tmp_path, extra, error):
    with pytest.raises(ConfigError, match=error):
        load_config(_toml(tmp_path, extra, private=False), env={**ENV, "X_PASSWORD": "pw-x"})


@pytest.mark.parametrize("extra,error", [
    ('fillers = "ну"\n', "'fillers' must be a list of non-empty strings"),
    ('never_open = ["ой", " "]\n', "'never_open' must be a list of non-empty strings"),
    ('private_lead = "так"\n', "'private_lead' must be true or false"),
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
    assert not {"fillers", "never_open", "private_lead"} & set(kira)                  # Кіра: unchanged


@pytest.mark.canon
def test_ustynas_config_carries_them_and_kiras_does_not():
    cfg = load_config("agents/ustyna.toml", env={**ENV, "USTYNA_PASSWORD": "pw-ustyna"})
    kira = load_config("agents/kira.toml", env={**ENV, "KIRA_PASSWORD": "pw-kira"})
    assert cfg.private_lead and cfg.never_open == ("ой",) and "капець" in cfg.fillers
    assert (kira.fillers, kira.never_open, kira.private_lead) == ((), (), False)


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


def test_without_them_kiras_answer_is_as_before(tmp_path, monkeypatch):
    agent = talking(tmp_path, monkeypatch)
    agent.llm.text = "Ой, привіт!"
    agent.private_channel = "matrix"
    agent.private_history = [("Ich", "Привіт")]
    agent._topics = ([("його звіти", 3, 1)], 4)
    asyncio.run(agent.private_reply())
    system = agent.llm.calls[-1][1]
    assert PRIVATE_BRIEF in system and TOPICS_CHOOSE in system and TOPICS_CHOOSE_LEAD not in system
    assert agent.private_history[-1] == ("Кіра", "Ой, привіт!")
