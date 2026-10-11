"""Claude through the Claude Agent SDK, on the owner's Max subscription only (v4.4).

One stateless `query()` per reply: the room transcript as the prompt, the brief as the system prompt, no tools, no
settings, one turn. An API key can never be used — several independent layers make sure of it:
  1. the stack carries none (Claude's own env file; a compose test checks every service);
  2. startup refuses when a forbidden variable is set or the OAuth token is missing (`check_startup`);
  3. the forbidden names are scrubbed from the environment the SDK's CLI inherits (`scrub`);
  4. no settings are read (`setting_sources=[]`) and the CLI's config dir is a fresh tmpfs;
  5. the CLI's `system/init` must report `apiKeySource == "none"` and no tools, or every later reply is blocked;
  6. no `anthropic` client anywhere — the SDK is imported here, lazily, and nowhere else;
  7. at a subscription limit he is silent until it resets — no fallback of any kind;
  8. every usage line is `subscription`.
The SDK's message classes are matched by name, so the tests need no SDK installed. Never any text in a log or a file.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import time
from collections.abc import Callable, Mapping, MutableMapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from agents.logic import build_transcript
from agents.responder import Reply, Turn

log = logging.getLogger("agent.claude")

OAUTH_VAR = "CLAUDE_CODE_OAUTH_TOKEN"
FORBIDDEN_PREFIXES = ("ANTHROPIC_", "CLAUDE_CODE_USE_")  # an API key, a gateway, Bedrock / Vertex / Foundry
FORBIDDEN_NAMES = (
    "CLAUDE_CODE_SIMPLE",                   # bare mode never reads the OAuth credentials
    "CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR",  # an API key handed over a file descriptor
    "CLAUDE_CODE_MANAGED_SETTINGS_PATH",    # managed settings are read even with no setting sources (an apiKeyHelper)
    "CLAUDE_CODE_API_BASE_URL",             # another endpoint
    "CLAUDE_CODE_HOST_CREDS_FILE",          # host credentials
)  # v4.4 review #10
# v4.5 (the owner, 2026-10-11): the web, and his own folder — nothing else; the guard below enforces both
ALLOWED_TOOLS = ["Read", "Write", "Edit", "Glob", "Grep", "WebSearch", "WebFetch"]
FILE_TOOLS = {"Read", "Write", "Edit", "Glob", "Grep"}
# belt and braces beside `tools=ALLOWED_TOOLS`: these never run in the chat container
DISALLOWED_TOOLS = ["Bash", "BashOutput", "KillShell", "Agent", "Task", "Skill", "NotebookEdit", "TodoWrite"]
MAX_TURNS = 8  # a few tool rounds — a search, a page, a note — then the answer
WARN_MUTE_S = 3600  # a warning mutes him for an hour, then the next call re-checks (review #9)


class AuthRefused(RuntimeError):
    """A forbidden variable is set or the OAuth token is missing — the message names variables, never values."""


def forbidden_vars(env: Mapping[str, str]) -> list[str]:
    return sorted(k for k in env if k.startswith(FORBIDDEN_PREFIXES) or k in FORBIDDEN_NAMES)


def check_startup(env: Mapping[str, str]) -> None:
    """Layer 2: refuse to start on any forbidden variable, or without the subscription's OAuth token."""
    bad = forbidden_vars(env)
    if bad:
        raise AuthRefused(f"forbidden variables set: {', '.join(bad)} — Claude runs on the subscription only")
    if not str(env.get(OAUTH_VAR, "")).strip():
        raise AuthRefused(f"{OAUTH_VAR} is missing — run `claude setup-token` and put it into Claude's env file")


def scrub(env: MutableMapping[str, str]) -> list[str]:
    """Layer 3: the SDK passes the whole environment to its CLI — the forbidden names leave it first."""
    gone = forbidden_vars(env)
    for k in gone:
        env.pop(k, None)
    return gone


def _inside(path: str, root: str) -> bool:
    """A path the CLI resolves inside `root`. The CLI trims Glob/Grep paths and expands `~` before use, so a path
    with surrounding whitespace, a `~` or a variable is refused outright (v4.5 review #1); the rest is compared by
    `realpath`, symlinks included."""
    if not path or path != path.strip() or path.startswith("~") or "$" in path or "\x00" in path:
        return False
    full = os.path.realpath(path if os.path.isabs(path) else os.path.join(root, path))
    root = os.path.realpath(root)
    return full == root or full.startswith(root + os.sep)


_GLOB_ESCAPE_RE = re.compile(r"(^|[{,])\s*[/~]")  # an absolute or home alternative: «/app/*», «{/app/state,x}/*»


def _glob_escapes(pattern: str, root: str) -> bool:
    """A Glob `pattern` or Grep `glob` that reaches outside `root`: `..`, a `~` or `$`, an absolute alternative
    inside braces, or an absolute pattern whose fixed head is not inside."""
    if pattern != pattern.strip() or ".." in pattern or "~" in pattern or "$" in pattern:
        return True
    if os.path.isabs(pattern):
        head = re.split(r"[*?\[{]", pattern, maxsplit=1)[0].rsplit("/", 1)[0] or "/"
        return not _inside(head, root) or bool(_GLOB_ESCAPE_RE.search(pattern[1:]))
    return bool(_GLOB_ESCAPE_RE.search(pattern))


def _private_host(url: str) -> bool:
    """A loopback, private, link-local or local-network address: the homeserver, the panel, the LAN."""
    import ipaddress
    from urllib.parse import urlparse
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    if not host or host in ("localhost", "homeserver", "panel") or host.endswith((".lan", ".local", ".internal")):
        return True
    if "." not in host and ":" not in host:
        return True  # a bare name: a compose service or a LAN host
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified


def tool_denial(tool: str, tool_input: Mapping[str, Any], workspace: str) -> str | None:
    """Why a tool call is refused, or None: only the allowed tools; files only inside his folder; the web only at
    public addresses (pure — the PreToolUse guard's decision)."""
    if tool not in ALLOWED_TOOLS:
        return f"{tool} is not available"
    if tool in FILE_TOOLS:
        for key in ("file_path", "path", "notebook_path"):
            value = tool_input.get(key)
            if value is not None and not (isinstance(value, str) and _inside(value, workspace)):
                return f"only {workspace} is his"
        patterns = [("glob", tool_input.get("glob"))] + ([("pattern", tool_input.get("pattern"))] if tool == "Glob"
                                                        else [])
        for _, value in patterns:
            if value is not None and not (isinstance(value, str) and not _glob_escapes(value, workspace)):
                return f"only {workspace} is his"
    if tool == "WebFetch" and _private_host(str(tool_input.get("url", ""))):
        return "not a private or local address"
    return None


def tool_guard(workspace: str):
    """The PreToolUse hook: our own, deterministic check of every tool call before it runs."""
    async def guard(hook_input: Mapping[str, Any], tool_use_id: str | None, context: Any) -> dict[str, Any]:
        tool = str(hook_input.get("tool_name", ""))
        try:
            why = tool_denial(tool, hook_input.get("tool_input") or {}, workspace)
        except Exception as exc:  # noqa: BLE001 — fail closed (v4.5 review #1)
            why = f"the guard could not judge it ({type(exc).__name__})"
        if why is None:
            return {}
        log.warning("claude tool denied: %s (%s)", tool, why)
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                       "permissionDecisionReason": why}}
    return guard


def sdk_options(brief: str | None, *, model: str, max_output_tokens: int, config_dir: str,
                effort: str | None = None, workspace: str | None = None) -> dict[str, Any]:
    """The `ClaudeAgentOptions` keyword arguments: a chat turn, nothing else. He thinks (adaptive — the owner,
    2026-10-11); `max_output_tokens` 0 means no cap (the owner), so thinking never eats the reply (v4.4 review #1);
    the brief keeps replies chat-sized."""
    env = {
        "CLAUDE_CODE_SKIP_PROMPT_HISTORY": "1",
        "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
        "CLAUDE_CONFIG_DIR": config_dir,
        "CLAUDE_CODE_MAX_RETRIES": "2",  # its own retries stay short; the reply is bounded anyway (review #11)
        "ENABLE_CLAUDEAI_MCP_SERVERS": "false",  # never the account's claude.ai connectors (review #10)
    }
    if max_output_tokens > 0:
        env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = str(max_output_tokens)
    opts: dict[str, Any] = {
        "system_prompt": brief or "",
        # v4.5: the web and his folder (the guard checks every call); without a folder, no tool at all
        "tools": list(ALLOWED_TOOLS) if workspace else [],
        "allowed_tools": list(ALLOWED_TOOLS) if workspace else [],
        "disallowed_tools": list(DISALLOWED_TOOLS),
        "permission_mode": "dontAsk",
        "setting_sources": [],
        "mcp_servers": {},
        "strict_mcp_config": True,
        "max_turns": MAX_TURNS if workspace else 1,
        "model": model,
        "cwd": workspace or config_dir,
        # he thinks (the owner, 2026-10-11) — with no output cap there is nothing for thinking to eat into (review #1)
        "thinking": {"type": "adaptive"},
        # no session transcript anywhere (review #7): accepted by the bundled CLI in the SDK's stream-json mode
        "extra_args": {"no-session-persistence": None},
        "env": env,
    }
    if effort:
        opts["effort"] = effort
    if workspace:
        opts["hooks"] = {"PreToolUse": [tool_guard(workspace)]}
    return opts


@dataclass
class ClaudeStatus:
    """`state/<name>.ratelimit.json` — for the panel; times and words, no texts, no token."""
    status: str | None = None          # allowed | allowed_warning | rejected
    utilization: float | None = None
    resets_at: int | None = None       # epoch seconds
    rate_limit_type: str | None = None
    muted_until: int | None = None     # epoch seconds
    auth: str | None = None            # "oauth" once the init check passed; "blocked: …" / "refused: …"
    model: str | None = None           # the model asked for (the panel's card shows it)
    last_error: str | None = None      # the last failed call — a subtype, an http status, a type name; never text
    updated_at: int | None = None


def write_status(path: Path, status: ClaudeStatus) -> None:
    """Atomic, private from birth (0600)."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, json.dumps(asdict(status)).encode())
        finally:
            os.close(fd)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except OSError as exc:
        log.error("claude status not written (%s)", type(exc).__name__)


def _default_query():
    from claude_agent_sdk import query  # layer 6: the SDK lives here only

    return query


def _default_options():
    from claude_agent_sdk import ClaudeAgentOptions

    return ClaudeAgentOptions


def _hook_matchers(hooks: Mapping[str, list]) -> dict[str, list]:
    from claude_agent_sdk import HookMatcher

    return {event: [HookMatcher(matcher=None, hooks=list(fns))] for event, fns in hooks.items()}


class ClaudeSdkResponder:
    """One stateless `query()` per reply on the subscription; silent when blocked, muted or failed."""

    def __init__(self, *, model: str, max_output_tokens: int, config_dir: str, status_file: Path,
                 usage_sink: Callable[[str, str, dict | None, bool, float | None], None],
                 clock: Callable[[], int] = lambda: int(time.time() * 1000), query=None, options=None,
                 timeout_s: float = 90.0, workspace: str | None = None) -> None:
        self.model = model
        self.max_output_tokens = max_output_tokens
        self.config_dir = config_dir
        self.status_file = status_file
        self.usage_sink = usage_sink
        self.clock = clock
        self._query = query
        self._options = options
        self.timeout_s = timeout_s
        self.workspace = workspace
        self.status = ClaudeStatus(model=model)
        self.blocked: str | None = None

    def resume_status(self) -> None:
        """Review #6: at start the card is refreshed — a refusal or a failure from an earlier run no longer shows —
        and a mute still running is kept, so a restart during a limit makes no call."""
        try:
            old = json.loads(self.status_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            old = None
        if isinstance(old, dict):
            for key in ("status", "utilization", "resets_at", "rate_limit_type"):
                value = old.get(key)
                if value is None or isinstance(value, str | int | float):
                    setattr(self.status, key, value)
            until = old.get("muted_until")
            if isinstance(until, int | float) and until > self._now():
                self.status.muted_until = int(until)
        self._save()

    def _now(self) -> int:
        return self.clock() // 1000

    def _save(self) -> None:
        self.status.updated_at = self._now()
        write_status(self.status_file, self.status)

    def _check_init(self, data: Mapping[str, Any]) -> None:
        """Layer 5: the CLI must say no API key is in use and no tool or MCP server is available."""
        source = data.get("apiKeySource") if isinstance(data, Mapping) else None
        tools = data.get("tools") if isinstance(data, Mapping) else None
        servers = data.get("mcp_servers") if isinstance(data, Mapping) else None
        if source != "none":
            self.blocked = f"apiKeySource={source!r}"
        elif extra := [t for t in (tools or []) if t not in (ALLOWED_TOOLS if self.workspace else [])]:
            self.blocked = f"tools={', '.join(map(str, extra))}"
        elif servers:
            self.blocked = f"mcp_servers={len(servers)}"
        if self.blocked:
            log.error("claude blocked: %s — no reply until restarted", self.blocked)
            self.status.auth = f"blocked: {self.blocked}"
        else:
            self.status.auth = "oauth"
        self._save()

    def _rate_limit(self, info: Any) -> None:
        """Layer 7: a warning mutes him for an hour before the owner's own work hits the wall — the CLI's warnings
        track the pace within a window, so a weekly one would otherwise mute him for days; a rejection silences him
        until the window resets."""
        status = getattr(info, "status", None)
        resets_at = getattr(info, "resets_at", None)
        self.status.status = status
        self.status.utilization = getattr(info, "utilization", None)
        self.status.resets_at = resets_at
        self.status.rate_limit_type = getattr(info, "rate_limit_type", None)
        if status == "rejected":
            self.status.muted_until = int(resets_at) if resets_at else self._now() + WARN_MUTE_S
            log.warning("claude rate limit %s — muted until %s", status, self.status.muted_until)
        elif status == "allowed_warning":
            self.status.muted_until = self._now() + WARN_MUTE_S
            log.warning("claude rate limit %s — muted until %s", status, self.status.muted_until)
        elif status == "allowed":
            self.status.muted_until = None
        self._save()

    def _failed(self, why: str) -> None:
        """Review #14: an expired or revoked token fails every call — the card must not keep showing «OAuth ✓»."""
        self.status.last_error = why
        self._save()

    def muted(self) -> bool:
        return bool(self.status.muted_until) and self._now() < int(self.status.muted_until)

    async def respond(self, turn: Turn) -> Reply | None:
        if self.blocked:
            log.info("silent: claude blocked (%s)", self.blocked)
            return None
        if self.muted():
            log.info("silent: claude rate limit (until %s)", self.status.muted_until)
            return None
        query = self._query or _default_query()
        kwargs = sdk_options(turn.instruction, model=self.model, max_output_tokens=self.max_output_tokens,
                             config_dir=self.config_dir, effort=turn.effort, workspace=self.workspace)
        if self._options is None and "hooks" in kwargs:  # the real SDK wants its HookMatcher
            kwargs["hooks"] = _hook_matchers(kwargs["hooks"])
        options = (self._options or _default_options())(**kwargs)
        parts: list[str] = []
        result = None
        saw_init = over_limit = False

        async def consume() -> None:
            nonlocal result, saw_init, over_limit
            async with contextlib.aclosing(query(prompt=build_transcript(turn.lines), options=options)) as stream:
                async for msg in stream:
                    kind = type(msg).__name__
                    if getattr(msg, "subtype", None) == "init" and isinstance(getattr(msg, "data", None), Mapping):
                        saw_init = True  # any SystemMessage subclass: matched by its subtype, not its class name
                        self._check_init(msg.data)
                        if self.blocked:
                            break  # stop reading a stream that is not on the subscription
                    elif kind == "RateLimitEvent":
                        info = getattr(msg, "rate_limit_info", None)
                        self._rate_limit(info)
                        raw = getattr(info, "raw", None)
                        # a rejected window answered anyway is extra usage — never a reply (review #4)
                        over_limit = over_limit or getattr(info, "status", None) == "rejected" or bool(
                            isinstance(raw, Mapping) and raw.get("isUsingOverage"))
                    elif kind == "AssistantMessage" and not getattr(msg, "error", None):  # never the CLI's error text
                        parts.extend(b.text for b in getattr(msg, "content", [])
                                     if isinstance(getattr(b, "text", None), str))
                    elif kind == "ResultMessage":
                        result = msg

        try:  # bounded: the CLI's own retries must never hold a reply for minutes (review #11)
            await asyncio.wait_for(consume(), timeout=self.timeout_s)
        except TimeoutError:
            log.error("claude query timed out after %.0fs — silent", self.timeout_s)
            self.usage_sink(turn.kind, self.model, None, False, None)
            self._failed("timeout")
            return None
        except Exception as exc:  # noqa: BLE001 — any SDK or CLI failure means silence
            log.error("claude query failed: %s", type(exc).__name__)
            self.usage_sink(turn.kind, self.model, None, False, None)
            self._failed(type(exc).__name__)
            return None
        # one usage line per call, ok only for a checked, successful one
        ok = (result is not None and not getattr(result, "is_error", True) and self.blocked is None and saw_init
              and not over_limit)
        self.usage_sink(turn.kind, self.model, getattr(result, "usage", None), ok, getattr(result, "total_cost_usd", None))
        if self.blocked:
            return None
        if over_limit:
            log.warning("silent: claude is over the subscription's limit — no extra usage, ever")
            return None
        if getattr(result, "api_error_status", None) == 429:  # the limit, told as an error: wait as for a rejection
            self.status.muted_until = max(int(self.status.muted_until or 0), self._now() + WARN_MUTE_S)
            self._save()
            log.warning("silent: claude rate limited (429) — muted until %s", self.status.muted_until)
            return None
        if not saw_init:  # the auth source unverified: never speak on an unchecked call (review #2)
            log.error("claude: no init message — the auth source is unverified; silent")
            return None
        if result is None or getattr(result, "is_error", True):
            log.error("claude result error: %s (http %s)", getattr(result, "subtype", None),
                      getattr(result, "api_error_status", None))
            self._failed(f"{getattr(result, 'subtype', None)} (http {getattr(result, 'api_error_status', None)})")
            return None
        text = (getattr(result, "result", None) or "\n".join(parts)).strip()
        if not text:
            log.error("claude returned an empty reply")
            return None
        if self.status.last_error:  # a good call clears the last failure from the card
            self.status.last_error = None
            self._save()
        return Reply(text, "max_tokens" if getattr(result, "stop_reason", None) == "max_tokens" else "stop")
