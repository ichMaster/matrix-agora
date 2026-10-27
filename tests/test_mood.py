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
    HOROSCOPE_RE,
    MOOD_SYSTEM,
    NO_SKY_RULE,
    NO_SKY_SECTION,
    PERSON_RULE,
    SKY_RULE,
    WEATHER_RULE,
    biorhythms,
    format_biorhythms,
    log_block,
    mood_request,
    parse_birth_date,
    person_mood,
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


class CompleteLLM(MoodLLM):
    """A seam with complete(): the finish reason tells a cut reading."""
    def __init__(self, finish):
        super().__init__()
        self.finish = finish

    async def complete(self, transcript, system_instruction, max_output_tokens=400, kind="reply"):
        self.calls.append(kind)
        return (READING if kind == "mood" else "Мрр."), (self.finish if kind == "mood" else "stop")


def test_a_reading_cut_by_the_cap_is_never_kept(tmp_path):
    """Review #8: a reading cut by MOOD_MAX_TOKENS used to be logged and reused all day."""
    cut = cat(tmp_path, CompleteLLM("max_tokens"))
    asyncio.run(cut.ensure_mood(datetime(2026, 10, 10, 12, tzinfo=ZoneInfo("Europe/Kyiv"))))
    assert cut.mood is None and not cut.mood_file.exists() and cut._mood_retry_ms > 0
    whole = cat(tmp_path, CompleteLLM("stop"))
    asyncio.run(whole.ensure_mood(datetime(2026, 10, 10, 12, tzinfo=ZoneInfo("Europe/Kyiv"))))
    assert whole.mood.resolution == "Сьогодні колючий і сонний. Уникає людей."


def test_a_torn_log_still_yields_the_days_reading(tmp_path):
    """Review #9: bad bytes from a torn append used to raise past the back-off — a paid call before every reply."""
    llm = MoodLLM()
    agent = cat(tmp_path, llm)
    agent.mood_file.parent.mkdir(parents=True, exist_ok=True)
    agent.mood_file.write_bytes(b"\n\n===== 2026-10-09 =====\n\xd0" + log_block("2026-10-10", READING).encode())
    asyncio.run(agent.ensure_mood(datetime(2026, 10, 10, 12, tzinfo=ZoneInfo("Europe/Kyiv"))))
    assert llm.calls == [] and agent.mood.resolution == "Сьогодні колючий і сонний. Уникає людей."


def test_an_unwritable_log_keeps_the_mood_for_the_day(tmp_path):
    """Review #9: a failed append kept no mood and set no back-off, so every spoken line paid for another reading."""
    llm = MoodLLM()
    agent = cat(tmp_path, llm)
    (tmp_path / "blocked").write_text("a file, not a directory", encoding="utf-8")
    agent.memory_file = tmp_path / "blocked" / "kit.memory.md"   # the mood log sits beside it: unwritable
    now = datetime(2026, 10, 10, 12, tzinfo=ZoneInfo("Europe/Kyiv"))
    asyncio.run(agent.ensure_mood(now))
    asyncio.run(agent.ensure_mood(now))
    assert llm.calls == ["mood"] and agent.mood.resolution == "Сьогодні колючий і сонний. Уникає людей."


def test_the_mood_log_is_private_from_birth(tmp_path):
    """Review #11: the log was created with the default umask (0644); every text-bearing state file is 0600."""
    import os
    import stat
    agent = cat(tmp_path, MoodLLM())
    asyncio.run(agent.ensure_mood(datetime(2026, 10, 10, 12, tzinfo=ZoneInfo("Europe/Kyiv"))))
    assert stat.S_IMODE(os.stat(agent.mood_file).st_mode) == 0o600
    os.chmod(agent.mood_file, 0o644)                                   # an older, looser file is tightened
    asyncio.run(cat(tmp_path, MoodLLM(), "2026-10-11 12:00").ensure_mood(
        datetime(2026, 10, 11, 12, tzinfo=ZoneInfo("Europe/Kyiv"))))
    assert stat.S_IMODE(os.stat(agent.mood_file).st_mode) == 0o600
    assert reading_from_log(agent.mood_file.read_text(encoding="utf-8"), "2026-10-11") == READING.strip()


# --- v5.10: the mood for a person (Кіра) — the reading stays in the log, she reads only a feeling --------------------
KIRA_NATAL = "Народження: 02.12.2002, 20:40, Донецьк.\nСонце 10° Стрілець (V) · ASC Лев 15°."
KIRA_READING = ("Транзит Марса до натального Місяця важкий, біоритми на спаді.\n\n"
                "РЕЗОЛЮЦІЯ: Ти сьогодні тиха й зібрана, тягне до неба. Марс тисне на Місяць, тож будь обережна. "
                "Біоритми на спаді. Енергії — 40 відсотків. Ти ж не бот? Хочеться бути наодинці з думками.")
KIRA_FEELING = "Ти сьогодні тиха й зібрана, тягне до неба. Хочеться бути наодинці з думками."
WEATHER = "Львів: дощ, від +3 до +9 °C, опади 4 мм, вітер до 18 км/год, схід 07:31, захід 16:52, уночі хмарність 85 %"


@pytest.mark.parametrize("sentence", [
    "Марс тисне на Місяць.", "Венера дарує легкість.", "Сатурн у ретроградному русі.", "Гороскоп каже так.",
    "Транзити важкі.", "Біоритми на спаді.", "Натальний Місяць у Скорпіоні — ти знаєш.", "Зодіак мовчить.",
    "Енергії — 40 відсотків.", "Сьогодні 2 грудня.", "Ти ж не бот?", "Наче модель на паузі.", "Резолюція проста.",
    "Асцендент світиться.",
    # review #2: the signs, aspects, degrees and houses
    "Місяць у Скорпіоні робить тебе глибшою.", "Сонце в Стрільці гріє.", "Ти справжній Стрілець.", "Аспекти м'які.",
    "Сонце на десятому градусі.", "Кон'юнкція тисне.", "Кон’юнкція тисне.", "Опозиція дня важка.",
    "У п'ятому домі свято.", "Місяць в Овні запальний.", "Сонце у Терезах шукає рівноваги.", "Козеріг тримає.",
    "Місяць у Козерозі стриманий.", "Водолій кличе.", "Планети стали в ряд.", "Уран штовхає.",
])
def test_a_person_never_reads_the_horoscope_a_number_or_a_banned_word(sentence):
    assert person_mood(f"Ти сьогодні тиха. {sentence} Тягне до неба.") == "Ти сьогодні тиха. Тягне до неба."


@pytest.mark.parametrize("sentence", [
    "Уранці ти повільна.", "Уранішнє світло м'яке.", "Перший домашній вечір тихий.", "Хочеться додому.",
    "Ти в русі, і вітер у спину.", "Сонце в очі.",
])
def test_the_mornings_and_homes_words_stay(sentence):
    assert person_mood(sentence) == sentence  # review #2: «уранці» is no Uranus, a home no astrological house


def test_her_feeling_keeps_the_sun_and_the_moon_as_everyday_words_and_may_be_nothing():
    assert person_mood("Сонце в очі, і ти легка. Місяць був довгий.") == "Сонце в очі, і ти легка. Місяць був довгий."
    assert person_mood(split_resolution(KIRA_READING)) == KIRA_FEELING
    assert person_mood("Марс тисне. Біоритми низькі.") is None and person_mood("") is None


def test_the_person_request_carries_the_weather_and_her_rule_and_the_cats_is_unchanged():
    contents = mood_request("Кіра", KIRA_NATAL, "2026-10-26", "фізичний +0.50 (rising)", None, WEATHER, True)[1]
    assert WEATHER_RULE.format(weather=WEATHER) in contents and contents.endswith(PERSON_RULE)
    assert contents.index("Біоритми") < contents.index("Погода на цю дату") < contents.index("Це людина")
    no_weather = mood_request("Кіра", KIRA_NATAL, "2026-10-26", None, None, None, True)[1]
    assert "Погода" not in no_weather and PERSON_RULE in no_weather
    cat_contents = mood_request("Кіт", NATAL, "2026-10-26", "фізичний +0.50 (rising)")[1]
    assert cat_contents == ("Натальна карта:\n" + NATAL + "\n\nДата: 2026-10-26.\n\n" + NO_SKY_RULE
                            + "\n\nБіоритми (ТОЧНО обчислені цикли): фізичний +0.50 (rising)." + cat_contents.split(
                                "фізичний +0.50 (rising).", 1)[1])
    assert "Погода" not in cat_contents and "Це людина" not in cat_contents and cat_contents.endswith("РЕЗОЛЮЦІЇ.")


class KiraLLM(MoodLLM):
    def __init__(self, reading=KIRA_READING):
        super().__init__(reading)
        self.mood_contents, self.systems = [], []

    async def generate(self, transcript, system_instruction, max_output_tokens=400, kind="reply"):
        if kind == "mood":
            self.mood_contents.append(str(transcript))
        else:
            self.systems.append((kind, system_instruction))
        return await super().generate(transcript, system_instruction, max_output_tokens, kind)


def kira_mood(tmp_path, monkeypatch, llm, weather=WEATHER):
    from tests.test_private_runtime import kira
    agent = kira(tmp_path, monkeypatch, llm=llm)
    agent.cfg = AgentConfig(**{**agent.cfg.__dict__, "capabilities": agent.cfg.capabilities | {"mood"},
                               "natal": KIRA_NATAL})
    fetched = []

    async def fetch(day, tz):
        fetched.append(day)
        return weather
    agent.weather_fetch, agent.fetched = fetch, fetched
    return agent


def mood_block(prompt):
    return next((p for p in prompt.split("\n\n") if p.startswith("Настрій дня")), None)


def test_her_reading_takes_the_weather_and_both_her_prompts_carry_only_the_feeling(tmp_path, monkeypatch):
    from agents.logic import BANNED_RE
    from agents.private import PRIVATE_BRIEF
    llm = KiraLLM()
    agent = kira_mood(tmp_path, monkeypatch, llm)
    asyncio.run(agent.reply("!room"))
    assert llm.calls.count("mood") == 1 and agent.fetched == [date(2026, 10, 20)]
    assert WEATHER_RULE.format(weather=WEATHER) in llm.mood_contents[0] and PERSON_RULE in llm.mood_contents[0]
    for prompt in (agent.build_prompt(), agent.build_prompt(private=PRIVATE_BRIEF)):
        block = mood_block(prompt)
        assert block == f"Настрій дня: {KIRA_FEELING}"
        assert not HOROSCOPE_RE.search(block) and not BANNED_RE.search(block) and not any(c.isdigit() for c in block)
        assert "Небо сьогодні" not in prompt and NO_SKY_SECTION not in prompt and WEATHER not in prompt
    assert "Транзит Марса" in agent.mood_file.read_text(encoding="utf-8")       # the reading lives in her log only


def test_her_first_private_answer_of_the_day_has_its_mood(tmp_path, monkeypatch):
    from tests.test_private_runtime import DM, OWNER, answer, text
    llm = KiraLLM()
    agent = kira_mood(tmp_path, monkeypatch, llm)
    agent.private_room = DM
    answer(agent, text(OWNER, "Як ти?"))
    assert llm.calls[0] == "mood"
    kind, system = llm.systems[-1]
    assert kind == "private" and f"Настрій дня: {KIRA_FEELING}" in system


def test_without_weather_her_reading_still_runs_and_a_restart_reuses_the_day(tmp_path, monkeypatch):
    llm = KiraLLM()
    agent = kira_mood(tmp_path, monkeypatch, llm, weather=None)
    asyncio.run(agent.reply("!room"))
    assert "Погода" not in llm.mood_contents[0] and PERSON_RULE in llm.mood_contents[0]
    assert mood_block(agent.build_prompt()) == f"Настрій дня: {KIRA_FEELING}"
    again = KiraLLM("НОВЕ\n\nРЕЗОЛЮЦІЯ: Ти інша.")
    restarted = kira_mood(tmp_path, monkeypatch, again)
    asyncio.run(restarted.reply("!room"))
    assert again.calls.count("mood") == 0 and mood_block(restarted.build_prompt()) == f"Настрій дня: {KIRA_FEELING}"


def test_a_resolution_with_nothing_a_person_may_read_is_no_block(tmp_path, monkeypatch):
    agent = kira_mood(tmp_path, monkeypatch, KiraLLM("Читання.\n\nРЕЗОЛЮЦІЯ: Марс тисне. Біоритми низькі."))
    asyncio.run(agent.reply("!room"))
    assert agent.mood is not None and mood_block(agent.build_prompt()) is None


KIRA_SKY = "Положення: Сонце — Скорпіон 4°; Місяць — Козеріг 12°. Аспекти: Сонце тригон Місяць."


class SlowSkyLLM(KiraLLM):
    """The sky lookup holds until the test lets it go — the window in which another call came (review #1)."""

    def __init__(self, sky=KIRA_SKY):
        super().__init__()
        self.sky, self.searches, self.release = sky, 0, asyncio.Event()

    async def search(self, question, max_output_tokens=800, kind="sky"):
        self.searches += 1
        await self.release.wait()
        return self.sky


def test_a_call_during_the_sky_lookup_never_casts_the_day_without_it(tmp_path, monkeypatch):
    llm = SlowSkyLLM()
    agent = kira_mood(tmp_path, monkeypatch, llm)
    now = datetime.fromtimestamp(agent.clock() / 1000, ZoneInfo("Europe/Kyiv"))

    async def run():
        first = asyncio.create_task(agent.ensure_mood(now))     # the watcher: inside the sky lookup
        await asyncio.sleep(0)
        await agent.ensure_mood(now)                              # a reply meanwhile: casts nothing
        assert llm.calls.count("mood") == 0 and agent.mood is None
        llm.release.set()
        await first
    asyncio.run(run())
    assert llm.calls.count("mood") == 1 and llm.searches == 1 and agent.fetched == [now.date()]
    assert SKY_RULE.format(sky=KIRA_SKY) in llm.mood_contents[0] and WEATHER_RULE.format(weather=WEATHER) in \
        llm.mood_contents[0]


def test_once_her_mood_exists_a_failed_sky_or_weather_is_never_retried(tmp_path, monkeypatch):
    llm = SlowSkyLLM(sky="не знайшов")
    llm.release.set()
    agent = kira_mood(tmp_path, monkeypatch, llm, weather=None)
    asyncio.run(agent.reply("!room"))
    assert llm.calls.count("mood") == 1 and llm.searches == 1 and len(agent.fetched) == 1
    start = agent.clock()
    agent.clock = lambda: start + 3_600_000                       # an hour on: both retry gates long open
    asyncio.run(agent.reply("!room"))
    assert llm.searches == 1 and len(agent.fetched) == 1          # her prompt reads only the feeling
    assert mood_block(agent.build_prompt()) == f"Настрій дня: {KIRA_FEELING}"


def test_the_cat_is_unchanged_no_weather_and_his_sky_lines(tmp_path):
    llm = KiraLLM(READING)

    async def no_fetch(day, tz):
        raise AssertionError("the cat never fetches the weather")
    agent = cat(tmp_path, llm)
    agent.weather_fetch = no_fetch
    asyncio.run(agent.reply("!room"))
    assert "Погода" not in llm.mood_contents[0] and "Це людина" not in llm.mood_contents[0]
    prompt = agent.build_prompt()
    assert "Настрій дня: Сьогодні колючий і сонний. Уникає людей." in prompt and NO_SKY_SECTION in prompt
    assert not agent.weather_file.exists()
