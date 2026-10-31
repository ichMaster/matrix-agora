"""v5.17 — her photos' seam (`agents/photo.py`): the `ФОТО:` / `СЕЛФІ:` line cut from her answer, the English request
built from her words and her moment, her faces picked, and the image call with one retry — a block or a second
failure a reason, never a crash (google-genai mocked; no network; made-up descriptions)."""

import asyncio
import logging
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from google.genai import errors

from agents.photo import (
    MAIN_FACE,
    SELFIE,
    STYLE,
    Made,
    Moment,
    PhotoMaker,
    Shot,
    load_faces,
    photo_request,
    pick_faces,
    split_photo,
)

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
    assert split_photo("Ось.\nФОТО:   ") == ("Ось.", None)                          # an empty one names nothing
    assert split_photo("Я не люблю фотографуватися, чесно.") == ("Я не люблю фотографуватися, чесно.", None)
    assert split_photo("Фото з Единбурга в мене десь є") == ("Фото з Единбурга в мене десь є", None)  # no colon


def test_the_request_holds_her_words_her_moment_and_the_look_and_the_face_only_for_a_selfie():
    selfie = photo_request(Shot("selfie", f"я на балконі з біноклем {SECRET}"), EVENING)
    photo = photo_request(Shot("photo", f"полиця склеєних чашок {SECRET}"), EVENING)
    for request in (selfie, photo):
        assert SECRET in request and STYLE in request and "evening in autumn, around 21:15, in Lviv" in request
        assert "хмарно, +8, дрібний дощ" in request
        for word in ("ранок", "вечір", "осінь", "ніч"):                              # the template is English
            assert word not in request.replace("хмарно, +8, дрібний дощ", "")
    assert SELFIE in selfie and "not the clothes of the reference photos" in selfie
    assert SELFIE not in photo and "Nobody's face" in photo
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
    picked = pick_faces(faces, scripted(0.0, 0.99, 0.5))
    assert [f[0] for f in picked] == [MAIN_FACE, "a.png", "d.png", "c.jpeg"]
    assert [f[0] for f in pick_faces(faces[:2], scripted(0.0))] == ["a.png", "b.jpg"]  # no kira.png: the first
    assert load_faces(tmp_path / "missing") == [] and load_faces(None) == [] and pick_faces([], scripted()) == []


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
    sink = lambda kind, model, usage, ok, **kw: seen.append((kind, model, ok, kw))
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
