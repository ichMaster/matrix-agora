"""The day's Lviv weather (v5.10; the owner, 2026-10-26) — the real weather around a person's mood of the day.

Open-Meteo's forecast, with no key: the day's temperature, rain and wind, sunrise and sunset, and the cloud cover
through the night (an astronomer reads the night). Fetched once a local day and kept in `state/<name>.weather.json`
(the day and the line — world data, no room text), so a restart makes no second request. Only the mood reading takes
the line; it never reaches a prompt by itself. A failed fetch means no weather, never a blocked mood. Pure but for
the HTTP call and the file I/O.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.parse
from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from pathlib import Path

log = logging.getLogger("agent.weather")

LVIV = (49.84, 24.03)
BASE_URL = "https://api.open-meteo.com/v1/forecast"
DAILY = ("temperature_2m_max", "temperature_2m_min", "precipitation_sum", "wind_speed_10m_max", "sunrise", "sunset",
         "weather_code")
NIGHT_HOURS = (21, 22, 23)       # that evening …
NIGHT_HOURS_NEXT = range(6)   # … and the small hours after midnight
# WMO weather codes, as Open-Meteo gives them → a word for the day
CODES = ((0, "ясно"), (1, "переважно ясно"), (2, "мінлива хмарність"), (3, "хмарно"), (48, "туман"),
         (57, "мряка"), (67, "дощ"), (77, "сніг"), (82, "зливи"), (86, "снігопад"), (99, "гроза"))

Fetch = Callable[[str], Awaitable[dict]]


def weather_url(lat: float = LVIV[0], lon: float = LVIV[1], tz: str = "Europe/Kyiv") -> str:
    """Today and tomorrow (the night runs past midnight), in local time."""
    return BASE_URL + "?" + urllib.parse.urlencode({
        "latitude": lat, "longitude": lon, "daily": ",".join(DAILY), "hourly": "cloud_cover", "timezone": tz,
        "forecast_days": 2})


def _code_word(code) -> str | None:
    if not isinstance(code, int | float) or isinstance(code, bool):
        return None
    return next((word for top, word in CODES if code <= top), None)


def _num(value) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _temp(value: float) -> str:
    n = round(value)
    return f"{n:+d}" if n else "0"


def parse_weather(data: dict, day: date) -> str | None:
    """The day's line, e.g. «Львів: дощ, від +3 до +9 °C, опади 4 мм, вітер до 18 км/год, схід 07:31, захід 16:52,
    уночі хмарність 85 %»; a missing field is left out, and an answer without the day's temperature is None."""
    daily = (data or {}).get("daily") if isinstance(data, dict) else None
    if not isinstance(daily, dict) or not isinstance(daily.get("time"), list) or day.isoformat() not in daily["time"]:
        return None
    i = daily["time"].index(day.isoformat())

    def at(key):
        values = daily.get(key)
        return values[i] if isinstance(values, list) and i < len(values) else None

    low, high = _num(at("temperature_2m_min")), _num(at("temperature_2m_max"))
    if low is None or high is None:
        return None
    parts = [w] if (w := _code_word(at("weather_code"))) else []
    parts.append(f"від {_temp(low)} до {_temp(high)} °C")
    if (rain := _num(at("precipitation_sum"))) is not None:
        parts.append(f"опади {round(rain)} мм" if round(rain) else "без опадів")
    if (wind := _num(at("wind_speed_10m_max"))) is not None:
        parts.append(f"вітер до {round(wind)} км/год")
    for key, word in (("sunrise", "схід"), ("sunset", "захід")):
        if isinstance(stamp := at(key), str) and "T" in stamp:
            parts.append(f"{word} {stamp.split('T', 1)[1][:5]}")
    if (clouds := night_clouds(data, day)) is not None:
        parts.append(f"уночі хмарність {clouds} %")
    return "Львів: " + ", ".join(parts)


def night_clouds(data: dict, day: date) -> int | None:
    """The mean cloud cover from 21:00 that day to 05:00 the next, or None without the hours."""
    hourly = data.get("hourly") if isinstance(data, dict) else None
    if not isinstance(hourly, dict) or not isinstance(hourly.get("time"), list):
        return None
    cover = hourly.get("cloud_cover") if isinstance(hourly.get("cloud_cover"), list) else []
    nxt = day + timedelta(days=1)
    wanted = {f"{day.isoformat()}T{h:02d}:00" for h in NIGHT_HOURS} | {
        f"{nxt.isoformat()}T{h:02d}:00" for h in NIGHT_HOURS_NEXT}
    values = [v for t, v in zip(hourly["time"], cover, strict=False) if t in wanted and _num(v) is not None]
    return round(sum(values) / len(values)) if values else None


async def http_json(url: str) -> dict:
    import aiohttp  # matrix-nio's own dependency

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session, session.get(url) as resp:
        resp.raise_for_status()
        return await resp.json()


async def fetch_weather(day: date, tz: str = "Europe/Kyiv", fetch: Fetch = http_json) -> str | None:
    """One request; any failure (the network, the status, the JSON, the shape) is logged by its type and is None."""
    try:
        data = await fetch(weather_url(tz=tz))
    except Exception as exc:  # noqa: BLE001 — no weather is never a blocked mood
        log.error("weather fetch failed (%s)", type(exc).__name__)
        return None
    line = parse_weather(data, day)
    if line is None:
        log.error("weather answer has no day's temperature")
    return line


def load_weather(path: Path, day: str) -> str | None:
    """The day's line from the file, or None (another day, missing, corrupt)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("day") != day or not isinstance(data.get("weather"), str):
        return None
    return data["weather"] or None


def save_weather(path: Path, day: str, line: str) -> None:
    """Atomic, private from birth (0600); a failure is logged by its type — the line is kept in memory anyway."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, json.dumps({"day": day, "weather": line}, ensure_ascii=False).encode("utf-8"))
        finally:
            os.close(fd)
        os.replace(tmp, path)
    except OSError as exc:
        log.error("weather not saved (%s)", type(exc).__name__)
