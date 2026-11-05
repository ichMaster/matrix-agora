"""v5.24 (AGORA-212) — the scan's pure parts (`agents/scan.py`): the hours it may soften, her window with the softened
spans, the next step, the run search with an injected check, and the ⚙️ answer — times, steps and counts, never a
text (made-up data only)."""

import asyncio
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from agents.logic import BANNED_RE, SOFT_LINE, SOFT_LINE_RE, clean_reply
from agents.scan import LEVEL_NAMES, STRICT_MAX, WHY, hour_spans, minimal_run, next_level, scan_line, soften

KYIV = ZoneInfo("Europe/Kyiv")


def ms(day, hour, minute=0):
    return int(datetime(2026, 11, day, hour, minute, tzinfo=KYIV).timestamp() * 1000)


def row(start, end, strict, text="Пам'ятаю тепло."):
    return SimpleNamespace(start_ms=start, end_ms=end, strict=strict, text=text)


def test_the_spans_are_the_hours_of_the_lines_before_his_waiting_one():
    times = [ms(5, 13, 10), ms(5, 13, 50), ms(5, 15, 5), ms(5, 17, 20), ms(5, 17, 40)]
    assert hour_spans(times, ms(5, 17, 40)) == [(ms(5, 13), ms(5, 14)), (ms(5, 15), ms(5, 16)),
                                                 (ms(5, 17), ms(5, 17, 40))]   # his line at 17:40: never softened
    assert hour_spans(times, ms(5, 13, 10)) == [] and hour_spans([], ms(5, 18)) == []


def test_a_softened_span_stands_once_at_its_first_line_and_one_left_out_not_at_all():
    lines = [(ms(5, 13, 10), "a"), (ms(5, 13, 50), "b"), (ms(5, 14, 5), "c"), (ms(5, 15, 5), "d"), (ms(5, 16), "e")]
    soft = row(ms(5, 13), ms(5, 14), 1)
    out = soften(lines, [soft, row(ms(5, 15), ms(5, 16), STRICT_MAX, "")])
    assert out == [(ms(5, 13, 10), soft), (ms(5, 14, 5), "c"), (ms(5, 16), "e")]
    assert soften(lines, [row(ms(5, 13), ms(5, 14), 0, "")]) == lines[2:]       # no text: left out too
    assert soften(lines, []) == lines


def test_each_step_is_one_stricter_up_to_left_out():
    assert next_level(None) == 0 and next_level(row(0, 1, 0)) == 1 and next_level(row(0, 1, 2)) == STRICT_MAX
    assert next_level(row(0, 1, STRICT_MAX)) == STRICT_MAX
    assert len(LEVEL_NAMES) == STRICT_MAX + 1


def test_the_run_is_the_shortest_that_blocks_at_the_end_then_its_shortest_head():
    def check(bad):
        asked = []

        async def blocks(a, b):
            asked.append((a, b))
            return bad <= set(range(a, b))
        return blocks, asked

    blocks, asked = check({2, 4})                       # spans 2 and 4 block only together
    assert asyncio.run(minimal_run(7, blocks)) == (2, 5) and len(asked) <= 1 + 2 * 3
    blocks, _ = check({6})
    assert asyncio.run(minimal_run(7, blocks)) == (6, 7)
    blocks, _ = check({0, 6})
    assert asyncio.run(minimal_run(7, blocks)) == (0, 7)
    blocks, _ = check({9})                              # all of them together pass
    assert asyncio.run(minimal_run(7, blocks)) is None and asyncio.run(minimal_run(0, blocks)) is None


def test_the_answer_names_the_spans_and_their_steps_or_why_never_a_text():
    now = ms(5, 18)
    line = scan_line("softened", [(ms(5, 14), ms(5, 15), 1), (ms(5, 13), ms(5, 14), 0), (ms(4, 23), ms(5, 0), 3)],
                     17, now, "Europe/Kyiv")
    assert line == ("⚙️ Пом'якшено: 04.11 23:00–00:00 — без підсумку; 13:00–14:00 — підсумок; 14:00–15:00 — "
                    "суворіший підсумок. Промпт проходить — далі gemini (перевірок: 17)")
    assert scan_line("passes", [], 1, now, "Europe/Kyiv") == "⚙️ Промпт проходить — нічого не треба (перевірок: 1)"
    assert scan_line("rest", [], 3, now, "Europe/Kyiv").startswith("⚙️ Блокує не розмова, а решта промпту")
    assert scan_line("nonsense", [], 0, now, "Europe/Kyiv") == f"⚙️ {WHY['failed']} (перевірок: 0)"


def test_a_softened_span_in_her_history_is_never_her_words():
    soft = SOFT_LINE.format(text="Пам'ятаю тепло.")
    assert SOFT_LINE_RE.match(soft) and not BANNED_RE.search(SOFT_LINE)
    assert clean_reply(f"{soft}\nТак, я теж пам'ятаю.", "Кіра", ["Ich"]) == "Так, я теж пам'ятаю."
