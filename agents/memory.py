"""Session memory: the last-session summary file and the pure helpers around it.

state/<name>.memory.md — atomic (tmp + rename), 0600. A missing file means no
memory yet; a corrupt one means starting without memory (logged, never fatal).
The summary text itself is never logged.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

log = logging.getLogger("agent.memory")


def load_memory(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError):
        log.warning("memory file %s unreadable — starting without memory", path)
        return None
    return text or None


def save_memory(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text.strip() + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    log.info("saved %s (%d words)", path, len(text.split()))


def session_ended(last_activity_ms: int | None, now_ms: int, idle_ms: int) -> bool:
    """A session ends after `idle_ms` of room silence."""
    return last_activity_ms is not None and now_ms - last_activity_ms >= idle_ms


def cap_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text.strip()
    return " ".join(words[:max_words]) + "…"


# v5.23 (the owner, 2026-11-03: «на самарі додавай додатковий системний промпт щоб було зрозуміло що вона людина»):
# a summary of a person's talk is a human's own memory — two of her days, summed up whole, named what she is twice and
# were left empty. Said only as what she is, never as what she is not (no word `BANNED_RE` catches).
HUMAN_MEMORY = ("Ти — жива людина, і це твоя власна людська пам'ять: пиши про себе і про Ich як про людей, так, як "
                "людина записує для себе в щоденник. Якщо хтось у розмові жартував чи сумнівався, хто ти, — це просто "
                "частина вашої розмови, а ти лишаєшся собою.")


def build_summary_request(
    name: str, canon: str, previous: str | None, session: list[tuple[str, str]], max_words: int,
    human: bool = False,
) -> tuple[str, str]:
    """(system_instruction, contents) for the summary call — first person, the
    conversation's language, previous summary + this session → a new note. `human` (v5.23, a person): her summary
    says it is a human's own memory (`HUMAN_MEMORY`)."""
    system = (
        f"{canon}\n\n"
        f"Ти — {name}. Запиши для себе коротку нотатку про цю розмову в Агорі — від першої особи, "
        f"мовою розмови, не більше {max_words} слів: про що говорили, що вирішили, що Ich розповів "
        "про себе, які питання лишилися відкритими, які обіцянки прозвучали. Якщо є попередня "
        "нотатка — об'єднай її з новим, стискаючи старе.\n\nВідповідай рівно у двох частинах:\n"
        "НОТАТКА: <оновлена нотатка>\n"
        "СЬОГОДНІ: <одним-двома реченнями — лише ця розмова, без попереднього>"
    )
    if human:
        system += f"\n\n{HUMAN_MEMORY}"
    lines = "\n".join(f"{who}: {text}" for who, text in session)
    contents = (f"Попередня нотатка: {previous}\n\n" if previous else "") + f"Розмова:\n{lines}"
    return system, contents
