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
from agents.config import AgentConfig, load_config
from agents.life import current_chapter, life_section, next_chapter
from agents.llm import GeminiClient
from agents.logic import (
    append_history,
    build_instruction,
    build_transcript,
    clean_reply,
    same_message,
    should_handle,
    should_join_invite,
)
from agents.memory import build_summary_request, cap_words, load_memory, save_memory, session_ended
from agents.plans import (
    HORIZONS,
    parse_items,
    plan_request,
    render_plan,
    roll_mutations,
    split_summary,
    strip_tags,
)
from agents.session import load_session, save_session
from agents.turns import bot_streak, decide_reply, is_pass, streak_frees_at
from agents.usage import usage_line
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

OTHER = {"ada": "@bruno:agora.lan", "bruno": "@ada:agora.lan"}


class Agent:
    def __init__(self, cfg: AgentConfig, llm: GeminiClient | None = None) -> None:
        self.cfg = cfg
        self.other = OTHER.get(cfg.localpart)
        self.client = AsyncClient(cfg.homeserver, cfg.user_id)
        self.started = False  # flips True after the first sync; nothing earlier is handled
        self.llm = llm or GeminiClient(sink=self.record_usage)
        self.history: list[tuple[str, str]] = []
        self.history_n = int(os.environ.get("HISTORY_N", "30"))
        self.max_bot_turns = int(os.environ.get("MAX_BOT_TURNS", "2"))
        self.bot_reply_p = float(os.environ.get("BOT_REPLY_P", "0.5"))
        self.reply_delay_s = float(os.environ.get("REPLY_DELAY_S", "4"))
        self.bot_window_ms = int(float(os.environ.get("BOT_WINDOW_S", "600")) * 1000)
        self.timeline: list[tuple[str, int]] = []  # (name, server_ts_ms), parallel to history
        self.rng = random.random  # injectable in tests
        self.names = {cfg.user_id: cfg.name, cfg.owner: "Ich"}
        if self.other:
            self.names[self.other] = "Ада" if "ada" in self.other else "Бруно"
        self.other_name = self.names.get(self.other) if self.other else None
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
        self._last_sent = ""
        self._tasks: set[asyncio.Task] = set()  # strong refs: pending tasks are only weakly referenced

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
            self.history = append_history(self.history, speaker, e.body, self.history_n)
            self.timeline = [*self.timeline, (speaker, int(e.server_timestamp))][-max(self.history_n, 1):]
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
            if room.room_id == self.cfg.room_id:
                # the context window sees every room message, own and the other agent's included
                speaker = self.names.get(event.sender, event.sender)
                self.history = append_history(self.history, speaker, event.body, self.history_n)
                self.timeline = [*self.timeline, (speaker, now_ms)][-max(self.history_n, 1):]
                self.session.append((speaker, event.body))
                self.last_activity_ms = self.clock()
                if len(self.session) > 2 * self.session_max:
                    self.session = self.session[-2 * self.session_max:]  # bounded even if summaries fail
                if (
                    len(self.session) >= self.session_max
                    and not self._summary_lock.locked()
                    and (self.last_attempt_ms is None or self.clock() - self.last_attempt_ms >= 60_000)
                ):
                    self._spawn(self.summarize())  # timeline cap → early summary (rate-limited)
            verdict = should_handle(room.room_id, event.sender, self.cfg, self.other)
            if not verdict.handle:
                log.info("ignored: %s (room %s)", verdict.reason, room.room_id)
                return
            decision = self.decide(event.sender, event.body, now_ms)
            if decision.reason == "streak-limit":
                self.pause_until_window_frees(room.room_id, event.sender, event.body, now_ms)
                return
            if not decision.reply:
                log.info("silent: %s", decision.reason)
                return
            if self._reply_pending:
                log.info("reply: %s — coalesced into the pending reply", decision.reason)
                return
            log.info("reply: %s (in %.1fs)", decision.reason, decision.delay_s)
            # scheduled, so the sync loop keeps running; context is read at fire time
            self._reply_pending = True
            self._spawn(self.reply_later(room.room_id, decision.delay_s))
        except Exception:
            log.exception("message handler failed (bot keeps running)")

    def decide(self, sender: str, text: str, now_ms: int):
        return decide_reply(
            sender, text,
            bot_streak(self.timeline[:-1], "Ich", now_ms, self.bot_window_ms),
            self.cfg, self.other, self.other_name,
            max_bot_turns=self.max_bot_turns,
            bot_reply_p=self.bot_reply_p,
            reply_delay_s=self.reply_delay_s,
            rng=self.rng,
        )

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)  # strong ref: pending tasks are only weakly referenced
        task.add_done_callback(self._tasks.discard)

    def pause_until_window_frees(self, room_id: str, sender: str, text: str, now_ms: int) -> None:
        """The streak limit is a rate, not a lock: resume once the window frees,
        but only if the conversation hasn't moved on in the meantime."""
        frees = streak_frees_at(self.timeline[:-1], "Ich", now_ms, self.bot_window_ms, self.max_bot_turns)
        if frees is None:
            log.info("silent: streak-limit")
            return
        wait_s = (frees - now_ms) / 1000 + 1.0 + self.rng() * max(self.reply_delay_s - 1.0, 0.0)
        log.info("paused: streak-limit; resume check in %.0fs", wait_s)
        self._spawn(self.resume_later(room_id, sender, text, self.timeline[-1], frees, wait_s))

    async def resume_later(
        self, room_id: str, sender: str, text: str, marker: tuple[str, int], at_ms: int, wait_s: float,
    ) -> None:
        try:
            await asyncio.sleep(wait_s)
            if not self.timeline or self.timeline[-1] != marker:
                log.info("resume dropped: the conversation moved on")
                return
            decision = self.decide(sender, text, at_ms)
            if not decision.reply:
                log.info("resume: silent (%s)", decision.reason)
                return
            log.info("resume: %s", decision.reason)
            await self.reply(room_id)
        except Exception:
            log.exception("resume failed (bot keeps running)")

    def build_prompt(self) -> str:
        """The full system instruction for a reply, in contract order."""
        now = local_now(self.clock(), self.tz)
        world = now_line(now, self.location)
        if self.summary_ms is not None:
            world += " " + last_talk_line(local_now(self.summary_ms, self.tz), now)
        life = life_section(self.cfg.life, now.date()) if self.cfg.life else None
        return build_instruction(
            self.cfg.name, self.cfg.canon, self.summary,
            life=life, world=world,
            memories=self.memories_section(now), plans=self.plans_section(now),
            today=self.today_section(now),
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
        try:
            line = usage_line(local_now(self.clock(), self.tz).isoformat(timespec="seconds"),
                              self.cfg.localpart, kind, model, usage, ok)
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
            first = self.first_run(today)
            ok = True
            for d in days_due(today, first, self._dates_in("days"), self.memory_days):
                ok = ok and await self.ensure_day_memory(d)
            day_files = self._dates_in("days")
            for m in weeks_due(today, first, self._dates_in("weeks"), day_files):
                ok = ok and await self.ensure_digest("week", m)
            for ym in months_due(today, first, self._dates_in("months"), day_files):
                ok = ok and await self.ensure_digest("month", ym)
            for y in years_due(today, first, self._dates_in("years"), self._dates_in("months")):
                ok = ok and await self.ensure_digest("year", y)
            if ok:
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

    async def reply_later(self, room_id: str, delay_s: float) -> None:
        try:
            if delay_s > 0:
                await asyncio.sleep(delay_s)
            await self.reply(room_id)
        except Exception:
            log.exception("scheduled reply failed (bot keeps running)")
        finally:
            self._reply_pending = False

    async def reply(self, room_id: str) -> None:
        """Typing on → Gemini → m.text; silence on failure or PASS; typing reset in finally."""
        try:
            await self.client.room_typing(room_id, True)
            try:
                await self.ensure_today(local_now(self.clock(), self.tz))
            except Exception:
                log.exception("today block refresh failed (reply continues)")
            text = await self.llm.generate(build_transcript(self.history), self.build_prompt(), kind="reply")
            if text is None:
                return  # already logged; stay silent
            others = [n for n in {*self.names.values()} if n != self.cfg.name]
            text = clean_reply(text, self.cfg.name, others)
            if text is None:
                log.info("silent: the reply spoke only for others")
                return
            if is_pass(text):
                log.info("silent: model passed")
                return
            if same_message(text, self._last_sent):
                log.info("silent: duplicate of my previous message")
                return
            self._last_sent = text
            await self.client.room_send(
                room_id=room_id,
                message_type="m.room.message",
                content={"msgtype": "m.text", "body": text},
            )
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
            now = self.clock()
            if (
                self.session
                and session_ended(self.last_activity_ms, now, self.idle_ms)
                and (self.last_attempt_ms is None or now - self.last_attempt_ms >= self.idle_ms)
            ):
                await self.summarize()

    async def shutdown(self, timeout_s: float = 20.0) -> None:
        """The shutdown summary, bounded so Ctrl+C never hangs."""
        try:
            await asyncio.wait_for(self.summarize(), timeout=timeout_s)
        except TimeoutError:
            log.error("shutdown summary timed out after %.0fs — keeping the previous one", timeout_s)

    async def run(self) -> None:
        self.summary = load_memory(self.memory_file)
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
        await self.join_pending_invites()
        self._spawn(self.world_tick(force=True))  # startup kick: catch up memories and today's plans
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
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    if len(sys.argv) != 2:
        print("usage: uv run agents/agent.py agents/<name>.toml", file=sys.stderr)
        raise SystemExit(2)
    cfg = load_config(sys.argv[1])
    agent = Agent(cfg)
    asyncio.run(agent.run())


if __name__ == "__main__":
    main()
