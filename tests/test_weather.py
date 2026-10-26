"""v5.10 — the day's Lviv weather for a person's mood: Open-Meteo, once a day, kept in `state/<name>.weather.json`;
a failure means no weather, never a blocked mood. No test touches the network."""
import asyncio
import json
import os
import stat
from datetime import date
from urllib.parse import parse_qs, urlparse

import pytest

from agents.weather import fetch_weather, load_weather, night_clouds, parse_weather, save_weather, weather_url
from tests.test_mood import MoodLLM, cat

DAY = date(2026, 10, 26)
NIGHT = [f"2026-10-26T{h:02d}:00" for h in range(24)] + [f"2026-10-27T{h:02d}:00" for h in range(24)]


def answer(**daily):
    base = {"time": ["2026-10-26", "2026-10-27"], "temperature_2m_max": [9.4, 7.0], "temperature_2m_min": [2.6, 1.0],
            "precipitation_sum": [4.2, 0.0], "wind_speed_10m_max": [17.8, 9.0],
            "sunrise": ["2026-10-26T07:31", "2026-10-27T07:33"], "sunset": ["2026-10-26T16:52", "2026-10-27T16:50"],
            "weather_code": [61, 3]}
    cover = [0] * 21 + [80, 90, 100] + [70, 80, 90, 100, 65, 90] + [0] * 18  # 21–23 and 00–05 → 85
    return {"daily": {**base, **daily}, "hourly": {"time": NIGHT, "cloud_cover": cover}}


LINE = ("Львів: дощ, від +3 до +9 °C, опади 4 мм, вітер до 18 км/год, схід 07:31, захід 16:52, "
        "уночі хмарність 85 %")


def test_the_url_asks_open_meteo_for_lviv_today_and_tomorrow_with_no_key():
    url = urlparse(weather_url())
    q = parse_qs(url.query)
    assert url.netloc == "api.open-meteo.com" and url.path == "/v1/forecast"
    assert (q["latitude"], q["longitude"], q["forecast_days"]) == (["49.84"], ["24.03"], ["2"])
    assert q["timezone"] == ["Europe/Kyiv"] and q["hourly"] == ["cloud_cover"] and "apikey" not in q
    assert set(q["daily"][0].split(",")) >= {"temperature_2m_max", "precipitation_sum", "sunrise", "sunset"}


def test_the_day_is_one_line_from_a_canned_answer():
    assert parse_weather(answer(), DAY) == LINE
    assert parse_weather(answer(), date(2026, 10, 27)).startswith("Львів: хмарно, від +1 до +7 °C, без опадів")


def test_the_nights_cloud_cover_runs_past_midnight():
    assert night_clouds(answer(), DAY) == 85
    assert night_clouds({"hourly": {"time": NIGHT[:22], "cloud_cover": [50] * 22}}, DAY) == 50   # only 21:00 left
    assert night_clouds({"daily": {}}, DAY) is None


def test_a_missing_field_is_left_out_and_no_temperature_is_no_weather():
    line = parse_weather(answer(precipitation_sum=None, weather_code=[None, None], sunrise=["?", "?"]), DAY)
    assert line == "Львів: від +3 до +9 °C, вітер до 18 км/год, захід 16:52, уночі хмарність 85 %"
    assert parse_weather(answer(temperature_2m_max=[None, 7.0]), DAY) is None
    assert parse_weather(answer(), date(2026, 10, 28)) is None                     # not the asked day
    assert parse_weather({"error": True, "reason": "bad"}, DAY) is None and parse_weather(None, DAY) is None
    assert parse_weather(answer(temperature_2m_min=[-2.6, 0], temperature_2m_max=[-0.4, 0]), DAY).startswith(
        "Львів: дощ, від -3 до 0 °C")


@pytest.mark.parametrize("fails", [OSError("down"), ValueError("not json"), TimeoutError()])
def test_a_failed_fetch_is_no_weather_never_an_exception(fails):
    async def fetch(url):
        raise fails
    assert asyncio.run(fetch_weather(DAY, fetch=fetch)) is None


def test_a_fetch_reads_the_day():
    seen = []

    async def fetch(url):
        seen.append(url)
        return answer()
    assert asyncio.run(fetch_weather(DAY, fetch=fetch)) == LINE and seen == [weather_url()]


def test_the_day_file_is_private_and_only_for_its_day(tmp_path):
    path = tmp_path / "kira.weather.json"
    save_weather(path, "2026-10-26", LINE)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert json.loads(path.read_text(encoding="utf-8")) == {"day": "2026-10-26", "weather": LINE}
    assert load_weather(path, "2026-10-26") == LINE and load_weather(path, "2026-10-27") is None
    path.write_text("{torn", encoding="utf-8")
    assert load_weather(path, "2026-10-26") is None and load_weather(tmp_path / "none.json", "2026-10-26") is None


class Fetches:
    def __init__(self, line=LINE):
        self.line, self.calls = line, []

    async def __call__(self, day, tz):
        self.calls.append((day, tz))
        return self.line


def test_one_fetch_a_day_kept_across_a_restart(tmp_path):
    agent = cat(tmp_path, MoodLLM(), "2026-10-26 09:00")
    agent.weather_fetch = fetch = Fetches()
    now = agent_now(agent)
    assert asyncio.run(agent.ensure_weather(now)) == LINE
    assert asyncio.run(agent.ensure_weather(now)) == LINE and fetch.calls == [(DAY, "Europe/Kyiv")]
    assert load_weather(agent.weather_file, "2026-10-26") == LINE
    restarted = cat(tmp_path, MoodLLM(), "2026-10-26 15:00")
    restarted.weather_fetch = again = Fetches()
    assert asyncio.run(restarted.ensure_weather(agent_now(restarted))) == LINE and again.calls == []


def test_a_failed_fetch_writes_nothing_and_retries_after_ten_minutes(tmp_path):
    agent = cat(tmp_path, MoodLLM(), "2026-10-26 09:00")
    agent.weather_fetch = fetch = Fetches(None)
    assert asyncio.run(agent.ensure_weather(agent_now(agent))) is None
    assert not agent.weather_file.exists()
    assert asyncio.run(agent.ensure_weather(agent_now(agent))) is None and len(fetch.calls) == 1   # backs off
    fetch.line = LINE
    start = agent.clock()
    agent.clock = lambda: start + 600_000
    assert asyncio.run(agent.ensure_weather(agent_now(agent))) == LINE and len(fetch.calls) == 2


def agent_now(agent):
    from agents.world import local_now
    return local_now(agent.clock(), agent.tz)
