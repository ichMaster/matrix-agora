"""v9.1 — a time on every memory and every plan (the owner, 2026-11-18: «всі спогади мають мати мітку часу щоб було
відомо що відбулось 6 год тому а що 12 а що вчора а що місяць тому. Давати їй дати але гвоорити вона має як зараз не з
датами»; «всі плани теж мали б мати мітку часу»): a member with `stamps` sees each memory's age and date — by the hour
in the prompt's tail and history (AGORA-278), by the day in the cached start (AGORA-279). nio and the model mocked;
made-up lines only."""

import asyncio
import dataclasses
from datetime import datetime
from zoneinfo import ZoneInfo

from agents.archive import Line, render_recalled
from agents.logic import TIME_LINE_RE, clean_reply
from agents.lumi import (
    DIGEST_HOURS,
    DIGEST_TITLE,
    Digest,
    aged_marks,
    load_digest,
    save_digest,
    talk_digest_request,
    talk_digest_section,
)
from agents.memory_tools import DAY_TALK
from agents.thoughts import Thought, thought_rows
from agents.world import history_times, with_time_lines
from tests.test_agora_window import Watcher
from tests.test_agora_window import seeded as agora_seeded
from tests.test_lumi_gists import day as day_of
from tests.test_lumi_memory import NOW, lumi, seeded, tick

KYIV = ZoneInfo("Europe/Kyiv")
AT = datetime(2026, 11, 18, 14, 20, tzinfo=KYIV)


def k(*a):
    return int(datetime(*a, tzinfo=KYIV).timestamp() * 1000)


def stamped(agent):
    agent.cfg = dataclasses.replace(agent.cfg, capabilities=agent.cfg.capabilities | {"stamps"})
    return agent


# --- AGORA-278: the tail and the history, by the hour (pure) --------------------------------------------------------
def test_time_lines_stamped_and_her_old_ones_unchanged():
    stamps_ = [k(2026, 11, 15, 21, 40), k(2026, 11, 15, 21, 45), k(2026, 11, 18, 8, 15)]
    assert history_times(stamps_, AT, "Europe/Kyiv", stamped=True) == {
        0: "— 3 дні тому (15.11): —",
        2: "— через 2 дні, 6 годин тому (сьогодні, 08:15): —",
    }
    plain = history_times(stamps_, AT, "Europe/Kyiv")
    assert plain[2] == "— через 2 дні, сьогодні вранці: —"                         # without `stamps` as before


def test_a_stamped_time_line_is_never_her_words():
    for line in ("— 6 годин тому (сьогодні, 08:15): —", "— через 3 дні, вчора ввечері (17.11, 21:40): —",
                 "— сьогодні вранці: —"):
        assert TIME_LINE_RE.match(line)
    assert clean_reply("— 6 годин тому (сьогодні, 08:15): —\nПривіт!", "Кіра", ["Ich"]) == "Привіт!"


def test_with_time_lines_puts_them_before_the_lines_they_mark():
    lines = [("Ich", "а"), ("Ада", "б"), ("Ich", "в")]
    times = [k(2026, 11, 18, 8, 0), k(2026, 11, 18, 8, 5), k(2026, 11, 18, 13, 0)]
    out = with_time_lines(lines, times, AT, "Europe/Kyiv")
    assert out == [("", "— 6 годин тому (сьогодні, 08:00): —"), ("Ich", "а"), ("Ада", "б"),
                   ("", "— через 4 години, годину тому (сьогодні, 13:00): —"), ("Ich", "в")]
    assert with_time_lines(lines, times[:2], AT, "Europe/Kyiv") == lines             # misaligned: as they are


def test_thoughts_by_their_age_and_hour():
    t = [Thought("09:12", "reflection", "thought", "", "Про зорі.")]
    assert thought_rows(t, True, 5, AT) == ["- 5 годин тому (сьогодні, 09:12): Про зорі."]
    assert thought_rows(t, True, 5) == ["- вранці: Про зорі."]


def test_recall_rows_by_their_age_and_date_and_still_then():
    line = Line(1, "k1", k(2026, 11, 18, 8, 15), "private", "telegram", "Ich", "Я завтра їду.", "gemini")
    thought = Line(2, "k2", k(2026, 11, 17, 21, 40), "thought", "thought", "Кіра", "Думала про нього.", "gemini")
    fact = Line(3, "k3", k(2026, 10, 18, 10, 0), "facts", "facts", "Ich", "У нього є сестра.", "gemini")
    got = render_recalled([[line], [thought], [fact]], "Europe/Kyiv", AT, stamped=True,
                          fact_days={"k3": datetime(2026, 10, 18, tzinfo=KYIV).date()})
    assert "6 годин тому (сьогодні, 08:15), " in got and "Ich тоді: «Я завтра їду.»" in got
    assert "16 годин тому (вчора, 21:40) я думала: Думала про нього." in got
    assert "(те, що ти знаєш про Ich, з 18.10) У нього є сестра." in got
    assert "якось" not in got
    plain = render_recalled([[line]], "Europe/Kyiv", AT)
    assert plain.splitlines()[1].startswith("сьогодні вранці, ")


def test_the_digest_keeps_its_hours_and_shows_their_age():
    system, contents = talk_digest_request("Кіра", "Канон.", "", [("[09:12] Ich", "Привіт")], 120, stamped=True)
    assert DIGEST_HOURS in system and "Без годин" not in system and "[09:12] Ich: Привіт" in contents
    assert "Без годин" in talk_digest_request("Кіра", "Канон.", "", [("Ich", "Привіт")], 120)[0]
    d = Digest("2026-11-18", 0, "[09:12] Ми говорили про зорі. [13:50] Потім про Атакаму.")
    got = talk_digest_section(d, "2026-11-18", AT)
    assert got.startswith("Раніше сьогодні (18.11) ви говорили")
    assert "[09:12, 5 годин тому] Ми говорили" in got and "[13:50, 30 хвилин тому] Потім" in got
    assert talk_digest_section(d, "2026-11-18") == f"{DIGEST_TITLE}\n{d.text}"       # without `stamps` as before
    old = Digest("2026-11-18", 0, "Ми говорили про зорі.")
    assert talk_digest_section(old, "2026-11-18", AT).endswith("\nМи говорили про зорі.")  # an old one as it is
    assert aged_marks("[15:00] Пізніше.", AT) == "[15:00] Пізніше."                 # a time ahead as it is


# --- AGORA-278: the agent -------------------------------------------------------------------------------------------
def test_her_private_window_and_her_folds_carry_the_time(tmp_path, monkeypatch):
    agent = stamped(lumi(tmp_path, monkeypatch))
    seeded(agent)
    tick(agent)
    sent = "".join(f["contents"] for f in agent.llm.folds)
    assert "[09:00] Ich: сьогодні 0" in sent and DIGEST_HOURS in agent.llm.folds[0]["system"]
    shown = [text for who, text in (e for _, e in agent.gemini_history_shown()) if not who]
    assert shown[0] == "— 8 годин тому (сьогодні, 09:04): —"                         # NOW is 18:00


def test_day_talk_names_the_day_by_its_age_and_date(tmp_path, monkeypatch):
    agent = stamped(lumi(tmp_path, monkeypatch))
    agent.archive.talk_put("gist_day", *day_of(2026, 11, 13), "Вчора про обсерваторію.", 3, 0, 0, NOW)
    got = asyncio.run(agent._run_memory_tool(DAY_TALK, {"date": "2026-11-13"}))
    assert got == "вчора (13.11):\n- Вчора про обсерваторію."
    save_digest(agent.digest_file, Digest("2026-11-14", 0, "[09:00] Про небо."))
    assert asyncio.run(agent._run_memory_tool(DAY_TALK, {"date": "2026-11-14"})) == (
        "Сьогодні: [09:00, 9 годин тому] Про небо.")
    assert load_digest(agent.digest_file).text == "[09:00] Про небо."              # the file never rewritten


def test_her_agora_prompt_has_time_lines_and_the_rooms_others_none(tmp_path):
    plain = agora_seeded(tmp_path / "a")
    mine = stamped(agora_seeded(tmp_path / "b"))
    assert [t for w, t in mine.agora_lines() if w] == [t for _, t in plain.agora_lines()]  # the same lines, in order
    marks = [t for w, t in mine.agora_lines() if not w]
    assert marks and marks[0].startswith("— 2 години тому (") and all(TIME_LINE_RE.match(m) for m in marks)
    assert all(w for w, _ in plain.agora_lines())                                   # Ада's prompt: none
    assert len(mine.history) == len(plain.history)                                  # the shared window untouched
    mine.responder = watcher = Watcher()
    asyncio.run(mine._compose("Інструкція."))
    assert watcher.lines[0][0][0] == "" and watcher.lines[0][-1] == plain.agora_lines()[-1]


# --- AGORA-279: the start, by the day -------------------------------------------------------------------------------
def test_facts_with_the_day_she_learned_them():
    from agents.facts import Fact, facts_section
    facts = [Fact("a", 1, "2026-11-17", "private", "У нього є сестра."), Fact("b", 1, "", "private", "Він любить чай.")]
    got = facts_section(facts, 10, 200, today=AT.date())
    assert "- (з 17.11, вчора) У нього є сестра." in got and "- Він любить чай." in got  # an unreadable day: as is
    assert "(з " not in facts_section(facts, 10, 200)                                  # without `stamps` as before


def test_talk_rows_and_gists_by_their_age_and_dates():
    from types import SimpleNamespace as Row

    from agents.talk import gist_section, talk_section
    hour = Row(level="hour", start_ms=k(2026, 11, 17, 20), end_ms=k(2026, 11, 17, 21), text="Про Атакаму.")
    day = Row(level="day", start_ms=k(2026, 11, 16), end_ms=k(2026, 11, 17), text="Про зорі.")
    got = talk_section([hour, day], k(2026, 11, 18, 9), AT, "Europe/Kyiv", stamped=True)
    assert "- позавчора (16.11): Про зорі." in got and "- вчора, 20:00–21:00 (17.11): Про Атакаму." in got
    gd = Row(level="gist_day", start_ms=k(2026, 11, 17), end_ms=k(2026, 11, 18), text="День про телескоп.")
    gw = Row(level="gist_week", start_ms=k(2026, 11, 9), end_ms=k(2026, 11, 16), text="Тиждень про Чилі.")
    got = gist_section([gd, gw], AT, "Europe/Kyiv", stamped=True)
    assert "- тиждень тому (09–15.11): Тиждень про Чилі." in got and "- вчора (17.11): День про телескоп." in got
    assert "(17.11)" not in gist_section([gd, gw], AT, "Europe/Kyiv")                  # without `stamps` as before


def test_a_weekday_in_a_plan_gets_its_date_in_the_plans_period():
    from datetime import date

    from agents.plans import date_weekdays
    week = (date(2026, 11, 16), date(2026, 11, 22))
    assert date_weekdays("- У четвер зустріч; у п’ятницю кіно; в неділю (22.11) пікнік", *week) == (
        "- У четвер (19.11) зустріч; у п’ятницю (20.11) кіно; в неділю (22.11) пікнік")
    assert date_weekdays("- у четвер, у середу", date(2026, 11, 18), date(2026, 11, 18)) == "- у четвер, у середу (18.11)"
    assert date_weekdays("- четвер без прийменника", *week) == "- четвер без прийменника"


def test_a_layers_age_by_dates_alone():
    from datetime import date

    from agents.world import day_age, layer_age
    today = date(2026, 11, 18)
    assert [layer_age("day", date(2026, 11, 15), today), layer_age("week", date(2026, 11, 9), today),
            layer_age("month", (2026, 10), today), layer_age("year", 2025, today)] == [
        "3 дні тому", "тиждень тому", "місяць тому", "рік тому"]
    assert day_age(today, today) == "сьогодні" and day_age(date(2026, 11, 19), today) == "завтра"


def test_the_last_summary_names_when_it_was():
    from agents.logic import instruction_and_start
    _, start = instruction_and_start("Кіра", "Канон.", "Говорили про зорі.", summary_when="вчора (17.11, 21:40)")
    assert "Що ти пам'ятаєш з минулої розмови — вчора (17.11, 21:40): Говорили про зорі." in start
    _, start = instruction_and_start("Кіра", "Канон.", "Говорили про зорі.")
    assert "Що ти пам'ятаєш з минулої розмови: Говорили про зорі." in start


def test_her_plans_and_memories_stamped_and_the_start_the_same_all_day(tmp_path):
    import os

    from agents.agent import Agent
    from agents.logic import instruction_and_start
    from tests.test_plans import CFG, FakeLLM
    agent = Agent(dataclasses.replace(CFG, capabilities=CFG.capabilities | {"plans", "chronicle", "stamps"}),
                  llm=FakeLLM("-"))
    agent.memory_file = tmp_path / "ada.memory.md"
    today = AT.date()
    paths = agent.plan_paths(today)
    for horizon, text in (("week", "- у четвер кіно"), ("day", "- лекція")):
        paths[horizon].parent.mkdir(parents=True, exist_ok=True)
        paths[horizon].write_text(text + "\n", encoding="utf-8")
    written = k(2026, 11, 16, 9) / 1000
    os.utime(paths["week"], (written, written))
    memory = agent._memory_path("day", today.replace(day=15))
    memory.parent.mkdir(parents=True, exist_ok=True)
    memory.write_text("Ходила в обсерваторію.", encoding="utf-8")

    def start_at(*when):
        agent.clock = lambda: k(*when)
        return instruction_and_start(**agent.prompt_layers())[1]

    morning = start_at(2026, 11, 18, 9, 0)
    assert "На цей тиждень (16.11–22.11), складений позавчора:\n- у четвер (19.11) кіно" in morning
    assert "На сьогодні (середа, 18.11), складений" in morning
    assert "3 дні тому — неділя, 15 листопада: Ходила в обсерваторію." in morning
    assert start_at(2026, 11, 18, 23, 59) == morning                                 # v7.5's cache: the same all day
    assert start_at(2026, 11, 19, 0, 1) != morning                                   # a new day, new labels


# --- AGORA-280: the rule, the count, the card, the switch ----------------------------------------------------------
def test_the_rule_is_hers_in_both_prompts_and_never_outs_her():
    from agents.agent import Agent
    from agents.logic import BANNED_RE
    from agents.private import PRIVATE_BRIEF, STAMPS_RULE
    from agents.roster import load_roster
    from tests.test_plans import CFG, FakeLLM
    assert not BANNED_RE.search(STAMPS_RULE) and "інструмент" not in STAMPS_RULE
    plain = Agent(CFG, llm=FakeLLM("-"))
    mine = Agent(dataclasses.replace(CFG, capabilities=CFG.capabilities | {"stamps"}), llm=FakeLLM("-"))
    assert STAMPS_RULE not in plain.build_prompt() and STAMPS_RULE not in plain.build_prompt(private=PRIVATE_BRIEF)
    assert mine.build_prompt().endswith(STAMPS_RULE) and mine.build_prompt(private=PRIVATE_BRIEF).endswith(STAMPS_RULE)
    roster = load_roster("agora")
    assert sorted(n for n, m in roster.items() if m.can("stamps")) == ["kira", "ustyna"]  # the switch: both, no other


def test_a_date_she_says_is_counted_never_kept(tmp_path, monkeypatch):
    import json

    from agents.usage import answer_line
    assert answer_line("t", "kira", "private", "telegram", "owner", 5, 0, "gemini", (), 2)["dates"] == 2
    assert "dates" not in answer_line("t", "kira", "private", "telegram", "owner", 5, 0, "gemini")  # 0: absent
    agent = stamped(lumi(tmp_path, monkeypatch))
    agent.answers_file.parent.mkdir(parents=True, exist_ok=True)
    agent.record_answer("private", "telegram", "owner", NOW - 1000, 0, "gemini", [], "Пам'ятаєш 17.11? Це було класно.")
    agent.record_answer("private", "telegram", "owner", NOW - 1000, 0, "gemini", [], "Вчора було класно.")
    rows = [json.loads(x) for x in agent.answers_file.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["dates"] == 1 and "dates" not in rows[1]
    assert "17.11" not in agent.answers_file.read_text(encoding="utf-8")                # the count alone, never the text


def test_her_card_sums_todays_dates(tmp_path):
    import json
    from datetime import date

    from panel.memory import dates_view, memory_view
    path = tmp_path / "kira.answers.jsonl"
    path.write_text("\n".join([json.dumps({"ts": "2026-11-18T10:00:00+02:00", "dates": 2}),
                               json.dumps({"ts": "2026-11-18T11:00:00+02:00"}),            # an old line: 0
                               "not json",                                                 # a corrupt one: 0
                               json.dumps({"ts": "2026-11-17T23:00:00+02:00", "dates": 5}),  # yesterday
                               json.dumps({"ts": "2026-11-18T12:00:00+02:00", "dates": True})]), encoding="utf-8")
    assert dates_view(tmp_path, "kira", date(2026, 11, 18)) == 2
    assert dates_view(tmp_path, "ustyna", date(2026, 11, 18)) == 0                       # no file yet
    (tmp_path / "kira.memory.md").write_text("x", encoding="utf-8")
    view = memory_view(tmp_path, "kira", date(2026, 11, 18), with_stamps=True)
    assert view["dates_today"] == 2 and memory_view(tmp_path, "kira", date(2026, 11, 18))["dates_today"] is None


# --- code review v9.1 ----------------------------------------------------------------------------------------------
def test_a_recalled_fact_is_dated_by_the_day_she_learned_it_never_by_the_archives_sync(tmp_path, monkeypatch):
    """#1: the archive rewrites every fact row with the sync's time (at each start, at each change) — a recalled fact
    said «з 18.11» for a fact of October. Its day comes from the fact's `added`; an unknown day shows none."""
    from datetime import date

    from agents.facts import add_fact
    fact = Line(3, "fact:x", k(2026, 11, 18, 23, 9), "facts", "", "факт", "У нього є сестра.", "gemini")
    assert "з 18.11" not in render_recalled([[fact]], "Europe/Kyiv", AT, stamped=True)   # the sync's day: never
    assert "(те, що ти знаєш про Ich) У нього є сестра." in render_recalled([[fact]], "Europe/Kyiv", AT, stamped=True)
    agent = stamped(lumi(tmp_path, monkeypatch))
    agent.facts_dir = tmp_path / "kira.facts"
    assert add_fact(agent.facts_dir, "У нього є сестра.", 1, "private", date(2026, 10, 18), 100, 300) is not None
    days = agent._fact_days()
    assert list(days.values()) == [date(2026, 10, 18)]
    key = next(iter(days))
    got = render_recalled([[dataclasses.replace(fact, key=key)]], "Europe/Kyiv", AT, stamped=True, fact_days=days)
    assert "(те, що ти знаєш про Ich, з 18.10) У нього є сестра." in got
