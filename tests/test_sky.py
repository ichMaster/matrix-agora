"""The owner, 2026-10-11: the cat's horoscope names the real sky — every body's sign and degree, the retrograde
planets and the Moon's phase, computed by `agents/sky.py` (PyEphem, no network)."""
import asyncio
from datetime import date
from zoneinfo import ZoneInfo

from agents.mood import SKY_RULE, mood_request
from agents.sky import format_sky, moon_phase, noon, placements, sky_line
from tests.test_mood import NATAL, MoodLLM, cat

KYIV = ZoneInfo("Europe/Kyiv")


def where(day: date) -> dict[str, tuple[str, int, bool]]:
    return {p.body: (p.sign, p.degree, p.retrograde) for p in placements(noon(day, KYIV))}


def test_the_sky_of_2026_10_11_matches_the_ephemeris():
    sky = where(date(2026, 10, 11))
    assert sky["Сонце"] == ("Терези", 18, False)
    assert sky["Місяць"][0] == "Терези"                       # a day after the new moon of 10 October
    assert sky["Венера"][:1] == ("Скорпіон",) and sky["Венера"][2]   # Venus retrograde from 3 October
    assert sky["Меркурій"] == ("Скорпіон", 13, False)
    assert sky["Марс"][0] == "Лев" and sky["Юпітер"][0] == "Лев"
    assert sky["Сатурн"][0] == "Овен" and sky["Сатурн"][2]
    assert sky["Уран"][0] == "Близнюки" and sky["Нептун"][0] == "Овен" and sky["Плутон"][0] == "Водолій"


def test_the_moons_phase_and_mercurys_station():
    assert moon_phase(placements(noon(date(2026, 10, 11), KYIV))) == "молодик"
    assert moon_phase(placements(noon(date(2026, 10, 26), KYIV))) == "повня"
    assert not where(date(2026, 10, 20))["Меркурій"][2] and where(date(2026, 10, 28))["Меркурій"][2]


def test_the_line_reads_in_ukrainian_with_every_body():
    line = sky_line(date(2026, 10, 11), KYIV)
    assert line.startswith("Сонце в Терезах 18°; Місяць в Терезах ") and "(молодик)" in line
    assert "Венера у Скорпіоні 7° (ретроградна)" in line and "Сатурн в Овні 10° (ретроградний)" in line
    assert line.count(";") == 9 and line == format_sky(placements(noon(date(2026, 10, 11), KYIV)))


def test_the_mood_call_carries_the_sky_and_forbids_invented_transits():
    contents = mood_request("Кіт", NATAL, "2026-10-11", None, "Сонце в Терезах 18°")[1]
    assert SKY_RULE.format(sky="Сонце в Терезах 18°") in contents and "не вигадуй" in contents
    assert "Небо на цю дату" not in mood_request("Кіт", NATAL, "2026-10-11")[1]


class RecordingMoodLLM(MoodLLM):
    def __init__(self):
        super().__init__()
        self.mood_contents = []

    async def generate(self, transcript, system_instruction, max_output_tokens=400, kind="reply"):
        if kind == "mood":
            self.mood_contents.append(str(transcript))
        return await super().generate(transcript, system_instruction, max_output_tokens, kind)


def test_the_cats_reading_and_his_prompt_know_todays_sky(tmp_path):
    llm = RecordingMoodLLM()
    agent = cat(tmp_path, llm, "2026-10-11 12:00")
    asyncio.run(agent.reply("!room"))
    line = sky_line(date(2026, 10, 11), KYIV)
    assert line in llm.mood_contents[0]
    prompt = agent.build_prompt()
    assert f"Небо сьогодні (справжнє, обчислене): {line}. Про зорі й планети кажи лише це." in prompt


def test_a_failed_sky_never_blocks_the_mood(tmp_path, monkeypatch):
    import agents.agent as agent_mod

    def boom(*_):
        raise RuntimeError("no sky")
    monkeypatch.setattr(agent_mod, "sky_line", boom)
    agent = cat(tmp_path, MoodLLM(), "2026-10-11 12:00")
    asyncio.run(agent.reply("!room"))
    prompt = agent.build_prompt()
    assert "Настрій дня:" in prompt and "Небо сьогодні" not in prompt
