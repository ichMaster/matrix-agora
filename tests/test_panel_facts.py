"""v5.8 — the panel: Кіра's facts about the owner (the view, re-pin, delete) and her archive's size; the id resolves
only inside her own folder, never a path from the request; an unreadable store is null, never a 500."""

import json
import os

import pytest
from fastapi.testclient import TestClient

from agents.archive import Archive
from agents.facts import add_fact, load_facts
from panel.app import create_app
from panel.docker_read import DockerReader
from panel.health import Prober
from panel.memory import archive_view, facts_view
from panel.registry import Registry

TOKEN = "t" * 32
AUTH = {"Authorization": f"Bearer {TOKEN}"}
SAME = {**AUTH, "Origin": "http://testserver"}


@pytest.fixture
def state(tmp_path):
    s = tmp_path / "state"
    s.mkdir()
    folder = s / "kira.facts"
    add_fact(folder, "Ich веган", 2, "private", "2026-10-22", 100, 240)
    add_fact(folder, "Ich народився навесні", 1, "private", "2026-10-25", 100, 240)
    add_fact(folder, "Ich колись грав у театрі", 0, "asked", "2026-10-24", 100, 240)
    arc = Archive(s / "kira.archive.db")
    arc.append("$1", 1, "agora", "matrix", "Ада", "перше")
    arc.append("$2", 2, "agora", "matrix", "Ада", "друге")
    arc.set_embeddings([(1, [0.1, 0.2])])
    arc.close()
    (tmp_path / "secret.md").write_text("---\npin: 1\n---\nчуже\n")
    return s


@pytest.fixture
def client(state):
    reg = Registry()
    return TestClient(create_app(token=TOKEN, registry=reg, docker_reader=DockerReader(client_factory=lambda: None),
                                 prober=Prober(reg), state_dir=state, background=False))


def test_the_memory_view_carries_her_facts_and_the_archives_size(client):
    view = client.get("/api/agents/kira/memory", headers=AUTH).json()
    assert [(f["pin"], f["text"]) for f in view["facts"]] == [(1, "Ich народився навесні"), (2, "Ich веган"),
                                                             (0, "Ich колись грав у театрі")]
    assert set(view["facts"][0]) == {"id", "pin", "source", "added", "text"} and view["facts"][0]["source"] == "private"
    assert view["archive"] == {"lines": 2, "embedded": 1, "waiting": 0, "censored": 0}  # v5.14: the closed lines
    ada = client.get("/api/agents/ada/memory", headers=AUTH).json()
    assert ada["facts"] is None and ada["archive"] is None                    # without the capabilities


def test_re_pin_and_delete_change_only_that_fact(client, state):
    fid = next(f.id for f in load_facts(state / "kira.facts") if f.pin == 0)
    r = client.put(f"/api/agents/kira/facts/{fid}", headers=SAME, content=json.dumps({"pin": 1}))
    assert r.status_code == 200 and r.json() == {"id": fid, "pin": 1}
    assert next(f.pin for f in load_facts(state / "kira.facts") if f.id == fid) == 1
    assert client.delete(f"/api/agents/kira/facts/{fid}", headers=SAME).status_code == 200
    assert fid not in {f.id for f in load_facts(state / "kira.facts")} and len(load_facts(state / "kira.facts")) == 2


@pytest.mark.parametrize("body", ['{"pin": 3}', '{"pin": "1"}', '{"pin": true}', "{}", "not json"])
def test_a_bad_pin_is_422(client, state, body):
    fid = load_facts(state / "kira.facts")[0].id
    assert client.put(f"/api/agents/kira/facts/{fid}", headers=SAME, content=body).status_code == 422


def test_an_unknown_id_a_path_or_an_agent_without_facts_is_404(client, state):
    for fid in ("nope", "a.b"):
        assert client.delete(f"/api/agents/kira/facts/{fid}", headers=SAME).status_code == 404
    for path in ("..", "..%2F..%2Fsecret"):                                   # normalised or split: never a fact
        assert client.delete(f"/api/agents/kira/facts/{path}", headers=SAME).status_code in (404, 405)
    assert client.delete("/api/agents/kira/facts/../../secret", headers=SAME).status_code in (404, 405)
    assert (state.parent / "secret.md").exists()
    fid = load_facts(state / "kira.facts")[0].id
    assert client.delete(f"/api/agents/ada/facts/{fid}", headers=SAME).status_code == 404
    assert client.delete(f"/api/agents/nobody/facts/{fid}", headers=SAME).status_code == 404


def test_the_routes_need_the_token_and_the_same_origin(client, state):
    fid = load_facts(state / "kira.facts")[0].id
    assert client.delete(f"/api/agents/kira/facts/{fid}").status_code == 401
    assert client.delete(f"/api/agents/kira/facts/{fid}",
                         headers={**AUTH, "Origin": "http://evil.example"}).status_code == 403
    assert len(load_facts(state / "kira.facts")) == 3


def test_an_unreadable_store_or_archive_is_null_never_a_500(tmp_path):
    s = tmp_path / "state"
    s.mkdir()
    assert facts_view(s, "kira") == [] and archive_view(s, "kira") == {"lines": 0, "embedded": 0}
    (s / "kira.archive.db").write_bytes(b"not a database")
    assert archive_view(s, "kira") is None
    (s / "kira.facts").mkdir()
    (s / "kira.facts" / "x.md").write_text("---\npin: 1\n---\nтекст\n")
    os.chmod(s / "kira.facts" / "x.md", 0)
    try:
        assert facts_view(s, "kira") == []                                    # an unreadable file is skipped
    finally:
        os.chmod(s / "kira.facts" / "x.md", 0o600)


# --- AGORA-116: «Update now» -------------------------------------------------------------------------------------------
def test_update_now_leaves_a_private_request_she_sees(client, state):
    assert client.get("/api/agents/kira/memory", headers=AUTH).json()["facts_pending"] is False
    r = client.post("/api/agents/kira/facts/update", headers=SAME)
    assert r.status_code == 200 and r.json() == {"requested": True}
    request = state / "kira.facts.request"
    assert json.loads(request.read_text())["requested_ms"] > 0 and os.stat(request).st_mode & 0o777 == 0o600
    assert client.get("/api/agents/kira/memory", headers=AUTH).json()["facts_pending"] is True
    assert client.get("/api/agents/ada/memory", headers=AUTH).json()["facts_pending"] is None


def test_update_now_needs_the_capability_the_token_and_the_same_origin(client, state):
    assert client.post("/api/agents/ada/facts/update", headers=SAME).status_code == 404
    assert client.post("/api/agents/kira/facts/update").status_code == 401
    assert client.post("/api/agents/kira/facts/update",
                       headers={**AUTH, "Origin": "http://evil.example"}).status_code == 403
    assert not (state / "kira.facts.request").exists()
