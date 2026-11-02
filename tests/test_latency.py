"""v5.22 — the call's time: every client times its own call on its monotonic clock, and its usage line holds
`latency_ms` — an ok, a failed and a blocked call alike; a video's first frame is a `frame` line, her photo a `photo`
line (google-genai, NovelAI, fal, ElevenLabs and the Claude SDK mocked; no network; no text)."""
import asyncio
from types import SimpleNamespace

from agents import llm as llm_mod
from agents.llm import EMBED_DIM, GeminiClient
from agents.photo import Shot
from agents.speech import voice_message
from agents.usage import usage_line
from tests.test_claude_sdk import INIT_OK, AssistantMessage, FakeSDK, TextBlock, responder, result, run
from tests.test_fallback import FakeResponse, stream
from tests.test_fallback import client as backup
from tests.test_photo import EVENING, blocked, image, maker, server_error
from tests.test_video import clips, done_by_uri, finished, interaction, notes, submitted


class Clock:
    """A monotonic clock that moves on `step` seconds at each read: a call read twice took `step` seconds."""

    def __init__(self, step: float):
        self.t, self.step = 100.0, step

    def __call__(self) -> float:
        self.t += self.step
        return self.t


class Models:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)

    async def generate_content(self, model, contents, config):
        out = self.outcomes.pop(0)
        if isinstance(out, Exception):
            raise out
        return out

    async def embed_content(self, model, contents, config):
        return SimpleNamespace(embeddings=[SimpleNamespace(values=[0.1] * EMBED_DIM) for _ in contents], metadata=None)


def gemini(monkeypatch, *outcomes):
    monkeypatch.setattr(llm_mod.genai, "Client", lambda: SimpleNamespace(aio=SimpleNamespace(models=Models(*outcomes))))
    seen = []
    client = GeminiClient(sink=lambda kind, model, meta, ok, **kw: seen.append((kind, ok, kw.get("latency_ms"),
                                                                               kw.get("blocked"))))
    client._mono = Clock(1.5)
    return client, seen


def answer(text="Привіт"):
    return SimpleNamespace(text=text, candidates=[SimpleNamespace(finish_reason=None)], usage_metadata=None,
                           prompt_feedback=None)


def prompt_block():
    return SimpleNamespace(text="", candidates=[], usage_metadata=None,
                           prompt_feedback=SimpleNamespace(block_reason=SimpleNamespace(name="PROHIBITED_CONTENT"),
                                                           safety_ratings=None))


def test_a_gemini_call_holds_its_time_ok_failed_or_blocked(monkeypatch):
    client, seen = gemini(monkeypatch, answer(), RuntimeError("down"), prompt_block())
    for _ in range(3):
        asyncio.run(client.generate("Ich: привіт", "КАНОН", kind="private"))
    asyncio.run(client.embed(["рядок"]))
    assert seen == [("private", True, 1500, None), ("private", False, 1500, None),
                    ("private", False, 1500, "prompt"), ("embed", True, 1500, None)]


def test_the_agents_sink_writes_the_time_into_its_line():
    line = usage_line("2026-11-02T12:00:00+02:00", "kira", "private", "m", None, True, latency_ms=1500)
    assert line["latency_ms"] == 1500 and "Привіт" not in str(line)


def test_her_photo_and_a_videos_frame_each_hold_their_time_and_their_own_kind():
    pm, _, _ = maker(image(), server_error(), image(), blocked())
    got = []
    pm._sink = lambda kind, model, usage, ok, **kw: got.append((kind, ok, kw.get("latency_ms"), kw.get("blocked")))
    pm._mono = Clock(2.0)
    asyncio.run(pm.make(Shot("photo", "чашка"), EVENING))
    asyncio.run(pm.make(Shot("photo", "кадр"), EVENING, "1:1", "a frame", kind="frame"))  # a retry: two calls
    asyncio.run(pm.make(Shot("photo", "чашка"), EVENING))
    assert got == [("photo", True, 2000, None), ("frame", False, 2000, None), ("frame", True, 2000, None),
                   ("photo", False, 2000, "prompt")]


def test_a_clip_and_a_kruzhechok_hold_their_time_from_the_submit_to_the_result(monkeypatch):
    clip, _, _, _ = clips([interaction("queued")], [interaction("in_progress"), done_by_uri()])
    got = []
    clip._sink = lambda kind, model, usage, ok, **kw: got.append((kind, ok, kw.get("latency_ms")))
    clip._mono = Clock(30.0)
    asyncio.run(clip.make(Shot("clip", "море"), EVENING, b"FRAME", "image/jpeg"))
    note, _, _ = notes(monkeypatch, submitted(), *finished())
    note._sink = lambda model, video_ms, ok, blocked, **kw: got.append(("video_note", ok, kw.get("latency_ms")))
    note._mono = Clock(80.0)
    asyncio.run(note.make(b"F", "image/png", b"M"))
    assert got == [("video", True, 30000), ("video_note", True, 80000)]


def test_a_backup_call_holds_the_whole_streams_time_ok_or_failed(monkeypatch):
    got = []
    for response in (FakeResponse(200, stream("Привіт", ", сонце.")), FakeResponse(403, [])):
        llm, _ = backup(monkeypatch, response)
        llm._sink = lambda kind, model, ok, **kw: got.append((kind, ok, kw.get("latency_ms")))
        llm._mono = Clock(6.0)
        asyncio.run(llm.reply("Ich: привіт", "КАНОН", 400, "private"))
    assert got == [("private", True, 6000), ("private", False, 6000)]


def test_a_claude_call_holds_its_time_from_the_query_to_its_result(tmp_path):
    got = []
    r, _ = responder(tmp_path, FakeSDK(INIT_OK, AssistantMessage(content=[TextBlock(text="Так.")]), result()))
    r.usage_sink = lambda *a, **k: got.append((a[3], k.get("latency_ms")))
    r._mono = Clock(12.0)
    run(r)
    r, _ = responder(tmp_path, FakeSDK(raises=RuntimeError("cli died")))
    r.usage_sink = lambda *a, **k: got.append((a[3], k.get("latency_ms")))
    r._mono = Clock(12.0)
    run(r)
    assert got == [(True, 12000), (False, 12000)]


def test_a_voice_message_reports_its_synthesis_time():
    class TTS:
        async def synth(self, text):
            return None  # a failed synthesis still reports its time

    got = []
    content, why = asyncio.run(voice_message(SimpleNamespace(upload=None), TTS(), "привіт", "a.ogg",
                                             on_synth=lambda ok, ms: got.append((ok, ms)), mono=Clock(0.9)))
    assert (content, why) == (None, "tts failed") and got == [(False, 900)]
