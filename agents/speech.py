"""v5.3 — the speakers' voices: the decisions (pure) and the shared voice pipeline (ARCHITECTURE §Voice messages).

Every voiced line is first a checked text line; voicing adds an Element voice message before the same text, never
replaces it — the other agents read only text. The decisions are pure; the pipeline returns why a line could not be
voiced and never logs a word.
"""

from __future__ import annotations

from collections.abc import Iterable

from agents.turns import uniform


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
