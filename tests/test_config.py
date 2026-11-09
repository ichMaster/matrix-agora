import pytest

from agents.config import ConfigError, load_config

ENV = {
    "HOMESERVER": "http://192.168.1.197:8008",
    "ROOM_ID": "!abc123",
    "OWNER": "@ich:agora.lan",
    "ADA_PASSWORD": "pw-ada",
    "BRUNO_PASSWORD": "pw-bruno",
}


@pytest.mark.canon
@pytest.mark.parametrize("toml,localpart,password", [
    ("agents/ada.toml", "ada", "pw-ada"),
    ("agents/bruno.toml", "bruno", "pw-bruno"),
])
def test_loads_both_agents(toml, localpart, password):
    cfg = load_config(toml, env=ENV)
    assert cfg.localpart == localpart
    assert cfg.user_id == f"@{localpart}:agora.lan"
    assert cfg.password == password
    assert cfg.room_id == "!abc123"
    assert cfg.owner == "@ich:agora.lan"
    assert cfg.name and cfg.canon
    assert cfg.canon.startswith("# Агора")  # common first, then personal
    assert cfg.state_file.name == f"{localpart}.json"  # the real path is state/<name>.json (isolated here)


@pytest.mark.canon
def test_missing_env_var_is_a_clear_error():
    env = {k: v for k, v in ENV.items() if k != "ADA_PASSWORD"}
    with pytest.raises(ConfigError, match="ADA_PASSWORD"):
        load_config("agents/ada.toml", env=env)


def test_missing_toml_is_a_clear_error(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.toml", env=ENV)


def test_missing_toml_key_is_a_clear_error(tmp_path):
    p = tmp_path / "x.toml"
    p.write_text('name = "X"\nuser_id = "@x:agora.lan"\n')
    with pytest.raises(ConfigError, match="canon"):
        load_config(p, env=ENV)


def test_missing_or_empty_canon_refuses_to_start(tmp_path):
    from agents.config import load_canon
    common = tmp_path / "common.md"
    common.write_text("спільне")
    with pytest.raises(ConfigError, match="not found"):
        load_canon(common, tmp_path / "nope.md")
    empty = tmp_path / "empty.md"
    empty.write_text("   \n")
    with pytest.raises(ConfigError, match="empty"):
        load_canon(common, empty)


@pytest.mark.canon
def test_real_state_paths_are_under_state(monkeypatch):
    # bypass the isolation fixture: the contract paths themselves
    from pathlib import Path

    monkeypatch.undo()
    cfg = load_config("agents/ada.toml", env=ENV)
    assert cfg.state_file == Path("state/ada.json")
    assert cfg.memory_file == Path("state/ada.memory.md")


@pytest.mark.canon
def test_ustynas_toml_loads_with_every_capability_and_her_own_files():
    """v6.3: her config from her TOML and her private canon — Кіра's capabilities, the guitar, her canon, shorter
    story, backup canon, voice palette, chart and reading."""
    cfg = load_config("agents/ustyna.toml", env={**ENV, "USTYNA_PASSWORD": "pw-ustyna"})
    kira = load_config("agents/kira.toml", env={**ENV, "KIRA_PASSWORD": "pw-kira"})
    assert cfg.localpart == "ustyna" and cfg.play == "guitar"
    assert cfg.capabilities == kira.capabilities | {"photos_fal"}  # v6.5: the switch is hers, never Кіра's
    assert cfg.canon_private and cfg.canon_backup and cfg.life_private and cfg.voice_spec and cfg.reading
    assert "Устина" in cfg.canon and cfg.natal and cfg.places and cfg.places["lviv"].news



def test_photos_fal_needs_her_chart_for_her_age(tmp_path):
    """v6.5: a selfie on fal always names her adult age from her chart — without `natal` the TOML is refused."""
    toml = tmp_path / "x.toml"
    toml.write_text('name = "X"\nuser_id = "@x:agora.lan"\ncanon = "c.md"\nlife = "l.md"\nsimulation = "agora"\n'
                    "[capabilities]\nprivate = true\ntelegram = true\nphotos = true\nphotos_fal = true\n")
    with pytest.raises(ConfigError, match="missing 'natal'"):
        load_config(str(toml), env={**ENV, "X_PASSWORD": "pw-x"})
