"""v5.17 — her photos' seam (`agents/photo.py`): the `ФОТО:` / `СЕЛФІ:` line cut from her answer, the English request
built from her words and her moment, her faces picked, and the image call with one retry — a block or a second
failure a reason, never a crash (google-genai mocked; no network; made-up descriptions)."""

import asyncio
import logging
from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from google.genai import errors

from agents.photo import (
    SELFIE_HEAD,
    SELFIE_TAIL,
    STYLE,
    Made,
    Moment,
    PhotoMaker,
    Shot,
    age_on,
    load_faces,
    load_look,
    photo_request,
    pick_faces,
    selfie_line,
    split_photo,
    strip_notes,
)
from agents.roster import RosterError, parse_member

SECRET = "опис-5170"
EVENING = Moment(datetime(2026, 10, 31, 21, 15, tzinfo=ZoneInfo("Europe/Kyiv")), "хмарно, +8, дрібний дощ")


def scripted(*values):
    it = iter(values)
    return lambda: next(it)


def test_the_marker_lines_are_cut_and_the_last_one_names_the_shot():
    assert split_photo("Ось, дивись!\nСЕЛФІ: я під куполом, вночі") == (
        "Ось, дивись!", Shot("selfie", "я під куполом, вночі"))
    assert split_photo("Тримай 🙂 ФОТО: чашка на підвіконні") == ("Тримай 🙂", Shot("photo", "чашка на підвіконні"))
    assert split_photo("ну от\n- фото — «скелі в Тустані»") == ("ну от", Shot("photo", "скелі в Тустані"))
    two = split_photo("перше\nФОТО: чашка\nдруге\nСЕЛФІ: я на скелі")
    assert two == ("перше\nдруге", Shot("selfie", "я на скелі"))                   # the last one counts
    assert split_photo("СЕЛФІ: [laughs] я з кавою")[1] == Shot("selfie", "я з кавою")  # no voice tag in a shot
    assert split_photo("Ось.\nФОТО:   ") == ("Ось.", Shot("photo", ""))             # an empty one: no description
    assert split_photo("Я не люблю фотографуватися, чесно.") == ("Я не люблю фотографуватися, чесно.", None)
    assert split_photo("Фото з Единбурга в мене десь є") == ("Фото з Единбурга в мене десь є", None)  # no colon


def test_her_kept_note_echoed_anywhere_in_any_case_is_cut_and_names_the_shot():
    # v5.17 review #2: her line is kept as «…\n[селфі: …]»; Gemini may echo it inside a line, in lower case
    assert split_photo("Ось я знову [селфі: я на балконі] 🙂") == ("Ось я знову 🙂", Shot("selfie", "я на балконі"))
    assert split_photo("Дивись\n[Фото: чашка на підвіконні]") == ("Дивись", Shot("photo", "чашка на підвіконні"))
    assert split_photo("ну [фото] і що") == ("ну [фото] і що", None)                  # no colon: not a note


def test_without_the_archive_geminis_history_has_no_kept_note_either(tmp_path, monkeypatch):
    """Code review v5.23 #4: without the archive (or when it fails) Gemini reads her own history — the notes cut out
    there too, a line that held only one gone, a closed line still left out."""
    from tests.test_archive import kira
    agent = kira(tmp_path, monkeypatch)
    agent.archive = None
    agent.private_history = [("Ich", "Покажи себе"), ("Кіра", "Ось я\n[селфі: ...]"), ("Кіра", "[фото: ...]"),
                             ("Ich", "Закрите"), ("Ich", "Гарна")]
    agent._closed = {("Ich", "Закрите")}
    assert agent.gemini_history() == [("Ich", "Покажи себе"), ("Кіра", "Ось я"), ("Ich", "Гарна")]


def test_an_older_lines_kept_note_is_cut_out_and_echoed_names_an_empty_shot():
    """v5.23 (the owner, 2026-11-03: «забери з тексту взагалі селфі чи фото воно в історії не потрібно»): no note is
    kept any more; an older line's note — the photo's, the кружечок's, the clip's — is cut out before a prompt reads
    it, a line that held only one is no line, and a line with none stays exactly as it is."""
    assert strip_notes("Ось я\n[селфі: ...]") == "Ось я" and strip_notes("[кружечок: ...]") == ""
    assert strip_notes("Тримай [фото: ...] 🙂\n[відео: ...]") == "Тримай 🙂"
    assert strip_notes("рядок без нотатки ") == "рядок без нотатки " and strip_notes("ну [фото] і що") == "ну [фото] і що"
    # code review v5.21 #1: cut, and a shot with no description — her words may promise it
    assert split_photo("Ось я знову [селфі: ...] 🙂") == ("Ось я знову 🙂", Shot("selfie", ""))
    assert split_photo("Дивись\n[фото: …]") == ("Дивись", Shot("photo", ""))
    assert split_photo("Тримай\nСЕЛФІ: ...") == ("Тримай", Shot("selfie", ""))
    assert split_photo("Ось [селфі: ...]\nСЕЛФІ: я на балконі")[1] == Shot("selfie", "я на балконі")  # described wins
    assert split_photo("СЕЛФІ: я на балконі\n[фото: ...]")[1] == Shot("selfie", "я на балконі")


def test_the_request_holds_her_words_her_moment_and_the_look_and_the_face_only_for_a_selfie():
    selfie = photo_request(Shot("selfie", f"я на балконі з біноклем {SECRET}"), EVENING)
    photo = photo_request(Shot("photo", f"полиця склеєних чашок {SECRET}"), EVENING)
    for request in (selfie, photo):
        assert SECRET in request and STYLE in request and "evening in autumn, around 21:15, in Lviv" in request
        assert "хмарно, +8, дрібний дощ" in request
        for word in ("ранок", "вечір", "осінь", "ніч"):                              # the template is English
            assert word not in request.replace("хмарно, +8, дрібний дощ", "")
    assert SELFIE_HEAD in selfie and SELFIE_TAIL in selfie and "not the clothes of the reference photos" in selfie
    assert SELFIE_HEAD not in photo and "Nobody's face" in photo
    # v6.2: her own line — her age and her look — when the maker passes it; a photo never carries it
    who = selfie_line(date(2003, 3, 9), "She never wears makeup: a bare, natural face.", EVENING.when.date())
    assert "She is 23." in photo_request(Shot("selfie", "я"), EVENING, who=who)
    assert "never wears makeup: a bare, natural face" in photo_request(Shot("selfie", "я"), EVENING, who=who)
    assert "makeup" not in photo_request(Shot("photo", "чашка"), EVENING, who=who)
    assert "weather" not in photo_request(Shot("photo", "чашка"), Moment(EVENING.when))


def test_her_faces_are_the_folders_own_images_and_a_selfie_takes_kira_png_and_three_drawn(tmp_path):
    folder = tmp_path / "kira.face"
    (folder / "places").mkdir(parents=True)
    for name in ("kira.png", "a.png", "b.jpg", "c.jpeg", "d.png", "notes.txt"):
        (folder / name).write_bytes(name.encode())
    (folder / "places" / "cup.jpg").write_bytes(b"cup")
    faces = load_faces(folder)
    assert [f[0] for f in faces] == ["a.png", "b.jpg", "c.jpeg", "d.png", "kira.png"]  # never places/, never text
    assert faces[1][2] == "image/jpeg" and faces[0][2] == "image/png"
    picked = pick_faces(faces, scripted(0.0, 0.99, 0.5), "kira.png")
    assert [f[0] for f in picked] == ["kira.png", "a.png", "d.png", "c.jpeg"]
    assert [f[0] for f in pick_faces(faces[:2], scripted(0.0), "kira.png")] == ["a.png", "b.jpg"]  # none: the first
    # v6.2: the main photo is the person's own — another's folder never puts kira.png first
    assert pick_faces(faces, scripted(0.0, 0.0, 0.0), "ustyna.png")[0][0] == "a.png"
    assert pick_faces(faces, scripted(0.0, 0.0, 0.0))[0][0] == "a.png"
    assert load_faces(tmp_path / "missing") == [] and load_faces(None) == [] and pick_faces([], scripted()) == []



def test_her_age_on_the_shots_day_counts_whole_years_from_her_birth_date():
    birth = date(2004, 11, 1)
    assert age_on(birth, date(2026, 10, 31)) == 21                                  # the day before her birthday
    assert age_on(birth, date(2026, 11, 1)) == 22 and age_on(birth, date(2026, 11, 7)) == 22
    assert age_on(date(2004, 2, 29), date(2025, 2, 28)) == 20 and age_on(None, date(2026, 11, 7)) is None


def test_the_selfie_line_is_hers_her_age_and_her_look_between_the_fixed_head_and_tail():
    look = "Her eyes are light grey. She never wears makeup."
    line = selfie_line(date(2004, 11, 1), look, date(2026, 11, 7))
    assert line == f"{SELFIE_HEAD} She is 22. {look} {SELFIE_TAIL}"
    assert selfie_line(None, "", date(2026, 11, 7)) == f"{SELFIE_HEAD} {SELFIE_TAIL}"   # no chart, no look: neither
    assert selfie_line(None, look, date(2026, 11, 7)) == f"{SELFIE_HEAD} {look} {SELFIE_TAIL}"


def test_her_look_file_is_its_lines_without_comments_and_a_missing_or_empty_one_is_none(tmp_path):
    path = tmp_path / "ustyna.look.md"
    path.write_text("# her look, for the image model\nShe is Ukrainian.\n\n  Her eyes are light grey.  \n",
                    encoding="utf-8")
    assert load_look(path) == "She is Ukrainian. Her eyes are light grey."
    (tmp_path / "empty.look.md").write_text("# nothing\n\n", encoding="utf-8")
    assert load_look(tmp_path / "empty.look.md") == "" and load_look(tmp_path / "missing.look.md") == ""
    assert load_look(None) == ""


def test_a_makers_selfie_is_its_persons_own_main_face_age_and_look():
    models = Models(image())
    faces = [(n, n.encode(), "image/png") for n in ("a.png", "b.png", "kira.png", "ustyna.png")]
    photos = PhotoMaker(SimpleNamespace(aio=SimpleNamespace(models=models)), faces=faces, rng=scripted(0.0, 0.0, 0.0),
                        main_face="ustyna.png", birth=date(2004, 11, 1), look="Her eyes are light grey.")
    asyncio.run(photos.make(Shot("selfie", "я з гітарою"), EVENING))
    contents = models.calls[0][1]
    assert contents[0].inline_data.data == b"ustyna.png"                             # her main face first
    assert "She is 21." in contents[-1] and "Her eyes are light grey." in contents[-1]  # 2026-10-31: still 21

class Models:
    """The SDK's `aio.models`: answers or raises in turn; keeps each call's contents and config."""

    def __init__(self, *outcomes):
        self.outcomes, self.calls = list(outcomes), []

    async def generate_content(self, model, contents, config):
        self.calls.append((model, contents, config))
        out = self.outcomes.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


def image(data=b"JPEG", mime="image/jpeg"):
    part = SimpleNamespace(inline_data=SimpleNamespace(data=data, mime_type=mime))
    return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))],
                           usage_metadata=SimpleNamespace(prompt_token_count=4600, candidates_token_count=1500),
                           prompt_feedback=None)


def blocked(prompt=True):
    feedback = SimpleNamespace(block_reason=SimpleNamespace(name="PROHIBITED_CONTENT")) if prompt else None
    return SimpleNamespace(candidates=[] if prompt else [SimpleNamespace(content=SimpleNamespace(parts=[]))],
                           usage_metadata=None, prompt_feedback=feedback)


def maker(*outcomes, faces=None):
    models = Models(*outcomes)
    seen = []
    sink = lambda kind, model, usage, ok, **kw: seen.append((kind, model, ok, {k: v for k, v in kw.items() if k != "latency_ms"}))
    faces = faces if faces is not None else [(n, n.encode(), "image/png") for n in ("kira.png", "a", "b", "c", "d")]
    return PhotoMaker(SimpleNamespace(aio=SimpleNamespace(models=models)), faces=faces, sink=sink,
                      rng=scripted(0.0, 0.0, 0.0)), models, seen


def server_error():
    return errors.ServerError(503, {"error": {"code": 503, "message": "Deadline expired", "status": "UNAVAILABLE"}})


def test_a_selfie_takes_four_faces_and_a_photo_none_and_each_call_is_a_photo_usage_line(caplog):
    caplog.set_level(logging.INFO)
    photos, models, seen = maker(image(), image(b"PNG", "image/png"))
    made = asyncio.run(photos.make(Shot("selfie", f"я з кавою {SECRET}"), EVENING))
    assert made == Made(b"JPEG", "image/jpeg", "ok")
    model, contents, config = models.calls[0]
    assert model == "gemini-nano-banana-2.1" and len(contents) == 5 and SECRET in contents[-1]
    assert config.response_modalities == ["IMAGE"] and config.image_config.aspect_ratio == "3:4"
    assert config.image_config.image_size == "1K"
    assert asyncio.run(photos.make(Shot("photo", "чашка"), EVENING)) == Made(b"PNG", "image/png", "ok")
    assert len(models.calls[1][1]) == 1                                               # the prompt alone
    assert seen == [("photo", "gemini-nano-banana-2.1", True, {})] * 2
    assert SECRET not in caplog.text


def test_one_retry_on_a_server_error_then_a_reason_never_a_crash(caplog):
    caplog.set_level(logging.INFO)
    photos, models, seen = maker(server_error(), image())
    assert asyncio.run(photos.make(Shot("photo", SECRET), EVENING)).why == "ok" and len(models.calls) == 2
    photos, models, seen = maker(server_error(), TimeoutError())
    assert asyncio.run(photos.make(Shot("photo", SECRET), EVENING)) == Made(None, why="failed")
    assert len(models.calls) == 2 and [s[2] for s in seen] == [False, False]
    photos, models, _ = maker(RuntimeError(SECRET))
    assert asyncio.run(photos.make(Shot("photo", "чашка"), EVENING)).why == "failed" and len(models.calls) == 1
    assert "photo: failed (TimeoutError)" in caplog.text and SECRET not in caplog.text


def test_a_block_or_no_image_is_blocked_and_counted_with_its_stage():
    photos, models, seen = maker(blocked(prompt=True))
    assert asyncio.run(photos.make(Shot("selfie", "я"), EVENING)) == Made(None, why="blocked")
    assert seen == [("photo", "gemini-nano-banana-2.1", False, {"blocked": "prompt"})] and len(models.calls) == 1
    photos, _, seen = maker(blocked(prompt=False))
    assert asyncio.run(photos.make(Shot("photo", "чашка"), EVENING)).why == "blocked"
    assert seen[0][3] == {"blocked": "answer"}
    photos, models, _ = maker(image(), faces=[])                                     # no faces: no selfie at all
    assert asyncio.run(photos.make(Shot("selfie", "я"), EVENING)).why == "blocked" and models.calls == []


def test_photos_are_a_persons_capability_that_needs_her_telegram_bot():
    # v5.17: her photos go only through Telegram
    base = {"name": "Кіра", "user_id": "@kira:agora.lan"}
    assert parse_member("kira", {**base, "capabilities": {"private": True, "telegram": True, "photos": True}},
                        "kira.toml").can("photos")
    with pytest.raises(RosterError, match="'photos' needs 'telegram' on the same member"):
        parse_member("kira", {**base, "capabilities": {"private": True, "photos": True}}, "kira.toml")
    with pytest.raises(RosterError, match="'photos' belongs to the persona type only"):
        parse_member("kit", {"name": "Кіт", "user_id": "@kit:agora.lan", "type": "creature",
                             "capabilities": {"photos": True}}, "kit.toml")


@pytest.mark.canon
def test_every_look_file_in_the_canon_names_no_model_or_bot_and_kiras_keeps_her_no_makeup_rule():
    """v6.2: the look files are private canon (`agents/canon/<localpart>.look.md`), read into a selfie's request — the
    human-belief scan covers them, and Кіра's carries v5.25's rule, so her selfie is as before."""
    from pathlib import Path

    from agents.logic import BANNED_RE
    looks = sorted(Path("agents/canon").glob("*.look.md"))
    assert {p.name for p in looks} >= {"kira.look.md", "ustyna.look.md"}
    for path in looks:
        assert not BANNED_RE.search(path.read_text(encoding="utf-8")), path.name
    assert "never wears makeup: a bare, natural face" in load_look(Path("agents/canon/kira.look.md"))
