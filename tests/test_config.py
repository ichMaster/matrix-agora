import pytest

from agents.config import ConfigError, load_config

ENV = {
    "HOMESERVER": "http://192.168.1.197:8008",
    "ROOM_ID": "!abc123",
    "OWNER": "@ich:agora.lan",
    "ADA_PASSWORD": "pw-ada",
    "BRUNO_PASSWORD": "pw-bruno",
}


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
    assert cfg.name and cfg.persona
    assert str(cfg.state_file) == f"state/{localpart}.json"


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
    with pytest.raises(ConfigError, match="persona"):
        load_config(p, env=ENV)
