from pathlib import Path

import pytest

from agents.config import ConfigError, load_config
from agents.registry import RegistryError, load_registry, parse_registry, simulation_of

ENV = {"HOMESERVER": "http://hs:8008", "ROOM_ID": "!room", "OWNER": "@ich:agora.lan",
       "ADA_PASSWORD": "pw", "BRUNO_PASSWORD": "pw", "KIT_PASSWORD": "pw"}
GOOD = """
[agora]
kind = "matrix-chat"
title = "Agora"
services = ["homeserver"]
agents = ["ada", "bruno"]
health = { service = "homeserver", port = 8008, path = "/_matrix/client/versions" }
endpoints = { homeserver = "HOMESERVER", room = "ROOM_ID" }
"""


def test_the_real_registry_holds_exactly_agora():
    reg = load_registry()
    assert list(reg) == ["agora"]
    agora = reg["agora"]
    assert (agora.kind, agora.services, agora.agents) == ("matrix-chat", ("homeserver",), ("ada", "bruno", "kit"))
    assert agora.health.path == "/_matrix/client/versions" and agora.health.service == "homeserver"
    assert agora.endpoints == {"homeserver": "HOMESERVER", "room": "ROOM_ID"}
    assert simulation_of(reg, "bruno").id == "agora" and simulation_of(reg, "carol") is None


@pytest.mark.parametrize("broken,needle", [
    (GOOD.replace('"matrix-chat"', '"minecraft"'), "unknown kind"),
    (GOOD.replace('agents = ["ada", "bruno"]', 'agents = ["ada", "ada"]'), "duplicate"),
    (GOOD.replace('title = "Agora"\n', ""), "missing 'title'"),
    (GOOD.replace('service = "homeserver", port', 'service = "db", port'), "health"),
    (GOOD.replace('room = "ROOM_ID"', 'x = "ROOM_ID"'), "endpoints"),
    (GOOD.replace('services = ["homeserver"]', 'services = ["../etc"]'), "names"),
    (GOOD + GOOD.replace("[agora]", "[other]"), "both"),
    ("", "empty"),
])
def test_a_malformed_registry_is_refused(broken, needle):
    with pytest.raises(RegistryError, match=needle):
        parse_registry(broken)


@pytest.mark.parametrize("toml", ["agents/ada.toml", "agents/bruno.toml", "agents/kit.toml"])
def test_agents_resolve_their_connection_through_the_registry(toml):
    cfg = load_config(toml, env=ENV)
    assert (cfg.simulation, cfg.homeserver, cfg.room_id) == ("agora", "http://hs:8008", "!room")


def test_an_unknown_simulation_or_a_stranger_agent_refuses_to_start(tmp_path):
    toml = tmp_path / "ada.toml"
    base = Path("agents/ada.toml").read_text(encoding="utf-8")
    toml.write_text(base.replace('simulation = "agora"', 'simulation = "nowhere"'), encoding="utf-8")
    with pytest.raises(ConfigError, match="unknown simulation"):
        load_config(toml, env=ENV)
    reg = tmp_path / "sims.toml"
    reg.write_text(GOOD.replace('agents = ["ada", "bruno"]', 'agents = ["bruno"]'), encoding="utf-8")
    with pytest.raises(ConfigError, match="not an agent"):
        load_config("agents/ada.toml", env=ENV, registry_path=reg)
