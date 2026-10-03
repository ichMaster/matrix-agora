from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from agents.world import (
    day_label,
    last_talk_line,
    local_now,
    month_label,
    now_line,
    part_of_day,
    relative_when,
    season,
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


def test_labels():
    today = date(2026, 10, 3)
    assert day_label(date(2026, 10, 2), today) == "вчора, п'ятниця, 2 жовтня"
    assert day_label(date(2026, 10, 1), today) == "позавчора, четвер, 1 жовтня"
    assert day_label(date(2026, 9, 26), today) == "субота, 26 вересня"
    assert week_label(date(2026, 9, 14)) == "тиждень 14–20 вересня"
    assert week_label(date(2026, 9, 28)) == "тиждень 28 вересня – 4 жовтня"
    assert month_label(2026, 9) == "вересень 2026"
