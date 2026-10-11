"""The owner, 2026-10-11: the cat's horoscope names the real sky — the astrological positions, the retrograde
planets, the Moon's phase and the day's aspects, asked of Gemini with Google Search once a day (as Lumi's web
lookup), never computed and never invented."""
import asyncio
import json
import os
import stat
from datetime import date
from types import SimpleNamespace

import agents.llm as llm_mod
from agents.mood import NO_SKY_RULE, NO_SKY_SECTION, SKY_RULE, SKY_SECTION, mood_request
from agents.sky import BODIES, SKY_MAX_CHARS, clean_sky, load_sky, save_sky, sky_query
from tests.test_mood import NATAL, MoodLLM, cat

SKY = ("Положення: Сонце — Терези 18°; Місяць — Терези 26° (молодик); Венера — Скорпіон 7° ℞; Плутон — Водолій 3° ℞. "
       "Аспекти: Сонце тригон Юпітер; Марс опозиція Сатурн.")


def test_the_question_is_date_anchored_and_asks_for_signs_and_aspects():
    q = sky_query(date(2026, 10, 11))
    assert q.startswith("Сьогодні 11 жовтня 2026 (неділя, 2026-10-11).")
    assert all(b in q for b in BODIES) and "тропічний зодіак" in q and "не астрономічні сузір'я" in q
    assert all(w in q for w in ("з'єднання", "опозиції", "тригони", "квадрати", "секстилі", "ретроградні"))
    assert "Нічого не вигадуй" in q


def test_the_answer_is_one_bounded_line_or_nothing():
    assert clean_sky(f"**{SKY[:40]}**\n\n{SKY[40:]}") == SKY
    assert clean_sky("Вибачте, не можу знайти.") is None and clean_sky(None) is None and clean_sky("") is None
    long = clean_sky("Сонце — Терези 18°; Місяць — Овен 1°; " + "Марс тригон Венера; " * 200)
    assert len(long) <= SKY_MAX_CHARS and not long.endswith(";")


def test_the_day_file_is_private_and_only_for_its_day(tmp_path):
    path = tmp_path / "kit.sky.json"
    save_sky(path, "2026-10-11", SKY)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert json.loads(path.read_text(encoding="utf-8")) == {"day": "2026-10-11", "sky": SKY}
    assert load_sky(path, "2026-10-11") == SKY and load_sky(path, "2026-10-12") is None
    path.write_text("{torn", encoding="utf-8")
    assert load_sky(path, "2026-10-11") is None and load_sky(tmp_path / "none.json", "2026-10-11") is None


def test_the_mood_call_carries_the_sky_or_is_told_it_has_none():
    contents = mood_request("Кіт", NATAL, "2026-10-11", None, SKY)[1]
    assert SKY_RULE.format(sky=SKY) in contents and NO_SKY_RULE not in contents
    assert NO_SKY_RULE in mood_request("Кіт", NATAL, "2026-10-11")[1]


class SkyLLM(MoodLLM):
    def __init__(self, sky=SKY):
        super().__init__()
        self.sky = sky
        self.questions = []
        self.mood_contents = []

    async def search(self, question, max_output_tokens=800, kind="sky"):
        self.questions.append((question, kind))
        return self.sky

    async def generate(self, transcript, system_instruction, max_output_tokens=400, kind="reply"):
        if kind == "mood":
            self.mood_contents.append(str(transcript))
        return await super().generate(transcript, system_instruction, max_output_tokens, kind)


def test_one_lookup_a_day_feeds_the_reading_and_his_prompt_and_survives_a_restart(tmp_path):
    llm = SkyLLM()
    agent = cat(tmp_path, llm, "2026-10-11 12:00")
    asyncio.run(agent.reply("!room"))
    asyncio.run(agent.reply("!room"))
    assert len(llm.questions) == 1 and llm.questions[0][1] == "sky"
    assert SKY_RULE.format(sky=SKY) in llm.mood_contents[0]
    assert SKY_SECTION.format(sky=SKY) in agent.build_prompt()
    again = SkyLLM()
    restarted = cat(tmp_path, again, "2026-10-11 15:00")
    asyncio.run(restarted.reply("!room"))
    assert again.questions == [] and SKY_SECTION.format(sky=SKY) in restarted.build_prompt()   # from the day's file


def test_a_failed_lookup_never_blocks_the_mood_and_retries_later(tmp_path):
    llm = SkyLLM(sky="не знайшов")
    agent = cat(tmp_path, llm, "2026-10-11 12:00")
    asyncio.run(agent.reply("!room"))
    assert NO_SKY_RULE in llm.mood_contents[0]                                     # no transits invented
    prompt = agent.build_prompt()
    assert "Настрій дня:" in prompt and NO_SKY_SECTION in prompt and "Небо сьогодні" not in prompt
    asyncio.run(agent.reply("!room"))
    assert len(llm.questions) == 1                                                  # no retry within 10 minutes
    llm.sky = SKY
    start = agent.clock()
    agent.clock = lambda: start + 600_000
    asyncio.run(agent.reply("!room"))
    assert len(llm.questions) == 2 and SKY_SECTION.format(sky=SKY) in agent.build_prompt()


def test_the_gemini_search_is_grounded_by_google_search(monkeypatch):
    seen = {}

    class Models:
        async def generate_content(self, **kw):
            seen.update(kw)
            return SimpleNamespace(text=" Сонце — Терези 18° ", usage_metadata=None, candidates=[])

    monkeypatch.setattr(llm_mod.genai, "Client", lambda: SimpleNamespace(aio=SimpleNamespace(models=Models())))
    usage = []
    out = asyncio.run(llm_mod.GeminiClient(sink=lambda *a: usage.append(a)).search("питання"))
    assert out == "Сонце — Терези 18°" and seen["contents"] == "питання"
    assert seen["config"].tools[0].google_search is not None and usage[0][0] == "sky"
