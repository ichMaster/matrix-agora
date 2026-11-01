"""v5.20 — Кіра's layered memory of the private chat: the periods (an hour, a local four-hour block, a week) and which
are due, pure over an injected clock; the archive's `talk` table and its readers (made-up lines only)."""

from datetime import datetime
from zoneinfo import ZoneInfo

from agents.archive import Archive
from agents.talk import period_of, periods_due

TZ = "Europe/Kyiv"
KYIV = ZoneInfo(TZ)


def ms(*a):
    return int(datetime(*a, tzinfo=KYIV).timestamp() * 1000)


def test_a_period_is_a_clock_hour_a_local_block_or_a_week_from_monday():
    assert period_of("hour", ms(2026, 11, 1, 13, 20), TZ) == (ms(2026, 11, 1, 13), ms(2026, 11, 1, 14))
    assert period_of("4h", ms(2026, 11, 1, 13, 20), TZ) == (ms(2026, 11, 1, 12), ms(2026, 11, 1, 16))
    assert period_of("4h", ms(2026, 11, 1, 23, 59), TZ) == (ms(2026, 11, 1, 20), ms(2026, 11, 2, 0))
    assert period_of("week", ms(2026, 11, 1, 23, 0), TZ) == (ms(2026, 10, 26), ms(2026, 11, 2))   # Sunday → Monday


def test_on_the_dst_day_a_block_and_a_week_have_their_true_length():
    start, end = period_of("4h", ms(2026, 10, 25, 2, 30), TZ)           # 04:00 EEST became 03:00 EET that night
    assert (start, end) == (ms(2026, 10, 25, 0), ms(2026, 10, 25, 4)) and end - start == 5 * 3_600_000
    start, end = period_of("week", ms(2026, 10, 21, 12), TZ)
    assert end - start == 7 * 86_400_000 + 3_600_000


def test_the_bands_oldest_first_and_never_a_period_held_or_not_over():
    now = ms(2026, 11, 2, 12, 0)                                         # the hours' band from 10-31 12:00, blocks' 10-19 12:00
    lines = [ms(2026, 10, 15, 10), ms(2026, 10, 20, 15), ms(2026, 10, 31, 9), ms(2026, 10, 31, 13, 10),
             ms(2026, 11, 2, 9, 5), ms(2026, 11, 2, 10, 15), ms(2026, 11, 2, 11, 59)]
    due = periods_due(now, TZ, lines, {("hour", ms(2026, 11, 2, 9))}, hour_days=2, fourh_days=14)
    assert due == [
        ("week", ms(2026, 10, 12), ms(2026, 10, 19)),                    # wholly before the blocks' band
        ("4h", ms(2026, 10, 20, 12), ms(2026, 10, 20, 16)),              # within it, before the hours'
        ("4h", ms(2026, 10, 31, 8), ms(2026, 10, 31, 12)),               # ends right at the hours' band
        ("hour", ms(2026, 10, 31, 13), ms(2026, 10, 31, 14)),
        ("hour", ms(2026, 11, 2, 10), ms(2026, 11, 2, 11)),              # 09:00 is held
        ("hour", ms(2026, 11, 2, 11), ms(2026, 11, 2, 12)),              # over at 12:00 sharp
    ]
    assert periods_due(ms(2026, 11, 2, 11, 45), TZ, [ms(2026, 11, 2, 11, 30)], set(), 2, 14) == []   # not over
    assert periods_due(now, TZ, [], set(), 2, 14) == []                  # no open line, nothing due


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


def test_her_prompt_shows_each_period_at_its_coarsest_level_before_the_window_oldest_first():
    from agents.talk import TALK_TITLE, talk_section
    now = datetime(2026, 11, 2, 12, 0, tzinfo=KYIV)                     # a Monday
    rows = [row("hour", ms(2026, 11, 2, 11), ms(2026, 11, 2, 12), "Пізніше, у вікні."),
            row("hour", ms(2026, 11, 2, 10), ms(2026, 11, 2, 11), "Кава."),
            row("hour", ms(2026, 11, 1, 21), ms(2026, 11, 1, 22), "Вечір."),
            row("hour", ms(2026, 11, 1, 22), ms(2026, 11, 1, 23), ""),   # all blocked: skipped
            row("hour", ms(2026, 10, 31, 9), ms(2026, 10, 31, 10), "Деталь ранку."),
            row("4h", ms(2026, 10, 31, 8), ms(2026, 10, 31, 12), "Ранок."),
            row("4h", ms(2026, 10, 20, 12), ms(2026, 10, 20, 16), "Планетарій."),
            row("week", ms(2026, 10, 12), ms(2026, 10, 19), "Гори.")]
    section = talk_section(rows, before_ms=ms(2026, 11, 2, 10, 30), now=now, tz=TZ)
    assert section == (f"{TALK_TITLE}\n"
                       "- минулого місяця: Гори.\n"
                       "- минулого місяця, вдень: Планетарій.\n"
                       "- позавчора вранці: Ранок.\n"                   # its hour under it is not shown
                       "- вчора ввечері: Вечір.\n"
                       "- сьогодні вранці: Кава.")                      # the window's own hour is left to the window
    assert talk_section(rows, before_ms=ms(2026, 10, 1), now=now, tz=TZ) is None
    budgeted = talk_section(rows, before_ms=ms(2026, 11, 2, 10, 30), now=now, tz=TZ, words_budget=9)
    assert budgeted.splitlines()[1:] == ["- вчора ввечері: Вечір.", "- сьогодні вранці: Кава."]  # the oldest go first
