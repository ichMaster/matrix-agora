"""Process runtime for one agent (v3.2): the single-instance lock and the rotating file log.

The lock is `flock` on state/<name>.lock with the PID inside, held for the process lifetime — a second
instance of the same agent on the same host refuses to start. Logs go to the console and to
state/logs/<name>.log (1 MB × 3) — events only, never tokens, passwords or texts.
"""

from __future__ import annotations

import fcntl
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FORMAT = "%(asctime)s %(name)s %(levelname)s %(message)s"
LOG_MAX_BYTES = 1_000_000
LOG_BACKUPS = 3


class Lock:
    def __init__(self, path: Path, fd: int) -> None:
        self.path = path
        self.fd = fd

    def release(self) -> None:
        fcntl.flock(self.fd, fcntl.LOCK_UN)
        os.close(self.fd)


def acquire_lock(path: Path) -> Lock | None:
    """The lock, or None while another process (or descriptor) holds it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None
    os.ftruncate(fd, 0)
    os.write(fd, f"{os.getpid()}\n".encode())
    return Lock(path, fd)


def lock_holder(path: Path) -> int | None:
    """The PID written by the instance holding the lock, if readable."""
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def setup_logging(localpart: str, log_dir: Path = Path("state/logs")) -> Path:
    """Console + a rotating file; replaces only the handlers this function installed before."""
    log_dir.mkdir(parents=True, exist_ok=True)
    file = log_dir / f"{localpart}.log"
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in [h for h in root.handlers if getattr(h, "_agora", False)]:
        root.removeHandler(h)
        h.close()
    fmt = logging.Formatter(LOG_FORMAT)
    for h in (logging.StreamHandler(),
              RotatingFileHandler(file, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUPS, encoding="utf-8")):
        h.setFormatter(fmt)
        h._agora = True
        root.addHandler(h)
    return file
