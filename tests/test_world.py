from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from agents.world import (
    ago,
    day_label,
    history_times,
    last_talk_line,
    local_now,
    month_label,
    now_line,
    part_of_day,
    relative_when,
    says_date,
    season,
    span,
    span_stamp,
    stamp,
    week_label,
)

KYIV = ZoneInfo("Europe/Kyiv")


def k(*a):
    return datetime(*a, tzinfo=KYIV)


def test_now_line_in_ukrainian():
    assert now_line(k(2026, 10, 3, 14, 20), "Львів, Україна") == (
        "Місце: Львів, Україна. Зараз субота, 3 жовтня 2026 року, 14:20, день, осінь."
    )


@pytest.mark.parametrize("hour,part", [(4, "ніч"), (5, "ранок"), (11, "ранок"), (12, "день"),
                                       (17, "вечір"), (22, "вечір"), (23, "ніч")])
def test_part_of_day(hour, part):
    assert part_of_day(hour) == part


def test_seasons():
    assert [season(m) for m in (12, 3, 6, 9)] == ["зима", "весна", "літо", "осінь"]


def test_dst_switch_is_handled_by_the_timezone():
    # 2026-10-25: Kyiv leaves summer time at 04:00 → 03:00
    before = local_now(int(datetime(2026, 10, 24, 23, 0, tzinfo=ZoneInfo("UTC")).timestamp() * 1000), "Europe/Kyiv")
    after = local_now(int(datetime(2026, 10, 25, 2, 0, tzinfo=ZoneInfo("UTC")).timestamp() * 1000), "Europe/Kyiv")
    assert (before.hour, after.hour) == (2, 4)


def test_relative_when():
    now = k(2026, 10, 3, 14, 0)
    assert relative_when(k(2026, 10, 3, 9, 0), now) == "сьогодні вранці"
    assert relative_when(k(2026, 10, 2, 21, 0), now) == "вчора ввечері"
    assert relative_when(k(2026, 10, 1, 13, 0), now) == "позавчора вдень"
    assert relative_when(k(2026, 9, 30, 13, 0), now) == "3 дні тому"
    assert relative_when(k(2026, 9, 28, 13, 0), now) == "5 днів тому"
    assert relative_when(k(2026, 9, 20, 13, 0), now) == "20 вересня"
    assert last_talk_line(k(2026, 10, 2, 21, 0), now) == "Востаннє ви говорили вчора ввечері."


@pytest.mark.parametrize("then,words", [
    ((2026, 10, 28, 4, 30), "сьогодні вночі"),
    ((2026, 10, 28, 9, 0), "сьогодні вранці"),
    ((2026, 10, 28, 15, 0), "сьогодні вдень"),       # a later hour today (a skewed clock) is still today
    ((2026, 10, 27, 23, 59), "вчора"),                # just before midnight
    ((2026, 10, 26, 0, 1), "позавчора"),              # Monday: the nearest band wins over «цього тижня»
    ((2026, 10, 25, 12, 0), "минулого тижня"),        # Sunday, three days back: the week turned on Monday
    ((2026, 10, 19, 0, 0), "минулого тижня"),         # last week's Monday
    ((2026, 10, 18, 23, 0), "цього місяця"),
    ((2026, 10, 1, 8, 0), "цього місяця"),
    ((2026, 9, 30, 8, 0), "минулого місяця"),
    ((2026, 9, 1, 8, 0), "минулого місяця"),
    ((2026, 8, 31, 8, 0), "якось"),
    ((2025, 10, 28, 8, 0), "якось"),                  # the same date a year ago is not «this month»
])
def test_ago_is_how_a_person_remembers_never_a_date(then, words):
    now = k(2026, 10, 28, 14, 0)                      # a Wednesday
    assert ago(k(*then), now) == words


def test_ago_across_the_years_turn_and_a_month_start():
    assert ago(k(2026, 12, 20, 10, 0), k(2027, 1, 14, 10, 0)) == "минулого місяця"
    assert ago(k(2026, 12, 31, 10, 0), k(2027, 1, 2, 10, 0)) == "позавчора"
    assert ago(k(2026, 12, 29, 10, 0), k(2027, 1, 1, 10, 0)) == "цього тижня"   # Tuesday → Friday, one week
    assert ago(k(2026, 11, 28, 10, 0), k(2027, 1, 1, 10, 0)) == "якось"


def ts(*a):
    return int(k(*a).timestamp() * 1000)


def test_her_history_gets_its_time_before_the_first_line_and_after_a_long_pause():
    """The owner, 2026-11-01: Wednesday's talk sat right before Sunday's and «I'm off to Kyiv» read as tonight's."""
    stamps = [ts(2026, 10, 28, 22, 50), ts(2026, 10, 28, 23, 11), ts(2026, 11, 1, 22, 27), ts(2026, 11, 1, 22, 40)]
    assert history_times(stamps, k(2026, 11, 1, 23, 0), "Europe/Kyiv") == {
        0: "— цього тижня: —", 2: "— через 3 дні, сьогодні ввечері: —"}
    assert history_times([], k(2026, 11, 1, 23, 0), "Europe/Kyiv") == {}


def test_a_pause_under_three_hours_gets_no_line_and_hours_are_said_rightly():
    day = [ts(2026, 11, 1, 9, 0), ts(2026, 11, 1, 11, 59), ts(2026, 11, 1, 14, 59), ts(2026, 11, 2, 11, 59)]
    assert history_times(day, k(2026, 11, 2, 12, 0), "Europe/Kyiv") == {
        0: "— вчора: —", 2: "— через 3 години, вчора: —", 3: "— через 21 годину, сьогодні вранці: —"}
    assert [span(h * 3_600_000) for h in (1, 4, 5, 11, 22, 24, 48, 120)] == [
        "1 годину", "4 години", "5 годин", "11 годин", "22 години", "1 день", "2 дні", "5 днів"]


def test_labels():
    today = date(2026, 10, 3)
    assert day_label(date(2026, 10, 2), today) == "вчора, п'ятниця, 2 жовтня"
    assert day_label(date(2026, 10, 1), today) == "позавчора, четвер, 1 жовтня"
    assert day_label(date(2026, 9, 26), today) == "субота, 26 вересня"
    assert week_label(date(2026, 9, 14)) == "тиждень 14–20 вересня"
    assert week_label(date(2026, 9, 28)) == "тиждень 28 вересня – 4 жовтня"
    assert month_label(2026, 9) == "вересень 2026"


# --- v9.1 (AGORA-277): a time on every memory and plan — its age and its date --------------------------------------
NOW = k(2026, 11, 18, 14, 20)  # a Wednesday


@pytest.mark.parametrize("then,fine,coarse", [
    (k(2026, 11, 18, 14, 19, 40), "щойно (14:19)", "сьогодні (18.11)"),
    (k(2026, 11, 18, 13, 40), "40 хвилин тому (13:40)", "сьогодні (18.11)"),
    (k(2026, 11, 18, 13, 19), "годину тому (сьогодні, 13:19)", "сьогодні (18.11)"),
    (k(2026, 11, 18, 8, 15), "6 годин тому (сьогодні, 08:15)", "сьогодні (18.11)"),
    (k(2026, 11, 17, 21, 40), "16 годин тому (вчора, 21:40)", "вчора (17.11)"),
    (k(2026, 11, 17, 9, 0), "вчора вранці (17.11, 09:00)", "вчора (17.11)"),
    (k(2026, 11, 16, 20, 0), "позавчора ввечері (16.11)", "позавчора (16.11)"),
    (k(2026, 11, 13, 10, 0), "5 днів тому (13.11)", "5 днів тому (13.11)"),
    (k(2026, 11, 11, 10, 0), "тиждень тому (11.11)", "тиждень тому (11.11)"),
    (k(2026, 10, 28, 10, 0), "3 тижні тому (28.10)", "3 тижні тому (28.10)"),
    (k(2026, 10, 18, 10, 0), "місяць тому (18.10)", "місяць тому (18.10)"),
    (k(2026, 6, 18, 10, 0), "5 місяців тому (18.06)", "5 місяців тому (18.06)"),
    (k(2025, 11, 18, 10, 0), "рік тому (18.11.2025)", "рік тому (18.11.2025)"),
    (k(2024, 1, 1, 10, 0), "2 роки тому (01.01.2024)", "2 роки тому (01.01.2024)"),
    (k(2026, 11, 18, 14, 50), "через 30 хвилин (14:50)", "сьогодні (18.11)"),
    (k(2026, 11, 18, 17, 30), "через 3 години (17:30)", "сьогодні (18.11)"),
    (k(2026, 11, 19, 10, 0), "завтра (19.11, 10:00)", "завтра (19.11)"),
    (k(2026, 11, 20, 10, 0), "післязавтра (20.11)", "післязавтра (20.11)"),
    (k(2026, 11, 22, 10, 0), "у неділю (22.11)", "у неділю (22.11)"),
    (k(2026, 11, 28, 10, 0), "через 10 днів (28.11)", "через 10 днів (28.11)"),
    (k(2027, 2, 1, 10, 0), "через 2 місяці (01.02.2027)", "через 2 місяці (01.02.2027)"),
])
def test_stamp_gives_the_age_then_the_date(then, fine, coarse):
    assert stamp(then, NOW) == fine
    assert stamp(then, NOW, fine=False) == coarse


@pytest.mark.parametrize("n,word", [(1, "хвилину"), (2, "2 хвилини"), (5, "5 хвилин"), (11, "11 хвилин"),
                                    (21, "21 хвилину"), (22, "22 хвилини"), (25, "25 хвилин")])
def test_stamp_minutes_plural(n, word):
    assert stamp(NOW - timedelta(minutes=n), NOW) == f"{word} тому ({(NOW - timedelta(minutes=n)):%H:%M})"


def test_stamp_hour_on_request_and_the_start_unchanged_within_a_day():
    then = k(2026, 11, 17, 21, 40)
    assert stamp(then, NOW, fine=False, hour=True) == "вчора (17.11, 21:40)"
    texts = {stamp(then, k(2026, 11, 18, h, m), fine=False) for h, m in ((0, 0), (9, 0), (14, 20), (23, 59))}
    assert texts == {"вчора (17.11)"}  # v7.5's cache: the start's label changes only with the date
    assert stamp(then, k(2026, 11, 19, 0, 1), fine=False) == "позавчора (17.11)"


def test_stamp_counts_her_local_days_across_dst_and_zones():
    # Kyiv leaves summer time on 2026-10-25 at 04:00: a day of 25 hours is still one day
    before = k(2026, 10, 24, 23, 30)
    after = k(2026, 10, 26, 0, 30)
    assert stamp(before, after, fine=False) == "позавчора (24.10)"
    # her southern zone: a UTC moment that is still yesterday in Santiago
    scl = ZoneInfo("America/Santiago")
    now = datetime(2026, 11, 18, 10, 0, tzinfo=scl)
    then = datetime(2026, 11, 18, 2, 0, tzinfo=ZoneInfo("UTC"))  # 23:00 on the 17th in Santiago
    assert stamp(then, now) == "11 годин тому (вчора, 23:00)"


def test_span_stamp_periods():
    assert span_stamp(k(2026, 11, 18, 8), k(2026, 11, 18, 9), NOW) == "сьогодні, 08:00–09:00 (18.11)"
    assert span_stamp(k(2026, 11, 18, 11), k(2026, 11, 18, 12), NOW, fine=True) == "2 години тому (11:00–12:00)"
    assert span_stamp(k(2026, 11, 17, 20), k(2026, 11, 17, 21), NOW, fine=True) == "17 годин тому (20:00–21:00)"
    assert span_stamp(k(2026, 11, 15, 20), k(2026, 11, 15, 21), NOW, fine=True) == "3 дні тому, 20:00–21:00 (15.11)"
    assert span_stamp(k(2026, 11, 17), k(2026, 11, 18), NOW) == "вчора (17.11)"
    assert span_stamp(k(2026, 11, 16), k(2026, 11, 23), NOW) == "цього тижня (16–22.11)"
    assert span_stamp(k(2026, 11, 9), k(2026, 11, 16), NOW) == "тиждень тому (09–15.11)"
    assert span_stamp(k(2026, 10, 26), k(2026, 11, 2), NOW) == "3 тижні тому (26.10–01.11)"
    assert span_stamp(k(2026, 11, 1), k(2026, 12, 1), NOW) == "цього місяця (листопад 2026)"
    assert span_stamp(k(2026, 10, 1), k(2026, 11, 1), NOW) == "місяць тому (жовтень 2026)"
    assert span_stamp(k(2025, 12, 1), k(2026, 1, 1), NOW) == "11 місяців тому (грудень 2025)"
    assert span_stamp(k(2025, 1, 1), k(2026, 1, 1), NOW) == "рік тому (2025)"
    assert span_stamp(k(2026, 1, 1), k(2027, 1, 1), NOW) == "цього року (2026)"


@pytest.mark.parametrize("text,n", [
    ("17.11", 1), ("це було 17.11.2026, памятаєш", 1), ("17.11.26", 1), ("17 листопада", 1),
    ("17-го листопада і 3 грудня", 2), ("2026-11-17", 1), ("3.05", 1),
    ("о 14:20", 0), ("о 17.30", 0), ("17 разів", 0), ("у 2026 році", 0), ("3.5 кілометра", 0), ("версія 8.3.8", 0),
    ("", 0), ("вчора ввечері", 0),
])
def test_says_date(text, n):
    assert says_date(text) == n
