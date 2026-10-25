"""v5.9 — emotion in Кіра's voice: the palette, the split of a reply into her words and the speech, the capability
and its prompt block (nio and Gemini mocked)."""

from pathlib import Path

import pytest

from agents.config import ConfigError, load_config
from agents.emotion import TAG_MODELS, TAG_RE, speech_for, split_tags
from agents.logic import BANNED_RE, build_instruction
from agents.roster import RosterError, parse_member

ROOT = Path(__file__).resolve().parent.parent
KIRA = "@kira:agora.lan"


# --- the split ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("reply", "text"), [
    ("[laughs] Я стояла з термосом!", "Я стояла з термосом!"),
    ("[starts laughing] Я стояла з термосом... [laughs] з термосом, розумієш! [laughs harder] Як пані на екскурсії.",
     "Я стояла з термосом... з термосом, розумієш! Як пані на екскурсії."),
    ("Ну от [deep belly laugh] і все.", "Ну от і все."),                      # an invented tag goes too
    ("Дивись [1] і arr[i] = 3, і [ОСТРІВ 3].", "Дивись [1] і arr[i] = 3, і [ОСТРІВ 3]."),  # not tags: stay
    ("Тихо [whispers] , так?", "Тихо, так?"),                                  # no space before the comma
    ("[sighs]\n[thoughtful] Може, завтра.", "Може, завтра."),
    ("[laughs] [laughs harder]", ""),                                          # tags only: no words at all
    ("Просто слова.", "Просто слова."),
])
def test_split_tags(reply, text):
    words, speech = split_tags(reply)
    assert words == text and speech == reply
    assert not TAG_RE.search(words)


def test_only_a_model_that_performs_tags_gets_them():
    """Measured 2026-10-25: eleven_turbo_v2_5 read «[laughs]» aloud as «лавс»; eleven_v4_turbo laughed."""
    assert "eleven_v4_turbo" in TAG_MODELS and "eleven_turbo_v2_5" not in TAG_MODELS
    assert speech_for("eleven_v4_turbo", "Ха.", "[laughs] Ха.") == "[laughs] Ха."
    assert speech_for("eleven_turbo_v2_5", "Ха.", "[laughs] Ха.") == "Ха."


# --- the capability and the palette --------------------------------------------------------------------------------
def test_emotion_is_a_persons_and_needs_a_voice():
    assert parse_member("kira", {"name": "Кіра", "user_id": KIRA,
                                 "capabilities": {"emotion": True}}, "kira.toml").can("emotion")  # a persona has voice
    with pytest.raises(RosterError, match="'emotion' needs 'voice' on the same member"):
        parse_member("kira", {"name": "Кіра", "user_id": KIRA,
                              "capabilities": {"emotion": True, "voice": False}}, "kira.toml")
    with pytest.raises(RosterError, match="'emotion' belongs to the persona type only"):
        parse_member("kit", {"name": "Кіт", "user_id": "@kit:agora.lan", "type": "creature",
                             "capabilities": {"emotion": True}}, "kit.toml")


def test_kiras_palette_is_loaded_and_says_nothing_of_what_she_is(monkeypatch):
    for var in ("OWNER", "KIRA_PASSWORD", "ROOM_ID", "HOMESERVER"):
        monkeypatch.setenv(var, "x")
    cfg = load_config(ROOT / "agents" / "kira.toml", env={"OWNER": "@ich:agora.lan", "KIRA_PASSWORD": "pw",
                                                            "ROOM_ID": "!r", "HOMESERVER": "http://hs"})
    assert cfg.can("emotion") and "[laughs]" in cfg.voice_spec and "[whispers]" in cfg.voice_spec
    assert not BANNED_RE.search(cfg.voice_spec)


def test_a_missing_voice_spec_is_named(tmp_path):
    toml = tmp_path / "kira.toml"
    src = (ROOT / "agents" / "kira.toml").read_text(encoding="utf-8")
    toml.write_text(src.replace('voice_spec = "agents/canon/kira.voice.md"', f'voice_spec = "{tmp_path}/none.md"'),
                    encoding="utf-8")
    with pytest.raises(ConfigError, match="voice spec not found"):
        load_config(toml, env={"OWNER": "o", "KIRA_PASSWORD": "pw", "ROOM_ID": "!r", "HOMESERVER": "h"})


def test_the_palette_sits_just_before_the_rules():
    out = build_instruction("Кіра", "КАНОН", "ПІДСУМОК", private="НАОДИНЦІ", move="ХІД", asked="ПИТАННЯ",
                            voice="ПАЛІТРА")
    order = [out.index(x) for x in ("КАНОН", "ПІДСУМОК", "НАОДИНЦІ", "ХІД", "ПИТАННЯ", "ПАЛІТРА", "Ти — Кіра")]
    assert order == sorted(order)
    assert "ПАЛІТРА" not in build_instruction("Ада", "КАНОН")


def test_the_palette_reaches_both_of_her_prompts_and_no_one_elses(tmp_path, monkeypatch):
    from agents.agent import Agent
    from agents.config import AgentConfig
    from tests.test_private_runtime import KindLLM
    monkeypatch.setenv("TIMEZONE", "Europe/Kyiv")
    base = {"name": "Кіра", "user_id": KIRA, "canon": "К.", "homeserver": "http://hs", "room_id": "!room",
            "owner": "@ich:agora.lan", "password": "pw", "voice_spec": "ПАЛІТРА"}
    kira = Agent(AgentConfig(**base, capabilities=frozenset({"canon", "voice", "private", "emotion"})), llm=KindLLM())
    assert "ПАЛІТРА" in kira.build_prompt() and "ПАЛІТРА" in kira.build_prompt(private="НАОДИНЦІ")
    plain = Agent(AgentConfig(**base, capabilities=frozenset({"canon", "voice"})), llm=KindLLM())
    assert "ПАЛІТРА" not in plain.build_prompt()
