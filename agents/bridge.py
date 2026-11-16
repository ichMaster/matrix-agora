"""v8.1 — the bridge: Лілі in Agora, on Lumi's own `agora` space (AGORA-266).

The bridge is one of our agents with all the room's rules — the filter and allowlist, R1–R4, the wave, the coalescing —
inherited from `Agent`. What is hers is the hearing and the reply path:
- **She hears** (`/v1/observe`): every room line the allowlist lets through, queued and sent in batches, never her own,
  never an edit; after a restart the lines she missed today. Lumi stores them in the room's session, idempotent by id.
- **She answers when named** (`/v1/turn`): the trigger alone (R1) — Lumi builds the room's prompt from what she heard.
  Only a `reply` is posted, exactly as returned; `pass`, every silence status and the bridge's own timeout are silence,
  never retried.
- **What the room never saw is retracted** (`/v1/turn/{id}/retract`): a reply the persona rule drops, a turn the bridge
  gave up on.

Never in a log, the state or a usage line: the room's token, a line's text, her reply, her thinking.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import signal
from contextvars import ContextVar
from pathlib import Path

from dotenv import dotenv_values
from nio import InviteMemberEvent, RoomMessageAudio, RoomMessageText, SyncError

from agents.agent import Agent
from agents.config import AgentConfig
from agents.logic import is_edit, outs_a_persona, should_handle
from agents.lumi_api import (
    BATCH_MAX,
    NAMED,
    TIMEOUT_S,
    AiohttpTransport,
    LumiClient,
    Transport,
    TurnResult,
    observed_line,
    plain_body,
    speaker_ok,
)
from agents.nudge import parse_hours
from agents.roster import Member
from agents.settings import save_json
from agents.turns import ReplyDecision
from agents.usage import lumi_usage_line
from agents.world import local_now

log = logging.getLogger("agent.bridge")

OBSERVE_QUIET_S = 3.0      # Q7: the queue goes after this much quiet …
OBSERVE_LINES = 20         # … or at this many lines, and always before a turn
OBSERVE_QUEUE_MAX = 2000   # bounded while Lumi is away; the oldest dropped beyond it, counted
BACKOFF_S = (10, 30, 60)   # a failed batch is sent again whole after these, then every 60 s
BACKLOG_N = 300            # after a restart: the room's lines paged back, for today's she missed (Q1)
HEALTH_S = 60.0            # `/v1/health` at start and this often
STOP_FLUSH_S = 10.0        # the last flush at a stop, bounded
PRE_TURN_FLUSH_S = 5.0     # code review v8.1 #5: the flush before a turn waits no longer; the turn goes anyway (Q6)

# v8.1 — whether the line on its way through `Agent.on_message` is one she hears: a room `m.text` (the owner's voice by
# Hermes's transcript included), never a member's voiced caption (the same words follow as `m.text`, Q8)
_HEARABLE: ContextVar[bool] = ContextVar("bridge_hearable", default=False)
# code review v8.1 #2 — the line on its way is an edit: it enters her timeline as it enters every agent's (shared input
# for R3 and the wave), but she neither hears it (Q4) nor answers it
_EDIT: ContextVar[bool] = ContextVar("bridge_edit", default=False)


def load_state(path: Path) -> dict:
    """`state/<name>.bridge.json` — missing or corrupt reads as empty."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def lumi_settings(env) -> tuple[str, str]:
    """The address and the room's token: taken out of the environment at once; in dev (`LUMI_ENV_FILE`, the gitignored
    `server/lili.dev.env`) read from that file in-process — never sourced, printed or put in argv."""
    url = env.pop("LUMI_URL", "").strip()
    token = env.pop("LUMI_ROOM_TOKEN", "").strip()
    dev = env.pop("LUMI_ENV_FILE", "").strip()
    if dev:
        values = dotenv_values(dev) if Path(dev).is_file() else {}
        if not values:
            log.warning("lumi: the dev env file %s is missing or empty", dev)
        url = str(values.get("LUMI_URL") or url).strip()
        token = str(values.get("LUMI_ROOM_TOKEN") or token).strip()
    return url, token


class Bridge(Agent):
    def __init__(self, cfg: AgentConfig, roster: dict[str, Member] | None = None,
                 transport: Transport | None = None, env=None) -> None:
        env = os.environ if env is None else env
        url, token = lumi_settings(env)  # first: no other part of the process ever sees them
        super().__init__(cfg, llm=None, roster=roster)
        self.wide_n = BACKLOG_N  # Q1: the backfill pages back far enough for today's missed lines
        self.timeout_s = float(env.get("LUMI_TIMEOUT_S", str(TIMEOUT_S)))
        self.health_s = float(env.get("LUMI_HEALTH_S", str(HEALTH_S)))
        # v8.3 (AGORA-273) — the room's rules for her own line: read only with `initiative` (a typo never takes the room
        # down, as the cat's); the silence never under the wave's window, so her line opens a fresh wave
        self.initiative_idle_ms, self.initiatives_per_day, self.initiative_hours = 0, 0, (0, 0)
        if cfg.can("initiative"):
            self.initiative_hours = parse_hours(os.environ.get("LILI_INITIATIVE_HOURS", "09-23"))
            self.initiatives_per_day = int(os.environ.get("LILI_INITIATIVE_PER_DAY", "4"))
            self.initiative_idle_ms = int(float(os.environ.get("LILI_INITIATIVE_IDLE_S", "1800")) * 1000)
            if self.initiative_idle_ms < self.bot_window_ms:
                log.warning("LILI_INITIATIVE_IDLE_S below BOT_WINDOW_S — using %d s", self.bot_window_ms // 1000)
                self.initiative_idle_ms = self.bot_window_ms
        self.transport = transport or AiohttpTransport()
        self.missing = None if url and token else ("no LUMI_URL" if not url else "no LUMI_ROOM_TOKEN")
        self.lumi = LumiClient(url, token, self.transport, self.timeout_s, clock=lambda: self.mono()) \
            if self.missing is None else None
        if self.missing:
            log.warning("lumi: %s — Лілі stays silent", self.missing)
        self.state_file = self.memory_file.parent / f"{cfg.localpart}.bridge.json"
        self.state = load_state(self.state_file)
        self.state["refused"] = None  # a restart tries again
        if self.missing:  # code review v8.1 #8: the card says why she is silent, by name
            self.state["health"] = {"ok": False, "agora": None, "why": self.missing, "checked_ms": self.clock()}
            self._save()
        self.healthy, self.health_why = False, "not checked yet"
        self.refused: str | None = None
        self.queue: list[tuple[dict, int]] = []  # (the line as observe takes it, its time in ms)
        self.dropped = 0
        self._last_line_ms = 0
        self._fails = 0
        self._retry_at = 0
        self._flush_lock = asyncio.Lock()

    # --- the state ---------------------------------------------------------------------------------------------------
    def _save(self) -> None:
        try:
            save_json(self.state_file, self.state)
        except OSError:
            log.exception("bridge state not written (she keeps running)")

    def _today(self) -> str:
        return local_now(self.clock(), self.tz).date().isoformat()

    def _lumi_closed(self) -> str | None:
        """Why no call goes to Lumi now: no address or token, a refused token, the space off or unreachable."""
        if self.lumi is None:
            return self.missing
        if self.refused:
            return f"refused ({self.refused})"
        if not self.healthy:
            return self.health_why
        return None

    async def check_health(self) -> bool:
        if self.lumi is None:
            return False
        ok, why, agora = await self.lumi.health()
        if ok != self.healthy or why != self.health_why:
            log.info("lumi: %s", f"reachable · agora {agora}" if ok else why)
        self.healthy, self.health_why = ok, why
        self.state["health"] = {"ok": ok, "agora": agora, "why": why, "checked_ms": self.clock()}
        self._save()
        return ok

    # --- she hears ---------------------------------------------------------------------------------------------------
    async def on_message(self, room, event) -> None:
        edit = is_edit(event)  # Q4: only new lines are heard — but an edit is in every agent's timeline, so in hers
        hearable, editing = _HEARABLE.set(isinstance(event, RoomMessageText) and not edit), _EDIT.set(edit)
        try:
            await super().on_message(room, event)
        finally:
            _EDIT.reset(editing)
            _HEARABLE.reset(hearable)

    def decide(self, sender: str, text: str, event_id: str, now_ms: int, resumed: bool = False):
        if _EDIT.get():  # code review v8.1 #2: never a turn on an edit (Lumi knows new lines alone, Q4)
            return ReplyDecision(False, reason="edit")
        return super().decide(sender, text, event_id, now_ms, resumed)

    def on_room_line(self, sender: str, text: str, event_id: str, ts_ms: int) -> None:
        if not _HEARABLE.get() or sender == self.cfg.user_id or self.lumi is None:  # code review v8.1 #8: nowhere to go
            return
        self._queue(sender, text, event_id, ts_ms)
        if len(self.queue) >= OBSERVE_LINES and not self._flush_lock.locked():  # code review v8.1 #5: one at a time
            self._spawn(self.flush())

    def _queue(self, sender: str, text: str, event_id: str, ts_ms: int) -> None:
        speaker = self.names.get(sender, sender)
        if not event_id or not speaker_ok(speaker):
            log.info("observe: a line passed over (no id or an unfit speaker)")
            return
        if any(line["id"] == event_id for line, _ in self.queue):
            return
        self.queue.append((observed_line(event_id, speaker, text, ts_ms, self.tz), ts_ms))
        self._last_line_ms = self.clock()
        if len(self.queue) > OBSERVE_QUEUE_MAX:
            over = len(self.queue) - OBSERVE_QUEUE_MAX
            self.queue = self.queue[over:]
            self.dropped += over
            log.warning("observe: the queue is full — %d oldest lines dropped so far", self.dropped)

    def seed_context(self, events_newest_first: list) -> int:
        """The room's context as every agent seeds it; then (Q1) the lines she missed — since the last one she
        observed, today's at most, oldest first, with their own time."""
        n = super().seed_context(events_newest_first)
        seen = self.state.get("observed") or {}
        since = seen.get("last_ts_ms") if isinstance(seen.get("last_ts_ms"), int) else 0
        today = self._today()
        missed = 0
        for e in reversed(events_newest_first):
            if not isinstance(e, RoomMessageText) or is_edit(e):
                continue
            line = self._heard(e)
            ts = int(getattr(line, "server_timestamp", 0) or 0)
            eid = str(getattr(line, "event_id", "") or "")
            if ts < since or eid == seen.get("last_id") or local_now(ts, self.tz).date().isoformat() != today:
                continue
            if not should_handle(self.cfg.room_id, line.sender, self.cfg, self.others).handle:
                continue
            self._queue(line.sender, line.body, eid, ts)
            missed += 1
        if missed:
            log.info("observe: %d lines of today to catch up on", missed)
        return n

    async def flush(self, force: bool = False) -> bool:
        """Send the queue to `/v1/observe`, at most `BATCH_MAX` lines a call; a failed batch stays whole and is sent
        again after the backoff (`force`: before a turn, once, whatever the backoff)."""
        if not self.queue:
            return True
        if self._lumi_closed() or (not force and self.clock() < self._retry_at):
            return False
        async with self._flush_lock:
            # code review v8.1 #5: a flush that waited on the lock reads the backoff and the state again
            if self._lumi_closed() or (not force and self.clock() < self._retry_at):
                return False
            while self.queue:
                batch = self.queue[:BATCH_MAX]
                status, body = await self.lumi.observe([line for line, _ in batch])
                ids = {line["id"] for line, _ in batch}
                if status == 200:
                    self.queue = [q for q in self.queue if q[0]["id"] not in ids]
                    self._fails, self._retry_at = 0, 0
                    self._observed(batch, body)
                    continue
                if status == 422:  # malformed: it would fail for good — dropped, by name
                    self.queue = [q for q in self.queue if q[0]["id"] not in ids]
                    log.warning("observe: %d lines dropped (%s)", len(batch), NAMED[422])
                    continue
                if status in (401, 403):
                    self._refuse(NAMED[status])
                elif status == 404:
                    self.healthy, self.health_why = False, NAMED[404]
                    log.warning("observe: %s — waiting for the space", NAMED[404])
                else:
                    self._fails += 1
                    wait = BACKOFF_S[min(self._fails, len(BACKOFF_S)) - 1]
                    self._retry_at = self.clock() + wait * 1000
                    log.info("observe: failed (%s) — %d lines kept, again in %ds",
                             "unreachable" if status is None else status, len(self.queue), wait)
                return False
        return True

    def _observed(self, batch: list[tuple[dict, int]], body: dict | None) -> None:
        today = self._today()
        seen = self.state.get("observed") or {}
        count = seen.get("count", 0) if seen.get("day") == today and isinstance(seen.get("count"), int) else 0
        last = max(batch, key=lambda q: q[1])
        if last[1] >= (seen.get("last_ts_ms") or 0):
            seen = {**seen, "last_ts_ms": last[1], "last_id": last[0]["id"]}
        self.state["observed"] = {**seen, "day": today, "count": count + len(batch)}
        self._save()
        stored = body.get("stored") if isinstance(body, dict) else None
        log.info("observe: %d lines (%s new)", len(batch), stored if isinstance(stored, int) else "?")

    def _refuse(self, name: str) -> None:
        if self.refused != name:
            log.error("lumi: %s — no more calls until a restart", name)
        self.refused = name
        self.state["refused"] = name
        self._save()

    # --- she answers -------------------------------------------------------------------------------------------------
    def _line_at(self, event_id: str) -> tuple[str, str] | None:
        """The trigger's speaker and its own text, from the room's timeline (nothing earlier is ever sent, R1)."""
        text = self._texts.get(event_id)
        if text is None:
            return None
        for speaker, _ts, eid, *_ in reversed(self.timeline):
            if eid == event_id:
                return speaker, text
        return None

    async def reply(self, room_id: str, trigger: str | None = None, at_ms: int | None = None,
                    fallback_for: str | None = None, delay_ms: int | None = None) -> bool:
        """One room turn of hers: R3 was checked before (`reply_later`); after the call the persona rule alone may drop
        her reply — and then it is retracted, as is a turn the bridge gave up on."""
        # v8.2 (AGORA-270): a fallback turn answers the owner's line it stands in for, never a newer one
        answered = trigger or fallback_for or (self.last_owner[0] if self.last_owner else "")
        why = self._lumi_closed()
        if why:
            log.info("silent: lumi %s", why)
            self._count("silent")  # code review v8.2 #1: a chosen turn counts once, whatever came of it
            return False
        found = self._line_at(answered) if answered else None
        if found is None or not speaker_ok(found[0]):
            log.info("silent: the trigger is not in the room's window")
            self._count("silent")
            return False
        speaker, text = found
        try:
            await self.client.room_typing(room_id, True)
            try:  # Q6: the lines before the trigger first; if it fails or is slow, the turn still goes
                await asyncio.wait_for(self.flush(force=True), PRE_TURN_FLUSH_S)  # code review v8.1 #5: bounded
            except TimeoutError:
                log.info("observe: still sending before the turn — the turn goes on")
            why = self._lumi_closed()  # code review v8.1 #6: the flush may have met a refused token or the space off
            if why:
                log.info("silent: lumi %s", why)
                self._count("silent")
                return False
            got = await self.lumi.turn(speaker, answered, plain_body(text))
            self._turn_done(got)
            if got.outcome == "timeout":
                await self._retract(answered, "the bridge's own timeout")
                self._count("silent")
                return False
            if got.outcome.startswith("refused:"):
                name = got.outcome.split(":", 1)[1]
                if got.status in (401, 403):
                    self._refuse(name)
                elif got.status == 404:
                    self.healthy, self.health_why = False, name
                log.info("silent: lumi %s", name)
                self._count("silent")
                return False
            if got.outcome in ("bad", "unreachable"):  # code review v8.1 #4: Lumi may have stored a reply we never got
                await self._retract(answered, f"lumi {got.outcome}")
                self._count("silent")
                return False
            if got.outcome != "reply":
                log.info("silent: lumi %s", got.outcome)
                self._count("pass" if got.outcome == "pass" else "silent")
                return False
            if outs_a_persona(got.reply, self.personas):  # the human-belief rule holds for the room's people (v4.2)
                await self._retract(answered, "would out a persona")
                self._count("silent")
                return False
            try:
                posted = await self.send_line(room_id, got.reply, answered, answering=answered)  # exactly as returned
            except Exception as exc:  # noqa: BLE001 — code review v8.1 #4: what the room never saw leaves her memory
                posted = None
                log.warning("send failed (%s)", type(exc).__name__)
            if posted is None:
                await self._retract(answered, "the room never got it")
                self._count("silent")
                return False
            self._count("reply")
            asked = self._event_at(answered)
            self.record_answer("agora", "matrix", asked[1] if asked else "none", asked[0] if asked else None,
                               delay_ms, "lumi", [])
            return True
        finally:
            await self.client.room_typing(room_id, False)

    def _count(self, kind: str) -> None:
        """v8.2 (AGORA-271) — today's turns by what came of them: `reply` (posted), `pass` (Lumi's), `silent` (anything
        else: busy, the cap, a timeout, unreachable, refused, off the contract, the persona drop, a failed send); reset
        at the room's midnight. Counts only, never a text."""
        today = self._today()
        turns = self.state.get("turns") if isinstance(self.state.get("turns"), dict) else {}
        if turns.get("day") != today:
            turns = {"day": today, "reply": 0, "pass": 0, "silent": 0}
        turns[kind] = int(turns.get(kind, 0)) + 1
        self.state["turns"] = turns
        self._save()

    def _turn_done(self, got: TurnResult) -> None:
        log.info("turn: %s in %s ms", got.outcome, got.wall_ms)
        self.state["last_turn"] = {"at_ms": self.clock(), "outcome": got.outcome, "latency_ms": got.wall_ms}
        self._save()
        self._append_usage(lambda ts: lumi_usage_line(ts, self.cfg.localpart, got.stats if got.answered else None,
                                                      got.answered, got.wall_ms))

    async def _retract(self, turn_id: str, why: str) -> None:
        """Best effort, never retried: what the room never saw leaves her memory (R8: always a 200)."""
        retracted = await self.lumi.retract(turn_id)
        log.info("silent: %s — retracted: %s", why, "unknown" if retracted is None else str(retracted).lower())

    # --- the process -------------------------------------------------------------------------------------------------
    async def health_loop(self) -> None:
        while True:
            await asyncio.sleep(self.health_s)
            try:
                if not self.refused:
                    await self.check_health()
            except Exception:
                log.exception("health check failed (she keeps running)")

    async def flush_loop(self) -> None:
        while True:
            await asyncio.sleep(1.0)
            try:
                if self.queue and self.clock() - self._last_line_ms >= OBSERVE_QUIET_S * 1000:
                    await self.flush()
            except Exception:
                log.exception("observe failed (she keeps running)")

    async def run(self) -> None:
        await self.login()
        first = await self.client.sync(timeout=10000, full_state=True)  # never processed
        if isinstance(first, SyncError):
            raise RuntimeError(f"first sync failed: {first.message}")
        try:
            await self.check_health()
        except Exception:
            log.exception("health check failed (starting without it)")
        try:
            await self.backfill(first.next_batch)  # the room's context, and today's lines she missed
        except Exception:
            log.exception("context backfill failed (starting without it)")
        self.started = True
        self.started_ms = self.clock()
        await self.join_pending_invites()
        self.client.add_event_callback(self.on_message, RoomMessageText)
        self.client.add_event_callback(self.on_audio, RoomMessageAudio)
        self.client.add_event_callback(self.on_invite, InviteMemberEvent)
        log.info("%s: entering sync_forever", self.cfg.localpart)
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
        sync_task = asyncio.create_task(self.client.sync_forever(timeout=30000))
        stop_task = asyncio.create_task(stop.wait())
        loops = [asyncio.create_task(self.health_loop()), asyncio.create_task(self.flush_loop())]
        await asyncio.wait({sync_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
        log.info("%s: stopping", self.cfg.localpart)
        for t in (sync_task, stop_task, *loops):
            t.cancel()
        with contextlib.suppress(Exception, TimeoutError):
            async with asyncio.timeout(STOP_FLUSH_S):
                await self.flush(force=True)
        for t in list(self._tasks):
            t.cancel()
        close = getattr(self.transport, "close", None)
        if close is not None:
            with contextlib.suppress(Exception):
                await close()
        await self.client.close()
        log.info("%s: stopped", self.cfg.localpart)
