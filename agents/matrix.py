"""The Matrix plumbing every member's process shares (v5.1: the speaking agents and the herald).

Login once, then the token (`state/<name>.json`): a password login on every start would make a new device each time.
Join with an explicit '{}' body: Continuwuity rejects nio's body-less POST /join with M_BAD_JSON.
"""

from __future__ import annotations

import logging
import re
import urllib.parse

from nio import AsyncClient, LoginResponse

from agents.session import load_session, save_session

log = logging.getLogger("agent")


async def login(client: AsyncClient, localpart: str, password: str, state_file) -> None:
    """Restore the stored session, or log in with the password once and store the token."""
    stored = load_session(state_file)
    if stored:
        client.restore_login(user_id=stored["user_id"], device_id=stored["device_id"],
                             access_token=stored["access_token"])
        log.info("%s: session restored (device %s)", localpart, stored["device_id"])
        return
    resp = await client.login(password, device_name=f"agent-{localpart}")
    if not isinstance(resp, LoginResponse):
        raise RuntimeError(f"login failed: {getattr(resp, 'status_code', resp)}")
    save_session(state_file, resp.user_id, resp.device_id, resp.access_token)
    log.info("%s: logged in with the password; token stored", localpart)


async def join_room(client: AsyncClient, room_id: str) -> bool:
    """Join with an explicit '{}' body: Continuwuity rejects nio's body-less POST /join with M_BAD_JSON, so
    client.join() fails silently."""
    path = f"/_matrix/client/v3/rooms/{urllib.parse.quote(room_id)}/join"
    resp = await client.send(
        "POST", path, data="{}",
        headers={"Authorization": f"Bearer {client.access_token}", "Content-Type": "application/json"},
    )
    await resp.read()  # consume the body — never leak the connection back unconsumed
    ok = resp.status == 200
    if ok:
        log.info("joined %s", room_id)
    else:
        log.error("join %s failed: HTTP %s", room_id, resp.status)
    return ok


MXC_RE = re.compile(r"^mxc://([A-Za-z0-9.\-:\[\]]+)/([A-Za-z0-9_\-]+)$")


async def download(client: AsyncClient, mxc: str, max_bytes: int) -> bytes | None:
    """v5.2 — a media file through the authenticated media API (`/_matrix/client/v1/media/download`, the Bearer
    token): None for a malformed `mxc://`, a failed request, or a file over `max_bytes` (by its Content-Length or
    by what arrives — never more than `max_bytes + 1` read)."""
    m = MXC_RE.match(mxc or "")
    if not m:
        log.error("download refused: not an mxc:// uri")
        return None
    path = f"/_matrix/client/v1/media/download/{urllib.parse.quote(m[1])}/{urllib.parse.quote(m[2])}"
    resp = await client.send("GET", path, headers={"Authorization": f"Bearer {client.access_token}"})
    try:
        if resp.status != 200:
            log.error("download failed: HTTP %s", resp.status)
            return None
        length = resp.headers.get("Content-Length")
        if length is not None and length.isdigit() and int(length) > max_bytes:
            log.error("download refused: %s bytes over the cap", length)
            return None
        body = await resp.content.read(max_bytes + 1)
        if len(body) > max_bytes:
            log.error("download refused: over the cap")
            return None
        return body
    finally:
        resp.release()
