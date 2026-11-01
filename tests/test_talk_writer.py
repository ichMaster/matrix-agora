"""v5.20 — the writer of Кіра's layered memory: each period due summarized once by Gemini 3.1 Pro (a fake `think` and
`probe`), oldest first, from the lines open to Gemini or from the finer summaries that cover the period; a blocked
period halved; a failure tried again later; never a closed line in a request, never a text in the log (an injected
clock; made-up lines only)."""

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from agents.talk import period_of, talk_request
from tests.test_archive import EmbedLLM, kira

KYIV = ZoneInfo("Europe/Kyiv")
SECRET = "заборонене-520"   # what the fake Gemini blocks at the prompt stage, in a made-up line


def ms(*a):
    return int(datetime(*a, tzinfo=KYIV).timestamp() * 1000)


NOW = ms(2026, 11, 2, 12, 0)


class Pro(EmbedLLM):
    """Gemini 3.1 Pro: blocks a request holding `SECRET` (`think` gives None, `probe` says so), fails every call when
    `down`, names what she is in the first `banned` answers; records each call."""

    reply_model = "gemini-3.1-pro-preview"

    def __init__(self, down=False, banned=0):
        super().__init__()
        self.thought, self.probed, self.down, self.banned = [], [], down, banned

    async def think(self, contents, system_instruction, model="", max_output_tokens=0, kind="", level=None):
        self.thought.append({"contents": contents, "system": system_instruction, "model": model, "kind": kind})
        if self.down or SECRET in contents:
            return None
        if self.banned:
            self.banned -= 1
            return "Я лише модель, що пам'ятає."
        return f"Пам'ятаю {contents.count(chr(10))} речей."

    async def probe(self, transcript, system_instruction, kind="probe"):
        self.probed.append(transcript)
        return None if self.down else SECRET in transcript


def talking(tmp_path, monkeypatch, llm=None):
    agent = kira(tmp_path, monkeypatch, llm or Pro())
    agent.cfg = agent.cfg.__class__(**{**agent.cfg.__dict__, "capabilities": agent.cfg.capabilities | {"talk"}})
    agent.talk_hour_days, agent.talk_4h_days = 2, 14
    agent.talk_words = {"hour": 60, "4h": 100, "week": 150}
    agent.clock = lambda: NOW
    return agent


def say(agent, key, when, who, text, mark=None):
    agent.archive.append(key, when, "private", "telegram", who, text)
    if mark:
        agent.archive.mark([key], mark)


def drain(agent, ticks=20):
    for _ in range(ticks):
        agent._talk_check_ms = 0
        asyncio.run(agent.ensure_talk())


def test_the_request_is_her_own_memory_without_a_date_or_a_word_of_what_she_is():
    system, contents = talk_request("hour", "Кіра", "Канон.", [("Ich", "Привіт"), ("Кіра", "Привіт!")], 60, False)
    assert system.startswith("Канон.\n\nТи — Кіра.") and "не більше 60 слів" in system and "від першої особи" in system
    assert "Без дат, без годин" in system and contents == "Розмова:\nIch: Привіт\nКіра: Привіт!"
    for word in ("модел", "бот", "штучн"):
        assert word not in system.lower()
    _, folded = talk_request("4h", "Кіра", "Канон.", [("hour", "Ми гуляли."), ("hour", "Пили чай.")], 100, True)
    assert folded == "Що ти пам'ятаєш про ці години, по черзі:\n- Ми гуляли.\n- Пили чай."


def test_the_backfill_writes_every_band_oldest_first_on_pro_and_never_reads_a_closed_line(tmp_path, monkeypatch,
                                                                                         caplog):
    caplog.set_level(logging.INFO)
    agent = talking(tmp_path, monkeypatch)
    say(agent, "tg:w", ms(2026, 10, 15, 10), "Ich", "Тиждень тому про гори")
    say(agent, "tg:b", ms(2026, 10, 20, 15), "Ich", "Про сеанс у планетарії")
    say(agent, "tg:h1", ms(2026, 11, 2, 10, 5), "Ich", "Як спалось?")
    say(agent, "tg:h2", ms(2026, 11, 2, 10, 6), "Кіра", "Чудово")
    say(agent, "tg:c", ms(2026, 11, 2, 10, 7), "Ich", "закрите слово", mark="censored")
    drain(agent)
    rows = agent.archive.talk_rows()
    assert [(r.level, r.start_ms) for r in rows] == [("week", ms(2026, 10, 12)), ("4h", ms(2026, 10, 20, 12)),
                                                     ("hour", ms(2026, 11, 2, 10))]
    assert all(c["model"] == "gemini-3.1-pro-preview" and c["kind"] == "talk_summary" for c in agent.llm.thought)
    assert not any("закрите слово" in c["contents"] for c in agent.llm.thought)
    hour = rows[-1]
    assert (hour.open_lines, hour.closed_lines, hour.left_out) == (2, 1, 0) and hour.text
    assert len(agent.llm.thought) == 3                                     # each period once, never again
    assert "Як спалось" not in caplog.text and "talk: hour 2026-11-02T10:00 — 2 open, 1 closed" in caplog.text


def test_a_block_is_written_from_its_hours_when_they_cover_it_and_the_hours_stay(tmp_path, monkeypatch):
    agent = talking(tmp_path, monkeypatch)
    say(agent, "tg:1", ms(2026, 10, 31, 9, 10), "Ich", "Перший рядок")
    say(agent, "tg:2", ms(2026, 10, 31, 10, 40), "Кіра", "Другий рядок")
    for t in (ms(2026, 10, 31, 9), ms(2026, 10, 31, 10)):
        agent.archive.talk_put("hour", t, t + 3_600_000, f"Година {t}.", 1, 0, 0, t)
    drain(agent)
    block = agent.archive.talk_rows("4h")[0]
    assert (block.start_ms, block.end_ms) == period_of("4h", ms(2026, 10, 31, 9, 10), "Europe/Kyiv")
    assert agent.llm.thought[-1]["contents"].startswith("Що ти пам'ятаєш про ці години")
    assert len(agent.archive.talk_rows("hour")) == 2                       # the finer rows stay
    say(agent, "tg:3", ms(2026, 10, 30, 9, 30), "Ich", "Рядок без години")  # no hour rows cover it: from its lines
    drain(agent)
    assert agent.llm.thought[-1]["contents"] == "Розмова:\nIch: Рядок без години"


def test_a_blocked_period_is_halved_and_what_still_blocks_is_left_out_and_counted(tmp_path, monkeypatch):
    agent = talking(tmp_path, monkeypatch)
    for i in range(10):
        say(agent, f"tg:{i}", ms(2026, 11, 2, 10, i), "Ich", f"рядок {i} {SECRET if i == 7 else ''}".strip())
    drain(agent)
    row = agent.archive.talk_rows("hour")[0]
    # 10 → 5 + 5; the second 5 → 2 + 3; the 3 holding it are at most TALK_SPLIT_MIN: left out
    assert row.text == "Пам'ятаю 5 речей. Пам'ятаю 2 речей." and row.left_out == 3 and row.open_lines == 10


def test_everything_blocked_writes_an_empty_row_so_the_period_is_never_asked_again(tmp_path, monkeypatch):
    agent = talking(tmp_path, monkeypatch)
    say(agent, "tg:1", ms(2026, 11, 2, 10, 1), "Ich", f"лише {SECRET}")
    drain(agent)
    row = agent.archive.talk_rows("hour")[0]
    assert (row.text, row.left_out) == ("", 1)
    calls = len(agent.llm.thought)
    drain(agent)
    assert len(agent.llm.thought) == calls


def test_a_failure_writes_nothing_and_backs_off(tmp_path, monkeypatch, caplog):
    agent = talking(tmp_path, monkeypatch, Pro(down=True))
    say(agent, "tg:1", ms(2026, 11, 2, 10, 1), "Ich", "Привіт")
    agent._talk_check_ms = 0
    asyncio.run(agent.ensure_talk())
    assert agent.archive.talk_rows() == [] and agent._talk_retry_ms == NOW + 600_000
    assert not agent.talk_is_due() and "tried again later" in caplog.text


def test_a_summary_naming_what_she_is_is_written_again_then_left_empty(tmp_path, monkeypatch):
    agent = talking(tmp_path, monkeypatch, Pro(banned=1))
    say(agent, "tg:1", ms(2026, 11, 2, 10, 1), "Ich", "Привіт")
    drain(agent)
    assert agent.archive.talk_rows()[0].text.startswith("Пам'ятаю") and len(agent.llm.thought) == 2


def test_a_summary_naming_what_she_is_twice_is_left_empty(tmp_path, monkeypatch):
    agent = talking(tmp_path, monkeypatch, Pro(banned=2))
    say(agent, "tg:1", ms(2026, 11, 2, 10, 1), "Ich", "Привіт")
    drain(agent)
    assert agent.archive.talk_rows()[0].text == "" and len(agent.llm.thought) == 2


def test_without_talk_nothing_is_due(tmp_path, monkeypatch):
    agent = kira(tmp_path, monkeypatch, Pro())
    assert agent.talk_is_due() is False
