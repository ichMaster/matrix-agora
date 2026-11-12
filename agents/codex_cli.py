"""v7.4 (AGORA-252) — `codex-gpt-6.1sol`: a companion's answer on GPT-6.1 Sol through the Codex CLI, on the owner's
ChatGPT plan, as the Claude CLI runs on his Max plan. One `codex exec --json` process per answer; the answer only.

- **Her prompt:** her whole instruction replaces Codex's own (`model_instructions_file`, a 0600 file removed after the
  call); the transcript goes in by stdin — never a text on argv, in a log or on disk (`--ephemeral`, no history).
- **No tools:** a read-only sandbox, no approvals, the shell, file edits, images, the web, MCP, apps, plugins, skills
  and the rest off, an empty working folder and no `AGENTS.md`; a run whose events show a tool is a failed answer.
- **Never an API key:** the login is forced to ChatGPT, the CLI gets an environment with no secret in it, and its own
  `login status` must say ChatGPT — any other login blocks the client until a restart. Not signed in: the choice
  answers nothing and is looked at again every `STATUS_TTL_S`, so a sign-in works with no restart.
- **Its credentials** live in `CODEX_HOME` = `state/<name>.codex/` (0700), signed in once by the owner
  (`codex login --device-auth`); never printed, logged, put in an image or in a test.
- **Its limit:** a ChatGPT usage limit mutes it for `LIMIT_MUTE_S`, and her answers go to her Gemini meanwhile (as at
  the Max limit, v7.1); a refusal is a `LAST_BLOCK` refusal; a timeout (`CODEX_TIMEOUT_S`) or an error is silence.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import tempfile
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agents.claude_sdk import LAST_SERVED
from agents.gemini_cache import SEPARATOR
from agents.llm import LAST_BLOCK, refusal_marker
from agents.logic import split_prompt
from agents.responder import ANSWER_KINDS
from agents.usage import PROMPT_SLOW

log = logging.getLogger("agent.codex")

MODEL = "gpt-6.1-sol"
EFFORTS = ("low", "medium", "high")
BINARY_VAR = "CODEX_BIN"
STATUS_TTL_S = 300      # not signed in: looked at again so often
STATUS_TIMEOUT_S = 30   # its `login status`, at most so long
LIMIT_MUTE_S = 3600     # a usage limit with no time named: an hour, as Claude's (v4.4)
# every tool and side door Codex has, off (`codex features list`, 0.167.1); the sandbox is read-only besides
FEATURES_OFF = ("shell_tool", "unified_exec", "view_image", "image_generation", "apps", "plugins", "multi_agent",
                "browser_use", "computer_use", "goals", "hooks", "skill_search", "sleep_tool", "tool_suggest",
                "workspace_dependencies", "code_mode_host")
# anything else an item is, is a tool; code review v7.4 #9: a plan (`todo_list`) acts on nothing — not a tool
QUIET_ITEMS = frozenset({"agent_message", "reasoning", "error", "todo_list"})
LIMIT_RE = re.compile(r"usage limit|rate limit|too many requests|\b429\b", re.IGNORECASE)


@dataclass
class Outcome:
    """What one run's JSON events say (pure): the answer, its usage, a tool used, the failure, a limit."""
    text: str = ""
    usage: dict = field(default_factory=dict)
    tools: list[str] = field(default_factory=list)
    failed: str | None = None
    limit: bool = False


def parse_events(lines: list[str]) -> Outcome:
    """`codex exec --json`'s events, oldest first → the run's `Outcome`; a line that is not JSON is skipped."""
    out = Outcome()
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        kind = event.get("type")
        if kind == "item.completed" and isinstance(event.get("item"), dict):
            item = event["item"]
            if item.get("type") == "agent_message" and isinstance(item.get("text"), str):
                out.text = item["text"]
            elif item.get("type") not in QUIET_ITEMS:
                out.tools.append(str(item.get("type")))
        elif kind == "item.started" and isinstance(event.get("item"), dict) \
                and event["item"].get("type") not in QUIET_ITEMS:
            out.tools.append(str(event["item"].get("type")))
        elif kind == "turn.completed" and isinstance(event.get("usage"), dict):
            u = event["usage"]
            out.usage = {"input_tokens": u.get("input_tokens"), "cached_tokens": u.get("cached_input_tokens"),
                         "output_tokens": u.get("output_tokens")}
        elif kind == "turn.failed":
            message = str((event.get("error") or {}).get("message", ""))
            out.failed = "limit" if LIMIT_RE.search(message) else "error"
            out.limit = out.failed == "limit"
    return out


def run_args(binary: str, work: Path, effort: str, instructions: Path) -> list[str]:
    """The run's argv (pure): no text in it — her instruction by its file's path, the transcript by stdin."""
    args = [binary, "exec", "--json", "--ephemeral", "--skip-git-repo-check", "--ignore-rules", "--ignore-user-config",
            "-s", "read-only", "-C", str(work), "-m", MODEL,
            "-c", "forced_login_method=chatgpt", "-c", "approval_policy=never",
            "-c", f"model_reasoning_effort={effort}", "-c", f'model_instructions_file="{instructions}"',
            "-c", "web_search=disabled", "-c", "project_doc_max_bytes=0", "-c", "history.persistence=none",
            "-c", "mcp_servers={}"]
    for feature in FEATURES_OFF:
        args += ["--disable", feature]
    return [*args, "-"]


def clean_env(home: Path, work: Path) -> dict[str, str]:
    """The CLI's whole environment: its home, its working folder, a path and a locale — no secret of any kind."""
    return {"CODEX_HOME": str(home), "HOME": str(work), "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "LANG": "C.UTF-8"}


class CodexAnswers:
    engine = "codex"

    def __init__(self, *, home: Path, sink: Callable[..., None] | None, effort: str = "medium",
                 binary: str = "codex", work: Path | None = None, timeout_s: float = 180, gemini: Any = None,
                 spawn: Callable[..., Any] = asyncio.create_subprocess_exec,
                 mono: Callable[[], float] = time.monotonic) -> None:
        self.reply_model = MODEL
        self.effort = effort if effort in EFFORTS else "medium"
        # code review v7.4 #2: absolute — the CLI runs in its work folder, and `state/<name>.codex` from there is nowhere
        self.home, self.binary, self.timeout_s, self.gemini = Path(home).resolve(), binary, timeout_s, gemini
        # its working folder: empty, never a repository, never the state — her instruction's file lives there a call
        self.work = (Path(work) if work is not None else Path(tempfile.gettempdir()) / f"codex-{self.home.name}").resolve()
        self._sink, self._spawn, self._mono = sink, spawn, mono
        self.blocked: str | None = None       # another login than ChatGPT's: until a restart
        self._signed: tuple[bool, float] | None = None
        self.muted_until = float("-inf")
        for folder in (self.home, self.work):
            folder.mkdir(mode=0o700, parents=True, exist_ok=True)

    def __repr__(self) -> str:
        return f"CodexAnswers(model={self.reply_model!r}, effort={self.effort!r})"

    # --- the login ----------------------------------------------------------------------------------------------
    async def _status(self) -> str:
        """`codex login status`, read for its kind alone — `chatgpt`, `other` (an API key: never) or `none` — and
        never logged. Code review v7.4 #3: only a login that names an API key is `other`; anything else (not signed
        in, an error, a panic) is `none`, looked at again later; a status that hangs is killed."""
        proc = await self._spawn(self.binary, "login", "status", stdin=asyncio.subprocess.DEVNULL,
                                 stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                                 env=clean_env(self.home, self.work), cwd=str(self.work))
        try:
            out, err = await asyncio.wait_for(proc.communicate(), STATUS_TIMEOUT_S)
        finally:
            if proc.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    proc.kill()
                with contextlib.suppress(Exception):
                    await proc.wait()
        said = ((out or b"") + b"\n" + (err or b"")).decode("utf-8", "replace").lower()
        if "chatgpt" in said and proc.returncode == 0:
            return "chatgpt"
        return "other" if "api key" in said else "none"

    async def signed_in(self) -> bool:
        if self.blocked:
            return False
        now = self._mono()
        if self._signed is not None and (self._signed[0] or now - self._signed[1] < STATUS_TTL_S):
            return self._signed[0]
        try:
            kind = await self._status()
        except Exception as exc:  # noqa: BLE001 — no CLI, a hang: not signed in, looked at again later
            log.warning("codex: login status failed (%s)", type(exc).__name__)
            kind = "none"
        if kind == "other":
            self.blocked = "not a ChatGPT login"
            log.error("codex: blocked — %s; never an API key", self.blocked)
            return False
        if kind == "none":
            log.warning("codex: not signed in (or its status unreadable) — codex-gpt-6.1sol answers nothing")
        self._signed = (kind == "chatgpt", now)
        return kind == "chatgpt"

    # --- the answer ---------------------------------------------------------------------------------------------
    def _report(self, kind: str, usage: dict | None, ok: bool, started: float, blocked: str | None = None) -> None:
        if self._sink is None:
            return
        try:
            self._sink(kind, self.reply_model, usage, ok, blocked=blocked,
                       latency_ms=round((self._mono() - started) * 1000))
        except Exception:
            log.exception("usage accounting failed")

    async def _on_gemini(self, why: str, transcript: str, system: str | None, cap: int, kind: str) -> Any:
        if self.gemini is None:
            log.info("silent: codex %s", why)
            return None
        log.info("on gemini: codex %s", why)
        LAST_SERVED.set("gemini")
        return await self.gemini.reply(transcript, system, cap, kind)

    def _instructions(self, system: str) -> Path:
        path = self.work / f"{uuid.uuid4().hex}.md"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(system)
        return path

    async def reply(self, transcript: str, system_instruction: str | None, max_output_tokens: int = 400,
                    kind: str = "reply") -> tuple[str, str] | None:
        LAST_BLOCK.set(None)
        # v7.5 (AGORA-257): the start as her instructions' file, the history then the tail by stdin
        split = split_prompt(system_instruction, PROMPT_SLOW.get()) if kind in ANSWER_KINDS else None
        if split is not None:
            system_instruction = split[0]
            transcript = f"{transcript}{SEPARATOR}{split[1]}" if transcript.strip() else split[1]
        if self._mono() < self.muted_until:
            return await self._on_gemini("at its limit", transcript, system_instruction, max_output_tokens, kind)
        if not await self.signed_in():
            return None
        started = self._mono()
        path = proc = None
        try:  # code review v7.4 #8: the file inside the `try` — a failed write is silence, never her prompt left behind
            path = self._instructions(system_instruction or "")
            proc = await self._spawn(*run_args(self.binary, self.work, self.effort, path),
                                     stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                                     stderr=asyncio.subprocess.DEVNULL, env=clean_env(self.home, self.work),
                                     cwd=str(self.work))
            out, _ = await asyncio.wait_for(proc.communicate((transcript or "…").encode("utf-8")), self.timeout_s)
        except TimeoutError:
            log.warning("codex %s timed out after %d s", kind, self.timeout_s)
            self._report(kind, None, False, started)
            return None
        except Exception as exc:  # noqa: BLE001 — no CLI, a crash: silence
            log.error("codex %s failed: %s", kind, type(exc).__name__)
            self._report(kind, None, False, started)
            return None
        finally:
            if path is not None:
                with contextlib.suppress(OSError):
                    path.unlink()
            if proc is not None and proc.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    proc.kill()
                with contextlib.suppress(Exception):
                    await proc.wait()
        got = parse_events((out or b"").decode("utf-8", "replace").splitlines())
        if got.limit:
            self.muted_until = self._mono() + LIMIT_MUTE_S
            self._report(kind, got.usage, False, started)
            return await self._on_gemini("at its limit", transcript, system_instruction, max_output_tokens, kind)
        if got.tools:
            log.error("codex %s used a tool (%s) — no answer", kind, ", ".join(sorted(set(got.tools))))
            self._report(kind, got.usage, False, started)
            return None
        if got.failed or not got.text.strip():
            log.error("codex %s %s", kind, "failed" if got.failed else "was empty")
            self._report(kind, got.usage, False, started)
            return None
        marker = refusal_marker(got.text)  # v5.13: an answer that is the model's own refusal is a block
        if marker is not None:
            block = ("refusal", marker, None)
            LAST_BLOCK.set(block)
            self._report(kind, got.usage, False, started, "refusal")
            log.warning("codex blocked: stage=%s reason=%s category=%s kind=%s model=%s", *block, kind, MODEL)
            return None
        self._report(kind, got.usage, True, started)
        return got.text, "stop"

    # code review v7.4 #1: her switch wraps every client in `LlmResponder`, which asks `complete` (else `generate`);
    # the background never comes here — a stray call is an answer all the same
    async def complete(self, transcript: str, system_instruction: str | None, max_output_tokens: int = 400,
                       kind: str = "reply", *_: Any, **__: Any) -> tuple[str, str] | None:
        return await self.reply(transcript, system_instruction, max_output_tokens, kind)
