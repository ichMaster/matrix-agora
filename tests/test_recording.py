"""v5.4 — the Agora recording: the period his answer names, the plan of pieces, the opening (pure); the assembly."""

import asyncio
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from agents import recording as rec
from agents.logic import BANNED_RE
from agents.recording import (
    CLOSING,
    RECORD_SKILL,
    Event,
    Piece,
    now_line,
    opening_line,
    plan_recording,
    recording_mark,
)

TZ = "Europe/Kyiv"
OWNER, ADA, BRUNO, KIT, HERMES = "@ich:agora.lan", "@ada:agora.lan", "@bruno:agora.lan", "@kit:agora.lan", "@hermes:agora.lan"
MEMBERS = {ADA, BRUNO, KIT}


def ms(day, hour, minute=0, second=0):
    return int(datetime(2026, 10, day, hour, minute, second, tzinfo=ZoneInfo(TZ)).timestamp() * 1000)


# --- the skill: the period his answer names ----------------------------------------------------------------------
@pytest.mark.parametrize("answer,words,period", [
    ("Зараз зберу тобі вечір.\nЗАПИС: 2026-10-19 17:00 — 2026-10-19 19:00", "Зараз зберу тобі вечір.",
     (ms(19, 17), ms(19, 19))),
    ("Лови.\n**ЗАПИС: 2026-10-19 17.30 – 2026-10-19 19:05**", "Лови.", (ms(19, 17, 30), ms(19, 19, 5))),
    ("ЗАПИС: 2026-10-19 22:00 - 2026-10-20 02:00", "", (ms(19, 22), ms(20, 2))),            # across midnight
    ("Увесь учорашній.\n«ЗАПИС: 2026-10-19 00:00 — 2026-10-19 24:00»", "Увесь учорашній.", (ms(19, 0), ms(20, 0))),
    ("Збираю.\nЗАПИС: 2026-10-20 00:00 — 2026-10-20 23:59", "Збираю.", (ms(20, 0), ms(20, 14))),  # never past now
])
def test_the_period_line_is_read_and_never_sent(answer, words, period):
    assert recording_mark(answer, ms(20, 14), TZ) == (words, period)


@pytest.mark.parametrize("answer,words", [
    ("Зараз зберу тобі вечір. ЗАПИС: 2026-10-19 17:00 — 2026-10-19 19:00", "Зараз зберу тобі вечір."),
    ("Лови вечір.\n```\nЗАПИС: 2026-10-19 17:00 — 2026-10-19 19:00\n```", "Лови вечір."),
    ("Лови вечір. `ЗАПИС: 2026-10-19 17:00 — 2026-10-19 19:00`.", "Лови вечір."),
])
def test_the_period_line_after_his_sentence_or_in_a_fence_is_read_too(answer, words):
    """v5.4 review #1: on the same line as his words the mark was sent to the owner as is, and nothing recorded."""
    assert recording_mark(answer, ms(20, 14), TZ) == (words, (ms(19, 17), ms(19, 19)))


@pytest.mark.parametrize("answer", [
    "Збираю.\nЗАПИС: 2026-10-19 19:00 — 2026-10-19 17:00",        # ends before it starts
    "Збираю.\nЗАПИС: 2026-10-17 10:00 — 2026-10-19 10:00",        # two days
    "Збираю.\nЗАПИС: 2026-10-21 10:00 — 2026-10-21 12:00",        # tomorrow
    "Збираю.\nЗАПИС: 2026-13-40 10:00 — 2026-10-19 12:00",        # no such day
])
def test_a_wrong_period_records_nothing_and_the_line_is_still_never_sent(answer):
    assert recording_mark(answer, ms(20, 14), TZ) == ("Збираю.", None)


def test_an_answer_with_no_line_is_just_an_answer():
    assert recording_mark("Привіт! Як ти?", ms(20, 14), TZ) == ("Привіт! Як ти?", None)
    assert recording_mark("Про запис: Ада просила ЗАПИС у студії.", ms(20, 14), TZ)[1] is None


def test_yesterday_across_the_dst_switch_is_its_whole_local_day():
    """2026-10-25: Kyiv falls back an hour — that day is 25 hours long, and still a day."""
    now = int(datetime(2026, 10, 26, 12, 0, tzinfo=ZoneInfo(TZ)).timestamp() * 1000)
    _, (start, end) = recording_mark("ЗАПИС: 2026-10-25 00:00 — 2026-10-26 00:00", now, TZ)
    assert end - start == 25 * 3600 * 1000


def test_the_skill_and_the_time_now():
    assert "ЗАПИС: РРРР-ММ-ДД ГГ:ХХ — РРРР-ММ-ДД ГГ:ХХ" in RECORD_SKILL and not BANNED_RE.search(RECORD_SKILL)
    assert now_line(ms(20, 1, 5), TZ) == "Зараз: вівторок, 20 жовтня 2026, 01:05."


# --- the plan -------------------------------------------------------------------------------------------------------
def text(sender, body, ts, eid=None, edit=False):
    return Event(eid or f"$t{ts}", sender, ts, "text", body, edit=edit)


def voice(sender, ts, caption=None, mime="audio/ogg"):
    return Event(f"$v{ts}", sender, ts, "audio", "Голосове повідомлення", mxc=f"mxc://agora.lan/{ts}", mime=mime,
                 caption=caption)


def test_each_kind_of_line_becomes_its_piece():
    t = ms(19, 10)
    events = [
        voice(OWNER, t, mime="audio/mp4"),                       # the owner's voice → as it is
        text(HERMES, "🎙 Ich: Адо, як ти?", t + 2000),           # his transcript → left out
        voice(ADA, t + 5000),                                    # Ada's voice…
        text(ADA, "Добре, дякую!", t + 6000),                    # …and its words, consumed
        text(OWNER, "А ти, Бруно?", t + 9000),                   # the owner typed → spoken in his voice
        text(BRUNO, "Я в горах.", t + 12000),                    # Bruno text-only (over budget) → spoken in his
        text(KIT, "*мружиться*", t + 14000),                     # an action purr → left out
        voice(KIT, t + 15000),
        text(KIT, "Мрррр.", t + 15500),
        text(BRUNO, "* Я в горах!", t + 16000, edit=True),       # an edit → left out
        text("@mallory:agora.lan", "привіт", t + 17000),         # a stranger → left out
    ]
    plan = plan_recording(events, OWNER, MEMBERS)
    assert [(p.kind, p.speaker) for p in plan] == [("audio", OWNER), ("audio", ADA), ("speak", OWNER),
                                                   ("speak", BRUNO), ("audio", KIT)]
    assert plan[0].mime == "audio/mp4" and plan[2].text == "А ти, Бруно?" and plan[3].text == "Я в горах."


def test_a_voice_with_no_text_and_a_late_text_and_a_caption():
    t = ms(19, 10)
    plan = plan_recording([voice(ADA, t, caption="Слова в підписі."),        # a voice-only line of 2026-10-18
                           voice(BRUNO, t + 1000),
                           text(BRUNO, "Пізній рядок.", t + 1000 + 31_000)],   # past 30 s: its own line
                          OWNER, MEMBERS)
    assert [(p.kind, p.speaker) for p in plan] == [("audio", ADA), ("audio", BRUNO), ("speak", BRUNO)]


def test_a_long_silence_gets_a_pause():
    plan = plan_recording([text(OWNER, "Привіт", ms(19, 10)), text(OWNER, "Я тут", ms(19, 10, 10)),
                           text(OWNER, "Знову я", ms(19, 17, 5))], OWNER, MEMBERS)
    assert [p.kind for p in plan] == ["speak", "speak", "gap", "speak"] and plan[2].ts == ms(19, 17, 5)


def test_an_empty_stretch_is_an_empty_plan():
    assert plan_recording([text(HERMES, "🎙 Ich: x", ms(19, 10))], OWNER, MEMBERS) == []


# --- the spoken words ------------------------------------------------------------------------------------------------
def test_the_opening_and_the_closing():
    assert opening_line(ms(19, 10, 5), ms(19, 23, 40), TZ) == "Агора, 19 жовтня, з десятої до двадцять третьої."
    assert opening_line(ms(19, 0, 5), ms(19, 1, 0), TZ) == "Агора, 19 жовтня, з опівночі до першої."
    assert CLOSING and Piece("gap").kind == "gap"
    assert not hasattr(rec, "gap_line")                  # no spoken time before a line (the owner, 2026-10-20)


# --- the assembly (ffmpeg mocked) -----------------------------------------------------------------------------------

def _read(path: str) -> bytes:
    return Path(path).read_bytes()


class FakeProc:
    def __init__(self, code=0, out=b"\x01\x00" * 100):
        self.returncode, self.out, self.input = code, out, "unset"

    async def communicate(self, input=None):
        self.input = input
        return self.out, b""


def test_the_decode_reads_a_file_or_raw_pcm_and_levels_it(monkeypatch):
    seen = []

    async def fake_exec(*argv, **kw):
        seen.append(argv)
        if "-i" in argv and argv[argv.index("-i") + 1] != "pipe:0":
            assert _read(argv[argv.index("-i") + 1]) == b"OggS-voice"   # the file exists while ffmpeg reads it
        return FakeProc()

    monkeypatch.setattr(rec.asyncio, "create_subprocess_exec", fake_exec)
    assert asyncio.run(rec.decode_to_pcm(b"OggS-voice")) == b"\x01\x00" * 100
    path = seen[0][seen[0].index("-i") + 1]
    assert not os.path.exists(path)                                       # removed after
    assert asyncio.run(rec.decode_to_pcm(b"\x00\x00" * 10, raw=True))
    assert seen[1][-9:] == ("-af", rec.LOUDNORM, "-f", "s16le", "-ar", "24000", "-ac", "1", "pipe:1")
    assert seen[1][4:12] == ("-f", "s16le", "-ar", "24000", "-ac", "1", "-i", "pipe:0")


def test_a_failed_decode_is_none(monkeypatch):
    async def fake_exec(*argv, **kw):
        return FakeProc(code=1, out=b"")

    monkeypatch.setattr(rec.asyncio, "create_subprocess_exec", fake_exec)
    assert asyncio.run(rec.decode_to_pcm(b"x")) is None


def test_silence_and_the_split_never_cuts_a_piece():
    assert len(rec.silence(0.5)) == 24000 and rec.pcm_seconds(rec.silence(2)) == 2
    assert rec.split_parts([1000, 1000, 1000, 1000], 3600) == [[0, 1, 2], [3]]
    assert rec.split_parts([5000, 10], 3600) == [[0], [1]]                 # a long piece is a part of its own
    assert rec.split_parts([], 3600) == []


def test_the_assembly_pads_lines_and_marks_and_encodes_each_part(monkeypatch):
    encoded = []

    async def fake_encode(pcm):
        encoded.append(pcm)
        return b"OggS" + bytes([len(encoded)])

    monkeypatch.setattr(rec, "encode_opus", fake_encode)
    line, mark = b"\x10\x00" * 24000, b"\x20\x00" * 12000                 # 1 s and 0.5 s
    parts = asyncio.run(rec.assemble([(line, False), (mark, True), (line, False)], max_s=10))
    assert len(parts) == 1 and parts[0][0] == b"OggS\x01"
    expected_s = (0.5 + 1) + (1.5 + 0.5 + 1.5) + (0.5 + 1) + 0.5
    assert parts[0][1] == int(expected_s * 1000)
    parts = asyncio.run(rec.assemble([(line, False)] * 3, max_s=3))       # 1.5 s each → two parts
    assert len(parts) == 2


def test_a_failed_encode_gives_no_recording(monkeypatch):
    async def fail(pcm):
        return None

    monkeypatch.setattr(rec, "encode_opus", fail)
    assert asyncio.run(rec.assemble([(b"\x00\x00", False)])) == []
