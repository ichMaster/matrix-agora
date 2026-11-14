"""v7.6 (AGORA-260) — a companion's memory as Lumi's (`MEMORY_MODE = lumi`, ROADMAP §v7.6, ARCHITECTURE §Memory).

The owner, 2026-11-12: «окрім того живої розмови там лише значно менше, вона періодично самарізується». In `lumi`
mode her private history word for word is a short **live window**: the open lines after the last one folded into her
day's **running digest**. Once `n + batch` lines wait there, the oldest `batch` are folded into the digest by a cheap
model, so the window is `n` to `n + batch` lines and its start moves by whole batches. The digest of her day stands
in the prompt's tail, never in its start, so the cache's start never changes with it. At her midnight (her own clock)
it starts empty.

The window here is pure: plain data, no clock of its own. The digest's file is written atomically. The agent reads
the archive and calls the model.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from agents.memory import HUMAN_MEMORY
from agents.talk import TALK_GENTLE

LIVE_WINDOW_N = 40       # Lumi's live window is 40–60 messages
LIVE_WINDOW_BATCH = 20   # … its oldest 20 folded at once
DIGEST_WORDS = 120
DIGEST_BATCHES_PER_TICK = 3  # a backlog (the first switch to `lumi`) is folded over a few ticks, never in one
DIGEST_CHECK_MS = 30_000
DIGEST_TITLE = "Раніше сьогодні ви говорили (твоя пам'ять, а не те, що кажуть зараз):"
MODES = ("layered", "lumi")


def lumi_window_start(times: list[int], upto_ms: int, n: int, batch: int, keep_from: int | None = None) -> int:
    """The index of the first line of her live window over the open lines' times, oldest first (pure): every line
    after the last one folded into her digest (`upto_ms`), but never more than `n + batch` lines — a digest behind
    (the first switch, a failed fold) leaves the oldest out until they are folded — nor fewer than `n` while there are
    so many, and his lines since her last one always (`keep_from`, as the window by time keeps them)."""
    total, n = len(times), max(n, 1)
    start = next((i for i, t in enumerate(times) if t > upto_ms), total)
    start = min(max(start, total - (n + max(batch, 0))), max(total - n, 0))
    return min(start, keep_from) if keep_from is not None else start


def batches_due(waiting: int, n: int, batch: int) -> int:
    """How many whole batches of the oldest waiting lines are due to fold (pure): once `n + batch` lines wait after
    the last one folded, the oldest `batch` go, and so on, so the window keeps `n` to `n + batch` lines."""
    if batch <= 0 or waiting < max(n, 1) + batch:
        return 0
    return (waiting - max(n, 1)) // batch


@dataclass
class Digest:
    """Her day's running digest: her local day (ISO), the last line folded (any day's), the digest's text; the day
    before, kept when the day rolls over (for the gists and the panel)."""
    day: str = ""
    upto_ms: int = 0
    text: str = ""
    previous_day: str = ""
    previous_text: str = ""


def load_digest(path: Path) -> Digest:
    """The digest's file; a missing or corrupt one is an empty digest, never an error."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return Digest(day=str(raw.get("day", "")), upto_ms=int(raw.get("upto_ms", 0) or 0),
                      text=str(raw.get("text", "")), previous_day=str(raw.get("previous_day", "")),
                      previous_text=str(raw.get("previous_text", "")))
    except (OSError, ValueError, TypeError, AttributeError):
        return Digest()


def save_digest(path: Path, digest: Digest) -> None:
    """Atomically (a temporary file renamed over it), readable by her alone (0600)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(asdict(digest), f, ensure_ascii=False)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def rolled(digest: Digest, today: str) -> Digest:
    """The digest on her day `today` (pure): the same day as it is; a new day starts empty, the last day's text kept
    as `previous_*` (an empty last day keeps the one before it), the fold point unchanged."""
    if digest.day == today:
        return digest
    if digest.day and digest.text:
        return Digest(today, digest.upto_ms, "", digest.day, digest.text)
    return Digest(today, digest.upto_ms, "", digest.previous_day, digest.previous_text)


def talk_digest_section(digest: Digest, today: str) -> str | None:
    """The tail's layer (pure): her day's digest, today's only; None when there is none."""
    if digest.day != today or not digest.text.strip():
        return None
    return f"{DIGEST_TITLE}\n{digest.text.strip()}"


def talk_digest_request(name: str, canon: str, so_far: str, items: list[tuple[str, str]], max_words: int,
                   strict: int = 0) -> tuple[str, str]:
    """(system instruction, contents) for folding a batch of her day's lines into her running digest: her own memory
    of the day's talk alone with Ich so far, first person, at most `max_words` words, from what she remembered and the
    lines that came after — never an hour, which her prompt does not need; their closeness told as
    `TALK_GENTLE[strict]` says (each rewrite one step stricter, as a talk summary's)."""
    system = (f"{canon}\n\nТи — {name}. Онови свою коротку пам'ять про сьогоднішню розмову наодинці з Ich: нижче те, що "
              "ти вже пам'ятаєш про раніше сьогодні, і те, що було далі. Напиши одну пам'ять про весь день досі — від "
              f"першої особи, мовою розмови, не більше {max_words} слів: про що говорили, що вирішили, що Ich розповів "
              "про себе, що ви одне одному пообіцяли, що ти відчувала. Найновіше — докладніше, давнє — коротше. Тільки "
              "те, що є нижче, нічого не вигадуй. Без годин.\n\n"
              f"{TALK_GENTLE[min(max(strict, 0), len(TALK_GENTLE) - 1)]}\n\n"
              f"{HUMAN_MEMORY}")
    before = f"Що ти вже пам'ятаєш про раніше сьогодні:\n{so_far.strip()}\n\n" if so_far.strip() else ""
    return system, before + "Розмова далі:\n" + "\n".join(f"{who}: {text}" for who, text in items)


# --- v7.6 (AGORA-261): her day memories in one line ----------------------------------------------------------------
def gist_path(path: Path) -> Path:
    """A memory's one-line gist, beside it: `2026-11-13.md` → `2026-11-13.gist.md` (never read as a memory)."""
    return path.with_name(f"{path.stem}.gist.md")


def first_sentence(text: str, max_words: int = 40) -> str:
    """A memory's first sentence (pure), at most `max_words` words — her day memory in `lumi` mode until its gist is
    written."""
    flat = " ".join(text.split())
    for i, ch in enumerate(flat):
        if ch in ".!?…" and (i + 1 == len(flat) or flat[i + 1] == " "):
            flat = flat[:i + 1]
            break
    words = flat.split()
    return " ".join(words[:max_words]) + ("…" if len(words) > max_words else "")


def memory_gist_request(name: str, canon: str, memory: str, max_words: int) -> tuple[str, str]:
    """(system instruction, contents) for a day memory's gist: one sentence of it, her own, at most `max_words`."""
    system = (f"{canon}\n\nТи — {name}. Стисни цей свій спогад до одного речення, не більше {max_words} слів, від першої "
              "особи: головне, що сталося і що ти відчувала. Тільки з того, що в ньому, нічого не вигадуй. Без дат."
              f"\n\n{HUMAN_MEMORY}")
    return system, f"Спогад:\n{memory.strip()}"

