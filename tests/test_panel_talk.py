"""v5.20 — the panel: Кіра's private chat in layers (the memory view's `talk`, read-only) — the summaries newest
first with their counts, never a closed line's text; null without the capability or when unreadable, never a 500
(made-up lines only)."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from agents.archive import Archive
from panel.app import create_app
from panel.docker_read import DockerReader
from panel.health import Prober
from panel.memory import talk_view
from panel.registry import Registry

TOKEN = "t" * 32
AUTH = {"Authorization": f"Bearer {TOKEN}"}
KYIV = ZoneInfo("Europe/Kyiv")
CLOSED = "закритий-рядок-5200"


def ms(*a):
    return int(datetime(*a, tzinfo=KYIV).timestamp() * 1000)


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("TIMEZONE", "Europe/Kyiv")
    s = tmp_path / "state"
    s.mkdir()
    arc = Archive(s / "kira.archive.db")
    arc.append("tg:1", ms(2026, 11, 1, 21, 5), "private", "telegram", "Ich", "Привіт")
    arc.append("tg:2", ms(2026, 11, 1, 21, 6), "private", "telegram", "Ich", CLOSED)
    arc.mark(["tg:2"], "censored")
    arc.talk_put("hour", ms(2026, 11, 1, 21), ms(2026, 11, 1, 22), "Ми привіталися.", 1, 1, 0, 1)
    arc.talk_put("4h", ms(2026, 10, 30, 8), ms(2026, 10, 30, 12), "", 3, 0, 3, 1)
    arc.close()
    return s


def client(state):
    reg = Registry()
    return TestClient(create_app(token=TOKEN, registry=reg, docker_reader=DockerReader(client_factory=lambda: None),
                                 prober=Prober(reg), state_dir=state, background=False))


def test_her_memory_view_carries_the_summaries_newest_first_with_their_counts(state):
    c = client(state)
    talk = c.get("/api/agents/kira/memory", headers=AUTH).json()["talk"]
    assert talk == [
        {"level": "hour", "start": "2026-11-01T21:00+02:00", "end": "2026-11-01T22:00+02:00", "text": "Ми привіталися.",
         "open_lines": 1, "closed_lines": 1, "left_out": 0},
        {"level": "4h", "start": "2026-10-30T08:00+02:00", "end": "2026-10-30T12:00+02:00", "text": "",
         "open_lines": 3, "closed_lines": 0, "left_out": 3}]
    assert CLOSED not in c.get("/api/agents/kira/memory", headers=AUTH).text   # a count, never the closed line
    assert c.get("/api/agents/ada/memory", headers=AUTH).json()["talk"] is None   # without the capability
    assert c.get("/api/agents/kira/memory").status_code == 401


def test_no_archive_or_no_table_is_none_and_an_unreadable_one_is_null(tmp_path):
    s = tmp_path / "state"
    s.mkdir()
    assert talk_view(s, "kira") == []
    import sqlite3
    con = sqlite3.connect(s / "kira.archive.db")                         # an archive from before v5.20
    con.execute("CREATE TABLE lines (id INTEGER PRIMARY KEY)")
    con.close()
    assert talk_view(s, "kira") == []
    (s / "kira.archive.db").write_bytes(b"not a database")
    assert talk_view(s, "kira") is None
