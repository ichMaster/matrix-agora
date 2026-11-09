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

    async def make(self, shot, moment, aspect="3:4", extra=None, kind="photo"):
        self.shots.append(shot)
        self.frames = [*getattr(self, "frames", []), (aspect, extra)]
        self.kinds = [*getattr(self, "kinds", []), kind]  # v5.22: her photo, or a video's frame
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
    assert agent.photos.kinds == ["photo"]                                          # v5.22: her photo
    assert agent.sent == ["voice", ("photo", "Ось я під куполом 🙂")]                  # no separate text message
    assert PHOTO_SKILL in agent.llm.calls[0][0]                                        # offered to Gemini in Telegram
    assert any(c.args[1] == "upload_photo" for c in agent.telegram.send_chat_action.call_args_list)
    assert her_line(agent) == "Ось я під куполом 🙂"     # v5.23 (the owner): no note of the photo in her history
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


def test_an_echoed_empty_note_draws_her_answer_again_without_a_photo(tmp_path, monkeypatch, ogg, caplog):
    # code review v5.21 #1: «[селфі: ...]» echoed from her history names nothing — never «лови» with nothing
    caplog.set_level(logging.INFO)
    agent = her(tmp_path, monkeypatch, "Ось, лови 🙂 [селфі: ...]", "Фото потім, зараз світла нема.")
    agent.private_line("скинь селфі", ms(17), "telegram", "tg:1")
    assert asyncio.run(agent.private_reply()) is True
    assert agent.photos.shots == []                                                       # nothing drawn
    redraw = agent.llm.calls[1][0]
    assert PHOTO_FAILED in redraw and PHOTO_SKILL not in redraw
    assert agent.sent == ["voice", ("text", "Фото потім, зараз світла нема.")]
    assert "photo: dropped (no description)" in caplog.text and not photos_dir(agent).exists()


def test_at_most_so_many_photos_in_any_window(tmp_path, monkeypatch, ogg, caplog):
    """v5.22 (the owner, 2026-11-02: «Кіра висилає фото з кожним меседжем … ліпше кількість на 30 хв, тоді вона може
    висилати нерівномірно»): at most `PHOTO_WINDOW_MAX` photos in any `PHOTO_WINDOW_S` — read from the kept photos'
    names — then no skill, and a photo line meanwhile is dropped as `window`."""
    caplog.set_level(logging.INFO)
    agent = her(tmp_path, monkeypatch, "А ось і ще\nСЕЛФІ: я з чаєм", "Тримай\nФОТО: чашка")
    agent.photo_window_max, agent.photo_window_s = 3, 1800
    photos_dir(agent).mkdir(parents=True)
    for name in ("174000", "175000", "175500"):                                 # three in the last half hour
        (photos_dir(agent) / f"{name}.jpg").write_bytes(b"JPEG")
    agent.clock = lambda: ms(18, 5)
    agent.private_line("а ще?", ms(18, 4), "telegram", "tg:1")
    assert asyncio.run(agent.private_reply()) is True
    assert PHOTO_SKILL not in agent.llm.calls[0][0] and agent.photos.shots == []
    assert "photo: dropped (window)" in caplog.text and agent.sent[-1] == ("text", "А ось і ще")
    agent.clock = lambda: ms(18, 11)                                            # 17:40 has left the window: two in it
    agent.private_line("а тепер?", ms(18, 10), "telegram", "tg:2")
    assert asyncio.run(agent.private_reply()) is True
    assert PHOTO_SKILL in agent.llm.calls[1][0] and agent.photos.shots == [Shot("photo", "чашка")]


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


def test_an_agora_line_that_begins_with_foto_is_never_cut(tmp_path, monkeypatch):
    # v5.17 review #1: the cut ran on every agent's reply — a line of Мія's «Фото: …» vanished from Agora
    agent = her(tmp_path, monkeypatch, "Фото: 1934 рік, архів на Підвальній.\nКраще бачити самим.")
    text = asyncio.run(agent._compose("канон", lines=[("Ich", "що там в архіві?")], kind="reply"))
    assert str(text) == "Фото: 1934 рік, архів на Підвальній.\nКраще бачити самим."
    assert agent.photos.shots == []


def test_no_faces_at_start_is_a_warning(tmp_path, monkeypatch, caplog):
    # v5.17 review #3: the first live deploy logged «photos: 0 faces» at INFO, and nothing stood out
    from agents.llm import GeminiClient
    monkeypatch.setattr(GeminiClient, "__init__", lambda self, sink=None: None)
    monkeypatch.setattr(agent_mod, "photo_maker", lambda *a: object())
    cfg = telegram_kira(tmp_path, monkeypatch).cfg
    cfg = cfg.__class__(**{**cfg.__dict__, "capabilities": cfg.capabilities | {"photos"}})
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(agent_mod, "load_faces", lambda folder: [])
    agent_mod.Agent(cfg, llm=GeminiClient())
    assert [r.levelname for r in caplog.records if "no faces" in r.getMessage()] == ["WARNING"]
    caplog.clear()
    monkeypatch.setattr(agent_mod, "load_faces", lambda folder: [("kira.png", b"x", "image/png")])
    agent_mod.Agent(cfg, llm=GeminiClient())
    assert "photos: 1 faces" in caplog.text and "no faces" not in caplog.text


def test_a_missing_look_file_is_a_warning(tmp_path, monkeypatch, caplog):
    # v6.2 review #1: «photos: 21 faces, no look file» at INFO would let her selfie lose her look unnoticed
    from agents.llm import GeminiClient
    monkeypatch.setattr(GeminiClient, "__init__", lambda self, sink=None: None)
    monkeypatch.setattr(agent_mod, "photo_maker", lambda *a: object())
    monkeypatch.setattr(agent_mod, "load_faces", lambda folder: [("kira.png", b"x", "image/png")])
    cfg = telegram_kira(tmp_path, monkeypatch).cfg
    cfg = cfg.__class__(**{**cfg.__dict__, "capabilities": cfg.capabilities | {"photos"}})
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(agent_mod, "load_look", lambda path: "")
    agent_mod.Agent(cfg, llm=GeminiClient())
    assert [r.levelname for r in caplog.records if "no look file" in r.getMessage()] == ["WARNING"]
    caplog.clear()
    monkeypatch.setattr(agent_mod, "load_look", lambda path: "She never wears makeup.")
    agent_mod.Agent(cfg, llm=GeminiClient())
    assert "no look file" not in caplog.text and "She never wears makeup" not in caplog.text  # never her look itself



def test_her_photo_maker_is_built_for_her_own_main_face_age_and_look(tmp_path, monkeypatch):
    # v6.2: nothing of the selfie is Кіра's in code — the localpart names the main face and the look file, the chart
    # gives the birth date
    from datetime import date

    from agents.llm import GeminiClient
    monkeypatch.setattr(GeminiClient, "__init__", lambda self, sink=None: None)
    built, looked = [], []
    monkeypatch.setattr(agent_mod, "photo_maker", lambda *a: built.append(a) or object())
    monkeypatch.setattr(agent_mod, "load_faces", lambda folder: [("ustyna.png", b"x", "image/png")])
    monkeypatch.setattr(agent_mod, "load_look", lambda path: looked.append(path) or "Her eyes are light grey.")
    cfg = telegram_kira(tmp_path, monkeypatch).cfg
    cfg = cfg.__class__(**{**cfg.__dict__, "user_id": "@ustyna:agora.lan", "capabilities": cfg.capabilities | {"photos"},
                           "natal": "Народження: 01.11.2004, 23:00, Львів."})
    agent_mod.Agent(cfg, llm=GeminiClient())
    assert built[0][4:] == ("ustyna.png", date(2004, 11, 1), "Her eyes are light grey.")
    assert str(looked[0]).endswith("agents/canon/ustyna.look.md")

class ShyOfPhotos(Says):
    """Gemini blocks a private prompt that offers her photo skill (`always`: every one), answers one that does not."""

    def __init__(self, always=False):
        super().__init__()
        self.always = always

    async def generate(self, transcript, system_instruction, max_output_tokens=400, kind="reply"):
        from agents.llm import LAST_BLOCK
        self.calls.append((system_instruction, kind))
        if kind == "private" and (self.always or PHOTO_SKILL in system_instruction):
            LAST_BLOCK.set(("prompt", "prohibited_content", None))
            return None
        return "Без фото цього разу 🙂"


def test_a_block_with_her_photo_skill_is_tried_once_more_without_it_never_the_backup(tmp_path, monkeypatch, ogg):
    """v5.23 (the owner, 2026-11-03: «не треба переключати на бекап якщо блок на фото» — «Повтор без фото»): Gemini
    answers without the photo skill; the backup is not asked, his line stays open, the route stays Gemini's."""
    from agents.fallback import FallbackResponder
    from agents.responder import responder_for
    from tests.test_private_route import Backup

    def gemini(llm):
        agent.llm, agent.responder = llm, responder_for("gemini", llm)
    agent = her(tmp_path, monkeypatch)
    gemini(ShyOfPhotos())
    agent.cfg = agent.cfg.__class__(**{**agent.cfg.__dict__, "capabilities": agent.cfg.capabilities | {"fallback"}})
    agent.fallback = Backup()
    agent.fallback_responder = FallbackResponder(agent.fallback)
    agent.private_line("скинь фото", ms(17), "telegram", "tg:1")
    assert asyncio.run(agent.private_reply()) is True
    first, again = [c[0] for c in agent.llm.calls if c[1] == "private"]
    assert PHOTO_SKILL in first and PHOTO_SKILL not in again and agent.fallback.calls == []
    assert agent.sent[-1] == ("text", "Без фото цього разу 🙂") and agent.photos.shots == []
    assert [x.mark for x in agent.archive.latest("private", 10, gemini=False) if x.key == "tg:1"] != ["blocked"]
    # blocked without the photo skill too: a block, as ever — the backup answers
    gemini(ShyOfPhotos(always=True))
    agent.private_line("а так?", ms(17) + 60_000, "telegram", "tg:2")
    assert asyncio.run(agent.private_reply()) is True
    assert len(agent.fallback.calls) == 1


# --- v6.5 (AGORA-234): her photo's request for fal, written by her backup ---------------------------------------------
class Backup:
    """Her backup model: answers with the given text (None: a failure), keeps each call."""

    def __init__(self, text):
        self.text, self.calls = text, []

    async def reply(self, transcript, system_instruction, max_output_tokens=400, kind="private"):
        self.calls.append((transcript, system_instruction, max_output_tokens, kind))
        return (self.text, "stop") if self.text is not None else None


def fal_prompt(agent, shot):
    from datetime import date, datetime
    from zoneinfo import ZoneInfo

    from agents.photo import Moment
    agent.photo_birth, agent.photo_look = date(2004, 11, 1), "Light grey eyes."
    return asyncio.run(agent._fal_prompt(shot, Moment(datetime(2026, 11, 9, 9, 15, tzinfo=ZoneInfo("Europe/Kyiv")))))


def test_the_backup_writes_the_scene_between_the_codes_own_lines_and_the_log_names_only_its_length(
        tmp_path, monkeypatch, caplog):
    from agents.photo import SCENE_INSTRUCTION
    caplog.set_level(logging.INFO)
    agent = her(tmp_path, monkeypatch)
    scene = f"A made-up scene {SECRET}: she laughs on a tram in a red scarf, grey daylight."
    agent.fallback = Backup(scene)
    req = fal_prompt(agent, Shot("selfie", f"я в трамваї {SECRET}"))
    assert scene in req and "She is an adult woman, 22 years old." in req and "Light grey eyes." in req
    transcript, instruction, _, kind = agent.fallback.calls[0]
    assert instruction == SCENE_INSTRUCTION and kind == "photo_prompt" and f"я в трамваї {SECRET}" in transcript
    assert f"photo: the request by the backup ({len(scene)} chars)" in caplog.text and SECRET not in caplog.text


@pytest.mark.parametrize("backup,why", [(None, "no backup"), (Backup(None), "failed"),
                                        (Backup("Дівчина в трамваї, сміється."), "not english")])
def test_the_template_without_a_backup_when_it_fails_or_answers_not_in_english(tmp_path, monkeypatch, caplog,
                                                                                backup, why):
    caplog.set_level(logging.INFO)
    agent = her(tmp_path, monkeypatch)
    agent.fallback = backup
    req = fal_prompt(agent, Shot("selfie", "я в трамваї"))
    assert "as she describes it (in Ukrainian): я в трамваї" in req and "She is an adult woman, 22" in req
    assert f"photo: the request by the template ({why})" in caplog.text and "трамва" not in caplog.text
