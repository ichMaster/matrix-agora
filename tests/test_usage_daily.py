from datetime import datetime
from zoneinfo import ZoneInfo

from agents.usage_daily import REPORT_HOUR, next_run, seconds_until

KYIV = ZoneInfo("Europe/Kyiv")


def test_before_seven_runs_today_after_seven_tomorrow():
    assert REPORT_HOUR == 7
    assert next_run(datetime(2026, 10, 4, 6, 59, tzinfo=KYIV)) == datetime(2026, 10, 4, 7, 0, tzinfo=KYIV)
    assert next_run(datetime(2026, 10, 4, 7, 0, tzinfo=KYIV)) == datetime(2026, 10, 5, 7, 0, tzinfo=KYIV)
    assert next_run(datetime(2026, 10, 4, 13, 20, tzinfo=KYIV)) == datetime(2026, 10, 5, 7, 0, tzinfo=KYIV)


def test_the_sleep_is_real_seconds_across_the_dst_switch():
    # Kyiv leaves summer time on the last Sunday of October (2026-10-25, 04:00 → 03:00)
    now = datetime(2026, 10, 24, 7, 0, tzinfo=KYIV)
    target = next_run(now)
    assert target == datetime(2026, 10, 25, 7, 0, tzinfo=KYIV)
    assert seconds_until(now, target) == 25 * 3600  # the night is one hour longer
    assert seconds_until(target, now) == 1.0  # never zero or negative
