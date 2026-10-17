"""v5.1 — the herald: Hermes's process (ARCHITECTURE §The herald).

He is a member of Agora who never takes part in the talk. He reads the room word for word from the homeserver and,
every few hours or when the owner says «підсумок», tells the owner what happened — as a voice message with its text —
in a private room he made with the owner. Any other owner message there is a question about the room's last days,
answered in text. In Agora nothing is ever sent: every send goes through `send_private`.

The decisions are pure (`agents/digest.py`, `route` below); this class is the nio adapter. Like every agent: login
once and reuse the token, the first sync is never processed, a failure is logged and leaves silence, and no message,
digest or answer text ever reaches a log.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import signal
import stat
import time
from dataclasses import replace
from pathlib import Path

from nio import (
    AsyncClient,
    InviteMemberEvent,
    MatrixRoom,
    MessageDirection,
    RoomCreateResponse,
    RoomMessagesError,
    RoomMessageText,
    RoomPreset,
    RoomSendResponse,
    RoomVisibility,
    SyncError,
    UploadResponse,
)

from agents.config import AgentConfig
from agents.digest import (
    ASK_MAX,
    COLLECT_MAX,
    NOTHING_NEW,
    Message,
    ask_request,
    ask_window,
    asks_digest,
    collect,
    counts,
    digest_due,
    digest_lines,
    digest_request,
    load_digest_state,
    period,
    record_sent,
    save_digest_state,
    since_point,
    target_chars,
    text_header,
    today_count,
    trim_digest,
)
from agents.llm import DIGEST_MODEL, GeminiClient
from agents.logic import should_join_invite, without_outing
from agents.matrix import join_room, login
from agents.nudge import parse_hours
from agents.roster import Member, load_roster, speakers
from agents.settings import VOICE_ID_RE
from agents.usage import month_chars, parse_lines, tts_usage_line, usage_line
from agents.voice import TTS_MODEL, ElevenLabsTTS, duration_ms, encode_opus, voice_content, waveform
from agents.world import local_now

log = logging.getLogger("agent.herald")

KEY_VAR = "ELEVENLABS_API_KEY"
PAGE = 100              # the homeserver's cap on one /messages page
MAX_PAGES = 40          # at most this many pages for one digest or question
WATCH_S = 60.0          # the watcher's tick
RETRY_MS = 600_000      # a failed digest is tried again after 10 minutes, never in a loop
ANSWER_MAX_CHARS = 3000
NOTHING_RECENT = "У моїх сувоях за останній тиждень порожньо: в Агорі мовчали."
ROOM_NAME = "Гермес"


def route(room_id: str, sender: str, text: str, cfg: AgentConfig, private_room: str | None) -> tuple[str, str]:
    """What a room message means to the herald: ("count", …) in Agora — read, never answered; ("digest", …) or
    ("ask", …) from the owner in the private room; ("ignored", reason) otherwise; ("own", …) for his own lines."""
    if sender == cfg.user_id:
        return "own", "own-message"
    if room_id == cfg.room_id:
        return ("count", "agora") if counts(text) else ("ignored", "purr")
    if private_room is None or room_id != private_room:
        return "ignored", "foreign-room"
    if sender != cfg.owner:
        return "ignored", "sender-not-owner"
    return ("digest", "asked") if asks_digest(text) else ("ask", "question")


def needs_private_room(stored: str | None, rooms: dict[str, set[str]], agora: str, owner: str) -> bool:
    """Whether to make a new private room: none yet, or the stored one is no longer his (not joined) or no longer
    the owner's (he left and was not re-invited). `rooms` maps each joined room to its joined and invited members.
    Agora itself is never the private room."""
    if stored is None or stored == agora:
        return True
    members = rooms.get(stored)
    return members is None or owner not in members


class Herald:
    def __init__(self, cfg: AgentConfig, llm: GeminiClient | None = None, tts: ElevenLabsTTS | None = None,
                 roster: dict[str, Member] | None = None, client: AsyncClient | None = None,
                 state_dir: Path = Path("state")) -> None:
        self.cfg = cfg
        roster = roster if roster is not None else load_roster(cfg.simulation, strict_for=cfg.localpart)
        self.personas = [m for m in roster.values() if m.type == "persona"]
        self.names = {cfg.owner: "Ich", **{m.user_id: m.name for m in roster.values()}}
        # who talks in the room, for the briefs — never himself
        self.members = ["Ich", *[m.name for m in speakers(roster.values()) if m.user_id != cfg.user_id]]
        self.client = client or AsyncClient(cfg.homeserver, cfg.user_id)
        self.llm = llm or GeminiClient(sink=self.record_usage)
        env = os.environ.get
        self.tz = env("TIMEZONE", "Europe/Kyiv")
        self.every_ms = int(float(env("HERMES_DIGEST_EVERY_S", "14400")) * 1000)
        self.min_new = int(env("HERMES_DIGEST_MIN_MESSAGES", "5"))
        self.max_chars = int(env("HERMES_DIGEST_MAX_CHARS", "1500"))
        self.hours = parse_hours(env("HERMES_DIGEST_HOURS", "09-23"))
        self.monthly_chars = int(env("HERMES_TTS_MONTHLY_CHARS", "150000"))
        self.voice_id = env("HERMES_VOICE_ID", "").strip()
        # the key stays in this process: out of the environment, never in a prompt, a log or the state
        key = os.environ.pop(KEY_VAR, "").strip()
        if tts is not None:
            self.tts: ElevenLabsTTS | None = tts
        else:
            self.tts = ElevenLabsTTS(key, self.voice_id) if key and self.voice_id else None
        self.text_only = ("no voice id" if not self.voice_id
                          else "voice id malformed" if not VOICE_ID_RE.match(self.voice_id)  # review #6: no tts line
                          else None if self.tts else f"no {KEY_VAR}")
        if self.text_only:
            log.warning("voice off: %s — the digests go out as text", self.text_only)
        self.clock = lambda: int(time.time() * 1000)  # injectable
        self.state_file = state_dir / f"{cfg.localpart}.digest.json"
        self.usage_file = state_dir / f"{cfg.localpart}.usage.jsonl"
        self.state = load_digest_state(self.state_file)
        self.started = False
        self.new_count = 0
        self._busy = asyncio.Lock()  # one digest or answer at a time
        self._retry_at = 0
        self._made_room: str | None = None
        self._tasks: set[asyncio.Task] = set()

    # --- the private room -------------------------------------------------------------------------------------------
    async def ensure_private_room(self) -> str | None:
        """The private room with the owner: the stored one while both are in it, else a new one, the owner invited."""
        joined = getattr(self.client, "rooms", {}) or {}
        if self.state.room is not None and self.state.room == self._made_room and self.state.room not in joined:
            return self.state.room  # made in this run and not synced back yet; once it is, the owner is checked (#4)
        rooms = {rid: {*getattr(r, "users", {}), *getattr(r, "invited_users", {})} for rid, r in joined.items()}
        if not needs_private_room(self.state.room, rooms, self.cfg.room_id, self.cfg.owner):
            return self.state.room
        resp = await self.client.room_create(
            visibility=RoomVisibility.private, name=ROOM_NAME, is_direct=True,
            preset=RoomPreset.trusted_private_chat, invite=[self.cfg.owner])
        if not isinstance(resp, RoomCreateResponse):
            log.error("private room not created: %s", getattr(resp, "status_code", type(resp).__name__))
            return None
        self.state = replace(self.state, room=resp.room_id)
        self._made_room = resp.room_id
        save_digest_state(self.state_file, self.state)
        log.info("private room %s created; the owner invited", resp.room_id)
        return resp.room_id

    async def send_private(self, content: dict) -> bool:
        """Every send goes here: only into the private room — never Agora, never anywhere else."""
        room = self.state.room
        if room is None or room == self.cfg.room_id:
            log.error("send refused: no private room")
            return False
        resp = await self.client.room_send(room, "m.room.message", content)
        if not isinstance(resp, RoomSendResponse):
            log.error("send failed: %s", getattr(resp, "status_code", type(resp).__name__))
            return False
        return True

    async def send_text(self, text: str) -> bool:
        return await self.send_private({"msgtype": "m.text", "body": text})

    async def _typing(self, on: bool) -> None:
        if self.state.room:
            try:
                await self.client.room_typing(self.state.room, on)
            except Exception:  # noqa: BLE001 — typing is cosmetic
                log.warning("typing %s failed", "on" if on else "off")

    # --- reading the room -------------------------------------------------------------------------------------------
    async def fetch(self, *, stop_event: str | None = None, stop_ts: int | None = None, since_ms: int | None = None,
                    limit: int = COLLECT_MAX) -> tuple[list[Message], bool]:
        """Agora's text messages, newest first, paged back from the latest sync until the stop or the bound — and
        whether the read completed (review #3): False when a page failed before the stop, the bound or the room's
        start, so nothing is digested from a partial read."""
        token = getattr(self.client, "next_batch", None)
        out: list[Message] = []
        for _ in range(MAX_PAGES):
            resp = await self.client.room_messages(self.cfg.room_id, start=token, direction=MessageDirection.back,
                                                   limit=PAGE)
            if isinstance(resp, RoomMessagesError):
                log.error("reading the room failed: %s", resp.status_code or "error")
                return out, False
            done = False
            for e in resp.chunk:
                if not isinstance(e, RoomMessageText):
                    continue
                m = Message(str(e.event_id), e.sender, int(e.server_timestamp), e.body)
                out.append(m)
                if (stop_event and m.event_id == stop_event or stop_ts is not None and m.ts < stop_ts
                        or since_ms is not None and m.ts < since_ms):
                    done = True
            end = getattr(resp, "end", None)
            if done or not resp.chunk or not isinstance(end, str) or end == token or len(out) >= limit * 2:
                break
            token = end
        return out, True  # the stop, the room's start, or the bound (the newest are what a digest covers)

    async def collect_since_point(self) -> tuple[list[Message], bool]:
        newest_first, complete = await self.fetch(
            stop_event=self.state.point_event, stop_ts=self.state.point_ts,
            since_ms=None if self.state.point_ts is not None or self.state.point_event else self.clock() - self.every_ms)
        return since_point(newest_first, self.state, self.clock(), self.every_ms), complete

    # --- the digest -------------------------------------------------------------------------------------------------
    async def digest(self, asked: bool = False) -> bool:
        """One digest of Agora since the last one, into the private room: the voice, then the text. True when done
        (sent, or nothing new); False on a failure worth retrying."""
        async with self._busy:
            if await self.ensure_private_room() is None:
                return False
            now = self.clock()
            seen = self.new_count  # review #2: only a settled digest takes these off the count; a failure keeps them

            def settled() -> None:
                self.new_count = max(0, self.new_count - seen)  # what arrived meanwhile counts toward the next one

            messages, complete = await self.collect_since_point()
            if not complete:  # never digest a partial read, never say "nothing new" from one (review #3)
                log.error("digest: the room could not be read — retrying later")
                return False
            if not messages:
                log.info("digest: nothing new")
                settled()
                if asked:
                    await self.send_text(NOTHING_NEW)
                return True
            lines = digest_lines(messages, self.names, self.tz)
            target = target_chars(len(messages), self.max_chars)
            system, contents = digest_request(self.cfg.canon, lines, period(messages, self.tz), len(messages),
                                              target, self.max_chars, self.members)
            text, guarded = await self._think(contents, system, "digest_voice", self.max_chars)
            day = local_now(now, self.tz).date().isoformat()
            if text is None:
                if guarded:  # the same stretch would trip it again: skip it rather than pay for it every 10 minutes
                    self.state = replace(record_sent(self.state, now, day, messages[-1]),
                                         count=today_count(self.state, day))  # nothing sent today (review #7)
                    save_digest_state(self.state_file, self.state)
                    settled()
                    log.warning("digest: dropped by the outgoing guard — %d messages skipped", len(messages))
                    return True
                log.error("digest: no text (%d messages) — retrying later", len(messages))
                return False
            why = await self.send_voice(text, now)
            if not await self.send_text(f"{text_header(messages, self.tz)}\n\n{text}") and why is not None:
                return False  # neither the voice nor the text reached the owner
            self.state = record_sent(self.state, now, day, messages[-1])
            save_digest_state(self.state_file, self.state)
            settled()
            log.info("digest: sent (%d messages, %d chars, %s)", len(messages), len(text),
                     "voice" if why is None else f"text: {why}")
            return True

    async def _think(self, contents: str, system: str, kind: str, cap: int) -> tuple[str | None, bool]:
        """One thinking call, trimmed to `cap`, through the herald's guard: a sentence tying a persona to a banned
        word is removed (`without_outing`, review #1); nothing left → regenerated once. (text, False), or (None, True)
        when the guard left nothing twice, (None, False) on a failure."""
        guarded = False
        await self._typing(True)
        try:
            for _ in range(2):
                out = await self.llm.think(contents, system, model=DIGEST_MODEL, kind=kind)
                if out is None:
                    return None, False
                out = trim_digest(out, cap)
                if not out:
                    log.error("%s: no full sentence within the cap", kind)
                    return None, False
                kept = without_outing(out, self.personas)
                if not kept:
                    guarded = True
                    log.warning("%s: dropped by the outgoing guard", kind)
                    continue
                if kept != out:
                    log.warning("%s: the outgoing guard removed a sentence", kind)
                return kept, False
            return None, guarded
        finally:
            await self._typing(False)

    def month_used(self, now: int) -> int:
        try:
            records, _ = parse_lines(self.usage_file.read_text(encoding="utf-8").splitlines())
        except FileNotFoundError:
            records = []
        except OSError:
            log.error("usage file unreadable — no voice this time")
            return self.monthly_chars + 1
        return month_chars(records, self.cfg.localpart, local_now(now, self.tz).strftime("%Y-%m"))

    async def send_voice(self, text: str, now: int) -> str | None:
        """The digest spoken, as an Element voice message. None when sent; else why it went out as text only."""
        if self.text_only or self.tts is None:
            return self.text_only or "no voice"
        if self.month_used(now) + len(text) > self.monthly_chars:
            return "monthly cap"
        pcm = await self.tts.synth(text)
        self.record_tts(len(text), pcm is not None)
        if pcm is None:
            return "tts failed"
        ogg = await encode_opus(pcm)
        if ogg is None:
            return "encode failed"
        name = f"hermes-{local_now(now, self.tz):%Y%m%d-%H%M}.ogg"
        resp, _ = await self.client.upload(io.BytesIO(ogg), content_type="audio/ogg", filename=name,
                                           filesize=len(ogg))
        if not isinstance(resp, UploadResponse):
            log.error("upload failed: %s", getattr(resp, "status_code", type(resp).__name__))
            return "upload failed"
        content = voice_content(resp.content_uri, len(ogg), duration_ms(pcm), waveform(pcm), text, name)
        return None if await self.send_private(content) else "send failed"

    # --- a question about the history -------------------------------------------------------------------------------
    async def answer(self, question: str) -> bool:
        async with self._busy:
            if await self.ensure_private_room() is None:
                return False
            since = ask_window(self.clock())
            newest_first, complete = await self.fetch(since_ms=since, limit=ASK_MAX)
            if not complete:  # an answer from part of the week could say «not a word» falsely (review #3)
                log.error("ask: the room could not be read")
                return False
            messages = collect(newest_first, since_ms=since, limit=ASK_MAX)
            if not messages:
                await self.send_text(NOTHING_RECENT)
                log.info("ask: nothing in the window")
                return True
            system, contents = ask_request(self.cfg.canon, digest_lines(messages, self.names, self.tz, True),
                                           question, self.members)
            text, _ = await self._think(contents, system, "ask", ANSWER_MAX_CHARS)
            if text is None:
                log.error("ask: no answer (%d messages read)", len(messages))
                return False
            ok = await self.send_text(text)
            log.info("ask: %s (%d messages read)", "answered" if ok else "not sent", len(messages))
            return ok

    # --- the nio adapters -------------------------------------------------------------------------------------------
    async def on_message(self, room: MatrixRoom, event: RoomMessageText) -> None:
        try:
            if not self.started:
                return  # the first sync's backlog: never processed
            what, why = route(room.room_id, event.sender, event.body, self.cfg, self.state.room)
            if what == "count":
                self.new_count += 1  # read, never answered — and no log line per room message
            elif what == "digest":
                log.info("digest: asked by the owner")
                self._spawn(self.digest(asked=True))
            elif what == "ask":
                log.info("ask: a question from the owner")
                self._spawn(self.answer(event.body))
            elif what == "ignored" and why != "purr":
                log.info("ignored: %s (room %s)", why, room.room_id)
        except Exception:
            log.exception("message handler failed (he keeps running)")

    async def on_invite(self, room: MatrixRoom, event: InviteMemberEvent) -> None:
        try:
            if event.state_key != self.cfg.user_id or event.membership != "invite":
                return
            if should_join_invite(room.room_id, event.sender, self.cfg):
                await join_room(self.client, room.room_id)
            else:
                log.info("ignored: invite to %s from %s", room.room_id, event.sender)
                await self.client.room_leave(room.room_id)
        except Exception:
            log.exception("invite handler failed (he keeps running)")

    async def join_pending_invites(self) -> None:
        """Invites from before this start sit in the first sync: Agora's from the owner is joined, any other left."""
        for room_id, room in list((getattr(self.client, "invited_rooms", {}) or {}).items()):
            inviter = getattr(room, "inviter", None)
            if inviter and should_join_invite(room_id, inviter, self.cfg):
                log.info("joining %s (pending invite from owner)", room_id)
                await join_room(self.client, room_id)
            else:
                log.info("ignored: pending invite to %s from %s", room_id, inviter)
                await self.client.room_leave(room_id)

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def tick(self) -> None:
        """One watcher step: a scheduled digest when it is due."""
        now = self.clock()
        if now < self._retry_at or self._busy.locked():
            return
        if self.state.room is None and await self.ensure_private_room() is None:
            self._retry_at = now + RETRY_MS
            return
        if digest_due(now, local_now(now, self.tz).hour, self.state.last_ms, self.every_ms, self.hours,
                      self.new_count, self.min_new) and not await self.digest():
            self._retry_at = self.clock() + RETRY_MS

    async def watcher(self) -> None:
        while True:
            await asyncio.sleep(WATCH_S)
            try:
                await self.tick()
            except Exception:
                log.exception("digest watcher failed (he keeps running)")

    # --- usage ------------------------------------------------------------------------------------------------------
    def record_usage(self, kind: str, model: str, usage, ok: bool) -> None:
        self._append_usage(lambda ts: usage_line(ts, self.cfg.localpart, kind, model, usage, ok))

    def record_tts(self, characters: int, ok: bool) -> None:
        self._append_usage(lambda ts: tts_usage_line(ts, self.cfg.localpart, TTS_MODEL, characters, ok))

    def _append_usage(self, build) -> None:
        try:
            line = build(local_now(self.clock(), self.tz).isoformat(timespec="seconds"))
            self.usage_file.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.usage_file, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            try:
                if stat.S_IMODE(os.fstat(fd).st_mode) != 0o600:
                    os.fchmod(fd, 0o600)
                os.write(fd, (json.dumps(line, ensure_ascii=False) + "\n").encode("utf-8"))
            finally:
                os.close(fd)
        except Exception:
            log.exception("usage line not written (he keeps running)")

    # --- the process ------------------------------------------------------------------------------------------------
    async def start(self) -> None:
        """Login, the first sync (never processed), the pending invites, the private room, the count since the
        last digest — then the callbacks."""
        await login(self.client, self.cfg.localpart, self.cfg.password, self.cfg.state_file)
        first = await self.client.sync(timeout=10000, full_state=True)
        if isinstance(first, SyncError):
            raise RuntimeError(f"first sync failed: {first.message}")
        await self.join_pending_invites()
        await self.ensure_private_room()
        try:
            self.new_count = len((await self.collect_since_point())[0])
        except Exception:
            log.exception("counting the room since the last digest failed (starting from zero)")
        log.info("%s: %d new room messages since the last digest", self.cfg.localpart, self.new_count)
        self.started = True
        self.client.add_event_callback(self.on_message, RoomMessageText)
        self.client.add_event_callback(self.on_invite, InviteMemberEvent)

    async def run(self) -> None:
        await self.start()
        log.info("%s: entering sync_forever", self.cfg.localpart)
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
        sync_task = asyncio.create_task(self.client.sync_forever(timeout=30000))
        watcher = asyncio.create_task(self.watcher())
        stop_task = asyncio.create_task(stop.wait())
        await asyncio.wait({sync_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
        for t in (sync_task, watcher, stop_task, *self._tasks):
            t.cancel()
        await self.client.close()
        log.info("%s: stopped", self.cfg.localpart)
