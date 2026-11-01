"""v5.19 — the panel's `GET /api/analytics`: the period and the agent validated, every usage file read once, the
prices from the environment (`PRICE_SUBSCRIPTIONS` too), and `analyze()`'s report — made-up lines, no text."""

import json
import logging
from datetime import date

import pytest
from fastapi.testclient import TestClient

import panel.memory as memory_mod
from agents.usage import judge_usage_line, tts_usage_line, video_note_usage_line
from panel.app import ANALYTICS_DAYS_MAX, create_app
from panel.docker_read import DockerReader
from panel.health import Prober
from panel.memory import analytics_period, analytics_view
from panel.registry import Registry

TOKEN = "t" * 32
AUTH = {"Authorization": f"Bearer {TOKEN}"}
KEYS = {"available", "priced", "corrupt_lines", "since", "until", "days", "agent", "total", "previous", "services",
        "kinds", "day_series", "previous_cumulative", "trend", "agents", "subscriptions", "unpriced", "rows"}


def gem(day, agent="kira", model="gemini-3.1-pro-preview"):
    return {"ts": f"{day}T12:00:00+02:00", "agent": agent, "kind": "private", "model": model,
            "prompt_tokens": 1_000_000, "output_tokens": 100_000, "total_tokens": 1_100_000, "ok": True,
            "engine": "gemini", "billing": "api"}


@pytest.fixture
def state(tmp_path, monkeypatch):
    s = tmp_path / "state"
    s.mkdir()
    kira = [gem("2026-10-31"), gem("2026-11-01"),
            judge_usage_line("2026-11-01T12:00:00+02:00", "kira", "google/gemma-4-31b-it", 1_000_000, 0, True),
            video_note_usage_line("2026-11-01T12:00:00+02:00", "kira", "veed/fabric-1.0", 20_000, True),
            tts_usage_line("2026-11-01T12:00:00+02:00", "kira", "eleven_v4_turbo", 300, True)]
    (s / "kira.usage.jsonl").write_text("\n".join(json.dumps(x) for x in kira) + "\n{torn\n", encoding="utf-8")
    (s / "ada.usage.jsonl").write_text(json.dumps(gem("2026-11-01", "ada", "gemini-2.5-flash")) + "\n",
                                       encoding="utf-8")
    for name, value in (("PRICE_INPUT_PER_1M", "0.30"), ("PRICE_OUTPUT_PER_1M", "2.50"),
                        ("PRICE_MODELS", "gemini-3.1-pro-preview=2/12,google/gemma-4-31b-it=0.75/1"),
                        ("PRICE_SECONDS", "veed/fabric-1.0=0.08"), ("PRICE_SUBSCRIPTIONS", "elevenlabs=99")):
        monkeypatch.setenv(name, value)
    yield s
    s.chmod(0o700)


def client(state):
    reg = Registry()
    return TestClient(create_app(token=TOKEN, registry=reg, docker_reader=DockerReader(client_factory=lambda: None),
                                 prober=Prober(reg), state_dir=state, background=False))


def test_the_route_answers_her_month_by_service_with_the_shape_pinned(state):
    r = client(state).get("/api/analytics?since=2026-10-31&until=2026-11-01&agent=kira", headers=AUTH)
    body = r.json()
    assert r.status_code == 200 and set(body) == KEYS
    assert body["available"] is True and body["priced"] is True and body["corrupt_lines"] == 1
    assert [s["service"] for s in body["services"]] == ["gemini", "fal", "openrouter", "elevenlabs"]
    assert body["total"]["cost"] == pytest.approx(2 * 3.2 + 1.6 + 0.75)
    assert body["agents"] == [] and body["subscriptions"] == []  # a fee is never split by agent


def test_all_agents_carry_the_agents_and_the_subscriptions_fee(state):
    body = client(state).get("/api/analytics?since=2026-11-01&until=2026-11-30", headers=AUTH).json()
    assert [a["agent"] for a in body["agents"]] == ["kira", "ada"]
    assert body["subscriptions"] == [{"service": "elevenlabs", "monthly": 99.0, "period_cost": pytest.approx(99)}]


@pytest.mark.parametrize("query, reason", [
    ("since=2026-11-01", "bad date"),
    ("until=2026-11-01", "bad date"),
    ("since=2026-13-01&until=2026-11-01", "bad date"),
    ("since=yesterday&until=2026-11-01", "bad date"),
    ("since=2026-11-02&until=2026-11-01", "since after until"),
    ("since=2025-10-31&until=2026-11-01", f"span over {ANALYTICS_DAYS_MAX} days"),
])
def test_a_bad_period_is_400_with_its_reason(state, query, reason):
    r = client(state).get(f"/api/analytics?{query}", headers=AUTH)
    assert r.status_code == 400 and r.json()["detail"] == reason


def test_a_year_is_allowed_and_a_day_after_today_counts_nothing(state):
    c = client(state)
    assert c.get("/api/analytics?since=2025-11-01&until=2026-11-01", headers=AUTH).status_code == 200  # 366 days
    body = c.get("/api/analytics?since=2027-01-01&until=2027-01-02", headers=AUTH).json()
    assert body["total"]["calls"] == 0 and body["total"]["cost"] is None


def test_the_token_and_the_agent_guard_the_route(state):
    c = client(state)
    assert c.get("/api/analytics?since=2026-11-01&until=2026-11-01").status_code == 401
    assert c.get("/api/analytics?since=2026-11-01&until=2026-11-01&agent=carol", headers=AUTH).status_code == 404
    assert c.get("/api/analytics?since=2026-11-01&until=2026-11-01&agent=../kira", headers=AUTH).status_code == 404


def test_an_unreadable_state_is_unavailable_never_a_500(state):
    state.chmod(0o000)
    assert client(state).get("/api/analytics?since=2026-11-01&until=2026-11-01", headers=AUTH).json() == {
        "available": False}


def test_every_usage_file_is_read_once_a_request(state, monkeypatch):
    reads = []
    original = memory_mod.parse_lines
    monkeypatch.setattr(memory_mod, "parse_lines", lambda lines: reads.append(len(lines)) or original(lines))
    analytics_view(state, date(2026, 11, 1), date(2026, 11, 1))
    assert reads == [7]   # both files, every line, in one pass


def test_a_malformed_fee_is_named_once_and_ignored(state, monkeypatch, caplog):
    monkeypatch.setenv("PRICE_SUBSCRIPTIONS", "elevenlabs=99,novelai=lots")
    memory_mod._WARNED.discard("novelai=lots")
    caplog.set_level(logging.WARNING, logger="panel.memory")
    for _ in range(2):
        body = analytics_view(state, date(2026, 11, 1), date(2026, 11, 1))
    assert [s["service"] for s in body["subscriptions"]] == ["elevenlabs"]
    assert caplog.text.count("PRICE_SUBSCRIPTIONS entry 'novelai=lots'") == 1


def test_the_period_is_parsed_purely():
    assert analytics_period("2026-10-01", "2026-10-31", 366) == (date(2026, 10, 1), date(2026, 10, 31))
    for since, until, reason in (("", "2026-10-01", "bad date"), ("2026-10-02", "2026-10-01", "since after until"),
                                 ("2026-10-01", "2026-10-03", "span over 2 days")):
        with pytest.raises(ValueError, match=reason):
            analytics_period(since, until, 2)
