"""v5.7 — Кіра in Telegram: a small Bot API client and its pure parts (ROADMAP §v5.7, ARCHITECTURE §Message flow).

The person's own bot is a second door to her private chat. Her process polls it itself (`getUpdates`, long polling —
outbound HTTPS only, no webhook, no open port) over `aiohttp`, already a dependency. Only the owner's numeric id in a
private chat is ever handled. The offset is kept in `state/<name>.telegram.json`, so a restart never answers an
update twice.

The token is part of every URL, so no URL, `repr` or exception text reaches a log: a failure is logged by its HTTP
status, Telegram's `error_code` or the exception's type — never the token, an id or a word.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiohttp

from agents.logic import Verdict
from agents.responder import trim_to_sentence

log = logging.getLogger("agent.telegram")

API = "https://api.telegram.org"
POLL_TIMEOUT_S = 30   # long polling: the server holds the request this long when there is nothing new
CALL_TIMEOUT_S = 60   # every other call — a voice note's upload included
TEXT_MAX = 4096       # Telegram's limit for one message's text
CHUNK = 65_536
VOICE_MAX_BYTES = 20_000_000  # Hermes's cap (and the Bot API's own for a download): a voice note is far smaller
ACTION_EVERY_S = 4.0  # a chat action shows about five seconds: repeated while she composes
BACKOFF_FIRST_S, BACKOFF_MAX_S = 5, 300
# after a week without updates Telegram picks the next `update_id` at random — an older offset would confirm new
# messages unseen, so an offset this stale is dropped (review #7)
OFFSET_STALE_MS = 6 * 24 * 3600 * 1000


@dataclass(frozen=True)
class Update:
    """One update as the runtime needs it — `kind` is `text`, `voice`, `edit` or `other`."""
    update_id: int
    sender: int | None
    chat_id: int | None
    chat_type: str
    date_ms: int
    kind: str
    text: str = ""
    file_id: str = ""
    duration_s: int = 0
    mime: str = ""
    file_size: int | None = None


def parse_update(raw: Any) -> Update | None:
    """A raw `getUpdates` item → an `Update`; malformed → None. A message with text or a voice note is `text` /
    `voice`; an edited message is `edit`; a channel post and every other update or message kind is `other`."""
    if not isinstance(raw, dict) or not isinstance(raw.get("update_id"), int):
        return None
    uid = raw["update_id"]
    edited = isinstance(raw.get("edited_message"), dict)
    msg = raw.get("message") if isinstance(raw.get("message"), dict) else raw.get("edited_message")
    if not isinstance(msg, dict):
        return Update(uid, None, None, "", 0, "other")
    sender = msg.get("from", {}).get("id") if isinstance(msg.get("from"), dict) else None
    chat = msg.get("chat") if isinstance(msg.get("chat"), dict) else {}
    date = msg.get("date")
    base = (uid, sender if isinstance(sender, int) else None, chat.get("id") if isinstance(chat.get("id"), int)
            else None, str(chat.get("type", "")), int(date) * 1000 if isinstance(date, int) else 0)
    if edited:
        return Update(*base, "edit")
    if isinstance(msg.get("text"), str):
        return Update(*base, "text", text=msg["text"])
    voice = msg.get("voice")
    if isinstance(voice, dict) and isinstance(voice.get("file_id"), str):
        size = voice.get("file_size")
        duration = voice.get("duration")
        return Update(*base, "voice", file_id=voice["file_id"],
                      duration_s=duration if isinstance(duration, int) else 0,
                      mime=str(voice.get("mime_type") or "audio/ogg"), file_size=size if isinstance(size, int) else None)
    return Update(*base, "other")


# v5.14 — the owner's commands in her chat (the route of her private answer): never a word of her talk
COMMANDS = (("status", "Маршрут і блоки"), ("auto", "Правила вирішують"), ("gemini", "Закріпити Gemini"),
            ("backup", "Закріпити резерв"))
COMMAND_HELP = "⚙️ Команди: " + ", ".join(f"/{name} — {about.lower()}" for name, about in COMMANDS)


def command_of(text: str) -> str:
    """`/status@kira_bot extra` → `status`; the name lower-cased, its bot suffix and arguments dropped."""
    head = text.strip().split(maxsplit=1)[0] if text.strip() else ""
    return head.lstrip("/").split("@", 1)[0].lower()


def allowed(update: Update, owner_id: int) -> Verdict:
    """Only the owner's private chat: a group or a channel is `not-private`, anyone else a `stranger`; then an edit
    is `edit`, anything but a text or a voice note `unsupported`, and a bot command (`/start`) `command`."""
    if update.chat_type != "private":
        return Verdict(False, "not-private")
    if update.sender != owner_id:
        return Verdict(False, "stranger")
    if update.kind == "edit":
        return Verdict(False, "edit")
    if update.kind not in ("text", "voice"):
        return Verdict(False, "unsupported")
    if update.kind == "text" and update.text.lstrip().startswith("/"):  # `/start` and the like: a bot's word never
        return Verdict(False, "command")                                  # reaches a person's prompt (review #6)
    return Verdict(True, "ok")


def next_offset(raw_updates: list, offset: int | None) -> int | None:
    """The offset that confirms every update of a batch: its highest `update_id` + 1 (the offset as it was when the
    batch holds none)."""
    ids = [u["update_id"] for u in raw_updates if isinstance(u, dict) and isinstance(u.get("update_id"), int)]
    return max(ids) + 1 if ids else offset


def backoff_s(failures: int) -> int:
    """The wait before polling again after `failures` failed polls in a row: 5 s, doubling, at most 5 min."""
    return min(BACKOFF_FIRST_S * 2 ** max(failures - 1, 0), BACKOFF_MAX_S)


def fit_text(text: str, limit: int = TEXT_MAX) -> str:
    """One message's text: whole when it fits, else cut at its last complete sentence (at the limit when none)."""
    if len(text) <= limit:
        return text
    return trim_to_sentence(text[:limit]) or text[:limit]


@dataclass
class TelegramState:
    """`state/<name>.telegram.json`: the next update to fetch and when updates last came — never a text, a token
    or an id."""
    offset: int | None = None
    seen_ms: int | None = None  # the last batch that held updates (review #7)


def load_telegram_state(path: Path) -> TelegramState:
    """A missing or corrupt file is a fresh state (no offset: the first start)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        offset, seen = data.get("offset"), data.get("seen_ms")
        return TelegramState(int(offset) if offset is not None else None, int(seen) if seen is not None else None)
    except (OSError, ValueError, TypeError, AttributeError):
        return TelegramState()


def poll_offset(state: TelegramState, now_ms: int) -> int | None:
    """The offset to poll from: the stored one while updates came within `OFFSET_STALE_MS`; else none, so only
    the unconfirmed updates come back — whatever ids Telegram gave them."""
    if state.offset is None or state.seen_ms is None or now_ms - state.seen_ms > OFFSET_STALE_MS:
        return None
    return state.offset


def save_telegram_state(path: Path, state: TelegramState) -> None:
    """Atomic, private from birth (0600)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, json.dumps({"offset": state.offset, "seen_ms": state.seen_ms}).encode())
    finally:
        os.close(fd)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


@dataclass(frozen=True)
class Reply:
    """A Bot API call's outcome: its `result`, or the HTTP status of a failure and 429's `retry_after`."""
    ok: bool
    result: Any = None
    status: int | None = None
    retry_after: int | None = None


class TelegramBot:
    def __init__(self, token: str) -> None:
        self._token = token

    def __repr__(self) -> str:  # never the token
        return "TelegramBot()"

    async def _call(self, method: str, timeout_s: float, json_body: dict | None = None,
                    data: aiohttp.FormData | None = None) -> Reply:
        url = f"{API}/bot{self._token}/{method}"
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout_s)) as session, \
                    session.post(url, json=json_body, data=data) as resp:
                status = resp.status
                try:
                    body = await resp.json(content_type=None)
                except ValueError:
                    body = None
        except Exception as exc:  # noqa: BLE001 — any failure is a failed call, named by its type only
            log.error("telegram: %s failed: %s", method, type(exc).__name__)
            return Reply(False)
        if status == 200 and isinstance(body, dict) and body.get("ok"):
            return Reply(True, body.get("result"))
        code = body.get("error_code") if isinstance(body, dict) else None
        params = body.get("parameters") if isinstance(body, dict) else None
        wait = params.get("retry_after") if isinstance(params, dict) else None
        log.error("telegram: %s failed: HTTP %s%s", method, status, f" ({code})" if code not in (None, status) else "")
        return Reply(False, None, status, wait if isinstance(wait, int) else None)

    async def get_updates(self, offset: int | None, timeout_s: int = POLL_TIMEOUT_S) -> Reply:
        """Long polling: the updates from `offset` on (messages only), the result a list."""
        body: dict = {"timeout": timeout_s, "allowed_updates": ["message", "edited_message"]}
        if offset is not None:
            body["offset"] = offset
        reply = await self._call("getUpdates", timeout_s + 10, json_body=body)
        if reply.ok and not isinstance(reply.result, list):
            log.error("telegram: getUpdates failed: no list")
            return Reply(False)
        return reply

    async def send_message(self, chat_id: int, text: str) -> bool:
        """Plain text (no parse mode), cut to one message at a sentence."""
        return (await self._call("sendMessage", CALL_TIMEOUT_S,
                                 json_body={"chat_id": chat_id, "text": fit_text(text)})).ok

    async def set_commands(self, chat_id: int) -> bool:
        """v5.14 — the command list, shown in the owner's chat only (`BotCommandScopeChat`)."""
        body = {"commands": [{"command": name, "description": about} for name, about in COMMANDS],
                "scope": {"type": "chat", "chat_id": chat_id}}
        return (await self._call("setMyCommands", CALL_TIMEOUT_S, json_body=body)).ok

    async def send_voice(self, chat_id: int, ogg: bytes, duration_s: int) -> bool:
        """A voice note: OGG/Opus as multipart, with its length in seconds."""
        form = aiohttp.FormData()
        form.add_field("chat_id", str(chat_id))
        form.add_field("duration", str(max(int(duration_s), 1)))
        form.add_field("voice", ogg, filename="voice.ogg", content_type="audio/ogg")
        return (await self._call("sendVoice", CALL_TIMEOUT_S, data=form)).ok

    async def send_chat_action(self, chat_id: int, action: str) -> bool:
        """`typing` or `record_voice` — shown about five seconds, so the caller repeats it."""
        return (await self._call("sendChatAction", CALL_TIMEOUT_S,
                                 json_body={"chat_id": chat_id, "action": action})).ok

    async def get_file(self, file_id: str) -> str | None:
        """A file's path on Telegram's file server, to download once."""
        reply = await self._call("getFile", CALL_TIMEOUT_S, json_body={"file_id": file_id})
        path = reply.result.get("file_path") if reply.ok and isinstance(reply.result, dict) else None
        return path if isinstance(path, str) and path else None

    async def download(self, file_path: str, max_bytes: int) -> bytes | None:
        """The file's bytes, read in memory; one over `max_bytes` is never read past the cap."""
        url = f"{API}/file/bot{self._token}/{file_path}"
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=CALL_TIMEOUT_S)) as session, \
                    session.get(url) as resp:
                if resp.status != 200:
                    log.error("telegram: download failed: HTTP %s", resp.status)
                    return None
                if resp.content_length is not None and resp.content_length > max_bytes:
                    log.error("telegram: download refused: over the cap")
                    return None
                data = bytearray()
                async for chunk in resp.content.iter_chunked(CHUNK):
                    data += chunk
                    if len(data) > max_bytes:
                        log.error("telegram: download refused: over the cap")
                        return None
        except Exception as exc:  # noqa: BLE001
            log.error("telegram: download failed: %s", type(exc).__name__)
            return None
        return bytes(data)
