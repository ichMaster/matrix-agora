"""v4.7 (the owner, 2026-10-11): the agents' tunable settings — the schema, the panel's overrides in
state/settings.json, applied at an agent's start over the environment (code default < env < panel), and what each
agent runs with in state/<name>.settings.json."""
import json
import os
import re
import stat
from pathlib import Path

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


def test_the_panel_overrides_the_env_which_overrides_the_default_only_where_it_concerns():
    env = {"MAX_BOT_TURNS": "3", "HISTORY_N": "40"}
    applied, ignored = apply_overrides(env, {"MAX_BOT_TURNS": "8", "CAT_NUDGE_IDLE_S": "900", "BOT_REPLY_P": "9",
                                             "GEMINI_API_KEY": "x"}, ROOM["ada"])
    assert applied == ["MAX_BOT_TURNS"] and ignored == ["BOT_REPLY_P", "GEMINI_API_KEY"]
    assert env == {"MAX_BOT_TURNS": "8", "HISTORY_N": "40"}                         # not the cat's, not a key
    out = effective(env, ROOM["ada"], applied)
    assert out["MAX_BOT_TURNS"] == {"value": "8", "source": "panel"}
    assert out["HISTORY_N"] == {"value": "40", "source": "env"}
    assert out["REPLY_DELAY_S"] == {"value": "4", "source": "default"} and "CAT_NUDGE_IDLE_S" not in out


def test_the_files_are_private_atomic_and_a_corrupt_one_means_none(tmp_path):
    path = tmp_path / "settings.json"
    save_json(path, {"MAX_BOT_TURNS": "8"})
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600 and load_overrides(path) == {"MAX_BOT_TURNS": "8"}
    path.write_text("{torn", encoding="utf-8")
    assert load_overrides(path) == {} and load_overrides(tmp_path / "none.json") == {}
    path.write_text("[1, 2]", encoding="utf-8")
    assert load_overrides(path) == {}


def test_an_agent_started_with_an_override_runs_with_it_and_says_so(tmp_path, monkeypatch, caplog):
    import logging

    from agents.agent import Agent
    from tests.test_first_sync import CFG, FakeLLM
    monkeypatch.setenv("MAX_BOT_TURNS", "3")
    monkeypatch.setenv("CAT_NUDGE_IDLE_S", "1200")
    save_json(tmp_path / "settings.json", {"MAX_BOT_TURNS": "7", "CAT_NUDGE_IDLE_S": "900"})
    caplog.set_level(logging.INFO)
    assert start(os.environ, tmp_path, CFG) == ["MAX_BOT_TURNS"]                      # Ada: not the cat's setting
    assert "settings: overridden MAX_BOT_TURNS" in caplog.text and "7" not in caplog.text.split("overridden")[1][:20]
    assert Agent(CFG, llm=FakeLLM()).max_bot_turns == 7
    written = json.loads((tmp_path / "ada.settings.json").read_text(encoding="utf-8"))
    assert written["MAX_BOT_TURNS"] == {"value": "7", "source": "panel"} and "CAT_NUDGE_IDLE_S" not in written
    assert stat.S_IMODE(os.stat(tmp_path / "ada.settings.json").st_mode) == 0o600
    assert not any(k.endswith(("_PASSWORD", "_KEY")) for k in written)
