"""v8.1 (AGORA-267) — Лілі's card in the panel: her bridge's state from `<name>.bridge.json` (never her words), no
memory of ours to forget, her settings the room's shared turns alone, and her turns in Analytics as Lumi's own
service — counted, never priced, never an incomplete total. Made-up state only; no network."""

import json
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agents.roster import load_member
from agents.settings import SCHEMA as SETTINGS
from agents.settings import concerns
from agents.usage import PriceBook, analyze, lumi_usage_line, usage_line
from panel.app import create_app
from panel.docker_read import DockerReader
from panel.health import Prober
from panel.memory import bridge_view, memory_view
from panel.registry import Registry

TOKEN = "t" * 32
AUTH = {"Authorization": f"Bearer {TOKEN}"}
TODAY = date(2026, 11, 16)
STATE = {"health": {"ok": True, "agora": 1, "why": None, "checked_ms": 1},
         "last_turn": {"at_ms": 2, "outcome": "reply", "latency_ms": 1840, "reply": "SECRET-WORDS"},
         "observed": {"day": "2026-11-16", "count": 42, "last_ts_ms": 3, "last_id": "$x"},
         "refused": None, "thinking": "SECRET-THOUGHT",
         "turns": {"day": "2026-11-16", "reply": 5, "pass": 2, "silent": 1}}


def registry(tmp_path) -> Registry:
    agents = tmp_path / "agents"
    agents.mkdir()
    (agents / "ada.toml").write_text('name = "Ада"\nuser_id = "@ada:agora.lan"\n[panel]\nname = "Ada"\n')
    (agents / "lili.toml").write_text(Path("agents/lili.toml").read_text(encoding="utf-8"))
    reg = tmp_path / "simulations.toml"
    reg.write_text('[agora]\nkind = "matrix-chat"\ntitle = "Agora"\nservices = ["homeserver"]\nagents = ["ada", "lili"]\n'
                   '[agora.health]\nservice = "homeserver"\nport = 8008\npath = "/x"\n'
                   '[agora.endpoints]\nhomeserver = "HOMESERVER"\nroom = "ROOM_ID"\n')
    return Registry(reg, agents)


def test_the_bridge_view_holds_lumis_state_and_none_of_her_words(tmp_path):
    (tmp_path / "lili.bridge.json").write_text(json.dumps(STATE))
    view = bridge_view(tmp_path, "lili", TODAY)
    assert view == {"health": {"ok": True, "agora": 1, "why": None, "checked_ms": 1},
                    "last_turn": {"at_ms": 2, "outcome": "reply", "latency_ms": 1840},
                    "observed_today": 42, "refused": None,
                    "turns_today": {"reply": 5, "pass": 2, "silent": 1}}  # v8.2 (AGORA-271)
    assert "SECRET" not in json.dumps(view)
    assert bridge_view(tmp_path, "lili", date(2026, 11, 17))["observed_today"] == 0  # another day
    assert bridge_view(tmp_path, "lili", date(2026, 11, 17))["turns_today"] == {"reply": 0, "pass": 0, "silent": 0}
    assert bridge_view(tmp_path, "nobody", TODAY) == {"health": None, "last_turn": None, "observed_today": 0,
                                                      "refused": None,
                                                      "turns_today": {"reply": 0, "pass": 0, "silent": 0}}
    (tmp_path / "lili.bridge.json").write_text("{torn")
    assert bridge_view(tmp_path, "lili", TODAY) is None                               # never a 500
    assert memory_view(tmp_path, "ada", TODAY)["bridge"] is None


def test_lilis_routes_carry_the_bridge_and_forget_is_refused(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    (state / "lili.bridge.json").write_text(json.dumps(STATE))
    reg = registry(tmp_path)
    no_containers = type("D", (), {"containers": type("C", (), {"list": lambda *a, **k: []})()})()
    c = TestClient(create_app(token=TOKEN, registry=reg, docker_reader=DockerReader(client_factory=lambda: no_containers),
                              prober=Prober(reg), state_dir=state, background=False))
    lili = c.get("/api/agents/lili", headers=AUTH).json()
    assert (lili["type"], lili["engine"], lili["capabilities"]) == ("bridge", "lumi-http", [])
    mem = c.get("/api/agents/lili/memory", headers=AUTH).json()
    assert mem["bridge"]["observed_today"] in (0, 42) and mem["bridge"]["health"]["agora"] == 1
    assert "SECRET" not in json.dumps(mem)
    assert c.get("/api/agents/ada/memory", headers=AUTH).json()["bridge"] is None
    assert c.post("/api/agents/lili/forget", headers=AUTH).status_code == 409
    assert c.post("/api/agents/lili/forget").status_code == 401                       # still token-gated


def test_her_settings_are_the_rooms_shared_turns_alone():
    lili = load_member(Path("agents/lili.toml"))
    mine = {s.name for s in SETTINGS if concerns(s, lili)}
    assert mine and all(s.scope == "shared" for s in SETTINGS if s.name in mine)
    assert not {"GEMINI_MODEL", "VOICE_MESSAGES", "AGORA_HISTORY_HOURS", "MEMORY_MODE"} & mine


def test_her_turns_are_lumis_own_service_counted_never_priced_never_incomplete():
    ts = "2026-11-16T09:00:00+02:00"
    meta = type("M", (), {"prompt_token_count": 1000, "candidates_token_count": 10, "total_token_count": 1010})()
    records = [usage_line(ts, "ada", "reply", "gemini-2.5-flash", meta, True),
               lumi_usage_line(ts, "lili", {"model": "gemini-2.5-flash", "input_tokens": 6420, "output_tokens": 38},
                               True, 1900),
               lumi_usage_line(ts, "lili", None, False, 60000)]
    report = analyze(records, TODAY, TODAY, prices=PriceBook(0.3, 2.5), today=date(2026, 11, 17))
    lumi = next(s for s in report["services"] if s["service"] == "lumi")
    assert (lumi["calls"], lumi["failed"], lumi["input"], lumi["output"], lumi["billing"]) == (
        2, 1, 6420, 38, "external")
    assert lumi["cost"] is None and lumi["complete"] is True
    assert report["total"]["complete"] is True and report["unpriced"] == []
    assert report["total"]["cost"] == pytest.approx(1000 * 0.3 / 1e6 + 10 * 2.5 / 1e6)  # Gemini's alone
