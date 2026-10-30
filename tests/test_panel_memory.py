import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

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
@pytest.mark.canon
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


def test_a_torn_mood_log_never_breaks_the_memory_route(state, monkeypatch):
    """Review #9: invalid UTF-8 from a torn append made /api/agents/kit/memory a 500 on every poll."""
    monkeypatch.setattr(app_mod, "local_today", lambda: TODAY)
    (state / "kit.mood.log").write_bytes(b"\n\n===== 2026-10-03 =====\n\xd0\n\n===== 2026-10-04 =====\n"
                                         + "РЕЗОЛЮЦІЯ: Мрр.\n".encode())
    reg = Registry()
    c = TestClient(create_app(token=TOKEN, registry=reg, docker_reader=DockerReader(client_factory=lambda: None),
                              prober=Prober(reg), state_dir=state, background=False))
    r = c.get("/api/agents/kit/memory", headers=AUTH)
    assert r.status_code == 200 and r.json()["mood"]["resolution"] == "Мрр."


# --- v5.10: Кіра's mood of the day and the Lviv weather ---------------------------------------------------------------
WEATHER = "Львів: дощ, від +3 до +9 °C, опади 4 мм, вітер до 18 км/год, схід 07:31, захід 16:52"


def test_the_weather_view_is_todays_line_or_none(state):
    (state / "kira.weather.json").write_text(json.dumps({"day": "2026-10-04", "weather": WEATHER}), encoding="utf-8")
    assert memory_view(state, "kira", TODAY, with_mood=True)["weather"] == {"date": "2026-10-04", "line": WEATHER}
    assert memory_view(state, "kira", date(2026, 10, 5), with_mood=True)["weather"] is None       # another day
    assert memory_view(state, "kira", TODAY)["weather"] is None                                    # no `mood`
    assert memory_view(state, "kit", TODAY, with_mood=True)["weather"] is None                     # never fetched
    (state / "kira.weather.json").write_bytes(b"{\"day\": \"2026-10-04\", \xd0")
    assert memory_view(state, "kira", TODAY, with_mood=True)["weather"] is None                    # corrupt, no 500


def test_the_memory_route_serves_kiras_mood_and_weather_and_the_cat_none(state, monkeypatch):
    monkeypatch.setattr(app_mod, "local_today", lambda: TODAY)
    (state / "kira.mood.log").write_text("\n\n===== 2026-10-04 =====\nЧитання.\n\nРЕЗОЛЮЦІЯ: Ти тиха.\n",
                                         encoding="utf-8")
    (state / "kira.weather.json").write_text(json.dumps({"day": "2026-10-04", "weather": WEATHER}), encoding="utf-8")
    reg = Registry()
    c = TestClient(create_app(token=TOKEN, registry=reg, docker_reader=DockerReader(client_factory=lambda: None),
                              prober=Prober(reg), state_dir=state, background=False))
    kira = c.get("/api/agents/kira/memory", headers=AUTH).json()
    assert kira["mood"]["resolution"] == "Ти тиха." and kira["weather"]["line"] == WEATHER
    assert c.get("/api/agents/kit/memory", headers=AUTH).json()["weather"] is None
    assert c.get("/api/agents/ada/memory", headers=AUTH).json()["weather"] is None


# --- v5.11: her events, by day ---------------------------------------------------------------------------------------
EVENTS_TODAY = ("<!-- rolled 09 -->\n\n## 09:00 · story · surprise\nПодзвонила подруга.\n"
                "<!-- news-rolled https://zaxid.net/a -->\n\n## 14:00 · heard · news\n<!-- link: https://zaxid.net/a -->\n"
                "Почула про трамвай.\n")


def test_the_events_view_by_day_newest_first(state):
    folder = state / "kira.events"
    folder.mkdir()
    (folder / "2026-10-04.md").write_text(EVENTS_TODAY, encoding="utf-8")
    (folder / "2026-10-02.md").write_text("\n## 18:00 · heavy · rolled\nМені відмовили.\n", encoding="utf-8")
    (folder / "2026-10-03.md").write_text("<!-- rolled 10 -->\n", encoding="utf-8")            # a day of misses
    (folder / "2026-09-20.md").write_text("\n## 10:00 · joyful · rolled\nДавно.\n", encoding="utf-8")  # past 7 days
    view = memory_view(state, "kira", TODAY, with_events=True)["events"]
    assert [d["date"] for d in view] == ["2026-10-04", "2026-10-02"]
    assert view[0]["events"] == [
        {"time": "09:00", "kind": "story", "source": "surprise", "text": "Подзвонила подруга.", "link": None},
        {"time": "14:00", "kind": "heard", "source": "news", "text": "Почула про трамвай.", "link": "https://zaxid.net/a"}]
    assert memory_view(state, "kira", TODAY)["events"] is None                         # no `events`
    assert memory_view(state, "ada", TODAY, with_events=True)["events"] == []          # none yet
    (folder / "2026-10-04.md").write_bytes(b"\n## 09:00 \xd0\xff broken")
    assert [d["date"] for d in memory_view(state, "kira", TODAY, with_events=True)["events"]] == ["2026-10-02"]


def test_the_memory_route_serves_her_events_and_only_hers(state, monkeypatch):
    monkeypatch.setattr(app_mod, "local_today", lambda: TODAY)
    (state / "kira.events").mkdir()
    (state / "kira.events" / "2026-10-04.md").write_text(EVENTS_TODAY, encoding="utf-8")
    reg = Registry()
    c = TestClient(create_app(token=TOKEN, registry=reg, docker_reader=DockerReader(client_factory=lambda: None),
                              prober=Prober(reg), state_dir=state, background=False))
    kira = c.get("/api/agents/kira/memory", headers=AUTH).json()
    assert kira["events"][0]["events"][1]["link"] == "https://zaxid.net/a"
    assert c.get("/api/agents/ada/memory", headers=AUTH).json()["events"] is None
    assert c.get("/api/agents/kira/memory").status_code == 401


# --- v5.12: her thoughts, by day ---------------------------------------------------------------------------------------
THOUGHTS_TODAY = ("\n## 09:15 · news · thought · zaxid\n<!-- title: Новий телескоп -->\n<!-- link: https://zaxid.net/n1 -->\n"
                  "Аж мурашки.\n\n## 21:40 · reflection · thought_private · private\nВін був тихий.\n")


def test_the_thoughts_view_by_day_newest_first(state):
    folder = state / "kira.thoughts"
    folder.mkdir()
    (folder / "2026-10-04.md").write_text(THOUGHTS_TODAY, encoding="utf-8")
    (folder / "2026-10-02.md").write_text("\n## 14:05 · reflection · thought · agora\nАда про слова.\n", encoding="utf-8")
    (folder / "2026-09-20.md").write_text("\n## 10:00 · news · thought · guardian\nДавно.\n", encoding="utf-8")
    view = memory_view(state, "kira", TODAY, with_thoughts=True)["thoughts"]
    assert [d["date"] for d in view] == ["2026-10-04", "2026-10-02"]
    assert view[0]["thoughts"] == [
        {"time": "09:15", "kind": "news", "place": "thought", "source": "zaxid", "title": "Новий телескоп",
         "text": "Аж мурашки.", "link": "https://zaxid.net/n1"},
        {"time": "21:40", "kind": "reflection", "place": "thought_private", "source": "private", "title": None,
         "text": "Він був тихий.", "link": None}]
    assert memory_view(state, "kira", TODAY)["thoughts"] is None                       # no `thoughts`
    assert memory_view(state, "ada", TODAY, with_thoughts=True)["thoughts"] == []      # none yet
    (folder / "2026-10-04.md").write_bytes(b"\n## 09:00 \xd0\xff broken")
    assert [d["date"] for d in memory_view(state, "kira", TODAY, with_thoughts=True)["thoughts"]] == ["2026-10-02"]


def test_an_unreadable_thoughts_folder_is_null_never_a_500(state):
    (state / "kira.thoughts").write_text("not a folder", encoding="utf-8")
    assert memory_view(state, "kira", TODAY, with_thoughts=True)["thoughts"] is None


def test_the_memory_route_serves_her_thoughts_and_only_hers(state, monkeypatch):
    monkeypatch.setattr(app_mod, "local_today", lambda: TODAY)
    (state / "kira.thoughts").mkdir()
    (state / "kira.thoughts" / "2026-10-04.md").write_text(THOUGHTS_TODAY, encoding="utf-8")
    reg = Registry()
    c = TestClient(create_app(token=TOKEN, registry=reg, docker_reader=DockerReader(client_factory=lambda: None),
                              prober=Prober(reg), state_dir=state, background=False))
    kira = c.get("/api/agents/kira/memory", headers=AUTH).json()
    assert kira["thoughts"][0]["thoughts"][0]["link"] == "https://zaxid.net/n1"
    assert c.get("/api/agents/ada/memory", headers=AUTH).json()["thoughts"] is None
    assert c.get("/api/agents/kira/memory").status_code == 401


# --- v4.3: the cat's past life and initiative -----------------------------------------------------------------------
@pytest.mark.canon
def test_the_cat_shows_his_theses_his_last_nudge_and_todays_count(state, monkeypatch):
    monkeypatch.setattr(app_mod, "local_today", lambda: TODAY)
    monkeypatch.setenv("TIMEZONE", "Europe/Kyiv")
    sent = 1_791_111_900_000  # 2026-10-04 14:05 Kyiv
    (state / "kit.nudge.json").write_text(json.dumps({"last_ms": sent, "day": "2026-10-04", "count": 2,
                                                      "sent_ms": sent}), encoding="utf-8")
    reg = Registry()
    c = TestClient(create_app(token=TOKEN, registry=reg, docker_reader=DockerReader(client_factory=lambda: None),
                              prober=Prober(reg), state_dir=state, background=False))
    kit = c.get("/api/agents/kit/memory", headers=AUTH).json()
    from pathlib import Path

    from agents.pastlife import parse_theses
    real = len(parse_theses(Path("agents/canon/kit.memories.md").read_text(encoding="utf-8")))
    assert kit["pastlife"] == {"theses": real}                              # what the agent loads (review #11)
    assert kit["nudge"] == {"last": "2026-10-04T14:05:00+03:00", "today": 2}
    ada = c.get("/api/agents/ada/memory", headers=AUTH).json()
    assert ada["pastlife"] is None and ada["nudge"] is None                 # a persona has neither
    assert c.get("/api/agents/kit/memory").status_code == 401


def test_the_nudge_view_rolls_over_and_degrades(state):
    from panel.memory import nudge_view, pastlife_view
    assert nudge_view(state, "kit", TODAY) == {"last": None, "today": 0}     # no file yet: none sent
    (state / "kit.nudge.json").write_text(json.dumps({"last_ms": 1, "day": "2026-10-03", "count": 5,
                                                      "sent_ms": None}), encoding="utf-8")
    assert nudge_view(state, "kit", TODAY) == {"last": None, "today": 0}     # yesterday's count
    (state / "kit.nudge.json").write_text("{torn", encoding="utf-8")
    assert nudge_view(state, "kit", TODAY) is None                          # never a 500
    bad = state / "bad.md"
    bad.write_text("- [broken thesis\n", encoding="utf-8")
    assert pastlife_view(bad) is None and pastlife_view(state / "missing.md") is None and pastlife_view(None) is None



def test_the_usage_view_never_prices_a_subscription_row(state, monkeypatch):
    """v4.4: Claude's rows carry tokens, engine and billing, and no cost."""
    from agents.usage import sdk_usage_line
    from panel.memory import usage_view
    monkeypatch.setenv("PRICE_INPUT_PER_1M", "0.30")
    monkeypatch.setenv("PRICE_OUTPUT_PER_1M", "2.50")
    line = sdk_usage_line("2026-10-04T12:00:00+03:00", "claude", "reply", "opus",
                          {"input_tokens": 1000, "output_tokens": 100}, True, 0.2)
    (state / "claude.usage.jsonl").write_text(json.dumps(line) + "\n", encoding="utf-8")
    view = usage_view(state, 7, TODAY)
    row = next(r for r in view["rows"] if r["agent"] == "claude")
    assert (row["engine"], row["billing"], row["cost"], row["total"]) == ("claude-sdk", "subscription", None, 1100)
    assert view["per_agent"]["claude"]["cost"] is None and view["per_agent"]["claude"]["billing"] == "subscription"


def test_claudes_card_reads_his_rate_limit_and_auth_check(state, monkeypatch):
    """v4.4: the memory view carries `ratelimit` for the claude-sdk engine only; a torn file degrades to null."""
    monkeypatch.setattr(app_mod, "local_today", lambda: TODAY)
    status = {"status": "allowed_warning", "utilization": 0.82, "resets_at": 1_791_200_000,
              "rate_limit_type": "seven_day_opus", "muted_until": 1_791_200_000, "auth": "oauth", "model": "opus",
              "last_error": None, "updated_at": 1_791_100_000}
    (state / "claude.ratelimit.json").write_text(json.dumps(status), encoding="utf-8")
    reg = Registry()
    c = TestClient(create_app(token=TOKEN, registry=reg, docker_reader=DockerReader(client_factory=lambda: None),
                              prober=Prober(reg), state_dir=state, background=False))
    assert c.get("/api/agents/claude/memory", headers=AUTH).json()["ratelimit"] == status
    assert c.get("/api/agents/kit/memory", headers=AUTH).json()["ratelimit"] is None
    (state / "claude.ratelimit.json").write_text("{torn", encoding="utf-8")
    r = c.get("/api/agents/claude/memory", headers=AUTH)
    assert r.status_code == 200 and r.json()["ratelimit"] is None


def test_claudes_card_reads_his_news(state, monkeypatch):
    """v4.5: the memory view carries `news` for an agent with the capability (Claude), null for the others."""
    monkeypatch.setattr(app_mod, "local_today", lambda: TODAY)
    monkeypatch.setenv("TIMEZONE", "Europe/Kyiv")
    (state / "claude.news.json").write_text(json.dumps({"last_ms": 1, "day": "2026-10-04", "count": 2,
                                                       "sent_ms": 1_791_111_900_000}), encoding="utf-8")
    reg = Registry()
    c = TestClient(create_app(token=TOKEN, registry=reg, docker_reader=DockerReader(client_factory=lambda: None),
                              prober=Prober(reg), state_dir=state, background=False))
    assert c.get("/api/agents/claude/memory", headers=AUTH).json()["news"] == {"last": "2026-10-04T14:05:00+03:00",
                                                                                "today": 2}
    assert c.get("/api/agents/kit/memory", headers=AUTH).json()["news"] is None


# --- v5.1: Hermes's card — his digests and the spoken characters ------------------------------------------------------
def hermes_client(state, monkeypatch):
    monkeypatch.setattr(app_mod, "local_today", lambda: TODAY)
    monkeypatch.setenv("TIMEZONE", "Europe/Kyiv")
    reg = Registry()
    return TestClient(create_app(token=TOKEN, registry=reg, docker_reader=DockerReader(client_factory=lambda: None),
                                 prober=Prober(reg), state_dir=state, background=False))


def test_hermes_card_reads_his_digests_his_characters_and_his_cap(state, monkeypatch):
    from agents.usage import tts_usage_line
    (state / "hermes.digest.json").write_text(json.dumps({
        "room": "!dm", "point_event": "$e", "point_ts": 1, "last_ms": 1_791_111_900_000, "day": "2026-10-04",
        "count": 2}), encoding="utf-8")
    (state / "hermes.usage.jsonl").write_text("\n".join(json.dumps(x) for x in (
        tts_usage_line("2026-10-02T10:00:00+03:00", "hermes", "eleven_turbo_v2_5", 1200, True),
        tts_usage_line("2026-10-03T10:00:00+03:00", "hermes", "eleven_turbo_v2_5", 900, False),
        tts_usage_line("2026-09-30T10:00:00+03:00", "hermes", "eleven_turbo_v2_5", 5000, True))) + "\n",
        encoding="utf-8")
    voice_id = "SecretishVoice0123456"
    (state / "hermes.settings.json").write_text(json.dumps({
        "HERMES_TTS_MONTHLY_CHARS": {"value": "150000", "source": "default"},
        "HERMES_VOICE_ID": {"value": voice_id, "source": "env"}}), encoding="utf-8")
    c = hermes_client(state, monkeypatch)
    view = c.get("/api/agents/hermes/memory", headers=AUTH).json()
    assert view["digest"] == {"last": "2026-10-04T14:05:00+03:00", "today": 2, "month_chars": 1200,
                              "cap": 150000, "voice": True}
    assert voice_id not in json.dumps(view) and "!dm" not in json.dumps(view["digest"])
    for other in ("ada", "kit", "claude"):
        assert c.get(f"/api/agents/{other}/memory", headers=AUTH).json()["digest"] is None


def test_hermes_digest_view_before_his_start_and_when_torn(state, monkeypatch):
    c = hermes_client(state, monkeypatch)
    assert c.get("/api/agents/hermes/memory", headers=AUTH).json()["digest"] == {
        "last": None, "today": 0, "month_chars": 0, "cap": None, "voice": None}
    (state / "hermes.digest.json").write_text("{torn", encoding="utf-8")
    r = c.get("/api/agents/hermes/memory", headers=AUTH)
    assert r.status_code == 200 and r.json()["digest"] is None


def test_the_usage_view_counts_characters_and_prices_pro_by_its_own_pair(state, monkeypatch):
    from types import SimpleNamespace

    from agents.usage import tts_usage_line
    pro = SimpleNamespace(prompt_token_count=1_000_000, candidates_token_count=0, thoughts_token_count=1_000_000,
                          total_token_count=2_000_000)
    (state / "hermes.usage.jsonl").write_text("\n".join(json.dumps(x) for x in (
        usage_line("2026-10-04T10:00:00+03:00", "hermes", "digest_voice", "gemini-3.1-pro-preview", pro, True),
        tts_usage_line("2026-10-04T10:00:05+03:00", "hermes", "eleven_turbo_v2_5", 1300, True))) + "\n",
        encoding="utf-8")
    monkeypatch.setenv("PRICE_INPUT_PER_1M", "0.30")
    monkeypatch.setenv("PRICE_OUTPUT_PER_1M", "2.50")
    monkeypatch.setenv("PRICE_MODELS", "gemini-3.1-pro-preview=2/12")
    u = usage_view(state, 3, TODAY, "hermes")
    rows = {r["kind"]: r for r in u["rows"]}
    assert rows["digest_voice"]["cost"] == 14.0 and rows["digest_voice"]["characters"] == 0
    assert (rows["tts"]["characters"], rows["tts"]["cost"], rows["tts"]["billing"]) == (1300, None, "subscription")
    assert u["per_agent"]["hermes"]["characters"] == 1300 and u["total"]["characters"] == 1300


def test_the_usage_view_says_when_only_some_models_are_priced(state, monkeypatch):
    """Review #5: PRICE_MODELS alone prices those models; the page then says the others have no price."""
    monkeypatch.delenv("PRICE_INPUT_PER_1M", raising=False)
    monkeypatch.delenv("PRICE_OUTPUT_PER_1M", raising=False)
    monkeypatch.setenv("PRICE_MODELS", "gemini-3.1-pro-preview=2/12")
    u = usage_view(state, 3, TODAY)
    assert u["priced"] is True and u["default_priced"] is False
    assert all(r["cost"] is None for r in u["rows"])                  # the fixture's rows are another model
    from panel.app import STATIC_DIR
    assert "Only some models have prices (PRICE_MODELS)" in (STATIC_DIR / "app.js").read_text(encoding="utf-8")



def test_a_malformed_price_models_entry_is_named_once(state, monkeypatch, caplog):
    """Review #12: ARCHITECTURE says a malformed entry is ignored with a warning — the panel said nothing."""
    import logging
    caplog.set_level(logging.WARNING)
    monkeypatch.setenv("PRICE_MODELS", "gemini-3.1-pro-preview=2/12, pro=twelve")
    for _ in range(3):
        u = usage_view(state, 3, TODAY)
    assert u["priced"] is True
    assert [r.getMessage() for r in caplog.records].count("PRICE_MODELS entry 'pro=twelve' is not model=in/out — ignored") == 1


def test_the_today_block_with_the_days_event_count_still_shows(state):
    """Review #1: from v5.11 the block's tag carries the day's event count; the card and the tab still read it."""
    (state / "kira.today.md").write_text("<!-- 2026-10-04T14 e2 -->\nСьогодні вже: робота.\nЩе сьогодні: сеанс.\n",
                                         encoding="utf-8")
    assert memory_view(state, "kira", TODAY)["today"] == {
        "hour": 14, "text": "Сьогодні вже: робота.\nЩе сьогодні: сеанс.", "first_line": "Сьогодні вже: робота."}


def test_the_blocks_are_counted_per_agent_and_for_today(state):
    """v5.13 — a line with `blocked` counts on its day; an older line without the field counts 0."""
    lines = [json.dumps(usage_line(ts, ag, "private", "m", None, False, stage))
             for ts, ag, stage in (("2026-10-04T09:00:00+03:00", "kira", "prompt"),
                                   ("2026-10-04T10:00:00+03:00", "kira", "answer"),
                                   ("2026-10-03T22:00:00+03:00", "kira", "answer"),
                                   ("2026-10-04T11:00:00+03:00", "kira", None))]
    (state / "kira.usage.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    v = usage_view(state, 7, TODAY)
    kira = v["per_agent"]["kira"]
    assert (kira["blocked"], kira["blocked_today"], kira["calls"]) == (3, 2, 4)
    assert (v["per_agent"]["ada"]["blocked"], v["per_agent"]["ada"]["blocked_today"]) == (0, 0)  # no field: 0
    assert v["total"]["blocked"] == 3
    assert {(r["day"], r["agent"]): r["blocked"] for r in v["rows"] if r["agent"] == "kira"} == {
        ("2026-10-03", "kira"): 1, ("2026-10-04", "kira"): 2}


def test_her_route_and_the_archives_marks_for_her_card(state, monkeypatch):
    """v5.14 — the route file read as the card needs it, today's counts only; the archive counts the closed lines."""
    import sqlite3

    from agents.archive import Archive
    from agents.route import Route, save_route
    from panel.memory import archive_view, route_view
    monkeypatch.setenv("TIMEZONE", "Europe/Kyiv")
    assert route_view(state, "kira", TODAY) == {"pin": "auto", "window_until": None, "window_open": False,
                                                "blocks_today": 0, "answers": {"gemini": 0, "backup": 0}}
    day0 = int(datetime(2026, 10, 4, tzinfo=ZoneInfo("Europe/Kyiv")).timestamp() * 1000)
    save_route(state / "kira.route.json", Route(blocks=(day0 - 1000, day0 + 60_000), window_until_ms=day0 + 3_600_000,
                                                day="2026-10-04", answers={"gemini": 3, "backup": 2}))
    view = route_view(state, "kira", TODAY, now_ms=day0 + 1_800_000)
    assert view["window_until"] == "2026-10-04T01:00+03:00" and view["blocks_today"] == 1
    assert view["window_open"] is True and view["answers"] == {"gemini": 3, "backup": 2}
    # review #3: the file keeps an ended window until Gemini answers again — it is not open any more
    assert route_view(state, "kira", TODAY, now_ms=day0 + 7_200_000)["window_open"] is False
    (state / "kira.route.json").write_text("{broken")
    assert route_view(state, "kira", TODAY) is None
    a = Archive(state / "kira.archive.db")
    for key, mark in (("a", "gemini"), ("b", "waiting"), ("c", "waiting"), ("d", "censored")):
        a.append(key, 1, "private", "telegram", "Ich", f"рядок {key}")
        a.mark([key], mark)
    a.close()
    assert archive_view(state, "kira") == {"lines": 4, "embedded": 0, "waiting": 2, "censored": 1}
    old = sqlite3.connect(state / "ada.archive.db")  # before v5.13: no mark column
    old.execute("CREATE TABLE lines (id INTEGER PRIMARY KEY, emb BLOB)")
    old.commit()
    old.close()
    assert archive_view(state, "ada") == {"lines": 0, "embedded": 0, "waiting": 0, "censored": 0}
    assert memory_view(state, "kira", TODAY, with_route=False)["route"] is None
