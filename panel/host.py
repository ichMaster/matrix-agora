"""Host metrics (v3.3), from /proc (the host's, in a container) and statvfs of the mounted state/."""

from __future__ import annotations

import os
from pathlib import Path


def parse_uptime(text: str) -> int:
    return int(float(text.split()[0]))


def parse_meminfo(text: str) -> tuple[int, int]:
    """(total, used) in bytes — used = MemTotal − MemAvailable."""
    kb = {}
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        if key in ("MemTotal", "MemAvailable"):
            kb[key] = int(rest.split()[0])
    return kb["MemTotal"] * 1024, (kb["MemTotal"] - kb["MemAvailable"]) * 1024


def parse_loadavg(text: str) -> tuple[float, float, float]:
    a, b, c = text.split()[:3]
    return float(a), float(b), float(c)


def parse_os_release(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("PRETTY_NAME="):
            return line.split("=", 1)[1].strip().strip('"')
    return ""


def disk(path: Path) -> tuple[int, int]:
    """(total, free) bytes of the filesystem holding `path`."""
    st = os.statvfs(path)
    return st.f_blocks * st.f_frsize, st.f_bavail * st.f_frsize


def host_metrics(proc: Path = Path("/proc"), state_dir: Path = Path("state"),
                 os_release: Path = Path("/host/os-release")) -> dict:
    out: dict = {}
    for key, fn in (("uptime_s", lambda: parse_uptime((proc / "uptime").read_text())),
                    ("memory", lambda: dict(zip(("total", "used"), parse_meminfo((proc / "meminfo").read_text()), strict=True))),
                    ("load", lambda: list(parse_loadavg((proc / "loadavg").read_text()))),
                    ("disk", lambda: dict(zip(("total", "free"), disk(state_dir), strict=True))),
                    ("os", lambda: parse_os_release(os_release.read_text()))):
        try:
            out[key] = fn()
        except (OSError, ValueError, KeyError, IndexError):
            out[key] = None
    return out
