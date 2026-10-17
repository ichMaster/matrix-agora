"""v5.1 — the voice: text to speech through ElevenLabs, an Element voice message through ffmpeg.

Ported from Lumi's `voice/tts.py` (the owner, 2026-10-13: the speech services are Lumi's): the REST endpoint her
streaming twin calls, asking for raw PCM, so the duration and the waveform are arithmetic before the Opus encode.
Every external step returns None on failure, logged by its type, HTTP status or exit code — never the key, never
the text. Pure helpers build the `m.audio` content Element shows as a voice message (MSC3245 + MSC1767).
"""

from __future__ import annotations

import array
import asyncio
import logging
import re
import sys
import urllib.parse

import aiohttp

log = logging.getLogger("agent.voice")

TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=pcm_24000"
TTS_MODEL = "eleven_turbo_v2_5"  # the owner's choice: multilingual, fast; 0.5 credit a character
RATE = 24_000                    # pcm_24000: signed 16-bit little-endian, mono
VOICE_SETTINGS = {"stability": 0.5, "similarity_boost": 0.75, "style": 0.4}  # Lumi's defaults
TIMEOUT_S = 60
VOICE_ID_RE = re.compile(r"^[A-Za-z0-9]{10,40}$")
WAVEFORM_POINTS = 100
WAVEFORM_MAX = 1024              # Element draws 0..1024
FFMPEG = ("ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "s16le", "-ar", str(RATE), "-ac", "1",
          "-i", "pipe:0", "-c:a", "libopus", "-b:a", "32k", "-application", "voip", "-f", "ogg", "pipe:1")


class ElevenLabsTTS:
    def __init__(self, api_key: str, voice_id: str, model: str = TTS_MODEL) -> None:
        self._key = api_key
        self.voice_id = voice_id
        self.model = model

    async def synth(self, text: str) -> bytes | None:
        """The text spoken in Ukrainian as PCM (s16le, 24 kHz, mono); None on any failure."""
        if not VOICE_ID_RE.match(self.voice_id or ""):
            log.error("tts: the voice id is malformed")
            return None
        url = TTS_URL.format(voice=urllib.parse.quote(self.voice_id, safe=""))
        body = {"text": text, "model_id": self.model, "language_code": "uk", "voice_settings": VOICE_SETTINGS}
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=TIMEOUT_S)) as session, \
                    session.post(url, json=body, headers={"xi-api-key": self._key, "Accept": "audio/*"}) as resp:
                if resp.status != 200:
                    await resp.read()
                    log.error("tts failed: HTTP %s", resp.status)
                    return None
                pcm = await resp.read()
        except Exception as exc:  # noqa: BLE001 — any network failure means a text-only digest
            log.error("tts failed: %s", type(exc).__name__)
            return None
        if len(pcm) < 2:
            log.error("tts returned no audio")
            return None
        return pcm[: len(pcm) - len(pcm) % 2]


async def encode_opus(pcm: bytes, timeout_s: float = 60.0) -> bytes | None:
    """PCM → OGG/Opus (32 kb/s, voice) through ffmpeg's fixed argv; None on any failure (logged by its code)."""
    try:
        proc = await asyncio.create_subprocess_exec(*FFMPEG, stdin=asyncio.subprocess.PIPE,
                                                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    except OSError as exc:
        log.error("encode failed: %s", type(exc).__name__)
        return None
    try:
        out, _ = await asyncio.wait_for(proc.communicate(input=pcm), timeout=timeout_s)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        log.error("encode timed out after %.0fs", timeout_s)
        return None
    if proc.returncode != 0 or not out:
        log.error("encode failed: ffmpeg exit %s", proc.returncode)
        return None
    return out


def duration_ms(pcm: bytes, rate: int = RATE) -> int:
    return len(pcm) // 2 * 1000 // rate


def waveform(pcm: bytes, points: int = WAVEFORM_POINTS) -> list[int]:
    """The peak of each of `points` equal stretches, scaled to 0..1024 against the loudest — Element's waveform."""
    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) - len(pcm) % 2])
    if sys.byteorder == "big":
        samples.byteswap()
    if not samples:
        return [0] * points
    n = len(samples)
    peaks = []
    for i in range(points):
        chunk = samples[i * n // points: max((i + 1) * n // points, i * n // points + 1)]
        peaks.append(max((abs(s) for s in chunk), default=0))
    top = max(peaks)
    return [round(p * WAVEFORM_MAX / top) if top else 0 for p in peaks]


def voice_content(mxc_url: str, size: int, duration: int, wave: list[int], text: str, filename: str) -> dict:
    """An `m.audio` event Element shows as a voice message: the voice flag, the duration and the waveform; the text
    in `body` (a caption where `filename` differs) and as MSC1767 text."""
    return {
        "msgtype": "m.audio",
        "body": text,
        "filename": filename,
        "url": mxc_url,
        "info": {"mimetype": "audio/ogg", "size": size, "duration": duration},
        "org.matrix.msc1767.audio": {"duration": duration, "waveform": wave},
        "org.matrix.msc3245.voice": {},
        "org.matrix.msc1767.text": text,
    }
