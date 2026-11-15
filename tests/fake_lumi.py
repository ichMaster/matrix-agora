"""v8.1 (AGORA-265) — a fake Lumi server built from the contract (`tests/fixtures/lumi_agora_api_v1.json`).

It is a transport for `agents.lumi_api.LumiClient`: each request is checked against the contract (the method and path,
the client header, the room's token, the body's keys) and answered with the contract's own example responses. It can
be scripted to answer any status, a `pass`, a reply of the test's own, a body with her thinking, a delay past the
timeout, or an unreachable Lumi. It keeps observed ids idempotently and answers retracts as R8 says. No network.
"""

from __future__ import annotations

import asyncio
import copy
import json
import urllib.parse
from pathlib import Path

CONTRACT = json.loads((Path(__file__).parent / "fixtures" / "lumi_agora_api_v1.json").read_text(encoding="utf-8"))
EP = CONTRACT["endpoints"]
TOKEN = "room-token-for-tests"  # a made-up token; the real one never reaches a test
BASE = CONTRACT["base_url"]["dev"]
RETRACT_PREFIX = "/v1/turn/"


class ContractError(AssertionError):
    """A request off the contract."""


class FakeLumi:
    def __init__(self, token: str = TOKEN) -> None:
        self.token = token
        self.calls: list[dict] = []          # every request: method, path, body, headers
        self.observed: dict[str, dict] = {}  # id → line, idempotent
        self.stored_turns: set[str] = set()  # turn ids with a stored reply (for retract)
        self.turn_status: list[int] = []     # scripted statuses for the next turns (200 = the contract's example)
        self.turn_bodies: list[dict] = []    # scripted bodies for the next 200 turns
        self.observe_status: list[int] = []  # scripted statuses for the next observes
        self.health_body: dict | None = copy.deepcopy(EP["health"]["response"]["body"])
        self.health_status = 200
        self.delay_s = 0.0                   # a turn's delay (past the client's timeout → TimeoutError)
        self.unreachable = False

    # --- the transport ------------------------------------------------------------------------------------------
    async def __call__(self, method: str, url: str, body: dict | None, headers: dict,
                       timeout_s: float) -> tuple[int, dict | None]:
        if not url.startswith(BASE):
            raise ContractError(f"not Lumi's dev base: {url}")
        path = url[len(BASE):]
        self.calls.append({"method": method, "path": path, "body": copy.deepcopy(body), "headers": dict(headers)})
        if self.unreachable:
            raise ConnectionError("unreachable")
        if headers.get("X-Lumi-Client") != "agora":
            raise ContractError("the client header is missing")
        if path == EP["health"]["request"]["path"]:
            if method != "GET" or "Authorization" in headers:
                raise ContractError("health is an open GET")
            return self.health_status, copy.deepcopy(self.health_body)
        if headers.get("Authorization") != f"Bearer {self.token}":
            return 401, {"detail": "the client token is missing or wrong"}
        if method != "POST":
            raise ContractError(f"{method} {path}")
        if path == EP["observe"]["request"]["path"]:
            return self._observe(body)
        if path == EP["turn"]["request"]["path"]:
            return await self._turn(body, timeout_s)
        if path.startswith(RETRACT_PREFIX) and path.endswith("/retract"):
            return self._retract(path)
        return 403, {"detail": "the room's token reaches only the agora space"}

    # --- the routes ---------------------------------------------------------------------------------------------
    def _observe(self, body: dict | None) -> tuple[int, dict]:
        want = EP["observe"]["request"]["body"]
        if not isinstance(body, dict) or set(body) != set(want) or body["channel"] != "agora":
            raise ContractError(f"observe body keys {sorted(body or {})}")
        line_keys = set(want["lines"][0])
        if not body["lines"] or len(body["lines"]) > CONTRACT["limits"]["observe_batch_max"]:
            raise ContractError(f"observe batch of {len(body['lines'])}")
        for line in body["lines"]:
            if set(line) != line_keys or ":" in line["speaker"] or not 1 <= len(line["speaker"]) <= 64:
                raise ContractError(f"observe line {sorted(line)}")
        if self.observe_status:
            status = self.observe_status.pop(0)
            if status != 200:
                return status, {"detail": "scripted"}
        stored = known = 0
        for line in body["lines"]:
            if line["id"] in self.observed:
                known += 1
            else:
                self.observed[line["id"]] = dict(line)
                stored += 1
        return 200, {"stored": stored, "known": known}

    async def _turn(self, body: dict | None, timeout_s: float) -> tuple[int, dict]:
        want = EP["turn"]["request"]["body"]
        if not isinstance(body, dict) or set(body) != set(want):
            raise ContractError(f"turn body keys {sorted(body or {})}")
        if body["channel"] != "agora" or body["register"] != "voice":
            raise ContractError("turn channel/register")
        if self.delay_s:
            if self.delay_s >= timeout_s:
                raise TimeoutError
            await asyncio.sleep(self.delay_s)
        status = self.turn_status.pop(0) if self.turn_status else 200
        if status != 200:
            errors = {e["status"]: e["body"] for e in CONTRACT["errors"]}
            return status, copy.deepcopy(errors.get(status, {"detail": "error"}))
        out = self.turn_bodies.pop(0) if self.turn_bodies else copy.deepcopy(EP["turn"]["response"]["body"])
        out = {**out, "turn_id": body["turn_id"]}
        if out.get("outcome") == "reply" and out.get("reply"):
            self.stored_turns.add(body["turn_id"])
        return 200, out

    def _retract(self, path: str) -> tuple[int, dict]:
        turn_id = urllib.parse.unquote(path[len(RETRACT_PREFIX):-len("/retract")])
        if "/" in turn_id:
            raise ContractError("the turn id is not URL-encoded")
        if turn_id in self.stored_turns:
            self.stored_turns.discard(turn_id)
            return 200, {"retracted": True}
        return 200, {"retracted": False}

    # --- helpers for the tests ----------------------------------------------------------------------------------
    def paths(self) -> list[str]:
        return [c["path"] for c in self.calls]

    def turns(self) -> list[dict]:
        return [c for c in self.calls if c["path"] == "/v1/turn"]

    def observes(self) -> list[dict]:
        return [c for c in self.calls if c["path"] == "/v1/observe"]
