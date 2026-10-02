"""The agent: one codebase for both bots; the TOML picks the identity.

v0.5 — echo only. Run: uv run agents/agent.py agents/ada.toml
The nio callbacks stay thin adapters; every decision lives in agents/logic.py.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import sys
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
from agents.llm import GeminiClient
from agents.logic import (
    append_history,
    build_instruction,
    build_transcript,
    should_handle,
    should_join_invite,
)
from agents.session import load_session, save_session
from agents.turns import bot_streak, decide_reply, is_pass

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
        self.rng = random.random  # injectable in tests
        self.names = {cfg.user_id: cfg.name, cfg.owner: "Ich"}
        if self.other:
            self.names[self.other] = "Ада" if "ada" in self.other else "Бруно"
        self.other_name = self.names.get(self.other) if self.other else None
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
            if room.room_id == self.cfg.room_id:
                # the context window sees every room message, own and the other agent's included
                speaker = self.names.get(event.sender, event.sender)
                self.history = append_history(self.history, speaker, event.body, self.history_n)
            verdict = should_handle(room.room_id, event.sender, self.cfg, self.other)
            if not verdict.handle:
                log.info("ignored: %s (room %s)", verdict.reason, room.room_id)
                return
            decision = decide_reply(
                event.sender, event.body,
                bot_streak(self.history[:-1], "Ich"),
                self.cfg, self.other, self.other_name,
                max_bot_turns=self.max_bot_turns,
                bot_reply_p=self.bot_reply_p,
                reply_delay_s=self.reply_delay_s,
                rng=self.rng,
            )
            if not decision.reply:
                log.info("silent: %s", decision.reason)
                return
            # scheduled, so the sync loop keeps running; context is read at fire time
            task = asyncio.create_task(self.reply_later(room.room_id, decision.delay_s))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        except Exception:
            log.exception("message handler failed (bot keeps running)")

    async def reply_later(self, room_id: str, delay_s: float) -> None:
        try:
            if delay_s > 0:
                await asyncio.sleep(delay_s)
            await self.reply(room_id)
        except Exception:
            log.exception("scheduled reply failed (bot keeps running)")

    async def reply(self, room_id: str) -> None:
        """Typing on → Gemini → m.text; silence on failure or PASS; typing reset in finally."""
        try:
            await self.client.room_typing(room_id, True)
            text = await self.llm.generate(
                build_transcript(self.history),
                build_instruction(self.cfg.name, self.cfg.persona),
            )
            if text is None:
                return  # already logged; stay silent
            if is_pass(text):
                log.info("silent: model passed")
                return
            await self.client.room_send(
                room_id=room_id,
                message_type="m.room.message",
                content={"msgtype": "m.text", "body": text},
            )
        finally:
            await self.client.room_typing(room_id, False)

    async def run(self) -> None:
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
        await self.client.sync_forever(timeout=30000)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    if len(sys.argv) != 2:
        print("usage: uv run agents/agent.py agents/<name>.toml", file=sys.stderr)
        raise SystemExit(2)
    cfg = load_config(sys.argv[1])
    agent = Agent(cfg)
    try:
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        log.info("%s: stopped", cfg.localpart)


if __name__ == "__main__":
    main()
