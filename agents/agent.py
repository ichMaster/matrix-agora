"""The agent: one codebase for both bots; the TOML picks the identity.

v0.5 — echo only. Run: uv run agents/agent.py agents/ada.toml
The nio callbacks stay thin adapters; every decision lives in agents/logic.py.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import re
import signal
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nio import (
    AsyncClient,
    InviteMemberEvent,
    LoginResponse,
    MatrixRoom,
    RoomMessageText,
    SyncError,
)

from agents.config import AgentConfig, load_config
from agents.life import life_section
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
from agents.session import load_session, save_session
from agents.turns import bot_streak, decide_reply, is_pass, streak_frees_at
from agents.world import last_talk_line, local_now, now_line

log = logging.getLogger("agent")

OTHER = {"ada": "@bruno:agora.lan", "bruno": "@ada:agora.lan"}


class Agent:
    def __init__(self, cfg: AgentConfig, llm: GeminiClient | None = None) -> None:
        self.cfg = cfg
        self.other = OTHER.get(cfg.localpart)
        self.client = AsyncClient(cfg.homeserver, cfg.user_id)
        self.started = False  # flips True after the first sync; nothing earlier is handled
        self.llm = llm or GeminiClient()
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

    # v2.2 sections — filled in by the memory/plan machinery (AGORA-020/021)
    def memories_section(self, now) -> str | None:
        return None

    def plans_section(self, now) -> str | None:
        return None

    def today_section(self, now) -> str | None:
        return None

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
            text = await self.llm.generate(build_transcript(self.history), self.build_prompt())
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
            text = await self.llm.generate(contents, system, max_output_tokens=self.summary_max_words * 3)
            if text is None:
                log.error("session summary failed — keeping the previous one")
                return False
            text = cap_words(re.sub(r"^\s*Нотатка\s*:\s*", "", text), self.summary_max_words)
            save_memory(self.memory_file, text)
            self.summary = text
            self.summary_ms = self.clock()
            self.session = self.session[len(snapshot):]  # keep what arrived meanwhile
            return True

    async def idle_watcher(self) -> None:
        """Ends a session after SESSION_IDLE_S of silence (retries a failed summary
        only after another idle period)."""
        interval = max(1.0, min(30.0, self.idle_ms / 4000))
        while True:
            await asyncio.sleep(interval)
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
        self.started = True
        await self.join_pending_invites()
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
