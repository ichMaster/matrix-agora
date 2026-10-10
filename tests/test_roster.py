"""The roster (v4.1): members from the registry + their TOMLs, types with capabilities, and the gating."""

import asyncio
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agents.agent import Agent
from agents.config import AgentConfig, ConfigError, load_config
from agents.roster import CAPABILITIES, TYPES, Member, RosterError, load_member, load_roster, parse_member
from tests.test_config import ENV
from tests.test_first_sync import CFG, FakeLLM

REGISTRY = """
[sim]
kind = "matrix-chat"
title = "Sim"
services = ["homeserver"]
agents = ["ada", "bruno", "kit"]
[sim.health]
service = "homeserver"
port = 8008
path = "/x"
[sim.endpoints]
homeserver = "HOMESERVER"
room = "ROOM_ID"
"""


def write_roster(tmp_path, kit_toml: str):
    agents = tmp_path / "agents"
    agents.mkdir()
    (agents / "ada.toml").write_text('name = "Ада"\nuser_id = "@ada:agora.lan"\nname_forms = ["ада", "адо"]\n')
    (agents / "bruno.toml").write_text('name = "Бруно"\nuser_id = "@bruno:agora.lan"\n')
    (agents / "kit.toml").write_text(kit_toml)
    reg = tmp_path / "simulations.toml"
    reg.write_text(REGISTRY)
    return reg, agents


def test_the_real_roster_holds_ada_and_bruno_as_ranked_personas():
    roster = load_roster("agora")
    assert list(roster) == ["ada", "bruno", "kit"]
    ada = roster["ada"]
    assert (ada.user_id, ada.name, ada.type, ada.engine, ada.mode, ada.weight) == (
        "@ada:agora.lan", "Ада", "persona", "gemini", "ranked", 1.0)
    assert "адо" in ada.name_forms  # the vocative lives in the TOML now, not in code
    assert roster["bruno"].name_forms == ("бруно",)
    assert ada.capabilities == TYPES["persona"] == frozenset(CAPABILITIES) - {"mood", "pastlife", "nudge"}
    assert ada.panel["name"] == "Ada"


def test_defaults_and_registry_order(tmp_path):
    reg, agents = write_roster(tmp_path, 'name = "Кіт"\nuser_id = "@kit:agora.lan"\n')
    roster = load_roster("sim", reg, agents)
    assert list(roster) == ["ada", "bruno", "kit"]
    kit = roster["kit"]
    assert (kit.type, kit.engine, kit.mode, kit.weight, kit.name_forms) == ("persona", "gemini", "ranked", 1.0, ("кіт",))


@pytest.mark.parametrize("extra,match", [
    ('type = "dragon"', "unknown type"),
    ('engine = "gpt"', "unknown engine"),
    ('[turns]\nmode = "shouting"', "unknown turn mode"),
    ('[turns]\nweight = 0', "weight"),
    ('[turns]\nweight = true', "weight"),
    ('[turns]\nweight = nan', "weight"),    # code review #6
    ('[turns]\nweight = inf', "weight"),
    ('[capabilities]\nwings = true', "bad capability"),
    ('[capabilities]\ntoday = "yes"', "bad capability"),
    ('name_forms = []', "name_forms"),
])
def test_malformed_members_refuse_to_start(tmp_path, extra, match):
    reg, agents = write_roster(tmp_path, f'name = "Кіт"\nuser_id = "@kit:agora.lan"\n{extra}\n')
    with pytest.raises(RosterError, match=match):
        load_roster("sim", reg, agents)


def test_a_missing_toml_or_simulation_is_a_clear_error(tmp_path):
    reg, agents = write_roster(tmp_path, 'name = "Кіт"\nuser_id = "@kit:agora.lan"\n')
    (agents / "kit.toml").unlink()
    with pytest.raises(RosterError, match="not found"):
        load_roster("sim", reg, agents)
    with pytest.raises(RosterError, match="unknown simulation"):
        load_roster("nope")
    with pytest.raises(RosterError, match="missing 'user_id'"):
        load_member_from(tmp_path, 'name = "X"\n')


def load_member_from(tmp_path, text):
    p = tmp_path / "x.toml"
    p.write_text(text)
    return load_member(p)


def test_capability_overrides_switch_defaults_off():
    m = parse_member("x", {"name": "X", "user_id": "@x:a", "capabilities": {"today": False, "plans": False}})
    assert not m.can("today") and not m.can("plans") and m.can("summary")


def test_config_requires_canon_and_life_only_when_the_type_has_them(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "agents" / "canon").mkdir(parents=True)
    (tmp_path / "agents" / "canon" / "common.md").write_text("# Агора\nспільне")
    (tmp_path / "simulations.toml").write_text(REGISTRY.replace('"ada", "bruno", "kit"', '"x"').replace("[sim", "[agora"))
    toml = tmp_path / "agents" / "x.toml"
    toml.write_text('name = "X"\nuser_id = "@x:agora.lan"\nsimulation = "agora"\n'
                    '[capabilities]\ncanon = false\nlife = false\n')
    cfg = load_config(toml, env={**ENV, "X_PASSWORD": "pw"})
    assert cfg.canon == "" and cfg.life is None and not cfg.can("canon")
    toml.write_text('name = "X"\nuser_id = "@x:agora.lan"\nsimulation = "agora"\n')  # a persona needs both
    with pytest.raises(ConfigError, match="canon"):
        load_config(toml, env={**ENV, "X_PASSWORD": "pw"})


def test_the_real_tomls_load_as_personas():
    cfg = load_config("agents/ada.toml", env=ENV)
    assert cfg.type == "persona" and cfg.engine == "gemini" and cfg.capabilities == TYPES["persona"]


# --- the agent gates by capability; with the persona defaults nothing changes ---------------------------------
def gated_agent(*off: str) -> Agent:
    cfg = AgentConfig(**{**CFG.__dict__, "capabilities": frozenset(TYPES["persona"]) - set(off)})
    agent = Agent(cfg, llm=FakeLLM())
    agent.client = SimpleNamespace(room_send=AsyncMock(), room_typing=AsyncMock())
    agent.ensure_today = AsyncMock()
    agent.summarize = AsyncMock(return_value=True)
    return agent


def test_a_reply_refreshes_the_today_block_only_with_the_capability():
    on, off = gated_agent(), gated_agent("today")
    asyncio.run(on.reply("!room"))
    asyncio.run(off.reply("!room"))
    on.ensure_today.assert_awaited()
    off.ensure_today.assert_not_awaited()


def test_no_summary_capability_means_no_session_and_no_shutdown_summary():
    agent = gated_agent("summary")
    agent.started = True
    room, event = SimpleNamespace(room_id="!room"), SimpleNamespace(sender="@x:a", body="hi", server_timestamp=1)
    asyncio.run(agent.on_message(room, event))
    assert agent.session == []
    asyncio.run(agent.shutdown())
    agent.summarize.assert_not_awaited()


def test_the_prompt_leaves_out_what_the_agent_cannot_have():
    agent = gated_agent("plans", "today", "chronicle", "world")
    agent.plans_section = lambda now: "ПЛАНИ"
    agent.today_section = lambda now: "СЬОГОДНІ"
    agent.memories_section = lambda now: "СПОГАДИ"
    prompt = agent.build_prompt()
    assert "ПЛАНИ" not in prompt and "СЬОГОДНІ" not in prompt and "СПОГАДИ" not in prompt
    assert "Канон." in prompt  # canon stays


def test_world_tick_does_nothing_without_chronicle_or_plans():
    agent = gated_agent("chronicle", "plans")
    agent.ensure_plans = AsyncMock()
    agent.ensure_day_memory = AsyncMock()
    asyncio.run(agent.world_tick(force=True))
    agent.ensure_plans.assert_not_awaited()
    agent.ensure_day_memory.assert_not_awaited()


def test_the_agent_reads_its_members_from_the_roster():
    agent = Agent(CFG, llm=FakeLLM())
    assert set(agent.others) == {"@bruno:agora.lan", "@kit:agora.lan"}
    assert agent.names["@bruno:agora.lan"] == "Бруно" and agent.names["@ich:agora.lan"] == "Ich"
    assert "адо" in agent.me.name_forms
    injected = {"ada": Member("ada", "@ada:agora.lan", "Ада", ("ада",)),
                "kit": Member("kit", "@kit:agora.lan", "Кіт", ("кіт",))}
    assert set(Agent(CFG, llm=FakeLLM(), roster=injected).others) == {"@kit:agora.lan"}


def test_the_launcher_lists_the_registry_agents():
    out = subprocess.run([sys.executable, "-m", "agents.roster"], capture_output=True, text=True, check=True).stdout
    assert out.split() == ["ada", "bruno", "kit"]


def test_an_unreadable_toml_is_a_roster_error_not_a_crash(tmp_path):
    """Code review #5: a directory, a permission problem or a non-UTF-8 file is a clear RosterError."""
    (tmp_path / "dir.toml").mkdir()
    with pytest.raises(RosterError, match="unreadable"):
        load_member(tmp_path / "dir.toml")
    bad = tmp_path / "latin.toml"
    bad.write_bytes('name = "Кіт"'.encode("cp1251"))
    with pytest.raises(RosterError, match="unreadable"):
        load_member(bad)


def test_the_panel_greys_an_unreadable_agent_card_instead_of_crashing(tmp_path):
    from panel.registry import Registry
    reg, agents = write_roster(tmp_path, 'name = "Кіт"\nuser_id = "@kit:agora.lan"\n')
    (agents / "kit.toml").unlink()
    (agents / "kit.toml").mkdir()  # unreadable as a file
    panel = Registry(reg, agents)
    assert panel.agent("kit").type == "unknown" and panel.agent("ada").type == "persona"



# --- v4.2: the creature type and the cat --------------------------------------------------------------------------
def test_the_cat_is_an_ambient_creature_with_a_horoscope_and_no_memories():
    kit = load_roster("agora")["kit"]
    assert (kit.type, kit.mode, kit.name) == ("creature", "ambient", "Кіт")
    assert kit.capabilities == frozenset({"canon", "life", "world", "mood", "pastlife", "nudge"})  # v4.3
    assert kit.memories == "agents/canon/kit.memories.md"
    assert {"кіт", "коте", "кота"} <= set(kit.name_forms)
    assert kit.panel["name"] == "Kit" and kit.panel["pronoun"] == "he"


def test_the_cats_config_loads_his_canon_life_and_natal_text():
    cfg = load_config("agents/kit.toml", env={**ENV, "KIT_PASSWORD": "pw"})
    assert cfg.type == "creature" and cfg.can("mood") and not cfg.can("summary")
    assert "штучний кіт" in cfg.canon.lower() and cfg.life is not None
    assert cfg.natal.startswith("Народження: 16.04.2005, 15:20, Портленд") and "#" not in cfg.natal.splitlines()[0]
    assert 60 <= len(cfg.theses) <= 100 and cfg.can("pastlife")          # v4.3: the past-life theses


def test_a_creature_needs_a_readable_theses_file(tmp_path):
    """v4.3 contract: `memories` is required with `pastlife`; missing, empty or malformed refuses to start."""
    from pathlib import Path
    base = tmp_path / "kit.toml"
    toml = Path("agents/kit.toml").read_text(encoding="utf-8")
    base.write_text(toml.replace('memories = "agents/canon/kit.memories.md"', "#"), encoding="utf-8")
    with pytest.raises(ConfigError, match="missing 'memories'"):
        load_config(base, env={**ENV, "KIT_PASSWORD": "pw"})
    for content, err in [("# no theses here\n", "empty"), ("- [tag text without a bracket\n", "line 1")]:
        theses = tmp_path / "t.md"
        theses.write_text(content, encoding="utf-8")
        base.write_text(toml.replace("agents/canon/kit.memories.md", str(theses)), encoding="utf-8")
        with pytest.raises(ConfigError, match=err):
            load_config(base, env={**ENV, "KIT_PASSWORD": "pw"})
    base.write_text(toml.replace("agents/canon/kit.memories.md", str(tmp_path / "nope.md")), encoding="utf-8")
    with pytest.raises(ConfigError, match="not found"):
        load_config(base, env={**ENV, "KIT_PASSWORD": "pw"})


def test_a_creature_without_a_natal_chart_refuses_to_start(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "agents" / "canon").mkdir(parents=True)
    (tmp_path / "agents" / "canon" / "common.md").write_text("# Агора\nспільне")
    (tmp_path / "agents" / "canon" / "x.md").write_text("канон")
    (tmp_path / "simulations.toml").write_text(REGISTRY.replace('"ada", "bruno", "kit"', '"x"').replace("[sim", "[agora"))
    toml = tmp_path / "agents" / "x.toml"
    toml.write_text('name = "X"\nuser_id = "@x:agora.lan"\nsimulation = "agora"\ntype = "creature"\n'
                    'canon = "agents/canon/x.md"\n[capabilities]\nlife = false\n')
    with pytest.raises(ConfigError, match="natal"):
        load_config(toml, env={**ENV, "X_PASSWORD": "pw"})


def test_a_broken_other_member_is_skipped_but_ones_own_still_refuses(tmp_path):
    reg, agents = write_roster(tmp_path, 'name = "Кіт"\nuser_id = "@kit:agora.lan"\ntype = "dragon"\n')
    roster = load_roster("sim", reg, agents, strict_for="ada")       # Ada loading her room: Кіт is skipped
    assert list(roster) == ["ada", "bruno"]
    with pytest.raises(RosterError, match="unknown type"):
        load_roster("sim", reg, agents, strict_for="kit")             # Кіт loading his own: refuses
    with pytest.raises(RosterError):
        load_roster("sim", reg, agents)                               # the strict default (the panel tolerates by itself)
