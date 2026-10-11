"""v4.7: the panel's settings API — the schema with overrides and effective values; a save validates, writes
state/settings.json and restarts exactly the agents a change concerns (a stopped one is skipped)."""
import json
import os
import stat

import pytest
from fastapi.testclient import TestClient

from panel.app import create_app
from panel.health import Prober
from panel.registry import Registry
from tests.test_panel_actions import AUTH, TOKEN, make
from tests.test_panel_actions import Container as C


@pytest.fixture
def room(tmp_path):
    sup, docker, compose = make(C("ada"), C("bruno"), C("kit"), C("claude"), state_dir=tmp_path)
    reg = Registry()
    client = TestClient(create_app(token=TOKEN, registry=reg, docker_reader=sup.reader, prober=Prober(reg),
                                   state_dir=tmp_path, background=False, supervisor=sup))
    return client, tmp_path, docker, compose


def put(client, body):
    return client.put("/api/settings", headers=AUTH, json=body)


def test_the_settings_need_the_token(room):
    client, *_ = room
    assert client.get("/api/settings").status_code == 401 and client.put("/api/settings", json={}).status_code == 401


def test_the_view_shows_defaults_overrides_and_each_agents_effective_value(room):
    client, state, *_ = room
    (state / "settings.json").write_text(json.dumps({"MAX_BOT_TURNS": "8"}), encoding="utf-8")
    (state / "ada.settings.json").write_text(json.dumps({"MAX_BOT_TURNS": {"value": "8", "source": "panel"}}),
                                             encoding="utf-8")
    (state / "kit.settings.json").write_text("{torn", encoding="utf-8")                 # unreadable → null, no 500
    view = client.get("/api/settings", headers=AUTH).json()
    rows = {r["name"]: r for r in view["settings"]}
    assert [g["id"] for g in view["groups"]] == ["turns", "personas", "memory", "cat", "claude", "gemini"]
    mbt = rows["MAX_BOT_TURNS"]
    assert (mbt["default"], mbt["override"], sorted(mbt["agents"])) == ("3", "8", ["ada", "bruno", "claude", "kit"])
    assert mbt["effective"]["ada"] == {"value": "8", "source": "panel"} and mbt["effective"]["kit"] is None
    assert rows["CAT_NUDGE_IDLE_S"]["agents"] == ["kit"] and rows["CLAUDE_TIMEOUT_S"]["agents"] == ["claude"]
    assert not any(k.endswith(("_PASSWORD", "_TOKEN", "_KEY")) for k in rows)
    assert "GEMINI_API_KEY" not in json.dumps(view) and "PANEL_TOKEN" not in json.dumps(view)


@pytest.mark.parametrize("change,restarted", [
    ({"MAX_BOT_TURNS": 8}, ["ada", "bruno", "kit", "claude"]),
    ({"CAT_NUDGE_IDLE_S": "900"}, ["kit"]),
    ({"CLAUDE_TIMEOUT_S": 600}, ["claude"]),
    ({"PERSONA_ASK_P": 0.3}, ["ada", "bruno"]),
])
def test_a_save_restarts_exactly_the_agents_it_concerns(room, change, restarted):
    client, state, _, compose = room
    out = put(client, {"set": change}).json()
    assert out["saved"] == list(change) and sorted(out["restarted"]) == sorted(restarted)
    assert sorted(compose.calls) == sorted(restarted)                                     # restart = stop + up
    saved = json.loads((state / "settings.json").read_text(encoding="utf-8"))
    assert saved == {k: str(v) for k, v in change.items()}
    assert stat.S_IMODE(os.stat(state / "settings.json").st_mode) == 0o600


def test_invalid_or_unknown_writes_nothing_and_names_the_setting(room):
    client, state, _, compose = room
    r = put(client, {"set": {"MAX_BOT_TURNS": "lots", "GEMINI_API_KEY": "x"}})
    assert r.status_code == 422 and set(r.json()["detail"]["invalid"]) == {"MAX_BOT_TURNS", "GEMINI_API_KEY"}
    assert put(client, {"reset": ["NOPE"]}).status_code == 422
    assert put(client, ["x"]).status_code == 422
    assert not (state / "settings.json").exists() and compose.calls == []


def test_a_reset_drops_the_override_a_stopped_agent_is_skipped_and_no_change_restarts_nobody(room):
    client, state, docker, compose = room
    put(client, {"set": {"CAT_NUDGE_IDLE_S": 900}})
    compose.calls.clear()
    assert put(client, {"set": {"CAT_NUDGE_IDLE_S": 900}}).json() == {"saved": [], "restarted": [], "skipped": []}
    docker.by["kit"].status = "exited"
    out = put(client, {"reset": ["CAT_NUDGE_IDLE_S"]}).json()
    assert out["saved"] == ["CAT_NUDGE_IDLE_S"] and out["restarted"] == []
    assert out["skipped"] == [{"agent": "kit", "why": "not running"}] and compose.calls == []   # never started
    assert json.loads((state / "settings.json").read_text(encoding="utf-8")) == {}


def test_a_cross_origin_save_is_refused(room):
    client, *_ = room
    r = client.put("/api/settings", headers={**AUTH, "origin": "http://evil.example"}, json={"set": {}})
    assert r.status_code == 403


def test_saves_run_one_at_a_time_and_docker_down_is_named(tmp_path):
    """v4.7 review #5: two saves at once could lose an update; docker unreachable read as «not running»."""
    import threading

    from panel.registry import Registry
    from panel.settings import save_settings
    agents = list(Registry().agents.values())
    inside, gate = threading.Event(), threading.Event()

    def slow_restart(container):
        inside.set()
        gate.wait(2)
        return {"ok": True}

    first = threading.Thread(target=save_settings, args=(tmp_path, agents, {"set": {"CAT_NUDGE_IDLE_S": 900}},
                                                          lambda c: "running", slow_restart))
    first.start()
    inside.wait(2)
    second = threading.Thread(target=save_settings, args=(tmp_path, agents, {"set": {"CLAUDE_TIMEOUT_S": 600}},
                                                           lambda c: "running", lambda c: {"ok": True}))
    second.start()
    second.join(0.3)
    assert second.is_alive()                                      # waits for the first save
    gate.set()
    first.join(2)
    second.join(2)
    saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert saved == {"CAT_NUDGE_IDLE_S": "900", "CLAUDE_TIMEOUT_S": "600"}          # no lost update
    out = save_settings(tmp_path, agents, {"set": {"MAX_BOT_TURNS": 8}}, lambda c: "unknown", lambda c: {})
    assert {x["why"] for x in out["skipped"]} == {"docker unreachable"} and out["restarted"] == []
