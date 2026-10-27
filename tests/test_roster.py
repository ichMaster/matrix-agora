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
    assert list(roster) == ["ada", "bruno", "leon", "mia", "irma", "kira", "kit", "claude", "hermes"]  # v5.1 the herald, v5.5 four people
    ada = roster["ada"]
    assert (ada.user_id, ada.name, ada.type, ada.engine, ada.mode, ada.weight) == (
        "@ada:agora.lan", "Ада", "persona", "gemini", "ranked", 1.0)
    assert "адо" in ada.name_forms  # the vocative lives in the TOML now, not in code
    assert roster["bruno"].name_forms == ("бруно", "bruno")  # v4.4 review #8: the Latin form too
    assert ada.capabilities == TYPES["persona"] == frozenset(CAPABILITIES) - {"mood", "pastlife", "nudge", "news",
                                                                              "digest", "transcribe", "private",
                                                                              "telegram", "recall", "facts",
                                                                              "emotion", "events"}
    assert ada.panel["name"] == "Ada"


@pytest.mark.parametrize("name,shown,forms", [
    ("leon", "Леон", ("леон", "леона", "леонові", "леону", "леоном", "леоне", "leon")),
    ("mia", "Мія", ("мія", "мії", "мію", "мією", "міє", "мійко")),
    ("irma", "Ірма", ("ірма", "ірми", "ірмі", "ірму", "ірмою", "ірмо", "irma")),
    ("kira", "Кіра", ("кіра", "кіри", "кірі", "кіру", "кірою", "кіро", "kira")),
])
def test_the_four_newcomers_are_people_like_ada_and_bruno(name, shown, forms):
    """v5.5 (the owner, 2026-10-20): four more persons, ranked with the same weight as Ada and Bruno, who speak."""
    m = load_roster("agora")[name]
    assert (m.user_id, m.name, m.type, m.engine, m.mode, m.weight) == (
        f"@{name}:agora.lan", shown, "persona", "gemini", "ranked", 1.0)
    assert m.name_forms == forms and m.can("voice")
    # v5.10: her mood of the day is hers alone, with her natal chart; the others have neither
    assert m.capabilities == TYPES["persona"] | ({"private", "telegram", "recall", "facts", "emotion", "mood", "events"}
                                                 if name == "kira" else set())
    assert m.natal == ("agents/canon/kira.natal.md" if name == "kira" else "")
    assert m.panel["name"] == name.capitalize()


@pytest.mark.canon
@pytest.mark.parametrize("name", ["ada", "bruno", "leon", "mia", "irma", "kira"])
def test_a_persons_canon_and_life_never_hold_a_banned_word(name):
    """The persons believe they are human: neither their canon nor their life story says a model or a bot (v5.5:
    the newcomers' drafts are checked like Ada's and Bruno's)."""
    from pathlib import Path

    from agents.logic import BANNED_RE
    for path in (f"agents/canon/{name}.md", f"agents/canon/{name}.life.md"):
        text = Path(path).read_text(encoding="utf-8")
        assert not BANNED_RE.search(text), (path, BANNED_RE.search(text))


def test_an_italian_line_never_names_mia():
    """v5.5 review #1: Ada studies Italian — «la mia città» must not choose Mia, who would then always answer."""
    from agents.turns import mentions
    mia = load_roster("agora")["mia"]
    assert not mentions("Це la mia città, і край", mia.name_forms, mia.user_id)
    assert mentions("Міє, а ти що скажеш?", mia.name_forms, mia.user_id)


def test_a_name_form_shared_by_two_members_is_refused(tmp_path):
    """v5.5: a form that names two members would choose the wrong one — the roster refuses it."""
    reg, agents = write_roster(tmp_path, 'name = "Кіт"\nuser_id = "@kit:agora.lan"\nname_forms = ["кіт", "адо"]\n')
    with pytest.raises(RosterError, match="'адо' belongs to both ada and kit"):
        load_roster("sim", reg, agents)
    real = load_roster("agora")
    forms = [f for m in real.values() for f in m.name_forms]
    assert len(forms) == len(set(forms))


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


@pytest.mark.canon
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
    assert set(agent.others) == {"@bruno:agora.lan", "@leon:agora.lan", "@mia:agora.lan", "@irma:agora.lan",
                                 "@kira:agora.lan", "@kit:agora.lan", "@claude:agora.lan"}
    assert agent.names["@bruno:agora.lan"] == "Бруно" and agent.names["@ich:agora.lan"] == "Ich"
    assert "адо" in agent.me.name_forms
    injected = {"ada": Member("ada", "@ada:agora.lan", "Ада", ("ада",)),
                "kit": Member("kit", "@kit:agora.lan", "Кіт", ("кіт",))}
    assert set(Agent(CFG, llm=FakeLLM(), roster=injected).others) == {"@kit:agora.lan"}


def test_the_launcher_lists_the_registry_agents():
    out = subprocess.run([sys.executable, "-m", "agents.roster"], capture_output=True, text=True, check=True).stdout
    assert out.split() == ["ada", "bruno", "leon", "mia", "irma", "kira", "kit", "claude", "hermes"]


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
    assert kit.capabilities == frozenset({"canon", "life", "world", "mood", "pastlife", "nudge", "voice"})  # v5.3
    assert kit.memories == "agents/canon/kit.memories.md"
    assert {"кіт", "коте", "кота"} <= set(kit.name_forms)
    assert kit.panel["name"] == "Kit" and kit.panel["pronoun"] == "he"


@pytest.mark.canon
def test_the_cats_config_loads_his_canon_life_and_natal_text():
    cfg = load_config("agents/kit.toml", env={**ENV, "KIT_PASSWORD": "pw"})
    assert cfg.type == "creature" and cfg.can("mood") and not cfg.can("summary")
    assert "штучний кіт" in cfg.canon.lower() and cfg.life is not None
    assert cfg.natal.startswith("Народження: 16.04.2005, 15:20, Портленд") and "#" not in cfg.natal.splitlines()[0]
    assert 60 <= len(cfg.theses) <= 100 and cfg.can("pastlife")          # v4.3: the past-life theses


@pytest.mark.canon
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


def test_a_person_may_have_a_mood_and_then_needs_a_natal_chart(tmp_path, monkeypatch):
    """v5.10: `mood` is no creature's alone — a person's TOML may switch it on, and then her natal chart is required
    and read like the cat's (comment lines dropped)."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "agents" / "canon").mkdir(parents=True)
    (tmp_path / "agents" / "canon" / "common.md").write_text("# Агора\nспільне")
    (tmp_path / "agents" / "canon" / "x.md").write_text("канон")
    (tmp_path / "simulations.toml").write_text(REGISTRY.replace('"ada", "bruno", "kit"', '"x"').replace("[sim", "[agora"))
    toml = tmp_path / "agents" / "x.toml"
    base = ('name = "X"\nuser_id = "@x:agora.lan"\nsimulation = "agora"\ntype = "persona"\n'
            'canon = "agents/canon/x.md"\n')
    toml.write_text(base + "[capabilities]\nlife = false\nmood = true\n")
    with pytest.raises(ConfigError, match="natal"):
        load_config(toml, env={**ENV, "X_PASSWORD": "pw"})
    (tmp_path / "agents" / "canon" / "x.natal.md").write_text("# карта\nНародження: 02.12.2002, 20:40, Донецьк.\n")
    toml.write_text(base + 'natal = "agents/canon/x.natal.md"\n[capabilities]\nlife = false\nmood = true\n')
    cfg = load_config(toml, env={**ENV, "X_PASSWORD": "pw"})
    assert cfg.type == "persona" and cfg.can("mood") and cfg.can("plans")
    assert cfg.natal == "Народження: 02.12.2002, 20:40, Донецьк."
    assert "mood" not in TYPES["persona"]                        # the type's default stays without it


def test_a_broken_other_member_is_skipped_but_ones_own_still_refuses(tmp_path):
    reg, agents = write_roster(tmp_path, 'name = "Кіт"\nuser_id = "@kit:agora.lan"\ntype = "dragon"\n')
    roster = load_roster("sim", reg, agents, strict_for="ada")       # Ada loading her room: Кіт is skipped
    assert list(roster) == ["ada", "bruno"]
    with pytest.raises(RosterError, match="unknown type"):
        load_roster("sim", reg, agents, strict_for="kit")             # Кіт loading his own: refuses
    with pytest.raises(RosterError):
        load_roster("sim", reg, agents)                               # the strict default (the panel tolerates by itself)


@pytest.mark.parametrize("cap", ["nudge", "pastlife"])
def test_only_a_creature_may_remember_a_past_life_or_speak_first(cap):
    """v4.3 review #6: «no other agent ever initiates» — a persona override is a named error."""
    data = {"name": "Ада", "user_id": "@ada:agora.lan", "capabilities": {cap: True}}
    with pytest.raises(RosterError, match=f"'{cap}' belongs to the creature type only"):
        parse_member("ada", data)
    assert parse_member("kit", {"name": "Кіт", "user_id": "@kit:agora.lan", "type": "creature"}).can(cap)


def test_a_room_has_at_most_one_initiator(tmp_path):
    """v4.3 review #6: two creatures with `nudge` would race on the same silence."""
    reg, agents = write_roster(tmp_path, 'name = "Кіт"\nuser_id = "@kit:agora.lan"\ntype = "creature"\n')
    (agents / "bruno.toml").write_text('name = "Бруно"\nuser_id = "@bruno:agora.lan"\ntype = "creature"\n')
    with pytest.raises(RosterError, match="only one member may start conversations"):
        load_roster("sim", reg, agents)
    (agents / "bruno.toml").write_text('name = "Бруно"\nuser_id = "@bruno:agora.lan"\ntype = "creature"\n'
                                       '[capabilities]\nnudge = false\n')
    assert [n for n, m in load_roster("sim", reg, agents).items() if m.can("nudge")] == ["kit"]


def test_claude_is_a_ranked_assistant_who_only_brings_news():
    """v4.4: Claude as itself — the `assistant` type, the `claude-sdk` engine; v4.5: ranked; weight 0.4 from
    2026-10-13 (the owner: Ada and Bruno talk more)."""
    from pathlib import Path

    from agents.turns import mentions
    claude = load_member(Path("agents/claude.toml"))
    assert (claude.type, claude.engine, claude.mode, claude.name) == ("assistant", "claude-sdk", "ranked", "Клод")
    assert claude.weight == 0.4  # the owner, 2026-10-13: lower, so Ada and Bruno talk more
    assert claude.capabilities == TYPES["assistant"] == frozenset({"news", "voice"})  # v4.5 news; v5.3 his voice
    assert all(mentions(t, claude.name_forms, claude.user_id) for t in ("Клоде, як ти?", "спитай Клода", "claude?"))
    assert claude.panel == {"name": "Claude", "role": "assistant · Opus · Max subscription", "pronoun": "it"}



def test_news_belongs_to_the_assistant_and_one_member_per_initiative(tmp_path):
    """v4.5: Claude brings news; the cat nudges; a persona does neither; one member per initiative."""
    with pytest.raises(RosterError, match="'news' belongs to the assistant type only"):
        parse_member("ada", {"name": "Ада", "user_id": "@ada:agora.lan", "capabilities": {"news": True}})
    roster = load_roster("agora")
    assert [n for n, m in roster.items() if m.can("news")] == ["claude"]
    assert [n for n, m in roster.items() if m.can("nudge")] == ["kit"]


# --- v5.1: the herald (Hermes) — a member with no turns -------------------------------------------------------------
def test_hermes_is_a_herald_with_no_turns_and_his_own_canon():
    from pathlib import Path
    hermes = load_member(Path("agents/hermes.toml"))
    assert (hermes.type, hermes.engine, hermes.mode, hermes.name) == ("herald", "gemini", "none", "Гермес")
    assert hermes.capabilities == TYPES["herald"] == frozenset({"canon", "digest", "transcribe"})  # v5.2: hearing
    assert hermes.panel == {"name": "Hermes", "role": "messenger god · voice digests", "pronoun": "he"}


@pytest.mark.parametrize("data,match", [
    ({"type": "herald", "turns": {"mode": "ranked"}}, "a herald takes no turns"),
    ({"type": "herald", "turns": {}}, "a herald takes no turns"),
    ({"turns": {"mode": "none"}}, "turn mode 'none' belongs to the herald type only"),
    ({"capabilities": {"digest": True}}, "'digest' belongs to the herald type only"),
    ({"type": "creature", "capabilities": {"digest": True}}, "'digest' belongs to the herald type only"),
])
def test_the_herald_rules_are_named_errors(data, match):
    with pytest.raises(RosterError, match=match):
        parse_member("x", {"name": "X", "user_id": "@x:agora.lan", **data})


def test_a_simulation_has_at_most_one_herald(tmp_path):
    reg, agents = write_roster(tmp_path, 'name = "Кіт"\nuser_id = "@kit:agora.lan"\ntype = "herald"\n')
    roster = load_roster("sim", reg, agents)
    assert roster["kit"].mode == "none" and roster["kit"].can("digest")
    (agents / "bruno.toml").write_text('name = "Бруно"\nuser_id = "@bruno:agora.lan"\ntype = "herald"\n')
    with pytest.raises(RosterError, match="only one member may digest the room with 'digest'"):
        load_roster("sim", reg, agents)


@pytest.mark.canon
def test_a_heralds_config_loads_his_own_canon_without_the_common_one(tmp_path):
    from pathlib import Path
    reg = tmp_path / "simulations.toml"  # the registry lists him from AGORA-084, with his compose service
    reg.write_text(Path("simulations.toml").read_text(encoding="utf-8").replace('"claude"]', '"claude", "hermes"]'))
    cfg = load_config("agents/hermes.toml", env={**ENV, "HERMES_PASSWORD": "pw"}, registry_path=reg)
    common = Path("agents/canon/common.md").read_text(encoding="utf-8").strip()
    own = Path("agents/canon/hermes.md").read_text(encoding="utf-8").strip()
    assert cfg.canon == own and common not in cfg.canon
    assert cfg.type == "herald" and cfg.can("digest") and cfg.life is None


@pytest.mark.canon
def test_hermes_canon_never_calls_a_persona_a_model_or_a_bot():
    """He is openly not human, but nothing he is given may tie a persona to a banned word (the outgoing guard's
    rule, v4.2): his canon passes the same check every digest will."""
    from agents.logic import SENTENCE_SPLIT, outs_a_persona
    personas = [m for m in load_roster("agora").values() if m.type == "persona"]
    from pathlib import Path
    text = Path("agents/canon/hermes.md").read_text(encoding="utf-8")
    assert [s for s in SENTENCE_SPLIT.split(text) if outs_a_persona(s, personas)] == []


def test_the_speaking_agents_never_allowlist_the_herald_but_name_him():
    """v5.1: a line from Hermes in Agora — he never sends one — would be ignored, never answered."""
    from pathlib import Path

    from agents.logic import should_handle
    hermes = load_member(Path("agents/hermes.toml"))
    roster = {**load_roster("agora"), "hermes": hermes}
    agent = Agent(CFG, llm=FakeLLM(), roster=roster)
    assert hermes.user_id not in agent.others
    assert should_handle(CFG.room_id, hermes.user_id, CFG, agent.others).reason == "sender-not-allowlisted"
    assert agent.names[hermes.user_id] == "Гермес"



def test_transcribe_belongs_to_the_herald_and_one_member(tmp_path):
    """v5.2: two transcribers would post every voice message twice."""
    with pytest.raises(RosterError, match="'transcribe' belongs to the herald type only"):
        parse_member("x", {"name": "X", "user_id": "@x:agora.lan", "capabilities": {"transcribe": True}})
    reg, agents = write_roster(tmp_path, 'name = "Кіт"\nuser_id = "@kit:agora.lan"\ntype = "herald"\n'
                                         '[capabilities]\ndigest = false\n')
    (agents / "bruno.toml").write_text('name = "Бруно"\nuser_id = "@bruno:agora.lan"\ntype = "herald"\n')
    with pytest.raises(RosterError, match="only one member may transcribe the owner with 'transcribe'"):
        load_roster("sim", reg, agents)


@pytest.mark.canon
def test_the_shared_canon_and_hermes_name_the_newcomers():
    """v5.5: the people already in the room know the four — the shared canon names them with their ties, Hermes's
    canon names every member, and Ada's and Bruno's canons hold a line for each."""
    from pathlib import Path
    common = Path("agents/canon/common.md").read_text(encoding="utf-8")
    hermes = Path("agents/canon/hermes.md").read_text(encoding="utf-8")
    ada = Path("agents/canon/ada.md").read_text(encoding="utf-8")
    bruno = Path("agents/canon/bruno.md").read_text(encoding="utf-8")
    for forms in (("Леон", "Леона"), ("Мія", "Мії"), ("Ірма", "Ірми"), ("Кіра", "Кіри", "Кірою")):
        assert any(f in common for f in forms) and any(f in hermes for f in forms), forms
        assert any(f in ada for f in forms) and any(f in bruno for f in forms), forms
    assert "«Ліхтар»" in common and "планетарії" in common
