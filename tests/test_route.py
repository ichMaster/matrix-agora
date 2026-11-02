"""v5.21 — the route of her private answer (`agents/route.py`): two modes, the hour after more than 10 blocks, `/gemini`
and `/backup`, the backup's mark with its end, `/status`; pure, with an injected clock, and its state file."""

import json
import os
import stat
from datetime import datetime
from zoneinfo import ZoneInfo

from agents.route import BACKUP_MARK_RE, Route, backup_mark, load_route, mode, route_status, save_route, step

TZ = "Europe/Kyiv"


def ms(day, hour, minute=0):
    return int(datetime(2026, 10, day, hour, minute, tzinfo=ZoneInfo(TZ)).timestamp() * 1000)


def test_the_state_file_survives_a_restart_is_private_and_holds_no_text(tmp_path):
    path = tmp_path / "kira.route.json"
    r = step(step(Route(), ms(28, 20), "block", 300, 10, 3600, "2026-10-28"), ms(28, 20, 1), "backup", 300, 10, 3600,
             "2026-10-28")
    save_route(path, r)
    assert load_route(path) == r
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert set(json.loads(path.read_text())) == {"pin", "pinned_at_ms", "blocks", "window_until_ms", "day", "answers"}


def test_a_missing_or_corrupt_file_is_auto_with_nothing_open(tmp_path):
    path = tmp_path / "kira.route.json"
    assert load_route(path) == Route()
    path.write_text("{broken")
    assert load_route(path) == Route()
    path.write_text(json.dumps({"pin": "hack", "blocks": ["x", 5, True], "window_until_ms": "soon",
                                "answers": {"gemini": "two", "backup": 3}}))
    r = load_route(path)
    assert (r.pin, r.blocks, r.window_until_ms, r.answers) == ("auto", (5,), None, {"gemini": 0, "backup": 3})


def test_a_file_from_before_v5_21_loads_its_gemini_pin_as_the_rules_and_ignores_the_judge_and_the_probe(tmp_path):
    path = tmp_path / "kira.route.json"
    path.write_text(json.dumps({"pin": "gemini", "pinned_at_ms": 5, "blocks": [7], "judged": {"rated": 25},
                                "pinned_blocks": [7], "probed": {"calls": 60}, "day": "2026-11-02"}))
    assert load_route(path) == Route(pin="auto", blocks=(7,), day="2026-11-02")


def test_a_day_change_resets_the_answers():
    r = step(Route(), ms(28, 23, 50), "gemini", 300, 10, 3600, "2026-10-28")
    assert step(r, ms(29, 0, 10), "backup", 300, 10, 3600, "2026-10-29").answers == {"gemini": 0, "backup": 1}


# --- v5.21 (the owner, 2026-11-02): two modes, the hour after more than 10 blocks, `/gemini` and `/backup` -------------
def test_a_block_gives_five_minutes_of_the_backup_then_gemini_directly():
    r = step(Route(), ms(28, 20), "block", 300, 10, 3600, "2026-10-28")
    assert mode(r, ms(28, 20, 4)) == "backup" and mode(r, ms(28, 20, 5)) == "gemini"   # no window_end any more
    assert mode(Route(), ms(28, 20)) == "gemini"
    r = step(r, ms(28, 20, 6), "gemini", 300, 10, 3600, "2026-10-28")
    assert r.window_until_ms is None and r.answers == {"gemini": 1, "backup": 0}


def test_more_than_ten_blocks_in_an_hour_give_an_hour_and_the_count_forgets_older_blocks():
    r = Route()
    for i in range(10):                                                     # ten blocks, six minutes apart
        r = step(r, ms(28, 20, 0) + i * 360_000, "block", 300, 10, 3600, "2026-10-28")
    tenth = ms(28, 20, 0) + 9 * 360_000
    assert r.window_until_ms == tenth + 300_000                              # ten: still five minutes
    edge = step(r, tenth + 360_000, "block", 300, 10, 3600, "2026-10-28")  # 21:00: the 20:00 block is an hour old
    assert edge.window_until_ms == tenth + 360_000 + 300_000                  # ten in the last hour: five minutes
    r = step(r, tenth + 300_000, "block", 300, 10, 3600, "2026-10-28")   # 20:59: the 11th within the hour
    assert r.window_until_ms == tenth + 300_000 + 3_600_000 and mode(r, tenth + 300_000 + 3_599_000) == "backup"
    later = Route(blocks=tuple(ms(28, 18, m) for m in range(0, 50, 5)))      # ten blocks over an hour ago
    later = step(later, ms(28, 20), "block", 300, 10, 3600, "2026-10-28")
    assert later.blocks == (ms(28, 20),) and later.window_until_ms == ms(28, 20, 5)


def test_gemini_by_hand_ends_either_window_and_empties_the_count_and_backup_holds_until_it():
    r = Route()
    for i in range(11):
        r = step(r, ms(28, 20) + i * 60_000, "block", 300, 10, 3600, "2026-10-28")
    assert mode(r, ms(28, 20, 30)) == "backup"
    r = step(r, ms(28, 20, 31), "pin:gemini", 300, 10, 3600, "2026-10-28")
    assert mode(r, ms(28, 20, 31)) == "gemini" and r.blocks == () and r.pin == "auto"
    r = step(r, ms(28, 21), "pin:backup", 300, 10, 3600, "2026-10-28")
    assert mode(r, ms(29, 9)) == "backup"                                   # no end of its own
    held = step(r, ms(28, 21, 1), "block", 300, 10, 3600, "2026-10-28")
    assert held.blocks == () and held.window_until_ms is None              # by hand: neither counted nor windowed
    assert mode(step(held, ms(29, 9), "pin:gemini", 300, 10, 3600, "2026-10-29"), ms(29, 9)) == "gemini"


def test_the_mark_names_the_windows_end_or_by_hand_and_every_form_is_stripped():
    r = step(Route(), ms(28, 20, 36), "block", 300, 10, 3600, "2026-10-28")
    assert backup_mark(r, ms(28, 20, 37), TZ) == "⚙️ backup до 20:41"
    assert backup_mark(Route(pin="backup"), ms(28, 20), TZ) == "⚙️ backup · вручну"
    assert backup_mark(Route(), ms(28, 20), TZ) == "⚙️ backup"
    dst = int(datetime(2026, 10, 25, 3, 58, tzinfo=ZoneInfo(TZ)).timestamp() * 1000)  # Kyiv's clocks went back at 04:00
    assert backup_mark(step(Route(), dst, "block", 300, 10, 3600, "2026-10-25"), dst, TZ) == "⚙️ backup до 03:03"
    for mark in ("⚙️ backup до 20:41", "⚙️ backup · вручну", "⚙️ backup"):
        assert BACKUP_MARK_RE.sub("", f"{mark}\nПривіт") == "Привіт"
    assert BACKUP_MARK_RE.sub("", "⚙️ backupний рядок\nПривіт") != "Привіт"


def test_the_status_names_the_mode_the_hours_blocks_and_never_a_text():
    r = step(Route(), ms(28, 20), "block", 300, 10, 3600, "2026-10-28")
    text = route_status(r, ms(28, 20, 1), TZ, 10, 7, {"gemini": 3, "backup": 1})
    assert text.splitlines() == ["⚙️ Маршрут — backup до 20:05 (повернути зараз: /gemini)",
                                 "Блоків за останню годину: 1 з 10 (більше — backup на годину)",
                                 "Приватний чат: закритих рядків 7",
                                 "Сьогодні відповіла: через gemini 3, через backup 1"]
    assert route_status(Route(pin="backup"), ms(28, 20), TZ, 10, 0, {}).startswith(
        "⚙️ Маршрут — backup вручну (повернути: /gemini)")
    assert route_status(Route(), ms(28, 20), TZ, 10, 0, {}).startswith("⚙️ Маршрут — gemini\n")
