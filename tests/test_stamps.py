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
    got = render_recalled([[line], [thought], [fact]], "Europe/Kyiv", AT, stamped=True)
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
