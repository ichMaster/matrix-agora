"""v5.4 — the Agora recording: the command and its period, the plan of pieces, the spoken time words (pure)."""

import asyncio
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from agents import recording as rec
from agents.recording import (
    CLOSING,
    Event,
    Piece,
    gap_line,
    hour_words,
    opening_line,
    plan_recording,
    recording_request,
)

TZ = "Europe/Kyiv"
OWNER, ADA, BRUNO, KIT, HERMES = "@ich:agora.lan", "@ada:agora.lan", "@bruno:agora.lan", "@kit:agora.lan", "@hermes:agora.lan"
MEMBERS = {ADA, BRUNO, KIT}


def ms(day, hour, minute=0, second=0):
    return int(datetime(2026, 10, day, hour, minute, second, tzinfo=ZoneInfo(TZ)).timestamp() * 1000)


# --- the command ----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text,period", [
    ("запис за сьогодні", (ms(20, 0), ms(20, 14))),
    ("Запис!", (ms(20, 0), ms(20, 14))),
    ("запиши мені Агору за вчора", (ms(19, 0), ms(20, 0))),
    ("запис з 10", (ms(20, 10), ms(20, 14))),
    ("запис з 9:30", (ms(20, 9, 30), ms(20, 14))),
    ("запис з 23", (ms(20, 0), ms(20, 14))),          # later than now: the whole of today
])
def test_the_command_and_its_period(text, period):
    assert recording_request(text, ms(20, 14), TZ) == period


@pytest.mark.parametrize("text", ["підсумок", "що Ада казала про запис у студії вчора ввечері коли ми говорили?", ""])
def test_anything_else_is_not_a_recording(text):
    assert recording_request(text, ms(20, 14), TZ) is None


def test_yesterday_across_the_dst_switch_is_its_whole_local_day():
    """2026-10-25: Kyiv falls back an hour — that day is 25 hours long."""
    now = int(datetime(2026, 10, 26, 12, 0, tzinfo=ZoneInfo(TZ)).timestamp() * 1000)
    start, end = recording_request("запис за вчора", now, TZ)
    assert (end - start) == 25 * 3600 * 1000


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


def test_a_long_silence_gets_a_time_mark():
    plan = plan_recording([text(OWNER, "Привіт", ms(19, 10)), text(OWNER, "Я тут", ms(19, 10, 10)),
                           text(OWNER, "Знову я", ms(19, 17, 5))], OWNER, MEMBERS)
    assert [p.kind for p in plan] == ["speak", "speak", "gap", "speak"] and plan[2].ts == ms(19, 17, 5)


def test_an_empty_stretch_is_an_empty_plan():
    assert plan_recording([text(HERMES, "🎙 Ich: x", ms(19, 10))], OWNER, MEMBERS) == []


# --- the spoken words ------------------------------------------------------------------------------------------------
def test_hours_and_the_opening():
    assert [hour_words(h) for h in (0, 1, 11, 17, 23)] == ["опівночі", "о першій", "об одинадцятій", "о сімнадцятій",
                                                          "о двадцять третій"]
    assert gap_line(ms(19, 17, 5), TZ) == "О сімнадцятій."
    assert opening_line(ms(19, 10, 5), ms(19, 23, 40), TZ) == "Агора, 19 жовтня, з десятої до двадцять третьої."
    assert CLOSING and Piece("gap").kind == "gap"


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
