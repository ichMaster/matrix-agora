import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

import panel.app as app_mod
from agents.usage import aggregate, parse_lines, usage_line
from panel.app import create_app
from panel.docker_read import DockerReader
from panel.health import Prober
from panel.memory import memory_view, plan_items, usage_view
from panel.registry import Registry

TODAY = date(2026, 10, 4)
TOKEN = "t" * 32
AUTH = {"Authorization": f"Bearer {TOKEN}"}
META = type("M", (), {"prompt_token_count": 1000, "candidates_token_count": 100, "total_token_count": 1100})()


@pytest.fixture
def state(tmp_path):
    s = tmp_path / "state"
    files = {
        "ada.memory.md": "Говорили про книжки в дорогу.\n",
        "ada.days/2026-10-02.md": "Перший день.\n",
        "ada.days/2026-10-03.md": "Другий день, довший текст.\n",
        "ada.days/2026-10-03.talk.md": "журнал — не спогад\n",
        "ada.weeks/2026-09-21.md": "старий тиждень\n",
        "ada.weeks/2026-09-28.md": "минулий тиждень\n",
        "ada.plans/year-2026.md": "- дочитати Пруста\n- поїхати у Флоренцію <!-- mutation: postponed -->\n",
        "ada.plans/2026-10-04.md": "- купити лампу\n",
        "ada.today.md": "<!-- 2026-10-04T14 -->\nНеділя, 14:00. Книжка і кава.\nДругий рядок.\n",
        "bruno.today.md": "<!-- 2026-10-03T22 -->\nучорашнє\n",
    }
    for rel, text in files.items():
        (s / rel).parent.mkdir(parents=True, exist_ok=True)
        (s / rel).write_text(text, encoding="utf-8")
    lines = [json.dumps(usage_line(f"2026-10-0{d}T10:00:00+03:00", ag, kind, "m", META, True))
             for d, ag, kind in ((3, "ada", "reply"), (3, "ada", "reply"), (4, "bruno", "plan"), (4, "ada", "summary"),
                                 (1, "ada", "reply"))]  # 10-01 is outside a 3-day window
    (s / "ada.usage.jsonl").write_text("\n".join(lines[:2] + lines[3:]) + "\n{broken\n", encoding="utf-8")
    (s / "bruno.usage.jsonl").write_text(lines[2] + "\n", encoding="utf-8")
    yield s
    s.chmod(0o700)


def test_every_memory_kind_with_its_metadata(state):
    v = memory_view(state, "ada", TODAY)
    assert v["available"] and v["summary"]["text"].startswith("Говорили") and v["summary"]["words"] == 5
    assert v["summary"]["written_at"]
    assert [d["date"] for d in v["days"]] == ["2026-10-03", "2026-10-02"]  # newest first, no journals
    assert v["digests"]["week"] == {"period": "2026-09-28", "text": "минулий тиждень"}
    assert v["digests"]["month"] is None and v["digests"]["year"] is None
    assert v["plans"]["year"]["items"] == [{"text": "дочитати Пруста", "deviation": False},
                                            {"text": "поїхати у Флоренцію", "deviation": True}]
    assert v["plans"]["day"]["period"] == "2026-10-04" and v["plans"]["month"] is None
    assert v["today"] == {"hour": 14, "text": "Неділя, 14:00. Книжка і кава.\nДругий рядок.",
                          "first_line": "Неділя, 14:00. Книжка і кава."}
    assert memory_view(state, "bruno", TODAY)["today"] is None  # yesterday's block is stale
    assert "mutation" not in json.dumps(v, ensure_ascii=False)  # the hidden tag never leaves raw


def test_plan_items_without_list_markup():
    assert plan_items("just a line <!-- mutation: place -->") == [{"text": "just a line", "deviation": True}]


def test_unreadable_state_is_unavailable_not_an_error(state):
    state.chmod(0o000)
    assert memory_view(state, "ada", TODAY) == {"available": False}
    assert usage_view(state, 7, TODAY) == {"available": False}


def test_usage_matches_the_v31_aggregation(state, monkeypatch):
    monkeypatch.setenv("PRICE_INPUT_PER_1M", "0.30")
    monkeypatch.setenv("PRICE_OUTPUT_PER_1M", "2.50")
    v = usage_view(state, 3, TODAY)
    lines = (state / "ada.usage.jsonl").read_text().splitlines() + (state / "bruno.usage.jsonl").read_text().splitlines()
    recs, bad = parse_lines(lines)
    expected = aggregate(recs, date(2026, 10, 2), TODAY)
    assert v["corrupt_lines"] == bad == 1 and v["priced"] and v["since"] == "2026-10-02"
    assert {(r["day"], r["agent"], r["kind"]): r["calls"] for r in v["rows"]} == {k: r.calls for k, r in expected.items()}
    assert v["total"]["calls"] == sum(r.calls for r in expected.values()) == 4
    assert v["per_agent"]["ada"]["input"] == 3000 and v["per_agent"]["bruno"]["calls"] == 1
    assert v["total"]["cost"] == pytest.approx(4000 / 1e6 * 0.30 + 400 / 1e6 * 2.50)
    assert [d["day"] for d in v["per_day"]] == ["2026-10-02", "2026-10-03", "2026-10-04"]
    assert v["per_day"][1]["agents"] == {"ada": 2200}
    only = usage_view(state, 3, TODAY, agent="bruno")
    assert set(only["per_agent"]) == {"bruno"}


def test_without_prices_there_is_no_cost(state, monkeypatch):
    monkeypatch.delenv("PRICE_INPUT_PER_1M", raising=False)
    monkeypatch.delenv("PRICE_OUTPUT_PER_1M", raising=False)
    v = usage_view(state, 7, TODAY)
    assert not v["priced"] and v["total"]["cost"] is None and all(r["cost"] is None for r in v["rows"])


def test_the_routes_validate_names_and_clamp_days(state, monkeypatch):
    monkeypatch.setattr(app_mod, "local_today", lambda: TODAY)
    reg = Registry()
    c = TestClient(create_app(token=TOKEN, registry=reg, docker_reader=DockerReader(client_factory=lambda: None),
                              prober=Prober(reg), state_dir=state, background=False))
    assert c.get("/api/agents/ada/memory", headers=AUTH).json()["today"]["hour"] == 14
    assert c.get("/api/agents/carol/memory", headers=AUTH).status_code == 404
    assert c.get("/api/usage?agent=carol", headers=AUTH).status_code == 404
    assert len(c.get("/api/usage?days=999", headers=AUTH).json()["per_day"]) == 31
    assert len(c.get("/api/usage?days=0", headers=AUTH).json()["per_day"]) == 1
    assert c.get("/api/usage", headers=AUTH).json()["total"]["calls"] == 5


# --- v4.2: the cat's mood of the day -------------------------------------------------------------------------------
def test_the_mood_view_reads_todays_horoscope_and_the_biorhythms(state):
    from pathlib import Path
    log = "\n\n===== 2026-10-03 =====\nвчора\n\n===== 2026-10-04 =====\nТранзити.\n\nРЕЗОЛЮЦІЯ: Колючий і сонний.\n"
    (state / "kit.mood.log").write_text(log, encoding="utf-8")
    view = memory_view(state, "kit", TODAY, Path("agents/canon/kit.natal.md"), with_mood=True)
    mood = view["mood"]
    assert (mood["date"], mood["resolution"]) == ("2026-10-04", "Колючий і сонний.")
    assert mood["reading"].startswith("Транзити.")
    assert [c["name"] for c in mood["biorhythms"]] == ["physical", "emotional", "intellectual"]
    assert memory_view(state, "kit", date(2026, 10, 5), Path("agents/canon/kit.natal.md"), True)["mood"] is None
    assert memory_view(state, "ada", TODAY)["mood"] is None          # a persona has no mood section


def test_the_memory_route_serves_the_cats_mood_and_not_adas(state, monkeypatch):
    monkeypatch.setattr(app_mod, "local_today", lambda: TODAY)
    (state / "kit.mood.log").write_text("\n\n===== 2026-10-04 =====\nРЕЗОЛЮЦІЯ: Мрр.\n", encoding="utf-8")
    reg = Registry()
    c = TestClient(create_app(token=TOKEN, registry=reg, docker_reader=DockerReader(client_factory=lambda: None),
                              prober=Prober(reg), state_dir=state, background=False))
    assert c.get("/api/agents/kit/memory", headers=AUTH).json()["mood"]["resolution"] == "Мрр."
    assert c.get("/api/agents/ada/memory", headers=AUTH).json()["mood"] is None
    assert c.get("/api/agents/kit/memory").status_code == 401
