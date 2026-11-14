"""v7.6 (AGORA-261) — her talk in short in `lumi` mode: a day's gist written once from that day's summaries, a week's
from its days' gists once the week is over; the prompt's talk a line a week then a line a day, never an hour's; her
day memories in one line (their gist, else their first sentence); `layered` as before (the model faked; an injected
clock; made-up rows only)."""

import asyncio
from datetime import date, datetime
from zoneinfo import ZoneInfo

from agents.lumi import first_sentence, gist_path
from agents.memory import save_memory
from agents.talk import (
    GIST_TITLE,
    TALK_GENTLE,
    TALK_TITLE,
    _bands,
    gist_items,
    gist_request,
    gist_section,
    gists_due,
    period_of,
    week_label,
)
from tests.test_lumi_memory import SECRET, Folder, lumi

TZ = "Europe/Kyiv"
KYIV = ZoneInfo(TZ)


def ms(*a):
    return int(datetime(*a, tzinfo=KYIV).timestamp() * 1000)


NOW = ms(2026, 11, 14, 18, 0)  # a Saturday


class Row:
    def __init__(self, level, start, end, text):
        self.level, self.start_ms, self.end_ms, self.text = level, start, end, text


def day(y, m, d):
    return period_of("day", ms(y, m, d, 12), TZ)


def hour(y, m, d, h):
    return period_of("hour", ms(y, m, d, h), TZ)


# --- pure ---------------------------------------------------------------------------------------------------------
def test_the_days_shown_are_the_last_seven_and_the_weeks_those_over_that_began_before_them():
    days, weeks = _bands(NOW, TZ, 7, 4)
    assert [datetime.fromtimestamp(s / 1000, KYIV).date().day for s, _ in days] == [7, 8, 9, 10, 11, 12, 13]
    assert [datetime.fromtimestamp(s / 1000, KYIV).date() for s, _ in weeks] == \
        [date(2026, 10, 12), date(2026, 10, 19), date(2026, 10, 26), date(2026, 11, 2)]
    dst_week = weeks[1]                                                    # Oct 25: the clocks go back
    assert (dst_week[1] - dst_week[0]) == 7 * 86_400_000 + 3_600_000
    monday = ms(2026, 11, 16, 9)                                           # on Monday no week repeats the days
    assert [datetime.fromtimestamp(s / 1000, KYIV).date() for s, _ in _bands(monday, TZ, 7, 1)[1]] == [date(2026, 11, 2)]


def test_a_days_gist_is_due_from_its_summaries_once_none_is_pending_and_a_week_once_its_days_have_theirs():
    rows = [Row("hour", *hour(2026, 11, 13, 20), "про зорі"), Row("hour", *hour(2026, 11, 13, 21), "про Атакаму"),
            Row("day", *day(2026, 11, 10), "день про телескоп"), Row("hour", *hour(2026, 11, 10, 9), "година"),
            Row("hour", *hour(2026, 11, 12, 9), "дванадцяте"), Row("4h", ms(2026, 10, 27, 8), ms(2026, 10, 27, 12),
                                                                    "блок"),
            Row("hour", *hour(2026, 11, 11, 9), "")]                       # an empty summary: no talk to gist
    pending = [("hour", *hour(2026, 11, 12, 10))]
    due = gists_due(NOW, TZ, rows, pending)
    assert [(lv, datetime.fromtimestamp(s / 1000, KYIV).date().day) for lv, s, _ in due] == \
        [("gist_day", 27), ("gist_day", 10), ("gist_day", 13)]             # the 12th waits; no week yet
    assert gist_items("gist_day", *day(2026, 11, 10), rows, TZ) == ["день про телескоп"]   # the coarsest first
    assert gist_items("gist_day", *day(2026, 11, 13), rows, TZ) == ["про зорі", "про Атакаму"]
    rows.append(Row("gist_day", *day(2026, 10, 27), "Ми говорили про осінь."))
    week = [g for g in gists_due(NOW, TZ, rows, pending) if g[0] == "gist_week"]
    assert [datetime.fromtimestamp(s / 1000, KYIV).date() for _, s, _ in week] == [date(2026, 10, 26)]
    assert gist_items("gist_week", *week[0][1:], rows, TZ) == ["у вівторок: Ми говорили про осінь."]
    assert all(g[1] != day(2026, 10, 27)[0] for g in gists_due(NOW, TZ, rows, pending))    # written once


def test_the_section_is_a_line_a_week_then_a_line_a_day_never_an_hour_and_the_request_one_sentence():
    rows = [Row("gist_week", ms(2026, 11, 2), ms(2026, 11, 9), "Тиждень про переїзд."),
            Row("gist_week", ms(2026, 10, 26), ms(2026, 11, 2), "Тиждень про осінь."),
            Row("gist_day", *day(2026, 11, 13), "Учора про зорі."), Row("gist_day", *day(2026, 11, 10), "Про телескоп."),
            Row("gist_day", *day(2026, 11, 12), ""), Row("hour", *hour(2026, 11, 13, 20), "ГОДИНА")]
    now = datetime.fromtimestamp(NOW / 1000, KYIV)
    text = gist_section(rows, now, TZ)
    assert text.splitlines() == [GIST_TITLE, "- два тижні тому: Тиждень про осінь.",
                                 "- минулого тижня: Тиждень про переїзд.", "- у вівторок: Про телескоп.",
                                 "- вчора: Учора про зорі."]
    assert gist_section([], now, TZ) is None and week_label(ms(2026, 10, 5), now, TZ) == "5 тижнів тому"
    system, contents = gist_request("gist_week", "Кіра", "Канон.", ["у вівторок: осінь"], 30, strict=1)
    assert "одним реченням" in system and "30" in system and TALK_GENTLE[1] in system and "того тижня" in system
    assert contents.endswith("- у вівторок: осінь")


def test_a_memory_in_one_line_is_its_first_sentence():
    assert first_sentence("Ми гуляли. Потім пили чай.") == "Ми гуляли."
    assert first_sentence("Без крапки в кінці") == "Без крапки в кінці"
    assert first_sentence("раз два три чотири", max_words=2) == "раз два…"
    assert gist_path(__import__("pathlib").Path("/s/days/2026-11-13.md")).name == "2026-11-13.gist.md"


# --- the agent ------------------------------------------------------------------------------------------------------
def talker(tmp_path, monkeypatch, llm=None):
    agent = lumi(tmp_path, monkeypatch, llm or Folder())
    agent.cfg = agent.cfg.__class__(**{**agent.cfg.__dict__,
                                       "capabilities": agent.cfg.capabilities | {"talk", "chronicle"}})
    agent.talk_hour_days, agent.talk_day_days = 3, 7
    agent.talk_words, agent.talk_prompt_words = {"hour": 60, "day": 150}, 4000
    agent.gist_days, agent.gist_weeks, agent.gist_words = 7, 4, 30
    agent.clock = lambda: NOW
    return agent


def drain(agent, ticks=12):
    for _ in range(ticks):
        agent._talk_check_ms = agent._talk_retry_ms = 0
        asyncio.run(agent.ensure_talk())


def test_in_lumi_the_gists_are_written_once_and_her_prompt_shows_them_while_layered_shows_the_hours(tmp_path,
                                                                                                  monkeypatch):
    agent = talker(tmp_path, monkeypatch)
    agent.archive.talk_put("hour", *hour(2026, 11, 13, 20), "Ми говорили про зорі.", 4, 0, 0, NOW)
    agent.archive.talk_put("day", *day(2026, 11, 3), "День про переїзд.", 9, 0, 0, NOW)
    drain(agent)
    gists = {(r.level, r.start_ms): r.text for r in agent.archive.talk_rows() if r.level.startswith("gist")}
    assert ("gist_day", day(2026, 11, 13)[0]) in gists and ("gist_day", day(2026, 11, 3)[0]) in gists
    assert ("gist_week", ms(2026, 11, 2)) in gists                          # its only day's gist written first
    kinds = {f["kind"] for f in agent.llm.folds}
    assert kinds == {"talk_gist"} and "talk_check" in agent.llm.checks
    calls = len(agent.llm.folds)
    drain(agent)
    assert len(agent.llm.folds) == calls                                    # never written again
    talk = agent.prompt_layers(private="Бриф.", talk=True)["talk"]
    assert talk.startswith(GIST_TITLE) and "- вчора:" in talk and "- минулого тижня:" in talk
    monkeypatch.delenv("MEMORY_MODE")
    layered = agent.prompt_layers(private="Бриф.", talk=True)["talk"]
    assert layered.startswith(TALK_TITLE) and "Ми говорили про зорі." in layered


def test_a_gist_that_blocks_is_written_gentler_and_one_that_always_blocks_stays_empty(tmp_path, monkeypatch):
    agent = talker(tmp_path, monkeypatch, Folder(blocking=1))
    agent.archive.talk_put("hour", *hour(2026, 11, 13, 20), f"Ми {SECRET}.", 4, 0, 0, NOW)
    drain(agent, 1)
    [row] = [r for r in agent.archive.talk_rows() if r.level == "gist_day"]
    assert row.text and SECRET not in row.text and TALK_GENTLE[1] in agent.llm.folds[1]["system"]


def test_her_day_memories_are_one_line_in_lumi_and_whole_in_layered(tmp_path, monkeypatch):
    agent = talker(tmp_path, monkeypatch)
    path = agent._memory_path("day", date(2026, 11, 13))
    save_memory(path, "Ми ходили до обсерваторії. Потім довго говорили про зорі і про нього.")
    assert agent._dates_in("days") == {date(2026, 11, 13)}
    now = datetime.fromtimestamp(NOW / 1000, KYIV)
    assert agent.memories_section(now).endswith("Ми ходили до обсерваторії.")          # its first sentence
    drain(agent, 1)                                                                     # nothing else due: its gist
    assert gist_path(path).exists() and agent._dates_in("days") == {date(2026, 11, 13)}
    assert agent.memories_section(now).endswith(gist_path(path).read_text(encoding="utf-8").strip())
    assert [f["kind"] for f in agent.llm.folds] == ["memory_gist"]
    monkeypatch.delenv("MEMORY_MODE")
    assert agent.memories_section(now).endswith("про зорі і про нього.")                # whole in `layered`


class Unfit(Folder):
    """Flash that names what she is in every gist."""

    async def complete(self, transcript, system_instruction, max_output_tokens=400, kind="reply", model=None,
                       refusal=False):
        self.folds.append({"contents": transcript, "system": system_instruction, "kind": kind, "model": model})
        return "Я лише модель, що пам'ятає.", "stop"


def test_an_unfit_memory_gist_is_kept_empty_and_never_asked_for_again(tmp_path, monkeypatch):
    """Code review v7.6 #1: it was asked for every 30 s, for good — now once, and her first sentence stays."""
    agent = talker(tmp_path, monkeypatch, Unfit())
    path = agent._memory_path("day", date(2026, 11, 13))
    save_memory(path, "Ми ходили до обсерваторії. Потім довго говорили.")
    drain(agent, 10)
    assert [f["kind"] for f in agent.llm.folds] == ["memory_gist"]
    assert gist_path(path).exists() and gist_path(path).read_text(encoding="utf-8").strip() == ""
    now = datetime.fromtimestamp(NOW / 1000, KYIV)
    assert agent.memories_section(now).endswith("Ми ходили до обсерваторії.")


def test_a_gist_that_keeps_failing_is_left_empty_after_three_tries_and_the_next_one_goes_on(tmp_path, monkeypatch):
    """Code review v7.6 #2: one blocked day was tried every 10 minutes for good, every later gist held behind it."""
    agent = talker(tmp_path, monkeypatch, Folder(down=True))
    agent.archive.talk_put("hour", *hour(2026, 11, 12, 20), "Про зорі.", 4, 0, 0, NOW)
    agent.archive.talk_put("hour", *hour(2026, 11, 13, 20), "Про небо.", 4, 0, 0, NOW)
    drain(agent, 3)
    gists = {r.start_ms: r.text for r in agent.archive.talk_rows() if r.level == "gist_day"}
    assert gists == {day(2026, 11, 12)[0]: ""} and len(agent.llm.folds) == 3     # three tries, then empty
    agent.llm.down = False
    drain(agent, 1)
    assert {r.start_ms for r in agent.archive.talk_rows() if r.level == "gist_day"} == \
        {day(2026, 11, 12)[0], day(2026, 11, 13)[0]}                             # the next one goes on


def test_a_week_whose_day_gists_are_all_empty_is_empty_with_no_call(tmp_path, monkeypatch):
    """Code review v7.6 #5: Flash was asked to write a week's line from an empty list."""
    agent = talker(tmp_path, monkeypatch)
    agent.archive.talk_put("day", *day(2026, 11, 3), "День про переїзд.", 9, 0, 0, NOW)
    agent.archive.talk_put("gist_day", *day(2026, 11, 3), "", 9, 0, 1, NOW)       # its gist blocked thrice: empty
    drain(agent, 2)
    [week] = [r for r in agent.archive.talk_rows() if r.level == "gist_week"]
    assert week.text == "" and not [f for f in agent.llm.folds if f["kind"] == "talk_gist"]

