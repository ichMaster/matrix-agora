"""v5.9 — emotion in Кіра's voice: the palette, the split of a reply into her words and the speech, the capability
and its prompt block (nio and Gemini mocked)."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agents import agent as agent_mod
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
    ("Глянь [тут](https://x.ua).", "Глянь [тут](https://x.ua)."),            # a link's text stays
    # review #3: a capital, a tag glued to a word, punctuation or an apostrophe inside — all tags
    ("[Laughs] Так[laughs] і [LAUGHS] все.", "Так і все."),
    ("[sighs.] Ну, [laughs softly, then sighs] добре.", "Ну, добре."),
    ("Я [зам’ялася] не знаю.", "Я не знаю."),
    # review #5: the tidy-up is only where a tag was; her own spacing stays
    ("Ну , добре :) так ?", "Ну , добре :) так ?"),
    ("Ну , так [laughs] ?  «[sighs] Ой»", "Ну , так?  «Ой»"),
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


# --- AGORA-119: tags to the voice, words to the text, on every path ----------------------------------------------

TAGGED = "[starts laughing] Я стояла з термосом! [laughs] З термосом, розумієш."
WORDS = "Я стояла з термосом! З термосом, розумієш."


class TaggedLLM:
    def __init__(self, text=TAGGED):
        self.text, self.calls = text, []

    async def generate(self, transcript, system_instruction, max_output_tokens=400, kind="reply"):
        self.calls.append((transcript, system_instruction))
        return self.text


class FakeTTS:
    def __init__(self, model="eleven_v4_turbo"):
        self.model, self.voice_id, self.spoken = model, "KiraVoice0123456789x", []

    async def synth(self, text):
        self.spoken.append(text)
        return b"\x01\x00" * 24_000


def her(tmp_path, monkeypatch, llm=None, model="eleven_v4_turbo"):
    from agents.agent import Agent
    from agents.config import AgentConfig
    monkeypatch.setenv("TIMEZONE", "Europe/Kyiv")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_OWNER_ID", "424242")
    caps = frozenset({"canon", "voice", "summary", "private", "telegram", "recall", "emotion"})
    cfg = AgentConfig(name="Кіра", user_id=KIRA, canon="К.", homeserver="http://hs", room_id="!room",
                      owner="@ich:agora.lan", password="pw", capabilities=caps, voice_spec="ПАЛІТРА")
    agent = Agent(cfg, llm=llm or TaggedLLM())
    agent.private_file = tmp_path / "kira.private.json"
    agent.private_room = "!dm"
    sent = []

    async def room_send(room_id, message_type, content):
        sent.append((room_id, content))
        return SimpleNamespace(event_id=f"$e{len(sent)}")

    agent.client = SimpleNamespace(room_send=room_send, room_typing=AsyncMock(), rooms={}, invited_rooms={})
    agent.tts, agent.voice_off, agent.voice_monthly_chars, agent.voice_reply_p = FakeTTS(model), None, 1_000_000, 1.0
    agent.telegram = SimpleNamespace(send_message=AsyncMock(return_value=True), send_voice=AsyncMock(return_value=True),
                                     send_chat_action=AsyncMock(return_value=True))
    agent.started, agent.started_ms = True, 0
    agent.clock = lambda: 1_761_400_000_000
    agent._spawn = lambda coro: coro.close()

    async def voice_message(client, tts, text, filename, reply_to=None, on_synth=None, caption=False):
        await tts.synth(text)
        on_synth(True)
        return {"msgtype": "m.audio", "body": "Голосове повідомлення", "url": "mxc://x"}, None

    async def encode(pcm, timeout_s=60.0):
        return b"OggS"
    monkeypatch.setattr(agent_mod, "voice_message", voice_message)
    monkeypatch.setattr(agent_mod, "encode_opus", encode)
    return agent, sent


def test_compose_gives_her_words_carrying_the_speech(tmp_path, monkeypatch):
    agent, _ = her(tmp_path, monkeypatch)
    line = asyncio.run(agent._compose(agent.build_prompt()))
    assert line == WORDS and line.speech == TAGGED


def test_element_the_voice_gets_the_tags_and_the_message_her_words(tmp_path, monkeypatch):
    agent, sent = her(tmp_path, monkeypatch)
    agent.private_channel = "matrix"
    agent.private_history = [("Ich", "Розкажи щось смішне")]
    assert asyncio.run(agent.private_reply()) is True
    assert agent.tts.spoken == [TAGGED]
    assert [c["body"] for _, c in sent if c["msgtype"] == "m.text"] == [WORDS]
    assert agent.private_history[-1] == ("Кіра", WORDS) and agent.session[-1] == ("Кіра (наодинці)", WORDS)
    stored = [r[0] for r in agent.archive.db.execute("SELECT text FROM lines WHERE speaker = 'Кіра'")]
    assert stored == [WORDS]                                                    # no bracket kept anywhere


def test_telegram_the_voice_note_gets_the_tags_and_the_text_her_words(tmp_path, monkeypatch):
    agent, _ = her(tmp_path, monkeypatch)
    agent.private_channel = "telegram"
    agent.private_history = [("Ich", "Розкажи щось смішне")]
    assert asyncio.run(agent.private_reply()) is True
    assert agent.tts.spoken == [TAGGED]
    assert agent.telegram.send_message.await_args.args[1] == WORDS


def test_agora_the_room_reads_her_words(tmp_path, monkeypatch):
    agent, sent = her(tmp_path, monkeypatch)
    asyncio.run(agent.send_line("!room", asyncio.run(agent._compose(agent.build_prompt())), "$t"))
    assert agent.tts.spoken == [TAGGED] and [c["body"] for _, c in sent if c["msgtype"] == "m.text"] == [WORDS]


def test_a_model_that_reads_tags_aloud_never_gets_one(tmp_path, monkeypatch):
    agent, _ = her(tmp_path, monkeypatch, model="eleven_turbo_v2_5")
    asyncio.run(agent.send_line("!room", asyncio.run(agent._compose(agent.build_prompt())), "$t"))
    assert agent.tts.spoken == [WORDS]


def test_a_tag_never_hides_anothers_line(tmp_path, monkeypatch):
    """v5.9 review #1: `[sighs] Ich: …` was sent as her words and spoken in her voice."""
    agent, _ = her(tmp_path, monkeypatch, llm=TaggedLLM("[laughs] Ну так.\n[sighs] Ich: ти де?"))
    line = asyncio.run(agent._compose(agent.build_prompt()))
    assert line == "Ну так." and line.speech == "[laughs] Ну так."


@pytest.mark.parametrize("reply", ["[laughs] [sighs]",
                                   "[starts laughing] … [laughs] … [laughs harder] …",  # review #2: was «………»
                                   "[laughs]!"])
def test_a_reply_of_tags_only_is_silence(tmp_path, monkeypatch, reply):
    agent, _ = her(tmp_path, monkeypatch, llm=TaggedLLM(reply))
    assert asyncio.run(agent._compose(agent.build_prompt())) is None


def test_the_monthly_budget_counts_the_speech(tmp_path, monkeypatch):
    agent, sent = her(tmp_path, monkeypatch)
    agent.voice_monthly_chars = len(WORDS) + 1                                 # the words fit, the speech does not
    asyncio.run(agent.send_line("!room", asyncio.run(agent._compose(agent.build_prompt())), "$t"))
    assert agent.tts.spoken == [] and [c["body"] for _, c in sent] == [WORDS]  # text only: her words
