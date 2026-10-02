"""The Matrix session file: login once with the password, reuse the token after.

state/<name>.json = {"user_id", "device_id", "access_token"} — 0600, atomic writes.
A corrupt or missing file means a fresh password login (logged), never a crash.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

log = logging.getLogger("agent.session")

FIELDS = ("user_id", "device_id", "access_token")


def load_session(path: Path) -> dict[str, str] | None:
    """Return the stored session, or None when absent or unusable."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError):
        log.warning("session file %s unreadable — falling back to password login", path)
        return None
    if not all(isinstance(data.get(k), str) and data[k] for k in FIELDS):
        log.warning("session file %s malformed — falling back to password login", path)
        return None
    return {k: data[k] for k in FIELDS}


def save_session(path: Path, user_id: str, device_id: str, access_token: str) -> None:
    """Atomic write (tmp + rename), 0600; the token is never logged."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps({"user_id": user_id, "device_id": device_id, "access_token": access_token}),
        encoding="utf-8",
    )
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    log.info("session saved to %s (device %s)", path, device_id)
