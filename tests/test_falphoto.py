"""v6.5 (AGORA-233) — her photos on fal.ai: Seedream 4 Edit for a selfie with her faces, text-to-image for a photo
without her, the safety checker off; a flagged, black or empty photo is blocked. fal and ffmpeg are faked — no test
reaches the network; the request is a made-up line."""

import asyncio
import logging

from agents import falphoto as fp
from agents import video as vd
from agents.falphoto import EDIT_MODEL, TEXT_MODEL, FalPhotoMaker, is_black, model_for, request_body
from agents.photo import Made, Shot
from tests.test_video import FILES, SIGNED, FakeProc, FakeResponse, FakeSession

KEY = "fal-key-6500"
PROMPT = "A made-up request: a girl with a cup of tea by a window, morning light."
CDN = "https://v3b.fal.media/files/out/photo.jpg"
STATUS = f"https://queue.fal.run/{EDIT_MODEL}/requests/p1/status"
RESULT = f"https://queue.fal.run/{EDIT_MODEL}/requests/p1"
CANCEL = f"https://queue.fal.run/{EDIT_MODEL}/requests/p1/cancel"
FACES = [("ustyna.png", b"MAIN", "image/png"), ("b.png", b"B", "image/png"), ("c.jpg", b"C", "image/jpeg"),
         ("d.png", b"D", "image/png"), ("e.png", b"E", "image/png")]
SELFIE = Shot("selfie", "я з чаєм біля вікна")
PHOTO = Shot("photo", "чашка чаю на підвіконні")


async def no_sleep(_s):
    return None


def submitted():
    return FakeResponse(200, {"request_id": "p1", "status_url": STATUS, "response_url": RESULT, "cancel_url": CANCEL})


def done(result=None, body=b"JPEG-photo"):
    result = result if result is not None else {"images": [{"url": CDN, "content_type": "image/jpeg"}], "seed": 7}
    return [FakeResponse(200, {"status": "IN_PROGRESS"}), FakeResponse(200, {"status": "COMPLETED"}),
            FakeResponse(200, result), FakeResponse(200, body=body)]


def maker(monkeypatch, *replies, black=False, faces=FACES):
    seen, sinks = [], []
    queue = list(replies)
    FakeSession.uploads, FakeSession.fail_uploads = [], 0
    monkeypatch.setattr(vd, "ClientSession", lambda **kw: FakeSession(queue, seen))

    async def black_check(_image, timeout_s=30.0):
        return black

    monkeypatch.setattr(fp, "is_black", black_check)
    sink = lambda model, images, ok, blocked, **kw: sinks.append((model, images, ok, blocked))
    return FalPhotoMaker(KEY, faces, "ustyna.png", sink, rng=lambda: 0.0, sleep=no_sleep), seen, sinks


def test_the_model_and_the_body_by_the_shot():
    assert (model_for(SELFIE), model_for(PHOTO)) == (EDIT_MODEL, TEXT_MODEL)
    body = request_body(PROMPT, ["u1", "u2"])
    assert body == {"prompt": PROMPT, "image_size": {"width": 1152, "height": 1536}, "num_images": 1,
                    "enable_safety_checker": False, "image_urls": ["u1", "u2"]}
    assert "image_urls" not in request_body(PROMPT, [])


def test_a_selfie_goes_to_the_edit_model_with_her_four_faces_and_the_key_only_on_fals_hosts(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    photos, seen, sinks = maker(monkeypatch, submitted(), *done())
    made = asyncio.run(photos.make(SELFIE, PROMPT))
    assert made == Made(b"JPEG-photo", "image/jpeg", "ok")
    method, url, _, body = seen[0]
    assert (method, url) == ("POST", f"https://queue.fal.run/{EDIT_MODEL}")
    assert body["enable_safety_checker"] is False and body["prompt"] == PROMPT
    assert body["image_size"] == {"width": 1152, "height": 1536}
    assert body["image_urls"] == [FILES + "frame.png", FILES + "frame.png", FILES + "frame.jpg", FILES + "frame.png"]
    puts = [u for m, u, *_ in FakeSession.uploads if m == "PUT"]
    assert len(puts) == 4 and all(u.startswith(SIGNED) for u in puts)          # her main face and three drawn
    assert all(h.get("Authorization") is None for m, _, h, _ in FakeSession.uploads if m == "PUT")
    assert all(s[2]["Authorization"] == f"Key {KEY}" for s in seen[:4]) and seen[4][2] is None  # never to the file
    assert sinks == [(EDIT_MODEL, 1, True, None)]
    for secret in (KEY, CDN, STATUS, FILES, SIGNED, PROMPT):
        assert secret not in caplog.text
    assert KEY not in repr(photos)


def test_a_photo_without_her_goes_to_text_to_image_with_no_face(monkeypatch):
    photos, seen, sinks = maker(monkeypatch, submitted(), *done())
    assert asyncio.run(photos.make(PHOTO, PROMPT)).why == "ok"
    assert seen[0][1] == f"https://queue.fal.run/{TEXT_MODEL}" and "image_urls" not in seen[0][3]
    assert FakeSession.uploads == [] and sinks == [(TEXT_MODEL, 1, True, None)]


def test_a_selfie_without_faces_is_blocked_and_never_asked(monkeypatch):
    photos, seen, sinks = maker(monkeypatch, faces=[])
    assert asyncio.run(photos.make(SELFIE, PROMPT)) == Made(None, why="blocked")
    assert seen == [] and sinks == []


def test_a_flagged_a_black_and_an_empty_photo_are_blocked(monkeypatch):
    flagged = {"images": [{"url": CDN}], "has_nsfw_concepts": [True]}
    photos, _, sinks = maker(monkeypatch, submitted(), *done(flagged))
    assert asyncio.run(photos.make(SELFIE, PROMPT)) == Made(None, why="blocked")
    assert sinks == [(EDIT_MODEL, 1, False, "answer")]                              # made, so paid: never sent
    photos, _, sinks = maker(monkeypatch, submitted(), *done(), black=True)
    assert asyncio.run(photos.make(SELFIE, PROMPT)).why == "blocked" and sinks == [(EDIT_MODEL, 1, False, "answer")]
    photos, _, sinks = maker(monkeypatch, submitted(), *done({"images": []})[:3])
    assert asyncio.run(photos.make(SELFIE, PROMPT)).why == "blocked" and sinks == [(EDIT_MODEL, None, False, "answer")]
    photos, _, _ = maker(monkeypatch, submitted(), *done(), black=None)               # ffmpeg failed: not black
    assert asyncio.run(photos.make(SELFIE, PROMPT)).why == "ok"


def test_one_retry_before_the_job_is_accepted_never_after(monkeypatch):
    photos, seen, sinks = maker(monkeypatch, FakeResponse(503), submitted(), *done())
    assert asyncio.run(photos.make(PHOTO, PROMPT)).why == "ok"
    assert [s[2] for s in sinks] == [False, True] and [m for m, *_ in seen].count("POST") == 2
    photos, seen, sinks = maker(monkeypatch, FakeResponse(502), FakeResponse(503))
    assert asyncio.run(photos.make(PHOTO, PROMPT)) == Made(None, why="failed") and len(sinks) == 2
    photos, seen, _ = maker(monkeypatch, submitted(), FakeResponse(400, {"detail": "bad"}))
    assert asyncio.run(photos.make(PHOTO, PROMPT)).why == "failed"
    assert [m for m, *_ in seen].count("POST") == 1                                # accepted: never sent again


def test_a_timeout_after_the_job_is_accepted_cancels_it(monkeypatch):
    photos, seen, sinks = maker(monkeypatch, submitted(), *[FakeResponse(200, {"status": "IN_QUEUE"})] * 50,
                                FakeResponse(200, {}))
    photos._timeout_s = 0.05

    async def slow(_s):
        await asyncio.sleep(0.01)

    photos._sleep = slow
    assert asyncio.run(photos.make(PHOTO, PROMPT)) == Made(None, why="failed")
    assert any(u == CANCEL for _, u, *_ in seen) and sinks == [(TEXT_MODEL, None, False, None)]


def test_a_black_photo_is_found_by_ffmpegs_grey_frame(monkeypatch):
    seen = {}

    def proc(out):
        async def fake_exec(*argv, **kw):
            seen["argv"] = argv
            return FakeProc(0, out)
        return fake_exec

    monkeypatch.setattr(vd.asyncio, "create_subprocess_exec", proc(bytes([0] * 64)))
    assert asyncio.run(is_black(b"JPEG")) is True and seen["argv"] == fp.FFMPEG_GREY
    monkeypatch.setattr(vd.asyncio, "create_subprocess_exec", proc(bytes([120] * 64)))
    assert asyncio.run(is_black(b"JPEG")) is False

    async def broken(*argv, **kw):
        return FakeProc(1, b"")

    monkeypatch.setattr(vd.asyncio, "create_subprocess_exec", broken)
    assert asyncio.run(is_black(b"JPEG")) is None
