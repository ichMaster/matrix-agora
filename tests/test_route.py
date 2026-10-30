"""v5.14 — the route of her private answer (`agents/route.py`): pure, with an injected clock, and its state file."""

import json
import os
import stat
from datetime import datetime
from zoneinfo import ZoneInfo

from agents.route import Route, after, blocks_since, day_bounds, load_route, save_route, state

TZ = "Europe/Kyiv"


def ms(day, hour, minute=0):
    return int(datetime(2026, 10, day, hour, minute, tzinfo=ZoneInfo(TZ)).timestamp() * 1000)


def step(route, now, outcome, window_s=300, day_max=10):
    day, start, end = day_bounds(now, TZ)
    return after(route, now, outcome, window_s, day_max, day, start, end)


def test_a_block_opens_five_minutes_of_the_backup_then_the_window_ends():
    r = step(Route(), ms(28, 20), "block")
    assert state(r, ms(28, 20, 4)) == "window" and state(r, ms(28, 20, 5)) == "window_end"
    assert state(Route(), ms(28, 20)) == "gemini"


def test_at_the_windows_end_gemini_takes_the_talk_back_and_a_block_there_opens_the_next():
    r = step(Route(), ms(28, 20), "block")
    closed = step(r, ms(28, 20, 6), "gemini")
    assert state(closed, ms(28, 20, 6)) == "gemini" and closed.answers == {"gemini": 1, "backup": 0}
    again = step(r, ms(28, 20, 6), "block")
    assert state(again, ms(28, 20, 10)) == "window" and state(again, ms(28, 20, 11)) == "window_end"
    inside = step(r, ms(28, 20, 2), "gemini")  # never closed from inside the window
    assert state(inside, ms(28, 20, 3)) == "window"


def test_the_tenth_block_of_her_day_holds_the_backup_to_local_midnight_and_the_next_day_starts_fresh():
    r = Route()
    for minute in range(10):
        r = step(r, ms(28, 12, minute * 6), "block")
    assert state(r, ms(28, 23, 59)) == "window" and state(r, ms(29, 0, 0)) == "window_end"
    assert blocks_since(r, day_bounds(ms(28, 12), TZ)[1]) == 10
    r = step(r, ms(29, 0, 1), "backup")
    assert r.day == "2026-10-29" and r.answers == {"gemini": 0, "backup": 1}
    assert blocks_since(r, day_bounds(ms(29, 0, 1), TZ)[1]) == 0


def test_a_dst_day_is_25_hours_and_the_cap_holds_to_its_real_midnight():
    day, start, end = day_bounds(ms(25, 12), TZ)  # 2026-10-25: summer time ends in Kyiv
    assert day == "2026-10-25" and end - start == 25 * 3_600_000
    r = Route()
    for minute in range(10):
        r = step(r, ms(25, 12, minute), "block")
    assert r.window_until_ms == end


def test_a_pin_overrides_the_rules_the_day_cap_included_until_auto():
    r = step(Route(), ms(28, 20), "pin:backup")
    assert state(r, ms(28, 20)) == "window" and state(r, ms(29, 20)) == "window" and r.pinned_at_ms == ms(28, 20)
    g = step(Route(), ms(28, 20), "pin:gemini")
    for minute in range(12):
        g = step(g, ms(28, 20, minute), "block")
    assert state(g, ms(28, 20, 30)) == "gemini" and g.window_until_ms is None  # a block opens no window
    assert blocks_since(g, ms(28, 0)) == 12                                      # but is counted
    auto = step(g, ms(28, 21), "pin:auto")
    assert auto.pin == "auto" and auto.pinned_at_ms is None and state(auto, ms(28, 21)) == "gemini"
    assert step(Route(), ms(28, 20), "pin:nonsense") == step(Route(), ms(28, 20), "nothing")


def test_old_blocks_are_dropped_but_the_last_hour_and_her_day_stay():
    r = Route(blocks=(ms(27, 23, 30), ms(27, 10)))
    r = step(r, ms(28, 0, 10), "backup")
    assert r.blocks == (ms(27, 23, 30),)


def test_the_state_file_survives_a_restart_is_private_and_holds_no_text(tmp_path):
    path = tmp_path / "kira.route.json"
    r = step(step(Route(), ms(28, 20), "block"), ms(28, 20, 1), "backup")
    save_route(path, r)
    assert load_route(path) == r
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert set(json.loads(path.read_text())) == {"pin", "pinned_at_ms", "blocks", "window_until_ms", "day", "answers",
                                                 "judged"}  # v5.15: today's ratings by the judge


def test_the_judges_ratings_are_counted_for_the_day_and_reset_with_it(tmp_path):
    """v5.15 — `rated` adds today's lines the judge rated and flagged; a new day starts at zero; the file keeps them."""
    def judged(r, at, rated, flagged):
        day, start, end = day_bounds(at, "Europe/Kyiv")
        return after(r, at, "rated", 300, 10, day, start, end, rated=rated, flagged=flagged)

    r = judged(judged(Route(), ms(28, 20), 25, 3), ms(28, 21), 4, 0)
    assert r.judged == {"rated": 29, "flagged": 3} and r.window_until_ms is None and r.blocks == ()
    path = tmp_path / "kira.route.json"
    save_route(path, r)
    assert load_route(path).judged == {"rated": 29, "flagged": 3}
    assert judged(r, ms(29, 9), 1, 1).judged == {"rated": 1, "flagged": 1}  # the next day


def test_a_missing_or_corrupt_file_is_auto_with_nothing_open(tmp_path):
    path = tmp_path / "kira.route.json"
    assert load_route(path) == Route()
    path.write_text("{broken")
    assert load_route(path) == Route()
    path.write_text(json.dumps({"pin": "hack", "blocks": ["x", 5, True], "window_until_ms": "soon",
                                "answers": {"gemini": "two", "backup": 3}}))
    r = load_route(path)
    assert (r.pin, r.blocks, r.window_until_ms, r.answers) == ("auto", (5,), None, {"gemini": 0, "backup": 3})
