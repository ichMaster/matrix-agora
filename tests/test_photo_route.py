"""v5.17 — her photo in her private answer: the skill in Gemini's prompt in Telegram only; her `СЕЛФІ:` / `ФОТО:` line
cut, the photo made before anything is sent; her voice note, then the photo with her words under it; kept as a file and
named in her line; a photo that does not come out draws her answer again without it; dropped from the backup, in
Element and past the day's cap (nio, Gemini, the image model and Telegram mocked; an injected clock; made-up lines)."""

import asyncio
import logging
import os
import stat
from unittest.mock import AsyncMock

import pytest

from agents import agent as agent_mod
from agents.archive import Archive
from agents.photo import PHOTO_FAILED, PHOTO_SKILL, Made, Shot
from agents.private import PRIVATE_BRIEF
from tests.test_private_runtime import ms
from tests.test_telegram_runtime import FakeTTS
from tests.test_telegram_runtime import kira as telegram_kira

SECRET = "кадр-5172"


class Says:
    """Gemini: says the given answers in turn (None: a silence), keeps each call's instruction."""

    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    async def generate(self, transcript, system_instruction, max_output_tokens=400, kind="reply"):
        self.calls.append((system_instruction, kind))
        return self.answers.pop(0) if self.answers else "ага"


class Maker:
    """The image model: one `Made` for every shot; keeps the shots."""

    def __init__(self, made=None):
        self.made, self.shots = made or Made(b"JPEG", "image/jpeg", "ok"), []

    async def make(self, shot, moment):
        self.shots.append(shot)
        return self.made


@pytest.fixture
def ogg(monkeypatch):
    async def encode(pcm, timeout_s=60.0):
        return b"OggS-kira"
    monkeypatch.setattr(agent_mod, "encode_opus", encode)


def her(tmp_path, monkeypatch, *answers, made=None):
    agent = telegram_kira(tmp_path, monkeypatch, llm=Says(*answers))
    agent.cfg = agent.cfg.__class__(**{**agent.cfg.__dict__, "capabilities": agent.cfg.capabilities | {"photos"}})
    agent.archive = Archive(tmp_path / "kira.archive.db")
    agent.photos, agent.photo_day_max = Maker(made), 40
    agent.tts = FakeTTS()
    agent._spawn = lambda coro: coro.close()  # the test answers by itself, at once
    agent.sent = []
    bot = agent.telegram

    async def voice(chat_id, ogg_bytes, duration_s):
        agent.sent.append("voice")
        return True

    async def photo(chat_id, image, caption=None, mime="image/jpeg"):
        agent.sent.append(("photo", caption))
        return True

    async def text(chat_id, body):
        agent.sent.append(("text", body))
        return True

    bot.send_voice, bot.send_photo, bot.send_message = (AsyncMock(side_effect=voice), AsyncMock(side_effect=photo),
                                                        AsyncMock(side_effect=text))
    return agent


def photos_dir(agent):
    return agent.memory_file.parent / "kira.photos" / "2026-10-20"


def her_line(agent):
    return [x for x in agent.archive.latest("private", 10, gemini=False) if x.speaker == "Кіра"][-1].text


def test_a_selfie_goes_after_her_voice_with_her_words_under_it_and_is_kept(tmp_path, monkeypatch, ogg, caplog):
    caplog.set_level(logging.INFO)
    agent = her(tmp_path, monkeypatch, f"Ось я під куполом 🙂\nСЕЛФІ: я під куполом уночі {SECRET}")
    agent.private_line("скинь своє фото", ms(17), "telegram", "tg:1")
    assert asyncio.run(agent.private_reply()) is True
    assert agent.photos.shots == [Shot("selfie", f"я під куполом уночі {SECRET}")]
    assert agent.sent == ["voice", ("photo", "Ось я під куполом 🙂")]                  # no separate text message
    assert PHOTO_SKILL in agent.llm.calls[0][0]                                        # offered to Gemini in Telegram
    assert any(c.args[1] == "upload_photo" for c in agent.telegram.send_chat_action.call_args_list)
    assert her_line(agent) == f"Ось я під куполом 🙂\n[селфі: я під куполом уночі {SECRET}]"
    assert agent.private_history[-1] == ("Кіра", her_line(agent))
    [kept] = list(photos_dir(agent).iterdir())
    assert kept.name == "180000.jpg" and kept.read_bytes() == b"JPEG"
    assert stat.S_IMODE(os.stat(kept).st_mode) == 0o600 and stat.S_IMODE(os.stat(kept.parent).st_mode) == 0o700
    assert "photo: sent (selfie, telegram)" in caplog.text
    assert SECRET not in caplog.text and str(kept) not in caplog.text


def test_a_long_text_goes_after_the_photo(tmp_path, monkeypatch, ogg):
    long = "Слухай. " * 200
    agent = her(tmp_path, monkeypatch, f"{long}\nФОТО: чашка на підвіконні")
    agent.private_line("що там у тебе?", ms(17), "telegram", "tg:1")
    assert asyncio.run(agent.private_reply()) is True
    assert agent.sent == ["voice", ("photo", None), ("text", long.strip())]
    assert agent.photos.shots == [Shot("photo", "чашка на підвіконні")]


@pytest.mark.parametrize("why", ["blocked", "failed"])
def test_a_photo_that_does_not_come_out_draws_her_answer_again_without_it(tmp_path, monkeypatch, ogg, caplog, why):
    caplog.set_level(logging.INFO)
    agent = her(tmp_path, monkeypatch, "Дивись!\nСЕЛФІ: я на скелі", "Сьогодні без фото, вибач, купол зачинений.",
                made=Made(None, why=why))
    agent.private_line("покажи себе", ms(17), "telegram", "tg:1")
    assert asyncio.run(agent.private_reply()) is True
    redraw = agent.llm.calls[1][0]
    assert PHOTO_FAILED in redraw and PHOTO_SKILL not in redraw                         # no skill the second time
    assert agent.sent == ["voice", ("text", "Сьогодні без фото, вибач, купол зачинений.")]
    assert her_line(agent) == "Сьогодні без фото, вибач, купол зачинений."
    assert not photos_dir(agent).exists() and f"photo: {why} — her answer without it" in caplog.text


def test_a_failed_redraw_sends_her_first_words_without_the_line(tmp_path, monkeypatch, ogg):
    agent = her(tmp_path, monkeypatch, "Дивись!\nФОТО: туман над Тустанню", None, made=Made(None, why="blocked"))
    agent.private_line("що там?", ms(17), "telegram", "tg:1")
    assert asyncio.run(agent.private_reply()) is True
    assert agent.sent == ["voice", ("text", "Дивись!")]


def test_past_the_days_cap_no_skill_and_the_line_is_dropped(tmp_path, monkeypatch, ogg, caplog):
    caplog.set_level(logging.INFO)
    agent = her(tmp_path, monkeypatch, "Ось.\nФОТО: чашка")
    agent.photo_day_max = 2
    photos_dir(agent).mkdir(parents=True)
    for name in ("090000.jpg", "120000.jpg"):
        (photos_dir(agent) / name).write_bytes(b"x")
    agent.private_line("ще фото?", ms(17), "telegram", "tg:1")
    assert asyncio.run(agent.private_reply()) is True
    assert PHOTO_SKILL not in agent.llm.calls[0][0] and agent.photos.shots == []
    assert agent.sent == ["voice", ("text", "Ось.")] and "photo: dropped (cap)" in caplog.text


def test_in_element_no_skill_and_the_line_is_dropped(tmp_path, monkeypatch, caplog):
    from tests.test_archive import DM
    caplog.set_level(logging.INFO)
    agent = her(tmp_path, monkeypatch, "Привіт!\nСЕЛФІ: я в бусі")
    agent.private_room, agent.voice_reply_p = DM, 0.0
    agent.private_line("привіт", ms(17), "matrix", "$p1")
    assert asyncio.run(agent.private_reply()) is True
    assert PHOTO_SKILL not in agent.llm.calls[0][0] and agent.photos.shots == []
    body = agent.client.room_send.call_args.kwargs.get("content") or agent.client.room_send.call_args.args[2]
    assert body["body"] == "Привіт!" and "photo: dropped (element)" in caplog.text


def test_the_skill_is_geminis_alone_never_the_backups(tmp_path, monkeypatch):
    from agents.fallback import FallbackResponder
    from tests.test_private_route import Backup
    agent = her(tmp_path, monkeypatch)
    agent.fallback = Backup(text="Ось.\nСЕЛФІ: я на балконі")
    agent.fallback_responder = FallbackResponder(agent.fallback)
    agent.fallback_context, agent.fallback_history_n = 32000, 60
    agent._offer_photo = True
    assert PHOTO_SKILL in asyncio.run(agent._gemini_private_prompt(PRIVATE_BRIEF))
    prompt, _ = asyncio.run(agent._backup_private_prompt(PRIVATE_BRIEF))
    assert PHOTO_SKILL not in prompt
    shots: list = []
    text = asyncio.run(agent._backup_text(PRIVATE_BRIEF, "private"))
    assert str(text) == "Ось." and shots == []                                          # its line dropped


def test_a_line_she_writes_first_can_carry_a_photo(tmp_path, monkeypatch, ogg):
    agent = her(tmp_path, monkeypatch, "Глянь, яке небо сьогодні\nФОТО: захід сонця над Високим Замком")
    agent.private_line("добраніч", ms(9), "telegram", "tg:0")
    assert asyncio.run(agent.private_reply(nudge=True, channel="telegram")) is True
    assert agent.photos.shots == [Shot("photo", "захід сонця над Високим Замком")]
    assert agent.sent == ["voice", ("photo", "Глянь, яке небо сьогодні")]


def test_the_skill_never_says_she_makes_pictures():
    for words in (PHOTO_SKILL, PHOTO_FAILED):
        low = words.lower()
        assert not any(w in low for w in ("модел", "бот", "штучн", "інтелект", "генер", "намалю", "ші "))
    assert "ФОТО" in PHOTO_SKILL and "СЕЛФІ" in PHOTO_SKILL
