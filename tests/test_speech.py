"""v5.3 — the speakers' voices: when a line goes out in voice, what a voice can say, and the speakers' monthly
budget (pure)."""

import pytest

from agents.speech import speakers_month_chars, voice_due, voiceable
from agents.usage import tts_usage_line


def test_the_owners_voice_is_always_answered_in_voice():
    assert voice_due(True, "$e", "ada", 0.0)


def test_the_share_decides_every_other_line_deterministically():
    assert not any(voice_due(False, f"$e{i}", "ada", 0.0) for i in range(200))
    assert all(voice_due(False, f"$e{i}", "ada", 1.0) for i in range(200))
    draws = [voice_due(False, f"$e{i}", "ada", 0.3) for i in range(2000)]
    assert 0.25 < sum(draws) / len(draws) < 0.35
    assert draws == [voice_due(False, f"$e{i}", "ada", 0.3) for i in range(2000)]      # the same every time
    assert draws != [voice_due(False, f"$e{i}", "bruno", 0.3) for i in range(2000)]    # each agent its own draw


@pytest.mark.parametrize("text,ok", [("Мрррр.", True), ("*потягується*", False), ("  ", False), ("", False),
                                     ("Привіт, Ich!", True), ("*сміється* так", True)])
def test_voiceable(text, ok):
    assert voiceable(text) is ok


def test_the_speakers_budget_leaves_out_the_herald_failures_and_other_months():
    records = [tts_usage_line("2026-10-01T09:00:00+03:00", "ada", "m", 100, True),
               tts_usage_line("2026-10-17T09:00:00+03:00", "claude", "m", 200, True),
               tts_usage_line("2026-10-17T09:00:00+03:00", "kit", "m", 400, False),
               tts_usage_line("2026-10-17T09:00:00+03:00", "hermes", "m", 800, True),
               tts_usage_line("2026-09-30T23:00:00+03:00", "bruno", "m", 1600, True)]
    assert speakers_month_chars(records, "2026-10", ["hermes"]) == 300
