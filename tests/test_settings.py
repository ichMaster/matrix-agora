"""v4.7 (the owner, 2026-10-11): the agents' tunable settings — the schema, the panel's overrides in
state/settings.json, applied at an agent's start over the environment (code default < env < panel), and what each
agent runs with in state/<name>.settings.json."""
import json
import os
import re
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from agents.claude_sdk import forbidden_vars
from agents.moves import DEFAULT_WEIGHTS, WEIGHT_VARS
from agents.roster import load_roster
from agents.settings import (
    BY_NAME,
    SCHEMA,
    apply_overrides,
    concerns,
    effective,
    load_overrides,
    save_json,
    start,
    validate,
)

ROOM = load_roster("agora")
CODE = "\n".join(p.read_text(encoding="utf-8") for p in Path("agents").glob("*.py"))


def code_default(name):
    m = re.search(rf'(?:os\.environ\.get|env)\("{name}", "([^"]*)"\)', CODE)
    if m:
        return m.group(1)
    if name in WEIGHT_VARS.values():
        kind = next(k for k, v in WEIGHT_VARS.items() if v == name)
        return str(DEFAULT_WEIGHTS[kind])
    if name == "GEMINI_MODEL":
        from agents.llm import MODEL
        return MODEL
    return None


@pytest.mark.parametrize("setting", SCHEMA, ids=lambda s: s.name)
def test_every_setting_is_read_by_the_agents_with_the_same_default(setting):
    found = code_default(setting.name)
    assert found is not None, f"{setting.name} is not read by the agents"
    assert validate(setting.name, found) == validate(setting.name, setting.default)
    assert validate(setting.name, setting.default)[1] is None                       # the default is valid


def test_no_secret_id_path_or_forbidden_name_is_tunable():
    for s in SCHEMA:
        assert not re.search(r"(_PASSWORD|_TOKEN|_KEY|SECRET|OAUTH)$", s.name), s.name
        assert s.name not in {"ROOM_ID", "OWNER", "TIMEZONE", "HOMESERVER", "CLAUDE_WORKSPACE", "CLAUDE_CONFIG_DIR"}
        assert not forbidden_vars({s.name: "x"}), s.name


@pytest.mark.parametrize("name,raw,ok,value", [
    ("MAX_BOT_TURNS", "8", True, "8"), ("MAX_BOT_TURNS", "8.5", False, None), ("MAX_BOT_TURNS", "0", False, None),
    ("BOT_REPLY_P", "0.70", True, "0.7"), ("BOT_REPLY_P", "nan", False, None), ("BOT_REPLY_P", "1.5", False, None),
    ("CAT_NUDGE_HOURS", "09-01", True, "09-01"), ("CAT_NUDGE_HOURS", "9to5", False, None),
    ("CLAUDE_MODEL", "sonnet", True, "sonnet"), ("CLAUDE_MODEL", "gpt", False, None),
    ("LOCATION", "Київ", True, "Київ"), ("LOCATION", "a\nb", False, None),
    ("GEMINI_API_KEY", "x", False, None),
])
def test_validate(name, raw, ok, value):
    v, why = validate(name, raw)
    assert (v is not None) is ok and v == value and (why is None) is ok


@pytest.mark.parametrize("name,who", [
    ("MAX_BOT_TURNS", {"ada", "bruno", "kit", "claude"}), ("CAT_REACT_P", {"ada", "bruno", "kit", "claude"}),
    ("PERSONA_ASK_P", {"ada", "bruno"}), ("MEMORY_DAYS", {"ada", "bruno"}), ("CAT_NUDGE_IDLE_S", {"kit"}),
    ("CLAUDE_TIMEOUT_S", {"claude"}), ("CLAUDE_NEWS_EVERY_S", {"claude"}), ("GEMINI_MODEL", {"ada", "bruno", "kit"}),
])
def test_a_setting_concerns_exactly_the_agents_it_changes(name, who):
    assert {k for k, m in ROOM.items() if concerns(BY_NAME[name], m)} == who


AGORA = SimpleNamespace(id="agora", kind="matrix-chat")


def test_every_setting_is_a_service_setting_or_an_agent_setting():
    """AGORA-078 (the owner, 2026-10-11): settings live under their service — the room's bound to matrix-chat — or
    are the agent's own."""
    service = {s.name for s in SCHEMA if s.service == "matrix-chat"}
    agent = {s.name for s in SCHEMA if s.service is None}
    assert service | agent == set(BY_NAME) and not service & agent
    assert {"MAX_BOT_TURNS", "CAT_NUDGE_IDLE_S", "PERSONA_ASK_P", "CLAUDE_NEWS_EVERY_S", "SESSION_IDLE_S"} <= service
    assert {"MEMORY_DAYS", "PLAN_MAX_WORDS", "LOCATION", "GEMINI_MODEL", "CLAUDE_MODEL", "CLAUDE_TIMEOUT_S"} <= agent


def test_the_simulations_then_the_agents_own_overrides_win_over_the_env_only_where_they_concern():
    env = {"MAX_BOT_TURNS": "3", "HISTORY_N": "40", "MEMORY_DAYS": "7"}
    overrides = {"services": {"agora": {"MAX_BOT_TURNS": "8", "CAT_NUDGE_IDLE_S": "900", "BOT_REPLY_P": "9",
                                        "MEMORY_DAYS": "3"},                       # an agent setting: out of scope
                              "portal": {"HISTORY_N": "99"}},                     # another simulation: not hers
                 "agents": {"ada": {"MEMORY_DAYS": "10", "MAX_BOT_TURNS": "1"},   # a service setting: out of scope
                            "bruno": {"MEMORY_DAYS": "2"}}}
    applied, ignored = apply_overrides(env, overrides, ROOM["ada"], AGORA)
    assert applied == ["MAX_BOT_TURNS", "MEMORY_DAYS"]
    assert sorted(ignored) == ["BOT_REPLY_P", "MAX_BOT_TURNS", "MEMORY_DAYS"]           # invalid / out of scope
    assert env == {"MAX_BOT_TURNS": "8", "HISTORY_N": "40", "MEMORY_DAYS": "10"}
    out = effective(env, ROOM["ada"], applied)
    assert out["MAX_BOT_TURNS"] == {"value": "8", "source": "panel"}
    assert out["HISTORY_N"] == {"value": "40", "source": "env"}
    assert out["REPLY_DELAY_S"] == {"value": "4", "source": "default"} and "CAT_NUDGE_IDLE_S" not in out
    env2 = {}
    assert apply_overrides(env2, overrides, ROOM["ada"], None)[0] == ["MEMORY_DAYS"]      # no registry: own only


def test_the_files_are_private_atomic_and_a_corrupt_one_means_none(tmp_path):
    path = tmp_path / "settings.json"
    save_json(path, {"services": {"agora": {"MAX_BOT_TURNS": "8"}}, "agents": {}})
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert load_overrides(path) == {"services": {"agora": {"MAX_BOT_TURNS": "8"}}, "agents": {}}
    empty = {"services": {}, "agents": {}}
    path.write_text("{torn", encoding="utf-8")
    assert load_overrides(path) == empty and load_overrides(tmp_path / "none.json") == empty
    path.write_text('{"MAX_BOT_TURNS": "8"}', encoding="utf-8")                          # the flat shape: none
    assert load_overrides(path) == empty


def test_an_agent_started_with_an_override_runs_with_it_and_says_so(tmp_path, monkeypatch, caplog):
    import logging

    from agents.agent import Agent
    from tests.test_first_sync import CFG, FakeLLM
    monkeypatch.setenv("MAX_BOT_TURNS", "3")
    monkeypatch.setenv("MEMORY_DAYS", "7")
    save_json(tmp_path / "settings.json", {"services": {"agora": {"MAX_BOT_TURNS": "7", "CAT_NUDGE_IDLE_S": "900"}},
                                           "agents": {"ada": {"MEMORY_DAYS": "3"}, "bruno": {"MEMORY_DAYS": "1"}}})
    caplog.set_level(logging.INFO)
    assert start(os.environ, tmp_path, CFG) == ["MAX_BOT_TURNS", "MEMORY_DAYS"]           # Ada: not the cat's
    assert "settings: overridden MAX_BOT_TURNS, MEMORY_DAYS" in caplog.text
    agent = Agent(CFG, llm=FakeLLM())
    assert agent.max_bot_turns == 7 and agent.memory_days == 3
    written = json.loads((tmp_path / "ada.settings.json").read_text(encoding="utf-8"))
    assert written["MAX_BOT_TURNS"] == {"value": "7", "source": "panel"} and "CAT_NUDGE_IDLE_S" not in written
    assert stat.S_IMODE(os.stat(tmp_path / "ada.settings.json").st_mode) == 0o600
    assert not any(k.endswith(("_PASSWORD", "_KEY")) for k in written)


def test_only_gemini_models_that_run_with_thinking_off():
    """v4.7 review #1: every Gemini call sends thinking_budget=0; 2.5 Pro cannot, so choosing it would silence Ada,
    Bruno and Кіт."""
    assert BY_NAME["GEMINI_MODEL"].choices == ("gemini-2.5-flash", "gemini-2.5-flash-lite")
    assert validate("GEMINI_MODEL", "gemini-2.5-pro")[0] is None


@pytest.mark.parametrize("raw", ["09-09", "0-0", "23-23", "24-01", "25-03"])
def test_an_hours_value_the_agent_cannot_use_is_refused(raw):
    """v4.7 review #2: «09-09» passed the pattern, then parse_hours raised in Agent.__init__ — a crash loop."""
    from agents.nudge import parse_hours
    assert validate("CAT_NUDGE_HOURS", raw)[0] is None and validate("CLAUDE_NEWS_HOURS", raw)[0] is None
    for ok in ("09-01", "09-22", "0-24"):
        assert validate("CAT_NUDGE_HOURS", ok)[0] == ok and parse_hours(ok)


def test_a_shared_setting_is_always_a_service_setting():
    """AGORA-078 review #5: a shared setting in the agent scope would let Ada and Bruno run different turns."""
    assert all(s.service for s in SCHEMA if s.scope == "shared")


def test_a_flat_or_hand_edited_file_is_named_not_applied(tmp_path, caplog):
    """AGORA-078 review #4: the v4.7-before-078 flat shape is read as no overrides — and now said by name."""
    import logging

    from tests.test_first_sync import CFG
    save_json(tmp_path / "settings.json", {"MAX_BOT_TURNS": "8", "services": {}, "agents": {}})
    caplog.set_level(logging.WARNING)
    env = {}
    assert start(env, tmp_path, CFG) == [] and "MAX_BOT_TURNS" not in env
    assert "settings: MAX_BOT_TURNS ignored — not under services/agents" in caplog.text


def test_a_herald_is_concerned_only_by_his_own_capabilities_settings():
    """v5.1: a turn setting, a persona's or the room's model never restarts Hermes."""
    from pathlib import Path

    from agents.roster import load_member
    hermes = load_member(Path("agents/hermes.toml"))
    for name in ("MAX_BOT_TURNS", "CAT_REACT_P", "PERSONA_ASK_P", "GEMINI_MODEL", "SESSION_IDLE_S", "MEMORY_DAYS"):
        assert not concerns(BY_NAME[name], hermes), name
    from agents.settings import Setting
    assert concerns(Setting("X", "int", "1", "g", "cap:digest", None, "x"), hermes)
