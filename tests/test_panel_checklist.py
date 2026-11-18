"""v9.2 (AGORA-285) — the panel: Кіра's checklist (the view, open first, «time passed» derived, corrupt lines counted)
and the owner's status for an item — Bearer as every route, the agent through the registry with `checklist`, the mark
validated in words and appended as his; never a path from the request (made-up items only)."""

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from agents.checklist import add_entry, append, fold, load, mark_entry
from panel.app import create_app
from panel.docker_read import DockerReader
from panel.health import Prober
from panel.memory import checklist_view
from panel.registry import Registry

TOKEN = "t" * 32
AUTH = {"Authorization": f"Bearer {TOKEN}"}
SAME = {**AUTH, "Origin": "http://testserver"}
KYIV = ZoneInfo("Europe/Kyiv")


def at(*a):
    return datetime(*a, tzinfo=KYIV)


@pytest.fixture
def state(tmp_path):
    s = tmp_path / "state"
    s.mkdir()
    append(s / "kira.checklist.jsonl", [
        add_entry(1, "сходити в кіно", at(2026, 11, 18, 21), who="Ich", ich=True, due="2026-11-18T19:00"),
        add_entry(2, "дочитати статтю", at(2026, 11, 18, 21)),
        add_entry(3, "подзвонити мамі", at(2026, 11, 17, 9), due="2026-11-17"),
        mark_entry(3, "done", at(2026, 11, 17, 20))])
    return s


@pytest.fixture
def client(state):
    reg = Registry()
    return TestClient(create_app(token=TOKEN, registry=reg, docker_reader=DockerReader(client_factory=lambda: None),
                                 prober=Prober(reg), state_dir=state, background=False))


def test_the_view_open_first_with_time_passed_and_a_corrupt_line_counted(state):
    with (state / "kira.checklist.jsonl").open("a", encoding="utf-8") as f:
        f.write("not json\n")
    view = checklist_view(state, "kira", at(2026, 11, 19, 10))
    assert [(x["id"], x["state"], x["open"]) for x in view["items"]] == [(1, "overdue", True), (2, "planned", True),
                                                                        (3, "done", False)]
    assert (view["open"], view["overdue"], view["closed"], view["corrupt"]) == (2, 1, 1, 1)
    assert checklist_view(state, "ustyna", at(2026, 11, 19, 10))["items"] == []              # no file yet


def test_the_memory_view_carries_her_checklist_and_another_member_none(client):
    view = client.get("/api/agents/kira/memory", headers=AUTH).json()
    assert view["checklist"]["open"] == 2 and view["checklist"]["items"][0]["what"] == "сходити в кіно"
    assert client.get("/api/agents/ada/memory", headers=AUTH).json()["checklist"] is None


def test_the_owner_sets_a_status_appended_as_his(client, state):
    r = client.post("/api/agents/kira/checklist/1", headers=SAME, content=json.dumps({"status": "done"}))
    assert r.status_code == 200 and r.json() == {"id": 1, "status": "done"}
    r = client.post("/api/agents/kira/checklist/2", headers=SAME,
                    content=json.dumps({"status": "moved", "due": "2026-11-21T18:00"}))
    assert r.status_code == 200
    entries, _ = load(state / "kira.checklist.jsonl")
    assert [(e["id"], e["status"], e["by"]) for e in entries if e["op"] == "mark"][-2:] == [(1, "done", "owner"),
                                                                                           (2, "moved", "owner")]
    assert next(x for x in fold(entries) if x.id == 2).due == "2026-11-21T18:00"


@pytest.mark.parametrize("path,body,code", [
    ("/api/agents/kira/checklist/1", {"status": "maybe"}, 422),
    ("/api/agents/kira/checklist/1", {"status": "moved"}, 422),                    # moved needs a time
    ("/api/agents/kira/checklist/1", {"status": "moved", "due": "завтра"}, 422),
    ("/api/agents/kira/checklist/1", {"status": "moved", "due": "2026-11-31T19:00"}, 422),   # review #1: no such day
    ("/api/agents/kira/checklist/1", {"status": "moved", "due": "2026-11-21T25:00"}, 422),   # nor such an hour
    ("/api/agents/kira/checklist/3", {"status": "missed"}, 422),                   # already closed
    ("/api/agents/kira/checklist/9", {"status": "done"}, 404),                     # no such item
    ("/api/agents/ada/checklist/1", {"status": "done"}, 404),                      # no checklist
    ("/api/agents/nobody/checklist/1", {"status": "done"}, 404),
    ("/api/agents/kira/checklist/x", {"status": "done"}, 422),
])
def test_a_bad_status_is_refused_and_nothing_is_written(client, state, path, body, code):
    before = (state / "kira.checklist.jsonl").read_text(encoding="utf-8")
    assert client.post(path, headers=SAME, content=json.dumps(body)).status_code == code
    assert (state / "kira.checklist.jsonl").read_text(encoding="utf-8") == before


def test_the_route_needs_the_token(client):
    assert client.post("/api/agents/kira/checklist/1", content=json.dumps({"status": "done"})).status_code == 401
