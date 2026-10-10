"""The mood of the day (v4.2): Lumi's horoscope service, ported — once per local day, reused after a restart."""

import asyncio
import math
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

from agents.agent import Agent
from agents.config import AgentConfig
from agents.mood import (
    MOOD_SYSTEM,
    biorhythms,
    format_biorhythms,
    log_block,
    mood_request,
    parse_birth_date,
    reading_from_log,
    split_resolution,
)
from agents.roster import TYPES
from tests.test_first_sync import CFG

NATAL = "Народження: 16.04.2005, 15:20, Портленд (Орегон).\nСонце 27° Овен (IX) · ASC Діва 5°."
READING = "Транзити дня важкі.\n\nМарс тисне на Місяць.\n\nРЕЗОЛЮЦІЯ: Сьогодні колючий і сонний. Уникає людей."


# --- the pure service -----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("reading,resolution", [
    ("Абзац.\n\nРЕЗОЛЮЦІЯ: Сонний і колючий.", "Сонний і колючий."),                   # inline marker
    ("Абзац.\n\n**РЕЗОЛЮЦІЯ**\nСонний і колючий.", "Сонний і колючий."),               # marker on its own line
    ("Перший абзац.\n\nОстанній абзац без маркера.", "Останній абзац без маркера."),     # the fallback
    # review #6: Gemini's Markdown, and the marker echoed inside the reading
    ("Абзац.\n\n**РЕЗОЛЮЦІЯ:** Сонний і колючий.", "Сонний і колючий."),
    ("Абзац.\n\n**РЕЗОЛЮЦІЯ:**\nСонний і колючий.", "Сонний і колючий."),
    ("Абзац.\n\n### Резолюція\nСонний і колючий.", "Сонний і колючий."),
    ("Абзац.\n\n**РЕЗОЛЮЦІЯ: Сонний і колючий.**", "Сонний і колючий."),
    ("Ритми ляжуть у резолюцію: так і буде.\n\nМарс тисне.\n\nРЕЗОЛЮЦІЯ: Сонний.", "Сонний."),
    ("Це відіб'ється в РЕЗОЛЮЦІЇ.\n\nМарс тисне.\n\nРЕЗОЛЮЦІЯ: Сонний.", "Сонний."),
])
def test_split_resolution(reading, resolution):
    assert split_resolution(reading) == resolution


def test_the_log_is_append_only_and_the_last_block_of_a_day_wins():
    log = log_block("2026-10-09", "вчора") + log_block("2026-10-10", "перше") + log_block("2026-10-10", "друге")
    assert reading_from_log(log, "2026-10-10") == "друге"
    assert reading_from_log(log, "2026-10-09") == "вчора"
    assert reading_from_log(log, "2026-10-11") is None and reading_from_log("", "2026-10-10") is None


def test_the_request_carries_the_chart_the_date_and_the_rhythms_and_names_the_agent():
    system, contents = mood_request("Кіт", NATAL, "2026-10-10", "фізичний +0.50 (rising)")
    assert system == MOOD_SYSTEM.format(name="Кіт") and "РЕЗОЛЮЦІЯ" in system and "(Кіт)" in system
    assert "Натальна карта:\nНародження: 16.04.2005" in contents and "Дата: 2026-10-10." in contents
    assert "Біоритми (ТОЧНО обчислені цикли): фізичний +0.50 (rising)." in contents
    assert "Біоритми" not in mood_request("Кіт", NATAL, "2026-10-10")[1]


def test_biorhythms_match_the_hand_computed_sines():
    birth, today = date(2005, 4, 16), date(2026, 10, 10)
    d = (today - birth).days
    cycles = biorhythms(birth, today)
    for c, period in zip(cycles, (23, 28, 33), strict=True):
        assert c.value == pytest.approx(math.sin(2 * math.pi * d / period))
    assert [c.name for c in cycles] == ["physical", "emotional", "intellectual"]
    assert format_biorhythms(cycles).startswith("фізичний ")


def test_biorhythm_labels():
    from agents.mood import _label
    assert _label(0.0, 0.1) == "critical" and _label(0.1, -0.1) == "critical"
    assert _label(0.8, 0.9) == "high" and _label(-0.8, -0.9) == "low"
    assert _label(0.2, 0.3) == "rising" and _label(0.3, 0.2) == "falling"


def test_the_birth_date_comes_from_the_natal_text():
    assert parse_birth_date(NATAL) == date(2005, 4, 16)
    assert parse_birth_date("без дати") is None and parse_birth_date("Народження: 31.02.2005") is None


# --- the agent: once per local day, reused after a restart, never blocking ----------------------------------------
class MoodLLM:
    def __init__(self, reading=READING):
        self.reading = reading
        self.calls = []

    async def generate(self, transcript, system_instruction, max_output_tokens=400, kind="reply"):
        self.calls.append(kind)
        return self.reading if kind == "mood" else "Мрр."


def cat(tmp_path, llm, day="2026-10-10 12:00"):
    cfg = AgentConfig(**{**CFG.__dict__, "name": "Кіт", "user_id": "@kit:agora.lan", "type": "creature",
                         "capabilities": TYPES["creature"], "natal": NATAL})
    agent = Agent(cfg, llm=llm)
    agent.memory_file = tmp_path / "kit.memory.md"
    agent.client = SimpleNamespace(room_send=AsyncMock(), room_typing=AsyncMock())
    when = datetime.strptime(day, "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo("Europe/Kyiv"))
    agent.clock = lambda: int(when.timestamp() * 1000)
    return agent


def test_one_mood_call_per_local_day_and_its_resolution_enters_the_prompt(tmp_path):
    llm = MoodLLM()
    agent = cat(tmp_path, llm)
    asyncio.run(agent.reply("!room"))
    asyncio.run(agent.reply("!room"))
    assert llm.calls.count("mood") == 1
    assert "Настрій дня: Сьогодні колючий і сонний. Уникає людей." in agent.build_prompt()
    assert "===== 2026-10-10 =====" in agent.mood_file.read_text(encoding="utf-8")
    nxt = cat(tmp_path, llm, "2026-10-11 00:05")      # after midnight in Kyiv: a new day, a new reading
    asyncio.run(nxt.reply("!room"))
    assert llm.calls.count("mood") == 2


def test_a_restart_reuses_the_days_logged_reading(tmp_path):
    first = MoodLLM()
    asyncio.run(cat(tmp_path, first).reply("!room"))
    again = MoodLLM("НОВИЙ\n\nРЕЗОЛЮЦІЯ: інший")
    restarted = cat(tmp_path, again)
    asyncio.run(restarted.reply("!room"))
    assert again.calls.count("mood") == 0                         # no re-roll
    assert restarted.mood.resolution == "Сьогодні колючий і сонний. Уникає людей."


def test_a_failed_mood_means_no_block_and_the_reply_still_goes(tmp_path):
    llm = MoodLLM(reading=None)
    agent = cat(tmp_path, llm)
    asyncio.run(agent.reply("!room"))
    agent.client.room_send.assert_awaited_once()
    assert "Настрій дня" not in agent.build_prompt()
    asyncio.run(agent.reply("!room"))                              # backs off: no second call within 10 minutes
    assert llm.calls.count("mood") == 1


def test_a_persona_has_no_mood():
    from tests.test_first_sync import FakeLLM, make_agent
    agent = make_agent(FakeLLM())
    asyncio.run(agent.reply("!room"))
    assert "Настрій дня" not in agent.build_prompt()
    assert not agent.cfg.can("mood")


def test_the_watcher_casts_the_new_days_mood_without_a_reply(tmp_path, monkeypatch):
    """Review #7: purrs skip `reply()`, so past midnight the day's mood waited for the cat's first spoken line —
    the panel could say "No horoscope yet" all day. The idle watcher casts it."""
    real_sleep = asyncio.sleep

    async def fast_sleep(_):
        await real_sleep(0)

    monkeypatch.setattr("agents.agent.asyncio.sleep", fast_sleep)
    llm = MoodLLM()
    agent = cat(tmp_path, llm, "2026-10-11 00:05")

    async def run():
        task = asyncio.create_task(agent.idle_watcher())
        for _ in range(100):
            await real_sleep(0)
            if agent.mood is not None:
                break
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    asyncio.run(run())
    assert agent.mood is not None and agent.mood.date == "2026-10-11" and llm.calls == ["mood"]
    agent.client.room_send.assert_not_awaited()
