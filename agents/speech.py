"""v5.3 — the speakers' voices: the decisions (pure) and the shared voice pipeline (ARCHITECTURE §Voice messages).

Every voiced line is first a checked text line; voicing adds an Element voice message before the same text, never
replaces it — the other agents read only text. The decisions are pure; the pipeline returns why a line could not be
voiced and never logs a word.
"""

from __future__ import annotations

import io
import logging
from collections.abc import Callable, Iterable

from nio import UploadResponse

from agents.turns import uniform
from agents.voice import duration_ms, encode_opus, voice_content, waveform

log = logging.getLogger("agent.speech")


def voice_due(answers_owner_voice: bool, event_key: str, localpart: str, p: float) -> bool:
    """Whether a line goes out in voice: always when it answers the owner's voice; otherwise its own deterministic
    draw against the agent's share (`VOICE_REPLY_P`)."""
    if answers_owner_voice:
        return True
    return p > 0 and uniform(event_key or "", "voice:" + localpart) < p


def voiceable(text: str) -> bool:
    """A line a voice can say: not empty, and not an action purr (`*потягується*`) — the stars' word read aloud."""
    t = (text or "").strip()
    return bool(t) and not (t.startswith("*") and t.endswith("*"))


def speakers_month_chars(records: Iterable[dict], month: str, heralds: Iterable[str]) -> int:
    """The month's spoken characters of every member but the heralds (Hermes keeps his own budget): their ok `tts`
    lines in `month` (`YYYY-MM`)."""
    skip = set(heralds)
    return sum(r.get("characters") or 0 for r in records
               if r.get("kind") == "tts" and r.get("ok") and r.get("agent") not in skip and str(r["ts"])[:7] == month)


async def voice_message(client, tts, text: str, filename: str, reply_to: str | None = None,
                        on_synth: Callable[[bool], None] | None = None,
                        caption: bool = False) -> tuple[dict | None, str | None]:
    """synth → OGG/Opus → upload → the `m.audio` content, not yet sent: (content, None), or (None, why it stays
    text). `reply_to` relates it to the owner's voice it answers; `on_synth(ok)` records the paid call."""
    pcm = await tts.synth(text)
    if on_synth is not None:
        on_synth(pcm is not None)
    if pcm is None:
        return None, "tts failed"
    ogg = await encode_opus(pcm)
    if ogg is None:
        return None, "encode failed"
    resp, _ = await client.upload(io.BytesIO(ogg), content_type="audio/ogg", filename=filename, filesize=len(ogg))
    if not isinstance(resp, UploadResponse):
        log.error("upload failed: %s", getattr(resp, "status_code", type(resp).__name__))
        return None, "upload failed"
    content = voice_content(resp.content_uri, len(ogg), duration_ms(pcm), waveform(pcm),
                            caption=text if caption else None, filename=filename)
    if reply_to:
        content["m.relates_to"] = {"m.in_reply_to": {"event_id": reply_to}}
    return content, None
