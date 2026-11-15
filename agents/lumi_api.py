"""v8.1 — Lumi's agora space API v1, as the bridge speaks it (AGORA-265).

The contract is Lumi's: `~/development/lumi/docs/agora-space-api.json`, copied byte for byte as
`tests/fixtures/lumi_agora_api_v1.json` (pinned by `tests/test_lumi_contract.py`). This module holds the pure helpers
(a room line as Lumi hears it, a response's outcome, the health check) and a thin client over an injectable transport,
so every test runs against the fake Lumi server built from the contract (`tests/fake_lumi.py`) and never the network.

Never in a log, a `repr` or an exception: the room's token, a line's text, her reply. Never kept from a response: her
thinking, emotion, intensity or state — only `outcome`, `reply`, `turn_id` and `stats`.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import urllib.parse
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

API_VERSION = 1                          # the `agora` field of /v1/health the bridge expects at least
CHANNEL = "agora"
REGISTER = "voice"                       # v8.1: the room's register (Lumi's v3.3)
CLIENT_HEADER = ("X-Lumi-Client", "agora")
SILENCE = frozenset({409, 429, 500, 502, 503, 504})  # silence in the room, never retried (the contract's `silence`)
NAMED = {401: "wrong token", 403: "token not allowed", 404: "space off", 422: "malformed request"}
TIMEOUT_S = 60.0                         # the bridge's own wait, always above Lumi's 20 s (`limits.timeout_s`)
BATCH_MAX = 200                          # `limits.observe_batch_max`
SPEAKER_MAX = 64                         # Q3: one line, 1–64 characters, no `:`
KEPT = ("outcome", "reply", "turn_id", "stats")  # all the bridge keeps of a turn's response
STATS = ("model", "input_tokens", "output_tokens", "latency_ms")

# (method, path, body | None, headers, timeout_s) → (status, parsed JSON | None); raises TimeoutError past timeout_s
Transport = Callable[[str, str, dict | None, dict, float], Awaitable[tuple[int, dict | None]]]


@dataclass(frozen=True)
class TurnResult:
    """What a turn came to: `reply`, `pass`, `silence:<status>`, `timeout`, `refused:<name>`, `unreachable` or `bad`;
    the reply exactly as Lumi returned it (`reply` alone), her stats (`model`, `input_tokens`, `output_tokens`,
    `latency_ms`) and the bridge's own wall time. Never her thinking."""
    outcome: str
    reply: str = ""
    stats: dict = field(default_factory=dict)
    wall_ms: int | None = None
    status: int | None = None

    @property
    def answered(self) -> bool:
        """Lumi answered the turn (a reply or a pass): her stats are real."""
        return self.outcome in ("reply", "pass")

    def __repr__(self) -> str:  # never her words in a log line or a traceback
        return f"TurnResult(outcome={self.outcome!r}, status={self.status!r}, wall_ms={self.wall_ms!r})"


def classify(status: int | None, body: dict | None, timed_out: bool = False) -> str:
    """A turn's outcome from Lumi's status and body (pure)."""
    if timed_out:
        return "timeout"
    if status is None:
        return "unreachable"
    if status in NAMED:
        return f"refused:{NAMED[status]}"
    if status in SILENCE:
        return f"silence:{status}"
    if status != 200 or not isinstance(body, dict):
        return "bad"
    outcome = body.get("outcome")
    reply = body.get("reply")
    if outcome == "pass" or (outcome == "reply" and isinstance(reply, str) and not reply.strip()):
        return "pass"
    if outcome == "reply" and isinstance(reply, str):
        return "reply"
    return "bad"


def kept(body: dict | None) -> dict:
    """The parts of a turn's response the bridge keeps — never `thinking`, `emotion`, `intensity` or state."""
    if not isinstance(body, dict):
        return {}
    out = {k: body[k] for k in KEPT if k in body}
    stats = out.get("stats")
    out["stats"] = {k: stats[k] for k in STATS if isinstance(stats, dict) and k in stats}
    return out


def health_ok(status: int | None, body: dict | None) -> tuple[bool, str | None, int | None]:
    """Whether the space is up for this bridge: `(ok, why, agora)`. `agora` absent → the space is off; older than
    `API_VERSION` → Lumi is too old; anything else unreadable → named (pure)."""
    if status is None:
        return False, "unreachable", None
    if status != 200 or not isinstance(body, dict):
        return False, f"health {status}", None
    agora = body.get("agora")
    if agora is None:
        return False, "space off", None
    if isinstance(agora, bool) or not isinstance(agora, int):
        return False, "health unreadable", None
    if agora < API_VERSION:
        return False, "too old", agora
    return True, None, agora


REPLY_FALLBACK_RE = re.compile(r"^> ?(\* )?<@[^>\s]+:[^>\s]+> ")  # Element's first fallback line: «> <@user:server> …»


def plain_body(body: str) -> str:
    """Q8 — a line's plain text: the Matrix reply fallback (the leading `> ` quote lines and the blank line after
    them) stripped — only when its first line quotes a sender (`> <@user:server> …`, code review v8.1 #7), so a quote
    the owner typed himself stays as typed; anything else as written (pure)."""
    lines = (body or "").split("\n")
    if not lines or not REPLY_FALLBACK_RE.match(lines[0]):
        return body or ""
    i = 0
    while i < len(lines) and lines[i].startswith(">"):
        i += 1
    if i < len(lines) and lines[i].strip() == "":
        i += 1
    return "\n".join(lines[i:])


def line_ts(origin_server_ts: int, tz: str) -> str:
    """Q9 — ISO-8601 to the second with the room's offset, from the event's `origin_server_ts` (pure)."""
    return datetime.fromtimestamp(origin_server_ts / 1000, UTC).astimezone(ZoneInfo(tz)).isoformat(timespec="seconds")


def speaker_ok(name: str) -> bool:
    """Q3 — a speaker Lumi accepts: one line, 1–64 characters, no `:` (pure)."""
    return isinstance(name, str) and 1 <= len(name) <= SPEAKER_MAX and ":" not in name and "\n" not in name


def observed_line(event_id: str, speaker: str, body: str, origin_server_ts: int, tz: str) -> dict:
    """One room line as `/v1/observe` takes it: `{id, speaker, text, ts}` (pure)."""
    return {"id": event_id, "speaker": speaker, "text": plain_body(body), "ts": line_ts(origin_server_ts, tz)}


class LumiClient:
    """The four routes of API v1 over a transport; the room's token in every call's header, never anywhere else."""

    def __init__(self, base_url: str, token: str, transport: Transport, timeout_s: float = TIMEOUT_S,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.base_url = base_url.rstrip("/")
        self._token = token
        self._transport = transport
        self.timeout_s = timeout_s
        self._clock = clock

    def __repr__(self) -> str:  # never the token
        return f"LumiClient({self.base_url!r})"

    def _headers(self, auth: bool = True) -> dict:
        headers = {CLIENT_HEADER[0]: CLIENT_HEADER[1], "Content-Type": "application/json"}
        if auth:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def _call(self, method: str, path: str, body: dict | None, auth: bool = True,
                    timeout_s: float | None = None) -> tuple[int | None, dict | None]:
        """One call: `(status, body)`, `(None, None)` when Lumi is unreachable. A timeout is raised to the caller."""
        try:
            return await self._transport(method, self.base_url + path, body, self._headers(auth),
                                         timeout_s or self.timeout_s)
        except TimeoutError:
            raise
        except Exception:  # noqa: BLE001 — a refused connection, DNS, a reset: unreachable, never the token
            return None, None

    async def health(self) -> tuple[bool, str | None, int | None]:
        try:
            status, body = await self._call("GET", "/v1/health", None, auth=False, timeout_s=10.0)
        except TimeoutError:
            return False, "unreachable", None
        return health_ok(status, body)

    async def observe(self, lines: list[dict]) -> tuple[int | None, dict | None]:
        """`POST /v1/observe` — at most `BATCH_MAX` lines; `(status, {stored, known})`. A timeout is unreachable."""
        try:
            return await self._call("POST", "/v1/observe", {"channel": CHANNEL, "lines": lines[:BATCH_MAX]},
                                    timeout_s=30.0)
        except TimeoutError:
            return None, None

    async def turn(self, speaker: str, turn_id: str, text: str) -> TurnResult:
        """`POST /v1/turn` with the trigger alone (R1): `{channel, speaker, register, turn_id, text}`."""
        body = {"channel": CHANNEL, "speaker": speaker, "register": REGISTER, "turn_id": turn_id, "text": text}
        start = self._clock()
        try:
            status, raw = await self._call("POST", "/v1/turn", body)
        except TimeoutError:
            return TurnResult("timeout", wall_ms=round((self._clock() - start) * 1000))
        wall = round((self._clock() - start) * 1000)
        outcome = classify(status, raw)
        got = kept(raw)
        return TurnResult(outcome, got.get("reply", "") if outcome == "reply" else "", got.get("stats", {}), wall,
                          status)

    async def retract(self, turn_id: str) -> bool | None:
        """`POST /v1/turn/{turn_id}/retract` (the id URL-encoded): `{retracted}` as given (R8: always a 200), None
        when it could not be read — best effort, never retried."""
        path = f"/v1/turn/{urllib.parse.quote(turn_id, safe='')}/retract"
        try:
            status, body = await self._call("POST", path, None, timeout_s=20.0)
        except TimeoutError:
            return None
        if status != 200 or not isinstance(body, dict) or not isinstance(body.get("retracted"), bool):
            return None
        return body["retracted"]


class AiohttpTransport:
    """The real transport: one aiohttp session, made at the first call and closed at stop."""

    def __init__(self) -> None:
        self._session = None

    async def __call__(self, method: str, url: str, body: dict | None, headers: dict,
                       timeout_s: float) -> tuple[int, dict | None]:
        import aiohttp  # the agent image has it (matrix-nio's own dependency)

        if self._session is None:
            self._session = aiohttp.ClientSession()
        try:
            async with asyncio.timeout(timeout_s), self._session.request(
                    method, url, data=None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8"),
                    headers=headers) as resp:
                try:
                    parsed = await resp.json(content_type=None)
                except (ValueError, aiohttp.ContentTypeError):
                    parsed = None
                return resp.status, parsed if isinstance(parsed, dict) else None
        except TimeoutError:
            raise
        except aiohttp.ClientError as exc:  # its message may hold the URL — never the token, which is a header
            raise ConnectionError(type(exc).__name__) from None

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None
