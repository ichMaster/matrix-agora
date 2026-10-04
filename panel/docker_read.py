"""Docker, read-only (v3.3): container state, uptime and log tails for the registry's services.

Containers are found by their compose labels (project + service), never by a name built from a request.
Docker unreachable → "unknown" everywhere, never an exception to the caller.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

import docker
import requests
from docker.errors import DockerException

DOCKER_ERRORS = (DockerException, OSError, requests.exceptions.RequestException)  # socket gone, daemon down
STOPPED_EXIT_CODES = {0, 137, 143}  # a clean exit, SIGKILL after the grace period, SIGTERM — all a stop
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
OURS = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}),\d+ (\S+) (DEBUG|INFO|WARNING|ERROR|CRITICAL) (.*)$")
ISO = re.compile(r"^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})\S*\s+(.*)$")
LEVEL = re.compile(r"\b(TRACE|DEBUG|INFO|WARN|WARNING|ERROR|CRITICAL)\b")


@dataclass(frozen=True)
class ContainerInfo:
    state: str            # running | restarting | stopped | crashed | missing | unknown
    started_at: str | None = None
    uptime_s: int | None = None
    image: str | None = None
    exit_code: int | None = None


def parse_log_line(raw: str) -> dict:
    """{time, source, level, message} from our format, an ISO-prefixed line, or anything else."""
    line = ANSI.sub("", raw).rstrip()
    if m := OURS.match(line):
        return {"time": m[2], "source": m[3], "level": m[4], "message": m[5]}
    if m := ISO.match(line):
        rest = m[3]
        lv = LEVEL.search(rest[:24])
        level = {"WARN": "WARNING"}.get(lv[1], lv[1]) if lv else ""
        message = rest[lv.end():].strip() if lv else rest
        source, _, tail = message.partition(": ")
        if tail and " " not in source:
            return {"time": m[2], "source": source, "level": level, "message": tail}
        return {"time": m[2], "source": "", "level": level, "message": message}
    return {"time": "", "source": "", "level": "", "message": line}


def _uptime(started_at: str | None, now: datetime) -> int | None:
    """Seconds since docker's StartedAt ("2026-10-04T10:26:02.123456789Z"); None for a never-started one."""
    if not started_at or started_at.startswith("0001"):
        return None
    try:
        start = datetime.fromisoformat(started_at[:19] + "+00:00")
    except ValueError:
        return None
    return max(0, int((now - start).total_seconds()))


def classify(status: str, exit_code: int | None) -> str:
    if status == "running":
        return "running"
    if status == "restarting":  # a restart loop is not "running" (v3.3 review #5)
        return "restarting"
    if status == "dead" or (status == "exited" and exit_code not in STOPPED_EXIT_CODES):
        return "crashed"
    return "stopped"  # exited cleanly, created, paused


class DockerReader:
    def __init__(self, project: str = "server", client_factory=docker.from_env, clock=lambda: datetime.now(UTC)):
        self.project = project
        self._factory = client_factory
        self._client = None
        self.clock = clock

    def _get(self):
        if self._client is None:
            self._client = self._factory()
        return self._client

    def _find(self, service: str):
        labels = [f"com.docker.compose.project={self.project}", f"com.docker.compose.service={service}"]
        found = self._get().containers.list(all=True, filters={"label": labels})
        return found[0] if found else None

    def find(self, service: str):
        """The container of a compose service, or None; docker errors propagate (the supervisor maps them)."""
        return self._find(service)

    def available(self) -> bool:
        try:
            self._get().ping()
            return True
        except DOCKER_ERRORS:
            self._client = None
            return False

    def container(self, service: str) -> ContainerInfo:
        try:
            c = self._find(service)
        except DOCKER_ERRORS:
            self._client = None
            return ContainerInfo("unknown")
        if c is None:
            return ContainerInfo("missing")
        state = c.attrs.get("State", {})
        exit_code = state.get("ExitCode")
        status = classify(c.status, exit_code)
        started = state.get("StartedAt")
        tags = getattr(c.image, "tags", None) or []
        image = tags[0].split("/")[-1].split(":")[0].split("@")[0] if tags else None
        return ContainerInfo(status, started, _uptime(started, self.clock()) if status == "running" else None,
                             image, exit_code)

    def logs(self, service: str, tail: int) -> list[dict] | None:
        """The last `tail` lines, oldest first; None when docker is unreachable or there is no container."""
        try:
            c = self._find(service)
            if c is None:
                return None
            raw = c.logs(tail=tail, stdout=True, stderr=True)
        except DOCKER_ERRORS:
            self._client = None
            return None
        return [parse_log_line(line) for line in raw.decode("utf-8", "replace").splitlines() if line.strip()]

    def running_count(self) -> int | None:
        try:
            return len(self._get().containers.list(filters={"status": "running"}))
        except DOCKER_ERRORS:
            self._client = None
            return None
