"""The supervisor's actions (v3.4): start / stop / restart / forget, for the registry's agents and services.

Two seams, both faked in tests: the docker reader (find the container by its compose labels, stop it) and a compose
runner (`docker compose -p <project> -f <file> up -d --no-deps <service>` — a fixed argv; the service name comes
only from the registry). One action at a time per target; every action is logged as an event, never a token.
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from pathlib import Path

from panel.docker_read import DOCKER_ERRORS, DockerReader

STOP_TIMEOUT_S = 30   # docker stop -t 30: SIGTERM → the session summary → SIGKILL after 30 s
COMPOSE_TIMEOUT_S = 180
ACTIONS = ("start", "stop", "restart")
log = logging.getLogger("panel.actions")


class ActionError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


class ComposeRunner:
    def __init__(self, project: str, compose_file: str | None) -> None:
        self.project = project
        self.compose_file = compose_file

    def up(self, service: str) -> None:
        if not self.compose_file or not Path(self.compose_file).is_file():
            raise ActionError(503, "compose is not configured on the panel (STACK_DIR)")
        argv = ["docker", "compose", "-p", self.project, "-f", self.compose_file, "up", "-d", "--no-deps", service]
        try:
            subprocess.run(argv, check=True, capture_output=True, timeout=COMPOSE_TIMEOUT_S)
        except subprocess.TimeoutExpired as exc:
            raise ActionError(504, f"compose up {service} timed out") from exc
        except subprocess.CalledProcessError as exc:
            # why it failed — compose's last stderr line names files and services, not values (code review #2)
            reason = (exc.stderr or b"").decode("utf-8", "replace").strip().splitlines()[-1:] or ["no output"]
            log.warning("compose up %s failed: %s", service, reason[0][:200])
            raise ActionError(502, f"compose up {service} failed") from exc
        except OSError as exc:
            log.warning("compose up %s could not run: %s", service, type(exc).__name__)
            raise ActionError(502, f"compose up {service} failed") from exc


class Supervisor:
    def __init__(self, reader: DockerReader, compose: ComposeRunner, state_dir: Path = Path("state")) -> None:
        self.reader = reader
        self.compose = compose
        self.state_dir = state_dir
        self._busy: set[str] = set()
        self._guard = threading.Lock()

    def busy(self) -> set[str]:
        with self._guard:
            return set(self._busy)

    def _claim(self, target: str) -> None:
        with self._guard:
            if target in self._busy:
                raise ActionError(409, f"{target} is busy with another action")
            self._busy.add(target)

    def _release(self, target: str) -> None:
        with self._guard:
            self._busy.discard(target)

    def _container(self, service: str):
        try:
            return self.reader.find(service)
        except DOCKER_ERRORS as exc:
            raise ActionError(503, "docker unreachable") from exc

    def act(self, service: str, action: str) -> dict:
        """start | stop | restart one compose service (an agent or a simulation service)."""
        if action not in ACTIONS:
            raise ActionError(404, "not found")
        self._claim(service)
        started = time.monotonic()
        try:
            if not self.reader.available():
                raise ActionError(503, "docker unreachable")
            if action == "start":
                if self.reader.container(service).state in ("running", "restarting"):
                    # compose would recreate a running container whose config hash differs (v3.4 review #4)
                    raise ActionError(409, f"{service} is already running")
                self.compose.up(service)   # creates the container when it does not exist yet
            else:
                container = self._container(service)
                if container is None and action == "stop":
                    raise ActionError(409, f"{service} has no container")
                if container is not None:
                    container.stop(timeout=STOP_TIMEOUT_S)
                if action == "restart":
                    self.compose.up(service)
            state = self.reader.container(service).state
            log.info("action %s %s → %s in %.1fs", action, service, state, time.monotonic() - started)
            return {"ok": True, "state": state}
        except ActionError as exc:
            log.warning("action %s %s refused: %s", action, service, exc.detail)
            raise
        finally:
            self._release(service)

    def forget(self, agent: str) -> dict:
        """Delete state/<agent>.memory.md — the last-session summary — for a stopped agent only."""
        self._claim(agent)
        try:
            state = self.reader.container(agent).state
            if state not in ("stopped", "missing"):
                raise ActionError(409, "stopped agents only")
            path = self.state_dir / f"{agent}.memory.md"
            try:
                path.unlink()
                forgotten = True
            except FileNotFoundError:
                forgotten = False
            log.info("forget %s → %s", agent, "deleted the last-session summary" if forgotten else "nothing to forget")
            return {"ok": True, "forgotten": forgotten}
        finally:
            self._release(agent)
