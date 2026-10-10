"""The agent: one codebase for both bots; the TOML picks the identity.

v0.5 — echo only. Run: uv run agents/agent.py agents/ada.toml
The nio callbacks stay thin adapters; every decision lives in agents/logic.py.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import signal
import stat
import sys
import time
import urllib.parse
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nio import (
    AsyncClient,
    InviteMemberEvent,
    LoginResponse,
    MatrixRoom,
    MessageDirection,
    RoomMessagesError,
    RoomMessageText,
    SyncError,
)

from agents.chronicle import (
    day_memory_request,
    days_due,
    digest_request,
    layer_label,
    months_due,
    select_layers,
    shares_span,
    today_request,
    weeks_due,
    years_due,
)
from agents.claude_sdk import (
    AuthRefused,
    ClaudeSdkResponder,
    ClaudeStatus,
    check_startup,
    scrub,
    write_status,
)
from agents.config import AgentConfig, load_config
from agents.life import current_chapter, life_section, next_chapter
from agents.llm import GeminiClient
from agents.logic import (
    CLAUDE_BRIEF_DIRECT,
    CREATURE_RULES,
    append_history,
    build_instruction,
    clean_reply,
    outs_a_persona,
    same_message,
    should_handle,
    should_join_invite,
)
from agents.memory import build_summary_request, cap_words, load_memory, save_memory, session_ended
from agents.mood import (
    MOOD_MAX_TOKENS,
    MoodState,
    biorhythms,
    format_biorhythms,
    log_block,
    mood_request,
    parse_birth_date,
    reading_from_log,
    split_resolution,
)
from agents.nudge import (
    COMMAND_MATERIAL,
    HOROSCOPE_MATERIAL,
    NUDGE_RULE,
    TELEGRAM_MATERIAL,
    TELEGRAM_MAX_WORDS,
    load_nudge_state,
    nudge_due,
    nudge_kind,
    parse_hours,
    save_nudge_state,
)
from agents.pastlife import VERBATIM_WORDS, pastlife_section, pick_memory
from agents.plans import (
    HORIZONS,
    parse_items,
    plan_request,
    render_plan,
    roll_mutations,
    split_summary,
    strip_tags,
)
from agents.responder import Turn, responder_for, trim_to_sentence
from agents.roster import Member, load_roster
from agents.runtime import acquire_lock, lock_holder, setup_logging
from agents.session import load_session, save_session
from agents.turns import (
    decide_reply,
    fallback_due,
    fallback_replier,
    is_latest,
    is_purr,
    owner_speakers,
    pending_answers,
    pick_purr,
    reservation_lapses_at,
    still_current,
    strip_pass,
    wave_count,
    wave_frees_at,
)
from agents.usage import sdk_usage_line, usage_line
from agents.world import (
    MONTHS_NOM,
    day_label,
    last_talk_line,
    local_now,
    month_label,
    now_line,
    week_label,
    year_label,
)

log = logging.getLogger("agent")

class Agent:
    def __init__(self, cfg: AgentConfig, llm: GeminiClient | None = None,
                 roster: dict[str, Member] | None = None) -> None:
        self.cfg = cfg
        # the room's members come from the registry (v4.1): nothing in the code names them
        self.roster = roster if roster is not None else load_roster(cfg.simulation, strict_for=cfg.localpart)
        self.me = self.roster.get(cfg.localpart) or Member(cfg.localpart, cfg.user_id, cfg.name, (cfg.name.lower(),))
        self.others = {m.user_id: m for m in self.roster.values() if m.user_id != cfg.user_id}
        self.personas = [m for m in self.others.values() if m.type == "persona"]
        self.client = AsyncClient(cfg.homeserver, cfg.user_id)
        self.started = False  # flips True after the first sync; nothing earlier is handled
        self.started_ms: int | None = None  # when it did (v4.3: the silence before a nudge counts from here at least)
        if cfg.engine == "claude-sdk":  # v4.4: the subscription only — refuse first, then scrub (agents/claude_sdk.py)
            check_startup(os.environ)
            scrub(os.environ)
            self.llm = llm  # no Gemini client: Claude's container has no Gemini key
            self.responder = ClaudeSdkResponder(
                model=os.environ.get("CLAUDE_MODEL", "opus"),
                max_output_tokens=int(os.environ.get("CLAUDE_CODE_MAX_OUTPUT_TOKENS", "0")),  # 0: no cap
                config_dir=os.environ.get("CLAUDE_CONFIG_DIR", "/tmp/claude"),
                status_file=cfg.memory_file.parent / f"{cfg.localpart}.ratelimit.json",
                usage_sink=self.record_sdk_usage, clock=lambda: self.clock(),
                timeout_s=float(os.environ.get("CLAUDE_TIMEOUT_S", "90")))
        else:
            self.llm = llm or GeminiClient(sink=self.record_usage)
            self.responder = responder_for(cfg.engine, self.llm)  # the reply engine seam (v4.1)
        self.reply_max_tokens = int(os.environ.get("REPLY_MAX_TOKENS", "200"))
        self.history: list[tuple[str, str]] = []
        self.history_n = int(os.environ.get("HISTORY_N", "40"))
        # v4.1: MAX_BOT_TURNS counts the message being answered (v1.2's count excluded it: new = old + 1)
        self.max_bot_turns = int(os.environ.get("MAX_BOT_TURNS", "3"))
        self.owner_repliers = int(os.environ.get("OWNER_REPLIERS", "2"))
        self.fallback_s = float(os.environ.get("FALLBACK_S", "30"))
        # v4.2 — the cat (an ambient creature): how often he reacts unasked, how often a reaction is a purr, his cap
        self.cat_react_p = float(os.environ.get("CAT_REACT_P", "0.3"))
        self.cat_purr_p = float(os.environ.get("CAT_PURR_P", "0.8"))
        self.cat_max_words = int(os.environ.get("CAT_MAX_WORDS", "12"))
        self.cat_memory_p = float(os.environ.get("CAT_MEMORY_P", "0.25"))  # v4.3: a past-life fragment in a line
        self.bot_reply_p = float(os.environ.get("BOT_REPLY_P", "0.5"))
        self.reply_delay_s = float(os.environ.get("REPLY_DELAY_S", "4"))
        self.bot_window_ms = int(float(os.environ.get("BOT_WINDOW_S", "600")) * 1000)
        # v4.3 — the cat's initiative: after this much silence, at most so many a day, only in these local hours.
        # Only an agent with `nudge` reads them, so a typo never takes the whole room down (review #7).
        self.nudge_idle_ms, self.nudges_per_day, self.nudge_hours = 0, 0, (0, 0)
        if cfg.can("nudge"):
            self.nudge_hours = parse_hours(os.environ.get("CAT_NUDGE_HOURS", "09-22"))
            self.nudges_per_day = int(os.environ.get("CAT_NUDGES_PER_DAY", "6"))
            self.nudge_idle_ms = int(float(os.environ.get("CAT_NUDGE_IDLE_S", "1200")) * 1000)
            if self.nudge_idle_ms < self.bot_window_ms:  # the silence must empty the wave window
                log.warning("CAT_NUDGE_IDLE_S below BOT_WINDOW_S — using %d s", self.bot_window_ms // 1000)
                self.nudge_idle_ms = self.bot_window_ms
        self.timeline: list[tuple[str, int, str]] = []  # (name, server_ts_ms, event_id), parallel to history
        self.last_owner: tuple[str, str] | None = None  # (event_id, text) of the owner's latest message
        self.rng = random.random  # injectable in tests
        self.names = {cfg.user_id: cfg.name, cfg.owner: "Ich", **{uid: m.name for uid, m in self.others.items()}}
        self.summary: str | None = None  # last-session memory (v2.1)
        self.memory_file = cfg.memory_file
        self.session: list[tuple[str, str]] = []  # every room message since the last summary
        self.session_max = int(os.environ.get("SESSION_MAX_MESSAGES", "200"))
        self.idle_ms = int(float(os.environ.get("SESSION_IDLE_S", "900")) * 1000)
        self.summary_max_words = int(os.environ.get("SUMMARY_MAX_WORDS", "200"))
        self.clock = lambda: int(time.time() * 1000)  # injectable
        self.last_activity_ms: int | None = None
        self.last_attempt_ms: int | None = None
        self._summary_lock = asyncio.Lock()
        self.location = os.environ.get("LOCATION", "Львів, Україна")
        self.tz = os.environ.get("TIMEZONE", "Europe/Kyiv")
        self.summary_ms: int | None = None  # when the last-session summary was written
        self.plan_max_words = int(os.environ.get("PLAN_MAX_WORDS", "120"))
        self.plan_mutation_rate = float(os.environ.get("PLAN_MUTATION_RATE", "0.3"))
        self._gen_lock = asyncio.Lock()
        env = os.environ.get
        self.memory_days = int(env("MEMORY_DAYS", "7"))
        self.memory_weeks = int(env("MEMORY_WEEKS", "4"))
        self.memory_months = int(env("MEMORY_MONTHS", "6"))
        self.max_words = {
            "day": int(env("DAY_MEMORY_MAX_WORDS", "120")),
            "week": int(env("WEEK_MEMORY_MAX_WORDS", "150")),
            "month": int(env("MONTH_MEMORY_MAX_WORDS", "200")),
            "year": int(env("YEAR_MEMORY_MAX_WORDS", "300")),
            "today": int(env("TODAY_MAX_WORDS", "100")),
        }
        self._gen_retry_ms = 0
        self._last_world_check_ms = 0
        self._last_world_day = None
        self._reply_pending = False  # one pending reply per agent; it reads the latest context anyway
        self._pending_trigger: str | None = None  # what the pending reply answers: an agent message, or None
        self._last_sent = ""
        self._tasks: set[asyncio.Task] = set()  # strong refs: pending tasks are only weakly referenced
        self.mood: MoodState | None = None  # v4.2: the day's horoscope (a `mood` agent)
        self._mood_lock = asyncio.Lock()
        self._mood_retry_ms = 0
        self.told: set[int] = set()  # v4.3: the theses retold this run — RAM only, like the context window
        self._nudging = False

    async def login(self) -> None:
        stored = load_session(self.cfg.state_file)
        if stored:
            self.client.restore_login(
                user_id=stored["user_id"],
                device_id=stored["device_id"],
                access_token=stored["access_token"],
            )
            log.info("%s: session restored (device %s)", self.cfg.localpart, stored["device_id"])
            return
        resp = await self.client.login(self.cfg.password, device_name=f"agent-{self.cfg.localpart}")
        if not isinstance(resp, LoginResponse):
            raise RuntimeError(f"login failed: {getattr(resp, 'status_code', resp)}")
        save_session(self.cfg.state_file, resp.user_id, resp.device_id, resp.access_token)
        log.info("%s: logged in with the password; token stored", self.cfg.localpart)

    async def join_room(self, room_id: str) -> bool:
        """Join with an explicit '{}' body: Continuwuity rejects nio's body-less
        POST /join with M_BAD_JSON, so client.join() fails silently."""
        path = f"/_matrix/client/v3/rooms/{urllib.parse.quote(room_id)}/join"
        resp = await self.client.send(
            "POST", path, data="{}",
            headers={
                "Authorization": f"Bearer {self.client.access_token}",
                "Content-Type": "application/json",
            },
        )
        await resp.read()  # consume the body — never leak the connection back unconsumed
        ok = resp.status == 200
        if ok:
            log.info("joined %s", room_id)
        else:
            log.error("join %s failed: HTTP %s", room_id, resp.status)
        return ok

    def seed_context(self, events_newest_first: list) -> int:
        """Restart backfill: room messages become context (history + streak
        timeline), chronologically — never replied to, never re-summarized."""
        texts = [e for e in reversed(events_newest_first) if isinstance(e, RoomMessageText)]
        for e in texts[-self.history_n:]:
            speaker = self.names.get(e.sender, e.sender)
            if e.sender == self.cfg.owner:
                self.last_owner = (str(getattr(e, "event_id", "")), e.body)
            self._add_context(speaker, e.body)
            self.timeline = [*self.timeline, (speaker, int(e.server_timestamp), str(getattr(e, "event_id", "")),
                                              self._purr_in_timeline(e.sender, e.body))][-max(self.history_n, 1):]
        return len(texts[-self.history_n:])

    async def backfill(self, from_token: str) -> None:
        resp = await self.client.room_messages(
            self.cfg.room_id, start=from_token, direction=MessageDirection.back, limit=self.history_n,
        )
        if isinstance(resp, RoomMessagesError):
            log.error("context backfill failed: %s", resp.message)
            return
        n = self.seed_context(list(resp.chunk))
        log.info("%s: context seeded with %d room messages", self.cfg.localpart, n)

    async def join_pending_invites(self) -> None:
        """Invites that arrived before this start sit in the first sync; the
        callback never sees them, so they are handled here once."""
        for room_id, room in list(self.client.invited_rooms.items()):
            inviter = getattr(room, "inviter", None)
            if inviter and should_join_invite(room_id, inviter, self.cfg):
                log.info("joining %s (pending invite from owner)", room_id)
                await self.join_room(room_id)
            else:
                log.info("ignored: pending invite to %s from %s", room_id, inviter)
                await self.client.room_leave(room_id)

    async def on_invite(self, room: MatrixRoom, event: InviteMemberEvent) -> None:
        try:
            if event.state_key != self.cfg.user_id or event.membership != "invite":
                return
            if should_join_invite(room.room_id, event.sender, self.cfg):
                log.info("joining %s (invited by owner)", room.room_id)
                await self.join_room(room.room_id)
            else:
                log.info("ignored: invite to %s from %s", room.room_id, event.sender)
                await self.client.room_leave(room.room_id)
        except Exception:
            log.exception("invite handler failed (bot keeps running)")

    async def on_message(self, room: MatrixRoom, event: RoomMessageText) -> None:
        try:
            if not self.started:
                return  # first-sync backlog: never replay history
            now_ms = int(getattr(event, "server_timestamp", 0) or time.time() * 1000)
            event_id = str(getattr(event, "event_id", "") or f"${now_ms}:{len(self.timeline)}")
            if room.room_id == self.cfg.room_id:
                # the context window sees every room message, own and the other agent's included
                speaker = self.names.get(event.sender, event.sender)
                self._add_context(speaker, event.body)
                self.timeline = [*self.timeline, (speaker, now_ms, event_id,
                                                  self._purr_in_timeline(event.sender, event.body))
                                 ][-max(self.history_n, 1):]
                if event.sender == self.cfg.owner:
                    self.last_owner = (event_id, event.body)
                self.last_activity_ms = self.clock()
                if self.cfg.can("summary") and not self._repeat_purr(self.session, speaker, event.body):
                    self.session.append((speaker, event.body))
                if len(self.session) > 2 * self.session_max:
                    self.session = self.session[-2 * self.session_max:]  # bounded even if summaries fail
                if (
                    self.cfg.can("summary")
                    and len(self.session) >= self.session_max
                    and not self._summary_lock.locked()
                    and (self.last_attempt_ms is None or self.clock() - self.last_attempt_ms >= 60_000)
                ):
                    self._spawn(self.summarize())  # timeline cap → early summary (rate-limited)
            verdict = should_handle(room.room_id, event.sender, self.cfg, self.others)
            if not verdict.handle:
                log.info("ignored: %s (room %s)", verdict.reason, room.room_id)
                return
            decision = self.decide(event.sender, event.body, event_id, now_ms)
            if decision.reason == "wave-limit":
                self.pause_until_window_frees(room.room_id, event.sender, event.body, event_id, now_ms)
                return
            if decision.reason == "owner-chose-others":
                self.maybe_fallback(room.room_id, event.body, event_id)
            if not decision.reply:
                log.info("silent: %s", decision.reason)
                return
            if decision.purr:  # v4.2: a purr is produced in code — zero tokens, no pending reply
                log.info("reply: %s (in %.1fs)", decision.reason, decision.delay_s)
                self._spawn(self.purr_later(room.room_id, decision.delay_s, event_id))
                return
            # An agent-to-agent reply carries its trigger for the fire-time re-check (R3); an answer to the owner
            # carries none. A newer trigger coalesces into the pending reply and becomes what it answers.
            trigger = event_id if event.sender != self.cfg.owner else None
            if self._reply_pending:
                if self._pending_trigger is not None:
                    self._pending_trigger = trigger
                log.info("reply: %s — coalesced into the pending reply", decision.reason)
                return
            log.info("reply: %s (in %.1fs)", decision.reason, decision.delay_s)
            # scheduled, so the sync loop keeps running; context is read at fire time
            self._reply_pending = True
            self._pending_trigger = trigger
            self._spawn(self.reply_later(room.room_id, decision.delay_s))
        except Exception:
            log.exception("message handler failed (bot keeps running)")

    def reserved(self, now_ms: int) -> int:
        """The owner's chosen answers still on their way — they hold their place in the wave until FALLBACK_S.
        Never one for this agent itself: whether it still owes an answer is its own knowledge (code review #2)."""
        if self.last_owner is None:
            return 0
        eid, text = self.last_owner
        chosen = {self.roster[n].name for n in owner_speakers(eid, text, self.roster, self.owner_repliers,
                                                            self.cat_react_p, self.cat_purr_p)}
        chosen.discard(self.cfg.name)
        return pending_answers(self.timeline, eid, chosen, "Ich", now_ms, int(self.fallback_s * 1000))

    def decide(self, sender: str, text: str, event_id: str, now_ms: int):
        return decide_reply(
            sender, text, event_id,
            wave_count(self.timeline, "Ich", now_ms, self.bot_window_ms) + self.reserved(now_ms),
            self.cfg, self.me, self.roster,
            owner_repliers_k=self.owner_repliers,
            react_p=self.cat_react_p,
            purr_p=self.cat_purr_p,
            max_bot_turns=self.max_bot_turns,
            bot_reply_p=self.bot_reply_p,
            reply_delay_s=self.reply_delay_s,
            rng=self.rng,
        )

    def _purr_in_timeline(self, sender: str, text: str) -> bool:
        """Only an agent's line is a purr — the owner's «Мур!» is a message like any other (review #2)."""
        return sender != self.cfg.owner and is_purr(text)

    @staticmethod
    def _repeat_purr(lines: list[tuple[str, str]], speaker: str, text: str) -> bool:
        """A purr right after the same speaker's purr — it collapses into the earlier one (v4.2)."""
        return bool(lines) and lines[-1][0] == speaker and is_purr(text) and is_purr(lines[-1][1])

    def _add_context(self, speaker: str, text: str) -> None:
        """The context window, with consecutive purrs collapsed so they never crowd out the talk."""
        if self._repeat_purr(self.history, speaker, text):
            self.history = [*self.history[:-1], (speaker, text)]
        else:
            self.history = append_history(self.history, speaker, text, self.history_n)

    async def purr_later(self, room_id: str, delay_s: float, event_id: str) -> None:
        try:
            if delay_s > 0:
                await asyncio.sleep(delay_s)
            if self._reply_pending:  # his words are on their way: a purr now would count as his answer (v4.3 review #1)
                log.info("purr dropped: a reply is on its way")
                return
            await self.client.room_send(
                room_id=room_id, message_type="m.room.message",
                content={"msgtype": "m.text", "body": pick_purr(event_id, self.cfg.localpart)},
            )
        except Exception:
            log.exception("purr failed (bot keeps running)")

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)  # strong ref: pending tasks are only weakly referenced
        task.add_done_callback(self._tasks.discard)

    def pause_until_window_frees(self, room_id: str, sender: str, text: str, event_id: str, now_ms: int) -> None:
        """R4 — the wave limit is a rate, not a lock: resume once the window frees,
        but only if the conversation hasn't moved on in the meantime."""
        wave, reserved = wave_count(self.timeline, "Ich", now_ms, self.bot_window_ms), self.reserved(now_ms)
        times = []
        if wave >= self.max_bot_turns:  # the wave itself is full: wait for its oldest turn to age out
            times.append(wave_frees_at(self.timeline, "Ich", now_ms, self.bot_window_ms, self.max_bot_turns))
        if reserved and self.last_owner:  # the owner's pending answers hold it: wait for them to lapse
            times.append(reservation_lapses_at(self.timeline, self.last_owner[0], int(self.fallback_s * 1000)))
        if not times or any(t is None for t in times):
            log.info("silent: wave-limit")
            return
        frees = max(times) + 1
        wait_s = (frees - now_ms) / 1000 + 1.0 + self.rng() * max(self.reply_delay_s - 1.0, 0.0)
        log.info("paused: wave-limit; resume check in %.0fs", wait_s)
        self._spawn(self.resume_later(room_id, sender, text, event_id, frees, wait_s))

    async def resume_later(self, room_id: str, sender: str, text: str, event_id: str, at_ms: int,
                           wait_s: float) -> None:
        try:
            await asyncio.sleep(wait_s)
            if not is_latest(self.timeline, event_id):  # a purr since the pause is no move (review #3)
                log.info("resume dropped: the conversation moved on")
                return
            decision = self.decide(sender, text, event_id, at_ms)
            if not decision.reply:
                log.info("resume: silent (%s)", decision.reason)
                return
            log.info("resume: %s", decision.reason)
            await self.reply(room_id, event_id, at_ms)
        except Exception:
            log.exception("resume failed (bot keeps running)")

    def maybe_fallback(self, room_id: str, text: str, event_id: str) -> None:
        """If no agent answers the owner within FALLBACK_S, the best-ranked unchosen member does — each agent
        checks for itself from the shared timeline, with no coordination."""
        if fallback_replier(event_id, text, self.roster, self.owner_repliers) == self.me.localpart:
            self._spawn(self.fallback_later(room_id, event_id))

    async def fallback_later(self, room_id: str, event_id: str) -> None:
        try:
            await asyncio.sleep(self.fallback_s)
            for _ in range(6):  # busy with another reply: re-arm briefly instead of giving up (code review #3)
                if not fallback_due(self.timeline, event_id):
                    return
                if not self._reply_pending:
                    break
                await asyncio.sleep(5)
            else:
                return
            log.info("reply: fallback — nobody answered the owner")
            self._reply_pending = True
            try:
                await self.reply(room_id, fallback_for=event_id)
            finally:
                self._reply_pending = False
        except Exception:
            log.exception("fallback failed (bot keeps running)")

    def _current(self, trigger: str, at_ms: int | None = None) -> bool:
        """R3 for an agent-to-agent reply: the answered message is still the latest and the wave below the limit."""
        now = at_ms if at_ms is not None else self.clock()
        return still_current(self.timeline, trigger, "Ich", now, self.bot_window_ms, self.max_bot_turns,
                             self.reserved(now))

    def build_prompt(self, pastlife: str | None = None, nudge: str | None = None) -> str:
        """The full system instruction for a reply, in contract order; `pastlife` is a chosen thesis, `nudge` a
        nudge's material and rule (v4.3). An assistant (v4.4, Claude) has no canon: its brief is the instruction."""
        if self.cfg.type == "assistant":
            return CLAUDE_BRIEF_DIRECT
        can = self.cfg.can
        now = local_now(self.clock(), self.tz)
        world = None
        if can("world"):
            world = now_line(now, self.location)
            if self.summary_ms is not None:
                world += " " + last_talk_line(local_now(self.summary_ms, self.tz), now)
        life = life_section(self.cfg.life, now.date()) if can("life") and self.cfg.life else None
        return build_instruction(
            self.cfg.name, self.cfg.canon if can("canon") else "", self.summary if can("summary") else None,
            life=life, world=world,
            memories=self.memories_section(now) if can("chronicle") else None,
            plans=self.plans_section(now) if can("plans") else None,
            today=self.today_section(now) if can("today") else None,
            mood=self.mood_section(now) if can("mood") else None,
            pastlife=pastlife if can("pastlife") else None,
            nudge=nudge if can("nudge") else None,
            rules_extra=CREATURE_RULES if self.cfg.type == "creature" else None,
        )

    # --- v2.2: files under state/ -------------------------------------------------
    def _dir(self, kind: str) -> Path:
        return self.memory_file.parent / f"{self.cfg.localpart}.{kind}"

    def append_journal(self, text: str) -> None:
        """The day's conversation journal: session-only notes with their time."""
        now = local_now(self.clock(), self.tz)
        path = self._dir("days") / f"{now.date().isoformat()}.talk.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(f"[{now:%H:%M}] {text.strip()}\n")
        os.chmod(path, 0o600)

    def _read(self, path: Path) -> str | None:
        try:
            return path.read_text(encoding="utf-8").strip() or None
        except (FileNotFoundError, UnicodeDecodeError, OSError):
            return None

    def plan_paths(self, today) -> dict[str, Path]:
        monday = today - timedelta(days=today.weekday())
        d = self._dir("plans")
        return {
            "year": d / f"year-{today.year}.md",
            "month": d / f"month-{today.year}-{today.month:02d}.md",
            "week": d / f"week-{monday.isoformat()}.md",
            "day": d / f"{today.isoformat()}.md",
        }

    def _previous_plan_path(self, horizon: str, today) -> Path:
        if horizon == "day":
            prev = today - timedelta(days=1)
        elif horizon == "week":
            prev = today - timedelta(days=7)
        elif horizon == "month":
            prev = today.replace(day=1) - timedelta(days=1)
        else:
            prev = today.replace(year=today.year - 1)
        return self.plan_paths(prev)[horizon]

    async def ensure_plans(self, today) -> None:
        """Generate the missing plans for today, coarse to fine; never rewrite one."""
        life = self.cfg.life
        cur = current_chapter(life, today) if life else None
        nxt = next_chapter(life, today) if life else None
        paths = self.plan_paths(today)
        monday = today - timedelta(days=today.weekday())
        labels = {
            "year": year_label(today.year),
            "month": month_label(today.year, today.month),
            "week": week_label(monday),
            "day": day_label(today, today + timedelta(days=3)),  # plain weekday + date
        }
        coarser: list[tuple[str, str]] = []
        for horizon in ("year", "month", "week", "day"):
            path = paths[horizon]
            existing = self._read(path)
            if existing is None:
                n_items = HORIZONS[horizon][0]
                mutations = roll_mutations(n_items, self.plan_mutation_rate, self.rng)
                prev = self._read(self._previous_plan_path(horizon, today))
                yesterday = self._read(self._dir("days") / f"{(today - timedelta(days=1)).isoformat()}.md")
                system, contents = plan_request(
                    horizon, self.cfg.name, self.cfg.canon, labels[horizon],
                    cur.body if cur else "", nxt.opening if nxt else None,
                    coarser, strip_tags(prev) if prev else None, yesterday,
                    mutations, self.plan_max_words,
                )
                text = await self.llm.generate(contents, system, max_output_tokens=self.plan_max_words * 3,
                                               kind="plan")
                if text is None:
                    log.error("plan %s failed — will retry later", horizon)
                    return
                items = parse_items(text)
                if not items:
                    log.error("plan %s came back empty — will retry later", horizon)
                    return
                existing = render_plan(items, mutations, self.plan_max_words)
                save_memory(path, existing)
                log.info("plan %s written (%d items, %d mutated)", horizon, len(items), sum(map(bool, mutations)))
            coarser.append((HORIZONS[horizon][1], strip_tags(existing)))

    def plans_section(self, now) -> str | None:
        today = now.date()
        names = {"year": f"На {today.year} рік", "month": f"На {MONTHS_NOM[today.month - 1]}",
                 "week": "На цей тиждень", "day": "На сьогодні"}
        parts = []
        for horizon, path in self.plan_paths(today).items():
            text = self._read(path)
            if text:
                parts.append(f"{names[horizon]}:\n{strip_tags(text)}")
        return "Твої плани:\n" + "\n\n".join(parts) if parts else None

    # --- v2.2: the chronicle -----------------------------------------------------
    @property
    def usage_file(self) -> Path:
        return self.memory_file.parent / f"{self.cfg.localpart}.usage.jsonl"

    def record_usage(self, kind: str, model: str, usage, ok: bool) -> None:
        """One JSON line per Gemini call (v3.1) — no texts; a write error never blocks."""
        self._append_usage(lambda ts: usage_line(ts, self.cfg.localpart, kind, model, usage, ok))

    def record_sdk_usage(self, kind: str, model: str, usage: dict | None, ok: bool,
                         reported_cost: float | None) -> None:
        """v4.4 — one line per Claude Agent SDK call: always `subscription`, never priced."""
        self._append_usage(lambda ts: sdk_usage_line(ts, self.cfg.localpart, kind, model, usage, ok, reported_cost))

    def _append_usage(self, build) -> None:
        try:
            line = build(local_now(self.clock(), self.tz).isoformat(timespec="seconds"))
            self.usage_file.parent.mkdir(parents=True, exist_ok=True)
            # private from birth (code review #2): created 0600, a looser old file tightened
            fd = os.open(self.usage_file, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            try:
                if stat.S_IMODE(os.fstat(fd).st_mode) != 0o600:
                    os.fchmod(fd, 0o600)
                os.write(fd, (json.dumps(line, ensure_ascii=False) + "\n").encode("utf-8"))
            finally:
                os.close(fd)
        except Exception:
            log.exception("usage line not written (the conversation continues)")

    @property
    def today_file(self) -> Path:
        return self.memory_file.parent / f"{self.cfg.localpart}.today.md"

    def first_run(self, today):
        """The agent's first day — memories are never generated before it."""
        path = self.memory_file.parent / f"{self.cfg.localpart}.first_run.txt"
        text = self._read(path)
        if text:
            return date.fromisoformat(text)
        session = self.memory_file.parent / f"{self.cfg.localpart}.json"
        born = today
        if session.exists():
            born = min(today, local_now(int(session.stat().st_mtime * 1000), self.tz).date())
        save_memory(path, born.isoformat())
        return born

    def _dates_in(self, kind: str) -> set:
        d = self._dir(kind)
        out = set()
        if d.exists():
            for p in d.glob("*.md"):
                if p.name.endswith(".talk.md"):
                    continue
                stem = p.stem
                try:
                    if kind in ("days", "weeks"):
                        out.add(date.fromisoformat(stem))
                    elif kind == "months":
                        y, m = stem.split("-")
                        out.add((int(y), int(m)))
                    else:
                        out.add(int(stem))
                except ValueError:
                    continue
        return out

    def _memory_path(self, kind: str, key) -> Path:
        if kind == "day":
            return self._dir("days") / f"{key.isoformat()}.md"
        if kind == "week":
            return self._dir("weeks") / f"{key.isoformat()}.md"
        if kind == "month":
            return self._dir("months") / f"{key[0]}-{key[1]:02d}.md"
        return self._dir("years") / f"{key}.md"

    def _chapter_body(self, d) -> str:
        life = self.cfg.life
        cur = current_chapter(life, d) if life else None
        return cur.body if cur else ""

    async def ensure_day_memory(self, d) -> bool:
        path = self._memory_path("day", d)
        if path.exists():
            return True  # never rewritten
        today = local_now(self.clock(), self.tz).date()
        prev_days = sorted(x for x in self._dates_in("days") if x < d)[-3:]
        previous = [(layer_label("day", x, today), self._read(self._memory_path("day", x)) or "")
                    for x in prev_days]
        block = self._read(self.today_file)
        block_text = None
        if block and block.startswith(f"<!-- {d.isoformat()}T"):
            block_text = block.split("-->", 1)[1].strip()
        chapter = self._chapter_body(d)
        system, contents = day_memory_request(
            self.cfg.name, self.cfg.canon, d, chapter, previous,
            self._read(self._dir("days") / f"{d.isoformat()}.talk.md"),
            self._read(self.plan_paths(d)["day"]), block_text, self.max_words["day"],
        )
        text = None
        for _attempt in range(2):  # one regeneration when it copies the story
            text = await self.llm.generate(contents, system, max_output_tokens=self.max_words["day"] * 3,
                                           kind="day_memory")
            if text is None:
                log.error("day memory %s failed — will retry later", d)
                return False
            if not shares_span(text, chapter + "\n" + self.cfg.canon):
                break
            log.info("day memory %s copied the story — regenerating", d)
        save_memory(path, cap_words(text, self.max_words["day"]))
        return True

    async def ensure_digest(self, kind: str, key) -> bool:
        path = self._memory_path(kind, key)
        if path.exists():
            return True  # never rewritten
        today = local_now(self.clock(), self.tz).date()
        if kind == "week":
            members = [key + timedelta(days=i) for i in range(7)]
            sources = [("day", d) for d in members if d in self._dates_in("days")]
            plan = self._read(self._dir("plans") / f"week-{key.isoformat()}.md")
            label = layer_label("week", key, today)
        elif kind == "month":
            sources = [("day", d) for d in sorted(self._dates_in("days")) if (d.year, d.month) == key]
            plan = self._read(self._dir("plans") / f"month-{key[0]}-{key[1]:02d}.md")
            label = layer_label("month", key, today)
        else:
            sources = [("month", k) for k in sorted(self._dates_in("months")) if k[0] == key]
            plan = self._read(self._dir("plans") / f"year-{key}.md")
            label = layer_label("year", key, today)
        texts = [(layer_label(k, x, today), self._read(self._memory_path(k, x)) or "") for k, x in sources]
        if not texts:
            return True
        system, contents = digest_request(kind, self.cfg.name, self.cfg.canon, label, texts, plan,
                                          self.max_words[kind])
        text = await self.llm.generate(contents, system, max_output_tokens=self.max_words[kind] * 3,
                                       kind="digest")
        if text is None:
            log.error("%s digest %s failed — will retry later", kind, key)
            return False
        save_memory(path, cap_words(text, self.max_words[kind]))
        return True

    async def world_tick(self, force: bool = False) -> None:
        """Day-boundary work: catch up day memories, digests, then today's plans.
        Cheap when nothing is due; a failure backs off for 10 minutes."""
        if not (self.cfg.can("chronicle") or self.cfg.can("plans")):
            return
        now_ms = self.clock()
        today = local_now(now_ms, self.tz).date()
        if now_ms < self._gen_retry_ms:
            return
        if not force and self._last_world_day == today and now_ms - self._last_world_check_ms < 600_000:
            return
        if self._gen_lock.locked():
            return
        async with self._gen_lock:
            self._last_world_check_ms, self._last_world_day = now_ms, today
            ok = True
            if self.cfg.can("chronicle"):
                first = self.first_run(today)
                for d in days_due(today, first, self._dates_in("days"), self.memory_days):
                    ok = ok and await self.ensure_day_memory(d)
                day_files = self._dates_in("days")
                for m in weeks_due(today, first, self._dates_in("weeks"), day_files):
                    ok = ok and await self.ensure_digest("week", m)
                for ym in months_due(today, first, self._dates_in("months"), day_files):
                    ok = ok and await self.ensure_digest("month", ym)
                for y in years_due(today, first, self._dates_in("years"), self._dates_in("months")):
                    ok = ok and await self.ensure_digest("year", y)
            if ok and self.cfg.can("plans"):
                await self.ensure_plans(today)
                ok = all(p.exists() for p in self.plan_paths(today).values())
            if not ok:
                self._gen_retry_ms = now_ms + 600_000

    def memories_section(self, now) -> str | None:
        today = now.date()
        layers = select_layers(
            today, self.memory_days, self.memory_weeks, self.memory_months,
            self._dates_in("days"), self._dates_in("weeks"), self._dates_in("months"), self._dates_in("years"),
        )
        parts = []
        for kind, key in layers:
            text = self._read(self._memory_path(kind, key))
            if text:
                parts.append(f"{layer_label(kind, key, today)}: {text}")
        return "Твої спогади:\n\n" + "\n\n".join(parts) if parts else None

    async def ensure_today(self, now) -> None:
        """The today block: regenerated when the hour changes; reset at midnight."""
        path = self.today_file
        tag = f"<!-- {now.date().isoformat()}T{now.hour:02d} -->"
        current = self._read(path)
        if current and current.startswith(tag):
            return
        previous = None
        if current and current.startswith(f"<!-- {now.date().isoformat()}T"):
            previous = current.split("-->", 1)[1].strip()
        system, contents = today_request(
            self.cfg.name, self.cfg.canon, now, self._chapter_body(now.date()),
            self._read(self.plan_paths(now.date())["day"]),
            self._read(self._dir("days") / f"{now.date().isoformat()}.talk.md"),
            previous, self.max_words["today"],
        )
        text = await self.llm.generate(contents, system, max_output_tokens=self.max_words["today"] * 3,
                                       kind="today")
        if text is None:
            log.error("today block failed — keeping the previous one")
            return
        save_memory(path, f"{tag}\n{cap_words(text, self.max_words['today'])}")

    def today_section(self, now) -> str | None:
        text = self._read(self.today_file)
        if not text or not text.startswith(f"<!-- {now.date().isoformat()}T"):
            return None  # reset at midnight
        return "Сьогодні:\n" + text.split("-->", 1)[1].strip()

    # --- v4.2: the mood of the day (Lumi's horoscope service) ----------------------------------------------------
    @property
    def mood_file(self) -> Path:
        return self.memory_file.parent / f"{self.cfg.localpart}.mood.log"

    def mood_section(self, now) -> str | None:
        if self.mood is None or self.mood.date != now.date().isoformat():
            return None
        return f"Настрій дня: {self.mood.resolution}"

    async def ensure_mood(self, now) -> None:
        """Once per local day: reuse the day's logged reading, else one model call; a failure means no mood and a
        retry after 10 minutes — never a blocked reply."""
        day = now.date().isoformat()
        if self.mood is not None and self.mood.date == day:
            return
        if self._mood_lock.locked() or self.clock() < self._mood_retry_ms:
            return
        async with self._mood_lock:
            logged = reading_from_log(self._read_raw(self.mood_file) or "", day)
            if logged:
                self.mood = MoodState(day, split_resolution(logged), logged)
                return
            birth = parse_birth_date(self.cfg.natal)
            rhythms = format_biorhythms(biorhythms(birth, now.date())) if birth else None
            system, contents = mood_request(self.cfg.name, self.cfg.natal, day, rhythms)
            reading = await self._mood_reading(contents, system)
            if not reading:
                log.error("mood of the day failed — none today until a retry")
                self._mood_retry_ms = self.clock() + 600_000
                return
            self.mood = MoodState(day, split_resolution(reading), reading)  # kept for the day even if the log fails
            try:
                self.mood_file.parent.mkdir(parents=True, exist_ok=True)
                # private from birth, like the usage file (review #11): created 0600, a looser old file tightened
                fd = os.open(self.mood_file, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
                try:
                    if stat.S_IMODE(os.fstat(fd).st_mode) != 0o600:
                        os.fchmod(fd, 0o600)
                    os.write(fd, log_block(day, reading).encode("utf-8"))
                finally:
                    os.close(fd)
            except OSError as exc:  # review #9: no repeated paid call per reply
                log.error("mood log not written (%s) — the mood is kept for today", type(exc).__name__)

    async def _mood_reading(self, contents: str, system: str) -> str | None:
        """The day's reading — None when the call failed or the cap cut it: a cut reading would be logged and reused
        all day, its half-paragraph standing in for the resolution (review #8)."""
        complete = getattr(self.llm, "complete", None)
        if complete is None:  # a seam with only generate() (older fakes)
            return await self.llm.generate(contents, system, max_output_tokens=MOOD_MAX_TOKENS, kind="mood")
        out = await complete(contents, system, max_output_tokens=MOOD_MAX_TOKENS, kind="mood")
        if out is None:
            return None
        text, finish = out
        if finish == "max_tokens":
            log.error("mood of the day cut by the %d-token cap — not kept", MOOD_MAX_TOKENS)
            return None
        return text

    def _read_raw(self, path: Path) -> str | None:
        """A torn append (disk full, SIGKILL) may leave bad bytes in the log; the day's block is still found."""
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

    async def reply_later(self, room_id: str, delay_s: float) -> None:
        try:
            if delay_s > 0:
                await asyncio.sleep(delay_s)
            for _ in range(3):  # a message that coalesced during generation gets its own pass (code review #1)
                trigger = self._pending_trigger
                if trigger and not self._current(trigger):
                    log.info("silent: moved on")
                    return
                if await self.reply(room_id, trigger) or self._pending_trigger == trigger:
                    return
                log.info("reply: a newer message arrived while generating — answering it")
        except Exception:
            log.exception("scheduled reply failed (bot keeps running)")
        finally:
            self._reply_pending = False

    async def reply(self, room_id: str, trigger: str | None = None, at_ms: int | None = None,
                    fallback_for: str | None = None) -> bool:
        """Typing on → Gemini → m.text; silence on failure or PASS; typing reset in finally. An agent-to-agent
        reply (`trigger`) is re-checked before sending (R3): the room may have moved on during generation.
        Returns whether a message was sent."""
        try:
            await self.client.room_typing(room_id, True)
            if self.cfg.can("today"):
                try:
                    await self.ensure_today(local_now(self.clock(), self.tz))
                except Exception:
                    log.exception("today block refresh failed (reply continues)")
            if self.cfg.can("mood"):
                try:
                    await self.ensure_mood(local_now(self.clock(), self.tz))
                except Exception:
                    log.exception("mood of the day failed (reply continues)")
            memory = self._pick_thesis()
            prompt = self.build_prompt(pastlife_section(self.cfg.theses[memory]) if memory is not None else None)
            text = await self._compose(prompt)
            if text is not None and memory is not None and self._verbatim(text, memory):
                log.info("verbatim memory: regenerating once")  # his own words, never the thesis (v4.3)
                text = await self._compose(prompt)
                if text is not None and self._verbatim(text, memory):
                    log.info("silent: verbatim memory")
                    return False
            if text is None:
                return False  # already logged; stay silent
            if same_message(text, self._last_sent):
                log.info("silent: duplicate of my previous message")
                return False
            if self.cfg.type != "persona" and outs_a_persona(text, self.personas):
                log.info("silent: would out a persona")  # the human-belief rule holds for Ada and Bruno (v4.2)
                return False
            if trigger and not self._current(trigger, at_ms):
                log.info("silent: moved on")
                return False
            if fallback_for and not fallback_due(self.timeline, fallback_for):  # a slow answer landed meanwhile
                log.info("silent: the owner was answered meanwhile")
                return False
            self._last_sent = text
            await self.client.room_send(
                room_id=room_id,
                message_type="m.room.message",
                content={"msgtype": "m.text", "body": text},
            )
            if memory is not None:
                self.told.add(memory)
            return True
        finally:
            await self.client.room_typing(room_id, False)

    async def _compose(self, prompt: str, max_words: int | None = None) -> str | None:
        """One model call → the line as it would be sent, or None (logged): never half a sentence, never another's
        words, PASS honoured, the creature's word cap applied (`max_words` overrides it: a telegram's joke)."""
        reply = await self.responder.respond(Turn(list(self.history), prompt, self.reply_max_tokens, "reply"))
        if reply is None:
            return None  # already logged
        text = reply.text
        if reply.finish == "max_tokens":  # the cap cut it: never send half a sentence
            text = trim_to_sentence(text)
            if text is None:
                log.info("silent: cut mid-sentence")
                return None
        others = [n for n in {*self.names.values()} if n != self.cfg.name]
        text = clean_reply(text, self.cfg.name, others)
        if text is None:
            log.info("silent: the reply spoke only for others")
            return None
        text = strip_pass(text)  # PASS alone → silence; text + PASS → the text only
        if text is None:
            log.info("silent: model passed")
            return None
        if self.cfg.type == "creature":  # v4.2: a small vocabulary, enforced
            text = cap_words(text, max_words or self.cat_max_words)
        return text

    def _pick_thesis(self) -> int | None:
        """v4.3 — with CAT_MEMORY_P, the past-life thesis this spoken line retells: chosen by the latest event and
        the message he answers (`pick_memory`), never one already told this run until all are."""
        if not (self.cfg.can("pastlife") and self.cfg.theses) or self.rng() >= self.cat_memory_p:
            return None
        event_id = str(self.timeline[-1][2]) if self.timeline else ""
        last_text = self.history[-1][1] if self.history else ""
        return self._choose_thesis(event_id, last_text)

    def _choose_thesis(self, event_id: str, last_text: str) -> int | None:
        if len(self.told) >= len(self.cfg.theses):
            self.told.clear()  # every thesis told: a new round, no repeats again until it is done (review #8)
        return pick_memory(event_id, last_text, self.cfg.theses, self.told)

    def _verbatim(self, text: str, memory: int) -> bool:
        return shares_span(text, self.cfg.theses[memory].text, VERBATIM_WORDS)

    # --- v4.3: the cat starts conversations -------------------------------------------------------------------------
    @property
    def nudge_file(self) -> Path:
        return self.memory_file.parent / f"{self.cfg.localpart}.nudge.json"

    async def maybe_nudge(self) -> bool:
        """After a quiet daytime stretch, one line of his own (`nudge_due`); never while a reply is on its way."""
        if not (self.started and self.cfg.can("nudge")) or self._nudging or self._reply_pending:
            return False
        now_ms = self.clock()
        now = local_now(now_ms, self.tz)
        state = load_nudge_state(self.nudge_file, now.date().isoformat())
        # the silence counts from the later of the room's last message and this start: a restart whose backfill
        # failed (an empty timeline) never nudges at once (review #9)
        marks = [int(self.timeline[-1][1])] if self.timeline else []
        last_room_ms = max([*marks, *([self.started_ms] if self.started_ms is not None else [])], default=None)
        if not nudge_due(now_ms, now, last_room_ms, state.last_ms, state.count, self.nudge_idle_ms,
                         self.nudges_per_day, self.nudge_hours):
            return False
        self._nudging = True
        try:
            state.last_ms = now_ms  # every attempt spaces the next one; only a sent nudge counts
            save_nudge_state(self.nudge_file, state)
            _kind, sent = await self.nudge(now, state.count + 1)
            if sent:
                state.count += 1
                state.sent_ms = now_ms
                save_nudge_state(self.nudge_file, state)
            return sent
        finally:
            self._nudging = False

    async def nudge(self, now, n: int) -> tuple[str, bool]:
        """The day's n-th nudge: its material by kind, the reply's checks, and a pre-send check that the room is
        still quiet. Logs the kind and the outcome — never the text."""
        day = now.date().isoformat()
        kind = nudge_kind(day, n)
        if kind == "horoscope" and self.mood_section(now) is None:
            kind = "memory"  # no horoscope today: a memory instead
        assistant = next((m for m in self.others.values() if m.type == "assistant"), None)
        if kind == "telegram" and assistant is None:
            kind = "memory"  # nobody to send a telegram to
        if kind == "memory" and not (self.cfg.can("pastlife") and self.cfg.theses):
            kind = "command"
        memory, max_words = None, None
        if kind == "memory":
            recent = " ".join(text for _, text in self.history[-5:])
            memory = self._choose_thesis(f"nudge:{day}:{n}", recent)
            prompt = self.build_prompt(pastlife_section(self.cfg.theses[memory]), NUDGE_RULE)
        elif kind == "telegram":
            material = TELEGRAM_MATERIAL.format(name=assistant.name, upper=assistant.name.upper())
            prompt = self.build_prompt(nudge=f"{material} {NUDGE_RULE}")
            max_words = TELEGRAM_MAX_WORDS
        else:
            material = COMMAND_MATERIAL if kind == "command" else HOROSCOPE_MATERIAL
            prompt = self.build_prompt(nudge=f"{material} {NUDGE_RULE}")
        marker = self.timeline[-1][2] if self.timeline else None
        room_id = self.cfg.room_id
        try:
            await self.client.room_typing(room_id, True)
            text = await self._compose(prompt, max_words)
            if text is not None and memory is not None and self._verbatim(text, memory):
                text = await self._compose(prompt)  # his own words, never the thesis
                if text is not None and self._verbatim(text, memory):
                    text = None
                    log.info("nudge silent: verbatim memory")
            if text is None:
                log.info("nudge silent (%s)", kind)
                return kind, False
            if is_purr(text):  # every agent would mark it a purr and nobody would answer (v4.3 review #2)
                log.info("nudge silent: purr")
                return kind, False
            if same_message(text, self._last_sent):
                log.info("nudge silent: duplicate of my previous message")
                return kind, False
            if self.cfg.type != "persona" and outs_a_persona(text, self.personas):
                log.info("nudge silent: would out a persona")
                return kind, False
            if (self.timeline[-1][2] if self.timeline else None) != marker:
                log.info("nudge silent: the room spoke meanwhile")
                return kind, False
            self._last_sent = text
            await self.client.room_send(
                room_id=room_id,
                message_type="m.room.message",
                content={"msgtype": "m.text", "body": text},
            )
            if memory is not None:
                self.told.add(memory)
            log.info("nudge sent (%s)", kind)
            return kind, True
        finally:
            await self.client.room_typing(room_id, False)

    async def summarize(self) -> bool:
        """Previous summary + this session → a new summary file. On failure the
        previous summary and the session are kept for a later retry."""
        async with self._summary_lock:
            snapshot = list(self.session)
            if not snapshot:
                return False
            self.last_attempt_ms = self.clock()
            system, contents = build_summary_request(
                self.cfg.name, self.cfg.canon, self.summary, snapshot, self.summary_max_words,
            )
            text = await self.llm.generate(contents, system, max_output_tokens=self.summary_max_words * 3,
                                           kind="summary")
            if text is None:
                log.error("session summary failed — keeping the previous one")
                return False
            note, session_part = split_summary(text)
            note = cap_words(re.sub(r"^\s*Нотатка\s*:\s*", "", note), self.summary_max_words)
            save_memory(self.memory_file, note)
            self.summary = note
            self.summary_ms = self.clock()
            self.append_journal(session_part or note)
            self.session = self.session[len(snapshot):]  # keep what arrived meanwhile
            return True

    async def idle_watcher(self) -> None:
        """Ends a session after SESSION_IDLE_S of silence (retries a failed summary
        only after another idle period)."""
        interval = max(1.0, min(30.0, self.idle_ms / 4000))
        while True:
            await asyncio.sleep(interval)
            try:
                await self.world_tick()
            except Exception:
                log.exception("world tick failed (bot keeps running)")
            if self.cfg.can("mood"):  # the day's horoscope at the day's start, not at the first spoken line (review #7)
                try:
                    await self.ensure_mood(local_now(self.clock(), self.tz))
                except Exception:
                    log.exception("mood of the day failed (bot keeps running)")
            if self.cfg.can("nudge"):  # v4.3: the only agent that ever speaks first
                try:
                    await self.maybe_nudge()
                except Exception:
                    log.exception("nudge failed (bot keeps running)")
            now = self.clock()
            if (
                self.cfg.can("summary")
                and self.session
                and session_ended(self.last_activity_ms, now, self.idle_ms)
                and (self.last_attempt_ms is None or now - self.last_attempt_ms >= self.idle_ms)
            ):
                await self.summarize()

    async def shutdown(self, timeout_s: float = 20.0) -> None:
        """The shutdown summary, bounded so Ctrl+C never hangs."""
        if not self.cfg.can("summary"):
            return
        try:
            await asyncio.wait_for(self.summarize(), timeout=timeout_s)
        except TimeoutError:
            log.error("shutdown summary timed out after %.0fs — keeping the previous one", timeout_s)

    async def run(self) -> None:
        self.summary = load_memory(self.memory_file) if self.cfg.can("summary") else None
        if self.summary:
            self.summary_ms = int(self.memory_file.stat().st_mtime * 1000)
            log.info("%s: last-session memory loaded", self.cfg.localpart)
        await self.login()
        # First sync: only to obtain next_batch; its events are never handled.
        first = await self.client.sync(timeout=10000, full_state=True)
        if isinstance(first, SyncError):
            raise RuntimeError(f"first sync failed: {first.message}")
        try:
            await self.backfill(first.next_batch)  # the context survives a restart
        except Exception:
            log.exception("context backfill failed (starting without it)")
        self.started = True
        self.started_ms = self.clock()
        await self.join_pending_invites()
        self._spawn(self.world_tick(force=True))  # startup kick: catch up memories and today's plans
        if self.cfg.can("mood"):
            self._spawn(self.ensure_mood(local_now(self.clock(), self.tz)))  # the day's horoscope, early
        self.client.add_event_callback(self.on_message, RoomMessageText)
        self.client.add_event_callback(self.on_invite, InviteMemberEvent)
        log.info("%s: entering sync_forever", self.cfg.localpart)
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
        sync_task = asyncio.create_task(self.client.sync_forever(timeout=30000))
        watcher = asyncio.create_task(self.idle_watcher())
        stop_task = asyncio.create_task(stop.wait())
        await asyncio.wait({sync_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
        log.info("%s: stopping — writing the session summary", self.cfg.localpart)
        for t in (sync_task, watcher, stop_task):
            t.cancel()
        await self.shutdown()
        await self.client.close()
        log.info("%s: stopped", self.cfg.localpart)


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: uv run agents/agent.py agents/<name>.toml", file=sys.stderr)
        raise SystemExit(2)
    cfg = load_config(sys.argv[1])
    setup_logging(cfg.localpart)
    lock = acquire_lock(cfg.lock_file)  # held until the process exits (v3.2)
    if lock is None:
        log.error("%s: another instance is running (pid %s) — exiting", cfg.localpart, lock_holder(cfg.lock_file))
        raise SystemExit(1)
    try:
        agent = Agent(cfg)
    except AuthRefused as exc:  # v4.4: the names of what tripped it, never a value
        log.error("%s: %s", cfg.localpart, exc)
        write_status(cfg.memory_file.parent / f"{cfg.localpart}.ratelimit.json",
                     ClaudeStatus(auth=f"refused: {exc}", updated_at=int(time.time())))
        raise SystemExit(1) from None
    asyncio.run(agent.run())


if __name__ == "__main__":
    main()
