"""v5.1 — Hermes's digests: the decisions, the prompts and the state file (ARCHITECTURE §The herald).

Pure but for the small state-file helpers: the clock comes in as numbers, the room's messages as plain data. Hermes
reads Agora word for word from the homeserver — nothing here keeps a copy of it — and tells the owner, in his own
room, what was talked about since the last digest; he answers the owner's questions about the last days the same
way. No text ever reaches a log or the state file.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, replace
from pathlib import Path

from agents.nudge import in_hours
from agents.responder import trim_to_sentence
from agents.turns import is_purr
from agents.world import local_now

log = logging.getLogger("agent.digest")

COLLECT_MAX = 1500        # at most this many messages in one digest (the newest since the point)
ASK_DAYS = 7              # a question about the history reads this many days back…
ASK_MAX = 2000            # …at most this many messages, the newest
DAY_MS = 86_400_000
DIGEST_WORDS = frozenset({"підсумок", "підсумки", "підсумуй"})
ASK_DIGEST_MAX_WORDS = 3  # «підсумок», «дай підсумок», «Гермесе, підсумок!»

# «підсумок» with nothing new since the last one: a fixed line in his voice — no model call
NOTHING_NEW = "Олімп мовчить: відколи я приносив тобі останні вісті, в Агорі не прозвучало ні слова."

DIGEST_BRIEF = (
    "Зараз ти складаєш голосовий підсумок Агори для Ich. Нижче — дослівні рядки розмови за {period} "
    "({count}), кожен у форматі «час Ім'я: текст». У кімнаті: {members}. Розкажи Ich, про що говорили, хто що "
    "думав, де сперечалися, про що питали Ich і до чого дійшли. Говори до Ich на «ти». Учасників називай на ім'я "
    "і не обговорюй, хто вони і яка їхня природа. Обсяг — близько {target} знаків, не більше {max_chars}: чим "
    "менше було розмови, тим коротше. Пиши суцільним усним текстом для озвучення — без списків, заголовків і "
    "розмітки, числа й години словами. Відповідай лише текстом підсумку."
)

# the owner, 2026-10-18: «він зазвичай відповідає цілим дайджестом» — a message from Ich is a conversation, not a digest
CHAT_BRIEF = (
    "Зараз Ich пише тобі сам, у вашій окремій кімнаті, — це розмова, а не підсумок. Відповідай саме на те, що він "
    "написав: коротко, як у чаті, одним–чотирма реченнями, у своєму характері, на «ти». Привітання — привітанням, "
    "жарт — жартом, питання — відповіддю на нього. Нижче — дослівні рядки з Агори за останні дні («дата час Ім'я: "
    "текст») і ваша недавня розмова. Агору згадуй лише тоді, коли він питає про неї, і лише те, про що питає, — без "
    "вісницького зачину й підпису; повний підсумок — тільки коли він попросить «підсумок». Коли питає про Агору, "
    "відповідай лише з цих рядків, а якщо відповіді там немає, так і скажи і нічого не вигадуй. У кімнаті: "
    "{members}. Учасників називай на ім'я і не обговорюй, хто вони і яка їхня природа. Без списків і розмітки."
)
CHAT_HISTORY_N = 20       # the last lines of the private room he sees, so a follow-up has its context
CHAT_LINE_MAX = 1500      # a digest in that history is cut to this many characters


@dataclass(frozen=True)
class Message:
    """One Agora text message, as read from the homeserver."""
    event_id: str
    sender: str
    ts: int      # the server timestamp, ms
    text: str


@dataclass(frozen=True)
class DigestState:
    """`state/<name>.digest.json` — ids, times and a count; never a text."""
    room: str | None = None          # the private room with the owner
    point_event: str | None = None   # the newest Agora message the last digest covered
    point_ts: int | None = None
    last_ms: int | None = None       # the last digest sent, scheduled or asked
    day: str = ""                    # the local day of `count`
    count: int = 0                   # digests sent that day


def load_digest_state(path: Path) -> DigestState:
    """A missing file is a fresh state; a corrupt one too, logged (never a crash)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return DigestState()
    except (OSError, ValueError):
        log.warning("digest state %s unreadable — starting fresh", path)
        return DigestState()
    if not isinstance(data, dict):
        log.warning("digest state %s malformed — starting fresh", path)
        return DigestState()

    def text(key: str) -> str | None:
        v = data.get(key)
        return v if isinstance(v, str) and v else None

    def num(key: str) -> int | None:
        v = data.get(key)
        return v if isinstance(v, int) and not isinstance(v, bool) else None

    return DigestState(room=text("room"), point_event=text("point_event"), point_ts=num("point_ts"),
                       last_ms=num("last_ms"), day=text("day") or "", count=num("count") or 0)


def save_digest_state(path: Path, state: DigestState) -> None:
    """Atomic, private from birth (0600)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, json.dumps({"room": state.room, "point_event": state.point_event, "point_ts": state.point_ts,
                                 "last_ms": state.last_ms, "day": state.day, "count": state.count}).encode())
    finally:
        os.close(fd)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def record_sent(state: DigestState, now_ms: int, day: str, newest: Message | None) -> DigestState:
    """The state after a digest went out: the point moves to the newest message it covered, the day's count grows."""
    point = (newest.event_id, newest.ts) if newest else (state.point_event, state.point_ts)
    return replace(state, point_event=point[0], point_ts=point[1], last_ms=now_ms, day=day,
                   count=state.count + 1 if state.day == day else 1)


def today_count(state: DigestState, day: str) -> int:
    return state.count if state.day == day else 0


def digest_due(now_ms: int, local_hour: int, last_ms: int | None, every_ms: int, hours: tuple[int, int],
               new_count: int, min_new: int) -> bool:
    """A scheduled digest: at least `every_ms` since the last one (none yet: at once), inside the local `hours`
    (start inclusive, end exclusive, a wrap past midnight allowed), and at least `min_new` new messages."""
    if not in_hours(local_hour, hours):
        return False
    if new_count < max(min_new, 1):
        return False
    return last_ms is None or now_ms - last_ms >= every_ms


def counts(text: str) -> bool:
    """Whether a room message counts toward a digest: anything but a purr."""
    return not is_purr(text)


def collect(newest_first: list[Message], *, stop_event: str | None = None, stop_ts: int | None = None,
            since_ms: int | None = None, limit: int = COLLECT_MAX) -> list[Message]:
    """The messages after a point, oldest first: walking back from the newest, stop at `stop_event`, at a message
    older than `stop_ts` or older than `since_ms`; purrs are left out; at most `limit` (the newest)."""
    out: list[Message] = []
    for m in newest_first:
        if stop_event and m.event_id == stop_event:
            break
        if stop_ts is not None and m.ts < stop_ts:
            break
        if since_ms is not None and m.ts < since_ms:
            break
        if not counts(m.text):
            continue
        out.append(m)
        if len(out) >= limit:
            break
    return list(reversed(out))


def since_point(newest_first: list[Message], state: DigestState, now_ms: int, every_ms: int,
                limit: int = COLLECT_MAX) -> list[Message]:
    """What the next digest covers: everything after the last digest's point; without a point (the first run),
    the last `every_ms`."""
    if state.point_event is None and state.point_ts is None:
        return collect(newest_first, since_ms=now_ms - every_ms, limit=limit)
    return collect(newest_first, stop_event=state.point_event, stop_ts=state.point_ts, limit=limit)


def ask_window(now_ms: int) -> int:
    """Where a question about the history starts reading: `ASK_DAYS` back (and at most `ASK_MAX` messages)."""
    return now_ms - ASK_DAYS * DAY_MS


def digest_lines(messages: list[Message], names: dict[str, str], tz: str, with_date: bool = False) -> list[str]:
    """`"HH:MM Name: text"` (`"DD.MM HH:MM …"` with the date), in the local time; the owner is «Ich» by `names`."""
    fmt = "%d.%m %H:%M" if with_date else "%H:%M"
    return [f"{local_now(m.ts, tz).strftime(fmt)} {names.get(m.sender, m.sender)}: {m.text}" for m in messages]


def period(messages: list[Message], tz: str) -> str:
    """«10:05–14:10», or with the dates when the stretch crosses a day."""
    if not messages:
        return ""
    first, last = local_now(messages[0].ts, tz), local_now(messages[-1].ts, tz)
    if first.date() == last.date():
        return f"{first:%H:%M}–{last:%H:%M}"
    return f"{first:%d.%m %H:%M} – {last:%d.%m %H:%M}"


def plural_messages(n: int) -> str:
    """«1 повідомлення», «3 повідомлення», «5 повідомлень», «21 повідомлення»."""
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) or n % 10 == 1 and n % 100 != 11:
        return f"{n} повідомлення"
    return f"{n} повідомлень"


def text_header(messages: list[Message], tz: str) -> str:
    """The first line of the digest's text message, made in code: «Агора, 10:05–14:10 · 23 повідомлення»."""
    return f"Агора, {period(messages, tz)} · {plural_messages(len(messages))}"


def target_chars(n_messages: int, max_chars: int) -> int:
    """The length follows the talk (the owner, 2026-10-13): a few lines make about half a minute, a lively stretch
    up to the cap (~1,000 characters a minute of Ukrainian speech)."""
    return min(max_chars, 300 + 40 * max(n_messages, 0))


def trim_digest(text: str, max_chars: int) -> str:
    """A digest over the cap is cut to its last full sentence within it; none complete → empty."""
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    return trim_to_sentence(text[:max_chars]) or ""


def asks_digest(text: str) -> bool:
    """The owner's «підсумок»: a short message (at most three words) that holds the word."""
    words = re.findall(r"[^\W\d_]+(?:['’][^\W\d_]+)?", (text or "").lower())
    return 0 < len(words) <= ASK_DIGEST_MAX_WORDS and any(w in DIGEST_WORDS for w in words)


def members_line(names: list[str]) -> str:
    return ", ".join(names)


def digest_request(canon: str, lines: list[str], when: str, n: int, target: int, max_chars: int,
                   members: list[str]) -> tuple[str, str]:
    """(system instruction, contents) of a digest: his canon, then the brief; the room's lines word for word."""
    brief = DIGEST_BRIEF.format(period=when, count=plural_messages(n), members=members_line(members),
                                target=target, max_chars=max_chars)
    return f"{canon}\n\n{brief}", "\n".join(lines)


def dialogue_lines(messages: list[Message], names: dict[str, str]) -> list[str]:
    """The private room's recent lines, `"Name: text"` (Ich and Гермес), each cut to `CHAT_LINE_MAX`."""
    out = []
    for m in messages:
        text = m.text if len(m.text) <= CHAT_LINE_MAX else m.text[:CHAT_LINE_MAX] + "…"
        out.append(f"{names.get(m.sender, m.sender)}: {text}")
    return out


def chat_request(canon: str, agora: list[str], dialogue: list[str], message: str,
                 members: list[str]) -> tuple[str, str]:
    """(system instruction, contents) of his answer to the owner: his canon and the chat brief; the room's last
    days as reference, your recent conversation, then what Ich just wrote."""
    brief = CHAT_BRIEF.format(members=members_line(members))
    parts = ["Агора за останні дні:\n" + ("\n".join(agora) or "(тиша)")]
    if dialogue:
        parts.append("Ваша недавня розмова:\n" + "\n".join(dialogue))
    parts.append(f"Ich: {message}")
    return f"{canon}\n\n{brief}", "\n\n".join(parts)
