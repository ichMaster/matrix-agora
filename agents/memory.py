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
    log.info("session summary saved to %s (%d words)", path, len(text.split()))


def session_ended(last_activity_ms: int | None, now_ms: int, idle_ms: int) -> bool:
    """A session ends after `idle_ms` of room silence."""
    return last_activity_ms is not None and now_ms - last_activity_ms >= idle_ms


def cap_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text.strip()
    return " ".join(words[:max_words]) + "…"


def build_summary_request(
    name: str, canon: str, previous: str | None, session: list[tuple[str, str]], max_words: int,
) -> tuple[str, str]:
    """(system_instruction, contents) for the summary call — first person, the
    conversation's language, previous summary + this session → a new note."""
    system = (
        f"{canon}\n\n"
        f"Ти — {name}. Запиши для себе коротку нотатку про цю розмову в Агорі — від першої особи, "
        f"мовою розмови, не більше {max_words} слів: про що говорили, що вирішили, що Ich розповів "
        "про себе, які питання лишилися відкритими, які обіцянки прозвучали. Якщо є попередня "
        "нотатка — об'єднай її з новим, стискаючи старе.\n\nВідповідай рівно у двох частинах:\n"
        "НОТАТКА: <оновлена нотатка>\n"
        "СЬОГОДНІ: <одним-двома реченнями — лише ця розмова, без попереднього>"
    )
    lines = "\n".join(f"{who}: {text}" for who, text in session)
    contents = (f"Попередня нотатка: {previous}\n\n" if previous else "") + f"Розмова:\n{lines}"
    return system, contents
