"""v5.6 — a private chat with a person: the owner and one person, one-to-one, beside Agora (ROADMAP §v5.6,
ARCHITECTURE §Message flow).

A person with the `private` capability accepts the owner's invite into one room besides Agora and answers every
message there, outside Agora's turn-taking. What is said there joins the person's one memory, labelled as private,
and in Agora the person keeps it to herself. After a long silence she writes first, at most a few times a day,
within the owner's hours. The decisions here are pure; the runtime is in `agents/agent.py`.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from agents.nudge import nudge_due

PRIVATE_MARK = "наодинці"  # how the session, the summary and the day's journal tell a private line apart

# the situation of a private reply: the freshest instruction, after the memory (ARCHITECTURE §Prompt assembly)
PRIVATE_BRIEF = (
    "Зараз ви з Ich удвох, в окремій розмові, не в Агорі: тут лише ти і він, більше ніхто цього не бачить. Говори "
    "як наодинці з близькою людиною — тепло, щиро, своїми словами, по-людськи; можеш розповідати про свій день і "
    "питати про його. Те, що сказано тут, лишається між вами."
)
# her Agora replies: one memory, kept to herself (the owner, 2026-10-20: «пам'ятає, але мовчить»)
PRIVATE_DISCRETION = (
    "Про те, що ви з Ich говорили наодинці, в Агорі не розповідай і не натякай — це лишається між вами."
)
# writing first in the private chat, after a long silence
PRIVATE_NUDGE = (
    "Ich давно не писав у вашій окремій розмові. Напиши йому сама один короткий рядок — щось зі свого дня, планів "
    "чи того, що в тебе зараз (із «Сьогодні» чи «Твої плани»), як пишуть близькій людині. Не питай, чому він "
    "мовчить, і не дорікай."
)


def private_label(name: str) -> str:
    """«Кіра (наодинці)» — a private line's speaker in the session and the summary."""
    return f"{name} ({PRIVATE_MARK})"


@dataclass
class PrivateState:
    """`state/<name>.private.json`: the private room and the initiative's bookkeeping — never a text."""
    room: str | None = None
    last_ms: int | None = None     # the last attempt to write first (spaces the next one)
    day: str = ""
    count: int = 0                 # lines written first that day
    sent_ms: int | None = None     # the last one sent


def load_private_state(path: Path, day: str) -> PrivateState:
    """The state for `day`: a missing or corrupt file is a fresh state (the room is then rediscovered at start);
    another day keeps the room and the last attempt and starts the count at 0."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        room = data.get("room")
        room = room if isinstance(room, str) and room else None
        last, sent = data.get("last_ms"), data.get("sent_ms")
        last = int(last) if last is not None else None
        sent = int(sent) if sent is not None else None
        stored_day, count = str(data.get("day", "")), int(data.get("count", 0))
    except (OSError, ValueError, TypeError, AttributeError):
        return PrivateState(day=day)
    return PrivateState(room, last, day, count if stored_day == day else 0, sent)


def save_private_state(path: Path, state: PrivateState) -> None:
    """Atomic, private from birth (0600) — a room id, times and a count, never a text."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, json.dumps({"room": state.room, "last_ms": state.last_ms, "day": state.day,
                                 "count": state.count, "sent_ms": state.sent_ms}).encode())
    finally:
        os.close(fd)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def private_nudge_due(now_ms: int, local_now: datetime, last_private_ms: int | None, state: PrivateState,
                      idle_ms: int, per_day: int, hours: tuple[int, int]) -> bool:
    """Write first? Within `hours`, under the day's `per_day`, after `idle_ms` of silence in the private chat (its
    last message, either side), and at least `idle_ms` after the last attempt — the cat's `nudge_due`."""
    return nudge_due(now_ms, local_now, last_private_ms, state.last_ms, state.count, idle_ms, per_day, hours)


def rediscover(rooms: dict, agora: str, me: str, owner: str) -> str | None:
    """The private room from the joined rooms when the state lost it: the one room besides Agora whose members are
    exactly this agent and the owner (`rooms`: room id → member user ids). Two such rooms — none is chosen."""
    found = [rid for rid, members in rooms.items() if rid != agora and set(members) == {me, owner}]
    return found[0] if len(found) == 1 else None
