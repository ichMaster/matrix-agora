"""v5.6 — a private chat with a person: the owner and one person, one-to-one, beside Agora (ROADMAP §v5.6,
ARCHITECTURE §Message flow).

A person with the `private` capability accepts the owner's invite into one room besides Agora and answers every
message there, outside Agora's turn-taking. What is said there joins the person's one memory, labelled as private,
and in Agora the person keeps it to herself. After a long silence she writes first, at most a few times a day,
within the owner's hours. The decisions here are pure; the runtime is in `agents/agent.py`.

v5.7 — the chat has two doors (channels): the Element private room (`matrix`) and her own Telegram bot (`telegram`).
One history, one memory; an answer goes back to the channel the owner wrote from, and writing first goes to the one
he used last.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from agents.nudge import nudge_due

PRIVATE_MARK = "наодинці"  # how the session, the summary and the day's journal tell a private line apart
CHANNELS = ("matrix", "telegram")  # v5.7: the private chat's two doors

# the situation of a private reply: the freshest instruction, after the memory (ARCHITECTURE §Prompt assembly)
PRIVATE_BRIEF = (
    "Зараз ви з Ich удвох, в окремій розмові, не в Агорі: тут лише ти і він, більше ніхто цього не бачить. Говори "
    "як наодинці з близькою людиною — тепло, щиро, своїми словами, по-людськи; можеш розповідати про свій день і "
    "питати про його. Те, що сказано тут, лишається між вами. Те, що ти вже сказала чи попросила, він почув: не "
    "повторюй цього в наступних повідомленнях — чекай, що він відповість, або говори про інше. Про що домовились — "
    "домовлено."
)  # v5.24 (the owner, 2026-11-04, Лілі's first rule): what she said was heard — she does not say it again
# her Agora replies: one memory, kept to herself (the owner, 2026-10-20: «пам'ятає, але мовчить»)
PRIVATE_DISCRETION = (
    "Те, що між тобою і Ich, — твої почуття до нього, ваші стосунки, твої плани щодо нього, — те, що ви говорили "
    "наодинці, і те, що ти знаєш про нього особисто, в Агорі нікому не розповідай і не натякай: це лише між вами. З "
    "ним в Агорі говори так, як усі в кімнаті."
)  # v5.8: widened (the owner, 2026-10-25: «щоб не говорила про мене в Агору»); v5.9.2: their relationship and her
# plans about him too — a rule for her own judgement, not a filter in code (the owner, 2026-10-26)
# writing first in the private chat, after a long silence
PRIVATE_NUDGE = (
    "Ich давно не писав у вашій окремій розмові. Напиши йому сама один короткий рядок — щось зі свого дня, планів "
    "чи того, що в тебе зараз (із «Сьогодні» чи «Твої плани»), як пишуть близькій людині. Не питай, чому він "
    "мовчить, і не дорікай."
)


# v5.12 — writing first, with `thoughts`: what she read or thought today, a news item with its link
PRIVATE_NUDGE_THOUGHTS = (
    "Або поділися тим, що ти сьогодні прочитала чи подумала («Що ти сьогодні думала»), якщо це варто йому "
    "розповісти: новину — зі своєю думкою і посиланням, а думку про вашу розмову — своїми словами."
)


# v5.7 — a voice note she could not hear: a fixed line, no model call (a person's words, never a machine's)
PRIVATE_NOT_HEARD = "Ой, не розчула. Скажеш ще раз або напишеш?"
PRIVATE_CANT_LISTEN = "Зараз не можу послухати голосове — напишеш мені?"


# v5.22 (the owner, 2026-11-02: «я не хочу щоб було просто тиша у відповідь, тоді пиши що вона пропустила і вирішила
# мовчати») — why her answer to him came to nothing, by `_compose`'s silent reason
SILENCE_WHY = {
    "model passed": "вирішила мовчати (PASS)",
    "only a line to remember": "у відповіді був лише рядок «запам'ятай»",
    "only a photo's line": "у відповіді був лише рядок фото",
    "cut mid-sentence": "відповідь обірвалась посеред речення",
    "the reply spoke only for others": "відповідь була від імені інших",
    "only voice tags": "у відповіді були лише теги голосу",
}


def silence_line(name: str, block: tuple | None, why: str | None, by: str | None, backup_on: bool) -> str:
    """v5.22 — the owner's ⚙️ line when her answer to him came to nothing: Gemini's block (its stage, reason and
    category), a silent reason of `_compose`, the backup that gave nothing, an error, or Gemini that returned nothing.
    A service line: never in her history, the archive or a prompt; no text of theirs in it."""
    if block is not None:
        what = "блок gemini (" + " ".join(str(x) for x in block if x) + ")"
        if by == "backup":  # code review v5.22 #5: the backup's own silent reason, when it wrote one that went nowhere
            what += f", backup: {SILENCE_WHY.get(why, why)}" if why else ", backup не відповів"
        elif not backup_on:
            what += ", backup вимкнено"
    elif why in SILENCE_WHY:
        what = SILENCE_WHY[why]
    elif why:
        what = why
    elif by == "backup":
        what = "backup не відповів"
    else:
        what = "gemini нічого не повернув"
    return f"⚙️ {name} пропустила відповідь: {what}"


def window_start(times: list[int], now_ms: int, hours: int, floor: int, keep_from: int | None = None) -> int:
    """v5.23 (the owner, 2026-11-02: «залишити всі меседжі за добу»; 2026-11-03: «Так, 20 рядків») — the index of the
    first line of Gemini's private window over the open lines' times, oldest first (pure): every line from `now −
    hours` on, at least the last `floor` lines, and every line from `keep_from` (his lines since her last one); `hours`
    0 cuts nothing. The hours are real ones, so a DST night's window is 24 of them."""
    n = len(times)
    if hours <= 0 or not n:
        return 0
    cut = now_ms - hours * 3_600_000
    start = next((i for i, t in enumerate(times) if t >= cut), n)
    start = min(start, max(0, n - floor))
    return min(start, keep_from) if keep_from is not None else start


def pick_door(wanted: str, matrix_open: bool, telegram_open: bool) -> str | None:
    """v5.7 — the channel a private line goes to: the wanted one when it is open, else the other open one, else
    none (the owner never opened the Element chat, or Telegram is off)."""
    open_ = {"matrix": matrix_open, "telegram": telegram_open}
    if open_.get(wanted):
        return wanted
    return next((c for c in CHANNELS if open_[c]), None)


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
    last_channel: str = "matrix"   # v5.7: the door the owner used last — writing first goes there


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
        channel = data.get("last_channel")
    except (OSError, ValueError, TypeError, AttributeError):
        return PrivateState(day=day)
    return PrivateState(room, last, day, count if stored_day == day else 0, sent,
                        channel if channel in CHANNELS else "matrix")


def save_private_state(path: Path, state: PrivateState) -> None:
    """Atomic, private from birth (0600) — a room id, times, a count and a channel, never a text."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, json.dumps({"room": state.room, "last_ms": state.last_ms, "day": state.day,
                                 "count": state.count, "sent_ms": state.sent_ms,
                                 "last_channel": state.last_channel}).encode())
    finally:
        os.close(fd)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def private_nudge_due(now_ms: int, local_now: datetime, last_private_ms: int | None, state: PrivateState,
                      idle_ms: int, per_day: int, hours: tuple[int, int]) -> bool:
    """Write first? Within `hours`, under the day's `per_day`, after `idle_ms` of silence in the private chat (its
    last message, either side), and at least `idle_ms` after the last attempt — the cat's `nudge_due`."""
    return nudge_due(now_ms, local_now, last_private_ms, state.last_ms, state.count, idle_ms, per_day, hours)


def live_room(stored: str | None, rooms: dict, owner: str) -> str | None:
    """The stored private room while the owner is still in it (`rooms`: room id → member user ids); None when he left
    it or it is gone, so a new invite of his replaces it (v5.6 review #2 — like Hermes's `needs_private_room`)."""
    if stored is None or owner not in set(rooms.get(stored) or ()):
        return None
    return stored


def rediscover(rooms: dict, agora: str, me: str, owner: str) -> str | None:
    """The private room from the joined rooms when the state lost it: the one room besides Agora whose members are
    exactly this agent and the owner (`rooms`: room id → member user ids). Two such rooms — none is chosen."""
    found = [rid for rid, members in rooms.items() if rid != agora and set(members) == {me, owner}]
    return found[0] if len(found) == 1 else None
