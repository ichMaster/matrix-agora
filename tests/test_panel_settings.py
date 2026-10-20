"""v4.7: the panel's settings under their service (AGORA-078) — a simulation's on its card, an agent's own in its
drawer; a save validates against the scope, writes state/settings.json and restarts exactly the concerned agents."""
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

SIM = "/api/simulations/agora/settings"


@pytest.fixture
def room(tmp_path):
    sup, docker, compose = make(C("ada"), C("bruno"), C("kit"), C("claude"), state_dir=tmp_path)
    reg = Registry()
    client = TestClient(create_app(token=TOKEN, registry=reg, docker_reader=sup.reader, prober=Prober(reg),
                                   state_dir=tmp_path, background=False, supervisor=sup))
    return client, tmp_path, docker, compose


def put(client, path, body):
    return client.put(path, headers=AUTH, json=body)


def saved(state):
    return json.loads((state / "settings.json").read_text(encoding="utf-8"))


def test_the_settings_need_the_token(room):
    client, *_ = room
    for path in (SIM, "/api/agents/ada/settings"):
        assert client.get(path).status_code == 401 and client.put(path, json={}).status_code == 401
    assert client.get("/api/simulations/nowhere/settings", headers=AUTH).status_code == 404
    assert client.get("/api/agents/carol/settings", headers=AUTH).status_code == 404


def test_the_service_view_holds_the_rooms_settings_and_the_agents_view_its_own(room):
    client, state, *_ = room
    (state / "settings.json").write_text(json.dumps({"services": {"agora": {"MAX_BOT_TURNS": "8"}}, "agents": {}}),
                                         encoding="utf-8")
    (state / "ada.settings.json").write_text(json.dumps({"MAX_BOT_TURNS": {"value": "8", "source": "panel"}}),
                                             encoding="utf-8")
    (state / "kit.settings.json").write_text("{torn", encoding="utf-8")                 # unreadable → null, no 500
    view = client.get(SIM, headers=AUTH).json()
    rows = {r["name"]: r for r in view["settings"]}
    assert view["scope"] == "services" and view["owner"] == "agora"
    assert [g["id"] for g in view["groups"]] == ["turns", "moves", "cat", "claude", "hermes", "voice",
                                                 "session"]  # v5.1, v5.3
    assert "MEMORY_DAYS" not in rows and "GEMINI_MODEL" not in rows                     # the agents' own
    mbt = rows["MAX_BOT_TURNS"]
    assert (mbt["default"], mbt["override"], sorted(mbt["agents"])) == (
        "3", "8", ["ada", "bruno", "claude", "irma", "kira", "kit", "leon", "mia"])  # v5.5: four more speakers
    assert mbt["effective"]["ada"] == {"value": "8", "source": "panel"} and mbt["effective"]["kit"] is None
    ada = {r["name"] for r in client.get("/api/agents/ada/settings", headers=AUTH).json()["settings"]}
    claude = {r["name"] for r in client.get("/api/agents/claude/settings", headers=AUTH).json()["settings"]}
    assert {"MEMORY_DAYS", "PLAN_MAX_WORDS", "LOCATION", "GEMINI_MODEL"} <= ada and "MAX_BOT_TURNS" not in ada
    assert claude == {"CLAUDE_MODEL", "CLAUDE_TIMEOUT_S", "CLAUDE_CODE_MAX_OUTPUT_TOKENS",
                      "VOICE_ID", "VOICE_REPLY_P"}  # v5.3: his voice
    assert "GEMINI_API_KEY" not in json.dumps(view) and "PANEL_TOKEN" not in json.dumps(view)


@pytest.mark.parametrize("path,change,restarted,where", [
    (SIM, {"MAX_BOT_TURNS": 8}, ["ada", "bruno", "kit", "claude"], ("services", "agora")),
    (SIM, {"CAT_NUDGE_IDLE_S": "900"}, ["kit"], ("services", "agora")),
    (SIM, {"PERSONA_ASK_P": 0.3}, ["ada", "bruno"], ("services", "agora")),
    ("/api/agents/claude/settings", {"CLAUDE_TIMEOUT_S": 600}, ["claude"], ("agents", "claude")),
    ("/api/agents/ada/settings", {"MEMORY_DAYS": 10}, ["ada"], ("agents", "ada")),
])
def test_a_save_writes_its_scope_and_restarts_exactly_who_it_concerns(room, path, change, restarted, where):
    client, state, _, compose = room
    out = put(client, path, {"set": change}).json()
    assert out["saved"] == list(change) and sorted(out["restarted"]) == sorted(restarted)
    assert sorted(compose.calls) == sorted(restarted)                                     # restart = stop + up
    part, owner = where
    assert saved(state)[part] == {owner: {k: str(v) for k, v in change.items()}}
    assert stat.S_IMODE(os.stat(state / "settings.json").st_mode) == 0o600


def test_a_setting_outside_the_scope_is_refused_and_nothing_is_written(room):
    client, state, _, compose = room
    r = put(client, SIM, {"set": {"MEMORY_DAYS": 3, "GEMINI_API_KEY": "x"}})
    assert r.status_code == 422 and r.json()["detail"]["invalid"] == {"MEMORY_DAYS": "not a setting here",
                                                                      "GEMINI_API_KEY": "unknown setting"}
    r = put(client, "/api/agents/ada/settings", {"set": {"MAX_BOT_TURNS": 8, "CLAUDE_MODEL": "haiku"}})
    assert r.status_code == 422 and set(r.json()["detail"]["invalid"]) == {"MAX_BOT_TURNS", "CLAUDE_MODEL"}
    assert put(client, SIM, {"set": {"MAX_BOT_TURNS": "lots"}}).status_code == 422
    assert put(client, SIM, {"reset": ["NOPE"]}).status_code == 422 and put(client, SIM, ["x"]).status_code == 422
    assert not (state / "settings.json").exists() and compose.calls == []


def test_a_reset_drops_the_override_a_stopped_agent_is_skipped_and_no_change_restarts_nobody(room):
    client, state, docker, compose = room
    put(client, SIM, {"set": {"CAT_NUDGE_IDLE_S": 900}})
    compose.calls.clear()
    assert put(client, SIM, {"set": {"CAT_NUDGE_IDLE_S": 900}}).json() == {"saved": [], "restarted": [], "skipped": []}
    docker.by["kit"].status = "exited"
    out = put(client, SIM, {"reset": ["CAT_NUDGE_IDLE_S"]}).json()
    assert out["saved"] == ["CAT_NUDGE_IDLE_S"] and out["restarted"] == []
    assert out["skipped"] == [{"agent": "kit", "why": "not running"}] and compose.calls == []   # never started
    assert saved(state)["services"] == {}


def test_a_cross_origin_save_is_refused(room):
    client, *_ = room
    r = client.put(SIM, headers={**AUTH, "origin": "http://evil.example"}, json={"set": {}})
    assert r.status_code == 403


def test_saves_run_one_at_a_time_and_docker_down_is_named(tmp_path):
    """v4.7 review #5: two saves at once could lose an update; docker unreachable read as «not running»."""
    import threading

    from panel.settings import save_settings
    reg = Registry()
    agents = [reg.agents[n] for n in reg.simulation("agora").agents]
    inside, gate = threading.Event(), threading.Event()

    def slow_restart(container):
        inside.set()
        gate.wait(2)
        return {"ok": True}

    first = threading.Thread(target=save_settings, args=(tmp_path, "services", "agora", "matrix-chat", agents,
                                                          {"set": {"CAT_NUDGE_IDLE_S": 900}}, lambda c: "running",
                                                          slow_restart))
    first.start()
    inside.wait(2)
    second = threading.Thread(target=save_settings, args=(tmp_path, "services", "agora", "matrix-chat", agents,
                                                           {"set": {"CLAUDE_NEWS_EVERY_S": 1800}},
                                                           lambda c: "running", lambda c: {"ok": True}))
    second.start()
    second.join(0.3)
    assert second.is_alive()                                      # waits for the first save
    gate.set()
    first.join(2)
    second.join(2)
    assert saved(tmp_path)["services"]["agora"] == {"CAT_NUDGE_IDLE_S": "900", "CLAUDE_NEWS_EVERY_S": "1800"}
    out = save_settings(tmp_path, "services", "agora", "matrix-chat", agents, {"set": {"MAX_BOT_TURNS": 8}},
                        lambda c: "unknown", lambda c: {})
    assert {x["why"] for x in out["skipped"]} == {"docker unreachable"} and out["restarted"] == []
