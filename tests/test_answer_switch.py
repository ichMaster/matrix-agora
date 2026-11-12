"""v7.4 (AGORA-250) — a companion's answers on the model the owner picks in her panel settings (`ANSWER_MODEL`, a
live switch): her answers on the chosen model, her background on Gemini, a missing choice silent and said by name,
the names the owner reads, Opus on Max built with its own settings and v4.4's layers, her photos' Gemini client, and
the panel's card (nio, the models and the CLI mocked; made-up lines only)."""

import asyncio
import json
import logging

import pytest

from agents import agent as agent_module
from agents.answer_models import CHOICES, ENGINE_OF
from agents.answers import SwitchedResponder
from agents.claude_sdk import OAUTH_VAR, claude_client_for
from agents.llm import LAST_BLOCK
from agents.private import silence_line
from agents.responder import Reply, Turn
from agents.route import Route, route_status
from agents.settings import BY_NAME, LIVE, OVERRIDES_FILE, concerns, validate
from agents.telegram import commands_for
from tests.test_private_route import ASKED, Gemini, her, marks
from tests.test_private_runtime import ms
from tests.test_settings import ROOM

DECLINE = ("refusal", "stop", "bio")


class Fake:
    """An answer model's responder: canned answers, or a decline (`LAST_BLOCK` set, None)."""

    def __init__(self, text="Від іншої моделі.", decline=None):
        self.text, self.decline, self.turns = text, decline, []

    async def respond(self, turn):
        self.turns.append(turn)
        if self.decline:
            LAST_BLOCK.set(self.decline)
            return None
        return Reply(self.text)


def choose(agent, value):
    """The owner's choice in her panel settings, as the panel writes it."""
    path = agent.cfg.memory_file.parent / OVERRIDES_FILE
    path.write_text(json.dumps({"services": {}, "agents": {agent.cfg.localpart: {"ANSWER_MODEL": value}}}),
                    encoding="utf-8")


def answers(agent):
    return [json.loads(x) for x in agent.answers_file.read_text(encoding="utf-8").splitlines()]


# --- the setting -------------------------------------------------------------------------------------------------------
def test_the_setting_has_five_choices_is_live_and_is_the_companions_alone():
    s = BY_NAME["ANSWER_MODEL"]
    assert s.choices == CHOICES and s.default == "api-gemini-3.1pro" and "ANSWER_MODEL" in LIVE
    assert all(validate("ANSWER_MODEL", c)[0] == c for c in CHOICES) and validate("ANSWER_MODEL", "off")[0] is None
    assert {name for name, m in ROOM.items() if concerns(s, m)} == {"kira", "ustyna"}
    assert {name for name, m in ROOM.items() if concerns(BY_NAME["OPUS_EFFORT"], m)} == {"kira", "ustyna"}
    assert BY_NAME["OPUS_EFFORT"].default == "high" and "off" not in BY_NAME["OPUS_EFFORT"].choices
    assert set(ENGINE_OF) == set(CHOICES)


# --- the switch --------------------------------------------------------------------------------------------------------
def test_her_answers_go_to_the_chosen_model_and_her_background_to_gemini():
    base, opus, choice = Fake("Gemini."), Fake("Opus."), ["api-gemini-3.1pro"]
    switch = SwitchedResponder(lambda: choice[0], {"api-gemini-3.1pro": base, "claudemax-opus": opus}, base)
    for kind in ("reply", "private", "private_nudge"):
        assert asyncio.run(switch.respond(Turn([], "sys", 100, kind))).text == "Gemini."
    choice[0] = "claudemax-opus"                                           # live: the next answer takes it
    assert asyncio.run(switch.respond(Turn([], "sys", 100, "private"))).text == "Opus."
    assert asyncio.run(switch.respond(Turn([], "sys", 100, "summary"))).text == "Gemini."  # the background
    assert [t.kind for t in opus.turns] == ["private"]
    choice[0] = "something else"                                           # a hand edit: the default's
    assert switch.chosen() == "api-gemini-3.1pro"


def test_a_missing_choice_is_silence_said_by_name_once_a_minute_never_another_model(caplog):
    caplog.set_level(logging.WARNING)
    now = [0.0]
    base = Fake("Gemini.")
    switch = SwitchedResponder(lambda: "api-sonnet", {"api-gemini-3.1pro": base}, base, mono=lambda: now[0])
    assert asyncio.run(switch.respond(Turn([], "sys", 100, "private"))) is None
    assert asyncio.run(switch.respond(Turn([], "sys", 100, "private"))) is None
    now[0] = 61.0
    assert asyncio.run(switch.respond(Turn([], "sys", 100, "reply"))) is None
    assert caplog.text.count("api-sonnet is not available") == 2 and base.turns == []


# --- the agent ---------------------------------------------------------------------------------------------------------
def test_a_companion_on_gemini_has_the_switch_and_its_answers_think_within_their_cap(tmp_path, monkeypatch):
    agent = her(tmp_path, monkeypatch)
    assert agent.switch is not None and agent.responder is agent.switch
    assert agent.switch.available() == ["api-gemini-3.1pro"]                # no subscription token in the test
    assert agent.reply_max_tokens == 4096                                  # every choice thinks: the cap counts it


def test_opus_answers_her_private_chat_live_and_its_decline_takes_the_backups_route(tmp_path, monkeypatch):
    agent = her(tmp_path, monkeypatch, Gemini())
    opus = Fake("Від Opus.")
    agent.switch.responders["claudemax-opus"] = opus
    choose(agent, "claudemax-opus")
    agent.private_line("Привіт", ms(17), "telegram", "tg:1")
    assert asyncio.run(agent.private_reply()) is True
    assert [t.kind for t in opus.turns] == ["private"] and agent.llm.transcripts == []  # Gemini never asked
    assert answers(agent)[-1]["by"] == "claude" and marks(agent)["tg:1"] == "gemini"   # the route's main model
    opus.decline = DECLINE                                                 # a decline: the backup, his lines closed
    agent.private_line(ASKED, ms(17, 1), "telegram", "tg:2")
    assert asyncio.run(agent.private_reply()) is True
    assert len(agent.fallback.calls) == 1 and answers(agent)[-1]["by"] == "backup" and marks(agent)["tg:2"] == "blocked"
    choose(agent, "api-gemini-3.1pro")                                     # back, with no restart
    assert agent.switch.chosen() == "api-gemini-3.1pro" and agent.main_label() == "gemini"


def test_the_owner_reads_the_chosen_model_and_the_commands_stay_telegrams(tmp_path, monkeypatch):
    agent = her(tmp_path, monkeypatch)
    assert (agent.main_name(), agent.main_label()) == ("gemini", "gemini")  # her Gemini, named as ever
    choose(agent, "claudemax-opus")
    assert (agent.main_name(), agent.main_label()) == ("gemini", "claudemax-opus")
    assert silence_line("Кіра", DECLINE, None, "claude", True, agent.main_label()) == \
        "⚙️ Кіра пропустила відповідь: відмова claudemax-opus (stop · bio)"
    assert silence_line("Кіра", None, None, "gemini", True, agent.main_label()).endswith("gemini нічого не повернув")
    names = dict(commands_for(False, agent.main_name(), agent.main_label()))
    assert names["gemini"] == "Повернути claudemax-opus зараз" and "claudemax-opus" not in names
    status = route_status(Route(pin="backup"), ms(17), "Europe/Kyiv", 10, 0, {"gemini": 2}, "gemini", "claudemax-opus")
    assert "(повернути: /gemini)" in status and "через claudemax-opus 2" in status
    assert "⚙️ Маршрут — claudemax-opus" in route_status(Route(), ms(17), "Europe/Kyiv", 10, 0, {}, "gemini",
                                                         "claudemax-opus")


# --- Opus on Max -------------------------------------------------------------------------------------------------------
def test_opus_on_max_is_built_with_its_own_settings_and_her_gemini_as_its_fallback(tmp_path, monkeypatch):
    built = {}

    def fake(environ, **kwargs):
        built.update(kwargs)
        return object()

    monkeypatch.setattr(agent_module, "claude_client_for", fake)
    monkeypatch.setenv(OAUTH_VAR, "oauth-token-for-the-test")
    agent = her(tmp_path, monkeypatch)
    assert agent.switch.available() == ["api-gemini-3.1pro", "claudemax-opus"] and agent.opus is not None
    assert (built["reply_model"], built["thinking"], built["effort"], built["warm"]) == ("opus", "adaptive", "high",
                                                                                         False)
    assert built["gemini"] is agent.llm and built["recall"] is False
    assert agent._media_gemini() is agent.llm                              # her photos: her Gemini client's own


def test_a_forbidden_variable_leaves_opus_out_and_her_running(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.WARNING)
    monkeypatch.setenv(OAUTH_VAR, "oauth-token-for-the-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "an-api-key-for-the-test")    # v4.4: never on the subscription's side
    agent = her(tmp_path, monkeypatch)
    assert agent.switch.available() == ["api-gemini-3.1pro"] and agent.opus is None
    assert "claudemax-opus off" in caplog.text and "an-api-key-for-the-test" not in caplog.text


def test_claude_client_for_takes_the_companions_opus_settings_over_the_rooms(tmp_path):
    env = {OAUTH_VAR: "oauth", "CLAUDE_REPLY_MODEL": "haiku", "CLAUDE_THINKING": "off", "CLAUDE_EFFORT": "low",
           "CLAUDE_WARM": "on", "GEMINI_API_KEY": "gemini-key", "OPENAI_API_KEY": "openai-key"}
    gemini = object()
    c = claude_client_for(env, status_file=tmp_path / "s.json", sink=None, gemini_sink=None, clock=lambda: 0,
                          recall=False, gemini=gemini, reply_model="opus", thinking="adaptive", effort="high",
                          warm=False)
    assert (c.reply_model, c.thinking, c.effort, c.warm, c.fallback) == ("opus", "adaptive", "high", False, gemini)
    assert set(env) == {OAUTH_VAR, "CLAUDE_REPLY_MODEL", "CLAUDE_THINKING", "CLAUDE_EFFORT", "CLAUDE_WARM"}  # no key


# --- the panel's card --------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("choice", "answers_on", "thinking", "fallback"), [
    ("api-gemini-3.1pro", "gemini-3.1-pro-preview", "low", None),
    ("claudemax-opus", "claude-opus-5-5", "high", "gemini-3.1-pro-preview"),
    ("api-sonnet", "claude-sonnet-5-5", "medium", None),
    ("codex-gpt-6.1sol", "gpt-6.1-sol · codex", "medium", "gemini-3.1-pro-preview"),
])
def test_the_panels_card_shows_her_chosen_model_and_its_thinking(tmp_path, choice, answers_on, thinking, fallback):
    from panel.memory import models_view
    (tmp_path / "kira.settings.json").write_text(json.dumps({
        "GEMINI_MODEL": {"value": "gemini-2.5-flash"}, "GEMINI_REPLY_MODEL": {"value": "gemini-3.1-pro-preview"},
        "GEMINI_THINKING_LEVEL": {"value": "low"}, "ANSWER_MODEL": {"value": "api-gemini-3.1pro"}}), encoding="utf-8")
    (tmp_path / OVERRIDES_FILE).write_text(json.dumps({"agents": {"kira": {"ANSWER_MODEL": choice}}}), encoding="utf-8")
    m = models_view(tmp_path, "kira")
    assert (m["choice"], m["answers"], m["thinking"], m.get("fallback")) == (choice, answers_on, thinking, fallback)
    assert m["background"] == "gemini-2.5-flash"


def test_a_restart_during_opuss_max_limit_keeps_it_muted(tmp_path, monkeypatch):
    """Code review v7.4 #4: `run()` read the mute back from the switch or her Gemini, never her Opus — the first Opus
    answer after a restart called the CLI into the limit again (v4.4 review #6)."""
    from agents.claude_sdk import ClaudeStatus, write_status
    monkeypatch.setenv(OAUTH_VAR, "oauth-token-for-the-test")
    status = tmp_path / "kira.ratelimit.json"
    write_status(status, ClaudeStatus(status="rejected", muted_until=4_102_444_800, model="opus"))
    agent = her(tmp_path, monkeypatch)
    agent.opus.clock = lambda: 1_000_000_000_000
    assert agent.opus is not None and not agent.opus.muted()
    agent.resume_cards()
    assert agent.opus.muted()
