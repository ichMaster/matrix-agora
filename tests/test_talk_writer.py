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
    agent.talk_hour_days, agent.talk_day_days = 3, 7
    agent.talk_words, agent.talk_prompt_words = {"hour": 60, "day": 150}, 4000
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
    _, folded = talk_request("day", "Кіра", "Канон.", [("hour", "Ми гуляли."), ("hour", "Пили чай.")], 150, True)
    assert folded == "Що ти пам'ятаєш про ці години, по черзі:\n- Ми гуляли.\n- Пили чай."


def test_the_backfill_writes_every_band_oldest_first_on_pro_and_never_reads_a_closed_line(tmp_path, monkeypatch,
                                                                                         caplog):
    caplog.set_level(logging.INFO)
    agent = talking(tmp_path, monkeypatch)
    say(agent, "tg:w", ms(2026, 10, 20, 15), "Ich", "Давно, про гори")            # older than 7 days: never written
    say(agent, "tg:b", ms(2026, 10, 28, 15), "Ich", "Про сеанс у планетарії")
    say(agent, "tg:h1", ms(2026, 11, 2, 10, 5), "Ich", "Як спалось?")
    say(agent, "tg:h2", ms(2026, 11, 2, 10, 6), "Кіра", "Чудово")
    say(agent, "tg:c", ms(2026, 11, 2, 10, 7), "Ich", "закрите слово", mark="censored")
    drain(agent)
    rows = agent.archive.talk_rows()
    assert [(r.level, r.start_ms) for r in rows] == [("day", ms(2026, 10, 28)), ("hour", ms(2026, 11, 2, 10))]
    assert all(c["model"] == "gemini-3.1-pro-preview" and c["kind"] == "talk_summary" for c in agent.llm.thought)
    assert not any("закрите слово" in c["contents"] for c in agent.llm.thought)
    hour = rows[-1]
    assert (hour.open_lines, hour.closed_lines, hour.left_out) == (2, 1, 0) and hour.text
    assert len(agent.llm.thought) == 2                                     # each period once, never again
    assert "Як спалось" not in caplog.text and "talk: hour 2026-11-02T10:00 — 2 open, 1 closed" in caplog.text


def test_a_day_is_written_from_its_hours_when_they_cover_it_and_the_hours_stay(tmp_path, monkeypatch):
    """v5.23: a day from its hours' summaries, at most `TALK_WORDS_DAY` words; a day with no hours (the first
    backfill's days 4–7) from its own open lines; never a four-hour block or a week again."""
    agent = talking(tmp_path, monkeypatch)
    agent.talk_words["day"] = 3
    say(agent, "tg:1", ms(2026, 10, 28, 9, 10), "Ich", "Перший рядок")
    say(agent, "tg:2", ms(2026, 10, 28, 10, 40), "Кіра", "Другий рядок")
    for t in (ms(2026, 10, 28, 9), ms(2026, 10, 28, 10)):
        agent.archive.talk_put("hour", t, t + 3_600_000, f"Година {t}.", 1, 0, 0, t)
    drain(agent)
    day = agent.archive.talk_rows("day")[0]
    assert (day.start_ms, day.end_ms) == period_of("day", ms(2026, 10, 28, 9, 10), "Europe/Kyiv")
    assert agent.llm.thought[-1]["contents"].startswith("Що ти пам'ятаєш про ці години")
    assert len(day.text.split()) <= 3 and len(agent.archive.talk_rows("hour")) == 2    # the cap; the finer rows stay
    say(agent, "tg:3", ms(2026, 10, 27, 9, 30), "Ich", "Рядок без години")  # no hour rows cover it: from its lines
    drain(agent)
    assert agent.llm.thought[-1]["contents"] == "Розмова:\nIch: Рядок без години"
    assert agent.archive.talk_rows("4h") == [] and agent.archive.talk_rows("week") == []


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


class Stuck(Pro):
    """A summary blocked at the answer stage: `think` gives None, and `probe` says the prompt passes."""

    async def think(self, contents, system_instruction, model="", max_output_tokens=0, kind="", level=None):
        self.thought.append({"contents": contents, "kind": kind})
        return None if "застрягле" in contents else f"Пам'ятаю {contents.count(chr(10))} речей."

    async def probe(self, transcript, system_instruction, kind="probe"):
        self.probed.append(transcript)
        return False


def test_a_period_that_keeps_failing_unblocked_is_left_empty_and_the_next_one_is_written(tmp_path, monkeypatch):
    """Code review v5.20 #2: an answer-stage block is no prompt-stage block — after three tries the period is written
    empty, its lines counted as left out, and the writer moves on to the next one."""
    agent = talking(tmp_path, monkeypatch, Stuck())
    say(agent, "tg:1", ms(2026, 11, 2, 9, 1), "Ich", "застрягле")
    say(agent, "tg:2", ms(2026, 11, 2, 10, 1), "Ich", "Привіт")
    for tick in range(2):
        drain(agent, 1)
        assert agent.archive.talk_rows() == [], tick                  # tried again later, twice
    drain(agent, 1)
    stuck = [r for r in agent.archive.talk_rows() if r.start_ms == ms(2026, 11, 2, 9)]
    assert len(stuck) == 1 and stuck[0].text == "" and stuck[0].left_out == 1
    drain(agent, 1)
    assert any(r.start_ms == ms(2026, 11, 2, 10) and r.text for r in agent.archive.talk_rows())


def test_an_outage_never_leaves_a_period_empty(tmp_path, monkeypatch):
    """Code review v5.20 #2: a failed call whose probe failed too is an outage — tried again, never given up."""
    agent = talking(tmp_path, monkeypatch, Pro(down=True))
    say(agent, "tg:1", ms(2026, 11, 2, 10, 1), "Ich", "Привіт")
    drain(agent, 6)
    assert agent.archive.talk_rows() == []


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


def test_a_day_without_hours_is_written_from_its_four_hour_blocks_when_they_cover_it(tmp_path, monkeypatch):
    """v5.23, the first live backfill (2026-11-03): two of four days written from a whole day's lines named what she
    is twice and were left empty; v5.20's blocks, which had passed, cover those days."""
    agent = talking(tmp_path, monkeypatch)
    say(agent, "tg:1", ms(2026, 10, 28, 9, 10), "Ich", "Ранковий рядок")
    say(agent, "tg:2", ms(2026, 10, 28, 15, 40), "Кіра", "Денний рядок")
    for t in (ms(2026, 10, 28, 8), ms(2026, 10, 28, 12)):
        agent.archive.talk_put("4h", t, t + 4 * 3_600_000, f"Блок {t}.", 1, 0, 0, t)
    drain(agent)
    assert agent.llm.thought[-1]["contents"].startswith("Що ти пам'ятаєш про ці години")
    assert "Ранковий рядок" not in agent.llm.thought[-1]["contents"] and agent.archive.talk_rows("day")[0].text
    say(agent, "tg:3", ms(2026, 10, 29, 9, 30), "Ich", "Рядок без блоку")    # neither hours nor blocks: its lines
    drain(agent)
    assert agent.llm.thought[-1]["contents"] == "Розмова:\nIch: Рядок без блоку"


def test_without_talk_nothing_is_due(tmp_path, monkeypatch):
    agent = kira(tmp_path, monkeypatch, Pro())
    assert agent.talk_is_due() is False


def test_her_private_prompt_to_gemini_holds_the_summaries_before_the_window_and_the_backups_does_not(tmp_path,
                                                                                                   monkeypatch):
    from agents.fallback import FallbackResponder
    from agents.private import PRIVATE_BRIEF
    from agents.talk import TALK_TITLE
    from tests.test_private_route import Backup
    agent = talking(tmp_path, monkeypatch)
    agent.history_n = 2
    say(agent, "tg:old", ms(2026, 10, 31, 9, 10), "Ich", "Давній рядок")
    say(agent, "tg:1", ms(2026, 11, 2, 11, 1), "Ich", "Новий рядок")
    say(agent, "tg:2", ms(2026, 11, 2, 11, 2), "Кіра", "І мій")
    agent.archive.talk_put("day", ms(2026, 10, 31), ms(2026, 11, 1), "Ми говорили про поїзд.", 1, 0, 0, 1)
    prompt = asyncio.run(agent._gemini_private_prompt(PRIVATE_BRIEF))
    assert TALK_TITLE in prompt and "- позавчора: Ми говорили про поїзд." in prompt
    agent.fallback, agent.fallback_responder = Backup(), FallbackResponder(Backup())
    agent.fallback_context, agent.fallback_history_n = 32000, 60
    assert TALK_TITLE not in asyncio.run(agent._backup_private_prompt(PRIVATE_BRIEF))[0]
    plain = kira(tmp_path / "plain", monkeypatch, Pro())
    assert TALK_TITLE not in asyncio.run(plain._gemini_private_prompt(PRIVATE_BRIEF))



def test_the_owners_switches_his_new_lines_only_and_no_summaries(tmp_path, monkeypatch):
    """2026-11-02 (the owner, «відключи всю історію … я маю на увазі 300 рядків»): `PRIVATE_HISTORY_N` 1 leaves Gemini
    only his lines since her last one; `TALK_PROMPT_WORDS` 0 takes the summaries out of her prompt."""
    from agents.private import PRIVATE_BRIEF
    from agents.talk import TALK_TITLE
    agent = talking(tmp_path, monkeypatch)
    for i, (who, text) in enumerate([("Ich", "Давнє"), ("Кіра", "Моє"), ("Ich", "Нове 1"), ("Ich", "Нове 2")]):
        say(agent, f"tg:{i}", ms(2026, 11, 2, 11, i), who, text)
    agent.archive.talk_put("day", ms(2026, 10, 31), ms(2026, 11, 1), "Ми говорили про поїзд.", 1, 0, 0, 1)
    assert [x.text for x in agent._gemini_lines()] == ["Давнє", "Моє", "Нове 1", "Нове 2"]
    agent.private_history_n = 1
    assert [x.text for x in agent._gemini_lines()] == ["Нове 1", "Нове 2"]     # never below his unanswered lines
    assert TALK_TITLE in asyncio.run(agent._gemini_private_prompt(PRIVATE_BRIEF))
    agent.talk_prompt_words = 0
    assert TALK_TITLE not in asyncio.run(agent._gemini_private_prompt(PRIVATE_BRIEF))


# --- v5.23: Gemini's window by time ----------------------------------------------------------------------------------
def test_the_cut_keeps_the_last_day_the_floor_and_his_new_lines():
    """v5.23 (the owner: «залишити всі меседжі за добу»; «Так, 20 рядків»): the pure cut over the open lines' times."""
    from agents.private import window_start
    hour = 3_600_000
    times = [NOW - 48 * hour, NOW - 25 * hour, NOW - 24 * hour - 60_000, NOW - 24 * hour + 60_000, NOW - hour]
    assert window_start(times, NOW, 24, 0) == 3                         # 24 h 01 min out, 23 h 59 min in
    assert window_start(times, NOW, 24, 3) == 2                         # the floor: the last 3 lines whatever their time
    assert window_start(times, NOW, 24, 0, keep_from=1) == 1            # his lines since her last one, always
    assert window_start(times, NOW, 0, 0) == 0 and window_start([], NOW, 24, 20) == 0
    assert window_start([NOW - 72 * hour] * 30, NOW, 24, 20) == 10      # three days' pause: the last 20 lines
    # a DST night (2026-10-25 04:00 → 03:00 in Kyiv): 24 real hours, never 24 of the wall clock
    dst_now = ms(2026, 10, 25, 12, 0)
    assert window_start([ms(2026, 10, 24, 12, 30), ms(2026, 10, 24, 13, 30)], dst_now, 24, 0) == 1


def test_her_window_is_the_last_day_at_least_the_floor_and_capped_as_before(tmp_path, monkeypatch):
    """`_gemini_lines` over a made-up archive with the clock injected: the last 24 hours, at least the floor, his
    unanswered lines, `PRIVATE_HISTORY_N` still the owner's cap, 0 hours the window by lines; the backup's view keeps
    its own history."""
    agent = talking(tmp_path, monkeypatch)
    agent.private_history_hours, agent.private_history_min = 24, 2
    lines = [(ms(2026, 10, 30, 20, 0), "Ich", "Давнє 1"), (ms(2026, 10, 30, 20, 1), "Кіра", "Давнє 2"),
             (ms(2026, 10, 31, 21, 0), "Ich", "Позавчора"), (ms(2026, 11, 1, 11, 59), "Кіра", "Добу тому"),
             (ms(2026, 11, 1, 12, 1), "Ich", "Вчора"), (ms(2026, 11, 2, 11, 0), "Кіра", "Сьогодні")]
    for i, (when, who, text) in enumerate(lines):
        say(agent, f"tg:{i}", when, who, text)
    assert [x.text for x in agent._gemini_lines()] == ["Вчора", "Сьогодні"]
    agent.private_history_min = 3
    assert [x.text for x in agent._gemini_lines()] == ["Добу тому", "Вчора", "Сьогодні"]
    agent.private_history_min = 0
    agent.clock = lambda: ms(2026, 11, 5, 12, 0)                        # three days later, he writes
    say(agent, "tg:9", ms(2026, 11, 5, 11, 58), "Ich", "Привіт")
    assert [x.text for x in agent._gemini_lines()] == ["Привіт"]       # his new line always, the rest in the summaries
    agent.private_history_hours = 0                                     # the window by lines, as before
    assert len(agent._gemini_lines()) == 7
    agent.private_history_n = 1
    assert [x.text for x in agent._gemini_lines()] == ["Привіт"]
    agent.seed_private_from_archive()                                   # the backup's own view: every line, untouched
    assert len(agent.private_history) == 7
