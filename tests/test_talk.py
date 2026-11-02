"""v5.20 — Кіра's layered memory of the private chat: the periods (v5.23: an hour, a local day) and which are due, pure
over an injected clock; the archive's `talk` table and its readers (made-up lines only)."""

from datetime import datetime
from zoneinfo import ZoneInfo

from agents.archive import Archive
from agents.talk import period_of, periods_due

TZ = "Europe/Kyiv"
KYIV = ZoneInfo(TZ)


def ms(*a):
    return int(datetime(*a, tzinfo=KYIV).timestamp() * 1000)


def test_a_period_is_a_clock_hour_or_a_local_day():
    import pytest
    assert period_of("hour", ms(2026, 11, 1, 13, 20), TZ) == (ms(2026, 11, 1, 13), ms(2026, 11, 1, 14))
    assert period_of("day", ms(2026, 11, 1, 23, 59), TZ) == (ms(2026, 11, 1), ms(2026, 11, 2))
    for gone in ("4h", "week"):                                          # v5.23: never written again
        with pytest.raises(ValueError):
            period_of(gone, ms(2026, 11, 1, 13), TZ)


def test_on_the_dst_day_a_day_has_its_true_length():
    start, end = period_of("day", ms(2026, 10, 25, 2, 30), TZ)          # 04:00 EEST became 03:00 EET that night
    assert (start, end) == (ms(2026, 10, 25), ms(2026, 10, 26)) and end - start == 25 * 3_600_000


def test_the_bands_three_days_by_the_hour_then_days_to_seven_oldest_first_and_nothing_older():
    """v5.23 (the owner: «далі за попередні 2 доби по годині і потім 4 дні підсумок дня а решта вже РАГ»): the hours of
    the last 3 days, the days ended before them and within 7 days, never a period held or not over, nothing older."""
    now = ms(2026, 11, 5, 12, 0)                                         # the hours' band from 11-02 12:00, days' 10-29 12:00
    lines = [ms(2026, 10, 27, 10), ms(2026, 10, 29, 10), ms(2026, 10, 30, 15), ms(2026, 11, 1, 9),
             ms(2026, 11, 2, 9), ms(2026, 11, 2, 13, 10), ms(2026, 11, 5, 9, 5), ms(2026, 11, 5, 10, 15),
             ms(2026, 11, 5, 11, 59)]
    due = periods_due(now, TZ, lines, {("hour", ms(2026, 11, 5, 9))}, hour_days=3, day_days=7)
    assert due == [
        ("day", ms(2026, 10, 29), ms(2026, 10, 30)),                     # ended after the days' edge (10-29 12:00)
        ("day", ms(2026, 10, 30), ms(2026, 10, 31)),
        ("day", ms(2026, 11, 1), ms(2026, 11, 2)),                       # ends before the hours' band
        ("hour", ms(2026, 11, 2, 13), ms(2026, 11, 2, 14)),              # 11-02 09:00 is before the hours' band, and
        ("hour", ms(2026, 11, 5, 10), ms(2026, 11, 5, 11)),              # its day is not over before it: not yet due
        ("hour", ms(2026, 11, 5, 11), ms(2026, 11, 5, 12)),              # 09:00 is held; over at 12:00 sharp
    ]                                                                    # 10-27: older than 7 days, never due
    assert periods_due(ms(2026, 11, 2, 11, 45), TZ, [ms(2026, 11, 2, 11, 30)], set(), 3, 7) == []   # not over
    assert periods_due(now, TZ, [], set(), 3, 7) == []                   # no open line, nothing due
    assert not any(level in ("4h", "week") for level, _, _ in due)


def test_the_talk_table_lives_beside_the_lines_and_a_row_is_written_once(tmp_path):
    path = tmp_path / "kira.archive.db"
    first = Archive(path)
    first.append("tg:1", ms(2026, 11, 1, 10), "private", "telegram", "Ich", "Ранкова кава")
    first.close()
    archive = Archive(path)                                              # an archive that existed: `talk` added, lines kept
    assert archive.counts() == (1, 0)
    assert archive.talk_put("hour", ms(2026, 11, 1, 10), ms(2026, 11, 1, 11), "Про каву.", 1, 0, 0, 1) is True
    assert archive.talk_put("hour", ms(2026, 11, 1, 10), ms(2026, 11, 1, 11), "Інше.", 2, 0, 0, 2) is False
    rows = archive.talk_rows()
    assert [(r.level, r.text, r.open_lines) for r in rows] == [("hour", "Про каву.", 1)]
    assert archive.talk_rows("week") == [] and archive.talk_rows(since_ms=ms(2026, 11, 1, 11)) == []


def test_the_periods_readers_count_by_mark_and_gemini_never_reads_a_closed_line(tmp_path):
    archive = Archive(tmp_path / "kira.archive.db")
    for i, minute in enumerate((5, 10, 20)):
        archive.append(f"tg:{i}", ms(2026, 11, 1, 10, minute), "private", "telegram", "Ich", f"рядок {i}")
    archive.append("$a", ms(2026, 11, 1, 10, 30), "agora", "matrix", "Ада", "в Агорі")
    archive.mark(["tg:1"], "censored")
    start, end = ms(2026, 11, 1, 10), ms(2026, 11, 1, 11)
    assert archive.private_counts(start, end) == (2, 1)
    assert [x.key for x in archive.private_between(start, end)] == ["tg:0", "tg:2"]
    assert [x.key for x in archive.private_between(start, end, gemini=False)] == ["tg:0", "tg:1", "tg:2"]
    assert archive.private_open_times() == [ms(2026, 11, 1, 10, 5), ms(2026, 11, 1, 10, 20)]
    assert archive.private_counts(end, end + 3_600_000) == (0, 0)


def row(level, start, end, text):
    from agents.archive import TalkRow
    return TalkRow(level, start, end, text, 1, 0, 0, end)


def test_her_prompt_shows_the_hours_and_the_days_before_the_window_oldest_first_and_nothing_older():
    """v5.23: only `hour` and `day` rows ended within 7 days; a day with text hides its hours; an old four-hour block
    or week is never shown; a day labelled by `ago` alone, an hour with its part of the day."""
    from agents.talk import TALK_TITLE, talk_section
    now = datetime(2026, 11, 5, 12, 0, tzinfo=KYIV)                     # a Thursday
    rows = [row("hour", ms(2026, 11, 5, 11), ms(2026, 11, 5, 12), "Пізніше, у вікні."),
            row("hour", ms(2026, 11, 4, 21), ms(2026, 11, 4, 22), "Вечір."),
            row("hour", ms(2026, 11, 4, 22), ms(2026, 11, 4, 23), ""),   # all blocked: skipped
            row("hour", ms(2026, 11, 1, 9), ms(2026, 11, 1, 10), "Деталь неділі."),
            row("day", ms(2026, 11, 1), ms(2026, 11, 2), "Неділя."),
            row("day", ms(2026, 10, 30), ms(2026, 10, 31), "Планетарій."),
            row("day", ms(2026, 10, 27), ms(2026, 10, 28), "Давнє."),  # ended more than 7 days ago: her recall's
            row("4h", ms(2026, 11, 2, 8), ms(2026, 11, 2, 12), "Блок."),
            row("week", ms(2026, 10, 26), ms(2026, 11, 2), "Тиждень.")]
    section = talk_section(rows, before_ms=ms(2026, 11, 5, 10, 30), now=now, tz=TZ)
    assert section == (f"{TALK_TITLE}\n"
                       "- у п'ятницю: Планетарій.\n"                  # a day of the last week by its weekday
                       "- у неділю: Неділя.\n"                          # its hour under it is not shown
                       "- вчора ввечері: Вечір.")                       # the window's own hour is left to the window
    assert talk_section(rows, before_ms=ms(2026, 10, 1), now=now, tz=TZ) is None
    budgeted = talk_section(rows, before_ms=ms(2026, 11, 5, 10, 30), now=now, tz=TZ, words_budget=8)
    assert budgeted.splitlines()[1:] == ["- у неділю: Неділя.", "- вчора ввечері: Вечір."]  # the oldest go first
    wider = talk_section(rows, before_ms=ms(2026, 11, 5, 10, 30), now=now, tz=TZ, day_days=10)
    assert "- минулого тижня: Давнє." in wider                           # older than a week: by `ago`


def test_an_empty_coarser_row_hides_nothing_so_its_hours_stay():
    """Code review v5.20 #3: a period folded from its hours and blocked whole is written empty — its hours' own
    summaries are still shown (v5.23: a day)."""
    from agents.talk import TALK_TITLE, talk_section
    now = datetime(2026, 11, 4, 12, 0, tzinfo=KYIV)
    rows = [row("day", ms(2026, 11, 2), ms(2026, 11, 3), ""),
            row("hour", ms(2026, 11, 2, 9), ms(2026, 11, 2, 10), "Кава."),
            row("hour", ms(2026, 11, 2, 10), ms(2026, 11, 2, 11), "Прогулянка.")]
    assert talk_section(rows, before_ms=ms(2026, 11, 4, 11), now=now, tz=TZ) == (
        f"{TALK_TITLE}\n- позавчора вранці: Кава.\n- позавчора вранці: Прогулянка.")


def test_the_recheck_is_gone():
    """v5.21 (the owner, 2026-11-02): nothing reopens a closed line — the v5.20 re-check went."""
    from agents import talk
    assert not hasattr(talk, "sift") and not hasattr(talk, "main") and not hasattr(talk, "RECHECK_GROUP")


def test_the_settings_are_three_days_by_the_hour_and_days_to_seven_and_the_old_levels_are_gone():
    """v5.23: the bands' and the words' settings; v5.20's four-hour and week settings are gone — a saved override of
    one is dropped at the next save and ignored at start (v5.21 code review #2)."""
    from agents.settings import BY_NAME, validate
    assert (BY_NAME["TALK_HOUR_DAYS"].default, BY_NAME["TALK_DAY_DAYS"].default, BY_NAME["TALK_WORDS_DAY"].default) == (
        "3", "7", "150")
    assert validate("TALK_DAY_DAYS", "2")[0] is None and validate("TALK_DAY_DAYS", "30")[0] == "30"
    assert (BY_NAME["PRIVATE_HISTORY_HOURS"].default, BY_NAME["PRIVATE_HISTORY_MIN"].default) == ("24", "20")
    for gone in ("TALK_4H_DAYS", "TALK_WORDS_4H", "TALK_WORDS_WEEK"):
        assert gone not in BY_NAME
