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
import uuid
from collections.abc import Callable, Mapping, MutableMapping
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from agents import guardian
from agents.llm import (
    DIGEST_MODEL,
    LAST_BLOCK,
    REPLY_TIMEOUT_S,
    REPLY_TRIES,
    THINK_MAX_TOKENS,
    THINK_TIMEOUT_S,
    refusal_marker,
)
from agents.logic import build_transcript
from agents.responder import ANSWER_KINDS, Reply, Turn
from agents.usage import PROMPT_SLOW

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
MCP_RESOURCE_TOOLS = ("ListMcpResourcesTool", "ReadMcpResourceTool", "ReadMcpResourceDirTool")
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


def tool_denial(tool: str, tool_input: Mapping[str, Any], workspace: str,
                allowed: list[str] = ALLOWED_TOOLS) -> str | None:
    """Why a tool call is refused, or None: only the allowed tools (the news call: the Guardian's only); files only
    inside his folder; the web only at public addresses (pure — the PreToolUse guard's decision)."""
    if tool not in allowed:
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


def tool_guard(workspace: str, allowed: list[str] = ALLOWED_TOOLS):
    """The PreToolUse hook: our own, deterministic check of every tool call before it runs."""
    async def guard(hook_input: Mapping[str, Any], tool_use_id: str | None, context: Any) -> dict[str, Any]:
        tool = str(hook_input.get("tool_name", ""))
        try:
            why = tool_denial(tool, hook_input.get("tool_input") or {}, workspace, allowed)
        except Exception as exc:  # noqa: BLE001 — fail closed (v4.5 review #1)
            why = f"the guard could not judge it ({type(exc).__name__})"
        if why is None:
            return {}
        log.warning("claude tool denied: %s (%s)", tool, why)
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                       "permissionDecisionReason": why}}
    return guard


def sdk_options(brief: str | None, *, model: str, max_output_tokens: int, config_dir: str,
                effort: str | None = None, workspace: str | None = None, toolset: str | None = None,
                news_server: Any = None) -> dict[str, Any]:
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
    if toolset == "news":  # the owner, 2026-10-11: the news comes from The Guardian, and only from it
        opts.update({"tools": [], "allowed_tools": list(guardian.TOOLS), "mcp_servers": {guardian.SERVER: news_server},
                     "max_turns": MAX_TURNS, "cwd": config_dir,
                     "hooks": {"PreToolUse": [tool_guard(workspace or config_dir, guardian.TOOLS)]}})
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


def _default_client():
    from claude_agent_sdk import ClaudeSDKClient

    return ClaudeSDKClient


def guardian_server(source: guardian.Guardian):
    """The in-process SDK server `guardian` with `search` and `read` (the key stays in this process)."""
    from claude_agent_sdk import create_sdk_mcp_server, tool

    search = tool("search", "The newest Guardian articles for an English query.", guardian.SEARCH_SCHEMA)(source.search)
    read = tool("read", "One Guardian article's text by its result id.", guardian.READ_SCHEMA)(source.read)
    return create_sdk_mcp_server(name=guardian.SERVER, version="1.0.0", tools=[search, read])


def _hook_matchers(hooks: Mapping[str, list]) -> dict[str, list]:
    from claude_agent_sdk import HookMatcher

    return {event: [HookMatcher(matcher=None, hooks=list(fns))] for event, fns in hooks.items()}


class _Subscription:
    """v7.1 — what every call on the subscription shares (v4.4's layers 5 and 7): the init check, the limit and the
    status file `state/<name>.ratelimit.json`. Claude as himself (`ClaudeSdkResponder`) and every other agent on
    Claude (`ClaudeClient`) differ only in the tools a call may have."""

    _mono = staticmethod(time.monotonic)  # v5.22: the calls' clock — a test sets its own

    def __init__(self, *, model: str, status_file: Path, clock: Callable[[], int]) -> None:
        self.model = model
        self.status_file = status_file
        self.clock = clock
        self._offered: dict[str | None, str] = {}
        self.status = ClaudeStatus(model=model)
        self.blocked: str | None = None

    def _allowed(self, toolset: str | None) -> list[str]:
        """The tools the CLI may offer on a call of this toolset."""
        raise NotImplementedError

    def _call_only(self, toolset: str | None) -> bool:
        """A wrong tool list refuses this call only (True) or blocks every later one (False)."""
        return False

    def _servers_ok(self, names: list, toolset: str | None) -> bool:
        """The MCP servers the CLI may report on a call of this toolset: none."""
        return not names

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

    def _check_init(self, data: Mapping[str, Any], toolset: str | None = None) -> str | None:
        """Layer 5: the CLI must say no API key is in use and only the call's tools are available (`_allowed`), with
        no MCP server but those `_servers_ok` names. A wrong auth source blocks every later call until restarted; a
        wrong tool list blocks them too, or refuses that call only (`_call_only`; returned) — Claude's news call, and
        every call of `ClaudeClient`."""
        source = data.get("apiKeySource") if isinstance(data, Mapping) else None
        tools = data.get("tools") if isinstance(data, Mapping) else None
        servers = data.get("mcp_servers") if isinstance(data, Mapping) else None
        allowed = self._allowed(toolset)
        names = [s.get("name") if isinstance(s, Mapping) else s for s in (servers or [])]
        why = None
        offered = ", ".join(sorted(map(str, tools or []))) or "none"
        if offered != self._offered.get(toolset):  # what the CLI gives him, once per call kind — names only
            self._offered[toolset] = offered
            log.info("claude tools offered%s: %s", f" ({toolset})" if toolset else "", offered)
        if source != "none":
            self.blocked = f"apiKeySource={source!r}"
        elif extra := [t for t in (tools or []) if t not in allowed]:
            why = f"tools={', '.join(map(str, extra))}"
        elif not self._servers_ok(names, toolset):
            why = f"mcp_servers={len(names)}"
        if why and self._call_only(toolset):
            log.error("claude %scall refused: %s", f"{toolset} " if toolset else "", why)
            self.status.auth = "oauth"
            self._save()
            return why
        self.blocked = self.blocked or why
        if self.blocked:
            log.error("claude blocked: %s — no reply until restarted", self.blocked)
            self.status.auth = f"blocked: {self.blocked}"
        else:
            self.status.auth = "oauth"
        self._save()
        return self.blocked

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

    def _mute_over_limit(self) -> None:
        """Code review v7.1 #3: an answer billed as extra usage is dropped, and the client waits for the window's
        reset (or `WARN_MUTE_S`) — a status `allowed` with overage cleared the mute, so every next call was billed
        so again and dropped again."""
        now = self._now()
        resets_at = self.status.resets_at
        until = int(resets_at) if resets_at and int(resets_at) > now else now + WARN_MUTE_S
        self.status.muted_until = max(int(self.status.muted_until or 0), until)
        self._save()

    def _failed(self, why: str) -> None:
        """Review #14: an expired or revoked token fails every call — the card must not keep showing «OAuth ✓»."""
        self.status.last_error = why
        self._save()

    def muted(self) -> bool:
        return bool(self.status.muted_until) and self._now() < int(self.status.muted_until)


class ClaudeSdkResponder(_Subscription):
    """One stateless `query()` per reply on the subscription; silent when blocked, muted or failed."""

    def __init__(self, *, model: str, max_output_tokens: int, config_dir: str, status_file: Path,
                 usage_sink: Callable[[str, str, dict | None, bool, float | None], None],
                 clock: Callable[[], int] = lambda: int(time.time() * 1000), query=None, options=None,
                 timeout_s: float = 90.0, workspace: str | None = None,
                 news_source: guardian.Guardian | None = None) -> None:
        super().__init__(model=model, status_file=status_file, clock=clock)
        self.max_output_tokens = max_output_tokens
        self.config_dir = config_dir
        self.usage_sink = usage_sink
        self._query = query
        self._options = options
        self.timeout_s = timeout_s
        self.workspace = workspace
        self.news_source = news_source  # the Guardian's tools (agents/guardian.py), for the news call only
        self._news_server: Any = None

    def _allowed(self, toolset: str | None) -> list[str]:
        # with an MCP server the CLI may list its resource tools too; the guard refuses them all the same
        return ([*guardian.TOOLS, *MCP_RESOURCE_TOOLS] if toolset == "news"
                else ALLOWED_TOOLS if self.workspace else [])

    def _call_only(self, toolset: str | None) -> bool:
        return toolset == "news"  # the news can never silence his replies

    def _servers_ok(self, names: list, toolset: str | None) -> bool:
        return not [n for n in names if not (toolset == "news" and n == guardian.SERVER)]

    async def respond(self, turn: Turn) -> Reply | None:
        if self.blocked:
            log.info("silent: claude blocked (%s)", self.blocked)
            return None
        if self.muted():
            log.info("silent: claude rate limit (until %s)", self.status.muted_until)
            return None
        if turn.toolset == "news" and self.news_source is None:
            log.info("silent: no news source")
            return None
        if turn.toolset == "news" and self._news_server is None:  # built once; a fake SDK in tests takes the source
            self._news_server = guardian_server(self.news_source) if self._options is None else self.news_source
        query = self._query or _default_query()
        kwargs = sdk_options(turn.instruction, model=self.model, max_output_tokens=self.max_output_tokens,
                             config_dir=self.config_dir, effort=turn.effort, workspace=self.workspace,
                             toolset=turn.toolset, news_server=self._news_server)
        if self._options is None and "hooks" in kwargs:  # the real SDK wants its HookMatcher
            kwargs["hooks"] = _hook_matchers(kwargs["hooks"])
        options = (self._options or _default_options())(**kwargs)
        parts: list[str] = []
        result = None
        saw_init = over_limit = False
        refused: str | None = None
        tools_used: list[str] = []  # names only — what a slow call was doing (never an input or a text)
        started = self._mono()

        async def consume() -> None:
            nonlocal result, saw_init, over_limit, refused
            async with contextlib.aclosing(query(prompt=build_transcript(turn.lines), options=options)) as stream:
                async for msg in stream:
                    kind = type(msg).__name__
                    if getattr(msg, "subtype", None) == "init" and isinstance(getattr(msg, "data", None), Mapping):
                        saw_init = True  # any SystemMessage subclass: matched by its subtype, not its class name
                        refused = self._check_init(msg.data, turn.toolset)
                        if refused:
                            break  # stop reading: not on the subscription, or not his tools
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
                        tools_used.extend(str(b.name) for b in getattr(msg, "content", [])
                                          if type(b).__name__ == "ToolUseBlock" and getattr(b, "name", None))
                    elif kind == "ResultMessage":
                        result = msg

        try:  # bounded: the CLI's own retries must never hold a reply for minutes (review #11)
            await asyncio.wait_for(consume(), timeout=self.timeout_s)
        except TimeoutError:
            log.error("claude query timed out after %.0fs — silent (%d tool calls: %s)", self.timeout_s,
                      len(tools_used), ", ".join(tools_used) or "none")
            self.usage_sink(turn.kind, self.model, None, False, None, latency_ms=round((self._mono() - started) * 1000))
            self._failed("timeout")
            return None
        except Exception as exc:  # noqa: BLE001 — any SDK or CLI failure means silence
            # v7.1: an error result (a 429, a refusal) ends with the CLI's exit 1, raised by the SDK as `ResultError`
            # after the result — read the result below, so a 429 still mutes him
            if result is None or not getattr(result, "is_error", False):
                log.error("claude query failed: %s", type(exc).__name__)
                self.usage_sink(turn.kind, self.model, None, False, None,
                                latency_ms=round((self._mono() - started) * 1000))
                self._failed(type(exc).__name__)
                return None
        # one usage line per call, ok only for a checked, successful one
        ok = (result is not None and not getattr(result, "is_error", True) and self.blocked is None and saw_init
              and not over_limit and refused is None)
        self.usage_sink(turn.kind, self.model, getattr(result, "usage", None), ok, getattr(result, "total_cost_usd", None),
                        latency_ms=round((self._mono() - started) * 1000))  # v5.22: the query to its result
        if self.blocked or refused:
            return None
        if over_limit:
            self._mute_over_limit()
            log.warning("silent: claude is over the subscription's limit — no extra usage, ever; muted until %s",
                        self.status.muted_until)
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
            log.error("claude result error: %s (http %s, stop %s, terminal %s, %s)", getattr(result, "subtype", None),
                      getattr(result, "api_error_status", None), getattr(result, "stop_reason", None),
                      getattr(result, "terminal_reason", None), cli_error_kind(result))  # names, never a text
            self._failed(f"{getattr(result, 'subtype', None)} (http {getattr(result, 'api_error_status', None)})")
            return None
        text = (getattr(result, "result", None) or "\n".join(parts)).strip()
        if not text:
            log.error("claude returned an empty reply")
            return None
        log.info("claude answered in %.0fs (%s turns, %d tool calls: %s)", time.monotonic() - started,
                 getattr(result, "num_turns", "?"), len(tools_used), ", ".join(tools_used) or "none")
        if self.status.last_error:  # a good call clears the last failure from the card
            self.status.last_error = None
            self._save()
        return Reply(text, "max_tokens" if getattr(result, "stop_reason", None) == "max_tokens" else "stop")


# --- v7.1: every other agent on Claude ---------------------------------------------------------------------------
# The kinds that are the agent's own voice — her answers, a line written first, Hermes's digest and his answers — on
# the reply model (Sonnet); every other kind (the summaries, memories, plans, the today block, events, the mood, the
# sky, topics, facts, thoughts) on the background model (Haiku).
VOICE_KINDS = frozenset({*ANSWER_KINDS, "digest_voice", "ask"})
SEARCH_TOOLS = ["WebSearch"]  # `search` (the cat's sky, a mood's reading): the web, nothing else
SEARCH_MAX_TURNS = 4          # a search or two, then the answer
LIMIT_FALLBACKS = ("gemini", "silent")  # decision 1 (ROADMAP §v7): at the limit — Gemini until the reset, or silence
CONCURRENCY = 2               # CLI processes at once per container (each is a Node process)
PROMPTS_DIR = "prompts"       # in the CLI's config dir (a tmpfs): one file a call, 0600, removed after it
_LIMIT = object()             # `_query`'s answer when the subscription's limit stopped the call
# code review v7.1 #6: who served this task's last call — `claude`, or `gemini` when decision 1 took it (an answer
# line counted the fallback's answers as Claude's); read by `served_by`
LAST_SERVED: ContextVar[str | None] = ContextVar("LAST_SERVED", default=None)


def served_by(engine: str) -> str:
    """The engine of an answer just made in this task: an agent on Gemini is Gemini's; on Claude, `claude` unless
    the Gemini fallback served the call."""
    return (LAST_SERVED.get() or "claude") if engine == "claude-sdk" else "gemini"
THINKING_MODES = ("off", "adaptive")  # v7.1 (the owner, 2026-11-10: «додай»): the voice's thinking on Claude
EFFORTS = ("low", "medium", "high", "max")  # how deep an adaptive call thinks (the CLI's `--effort`)
# Measured 2026-11-10: the 5.5 models think whatever the CLI is told — Haiku 5.5 600–1,300 thinking tokens with
# `--thinking disabled` (also with `--max-thinking-tokens 0` or MAX_THINKING_TOKENS=0), 150–300 at `--effort low`,
# and 2–3 s faster; the cap counts the thinking, and an answer cut at the cap is continued by the CLI in a second
# request whose text alone is the result. So every call runs at least at `low`, and every cap gets the headroom
# (the owner: «для хайку не треба думання», «тоді збільш кількість токенів»).
THINK_HEADROOM = 4096         # added to every capped call: the thinking never eats the answer
QUIET_EFFORT = "low"          # the least thinking a 5.5 model can be held to


_CATEGORY = re.compile(r"Details: `\[([a-z_]{1,24})\]`")


def refusal_category(result: Any) -> str | None:
    """The safety classifier's label (`bio`, …) the CLI names in a refusal's error result, or None — the CLI's own
    error line, never the model's text."""
    found = _CATEGORY.search(str(getattr(result, "result", "") or "")) if getattr(result, "is_error", False) else None
    return found.group(1) if found else None


_CLI_ERRORS = (("output token maximum", "max_output"), ("overloaded", "overloaded"), ("rate limit", "rate_limit"),
               ("prompt is too long", "too_long"), ("timed out", "timeout"), ("timeout", "timeout"),
               ("can't help", "refusal"), ("authentication", "auth"), ("oauth", "auth"))


def cli_error_kind(result: Any) -> str:
    """A name for the CLI's error line on an error result (`API Error: …`) — matched against known phrases, so the
    log carries a name and never the line itself."""
    line = str(getattr(result, "result", "") or "").lower() if getattr(result, "is_error", False) else ""
    return next((name for phrase, name in _CLI_ERRORS if phrase in line), "other" if line else "none")


WARM_IDLE_S = 3600     # v7.2: a waiting CLI unused this long (its prompt cache's life) is closed, the next call cold
WARM_CONNECT_S = 30    # a connect that takes longer is a failed one: the call it was for goes cold
_END = object()        # the end of a warm call's answer


class WarmCli:
    """v7.2 (AGORA-243) — one CLI started ahead for exactly one call. Measured 2026-11-10/11: a new CLI per call costs
    ~1.4 s of its start; one long session for every call is not safe (a new `session_id` still knew the previous call,
    `/clear` is named aloud by the model, `set_model` is ignored, the system prompt is read once at the start). So its
    worker task owns a `ClaudeSDKClient` from connect to disconnect — the SDK's client must stay in the task that
    connected it — takes one message, streams its answer back, disconnects and ends. Its system prompt is the call's
    slow part, in a 0600 file of its own, removed when it ends; `key` is what a call must match to take it."""

    def __init__(self, key: tuple, options: Any, path: str | None, make_client: Callable[..., Any],
                 now: Callable[[], float]) -> None:
        self.key = key
        self.born = now()
        self._now = now
        self._path = path
        self._requests: asyncio.Queue = asyncio.Queue(maxsize=1)
        self._taken = False
        self._ready: asyncio.Future = asyncio.get_running_loop().create_future()
        self._task = asyncio.create_task(self._run(options, make_client))
        self._task.add_done_callback(self._forget_file)  # however it ends — even cancelled before it ran

    def _forget_file(self, _task: Any = None) -> None:
        if self._path:
            with contextlib.suppress(OSError):
                os.unlink(self._path)

    def ready(self) -> bool:
        """Connected and waiting: a call may take it (one still connecting is left for the next call)."""
        return self._ready.done() and self._ready.result() is True and not self._task.done()

    def stale(self) -> bool:
        return self._now() - self.born > WARM_IDLE_S or self._task.done()

    def close(self) -> None:
        self._task.cancel()

    async def aclose(self) -> None:
        """Closed and waited for: its CLI disconnected and its prompt file removed."""
        self._task.cancel()
        with contextlib.suppress(BaseException):
            await asyncio.wait_for(asyncio.shield(self._task), 15)

    async def _run(self, options: Any, make_client: Callable[..., Any]) -> None:
        client, out = None, None
        try:
            client = make_client(options=options)
            await asyncio.wait_for(client.connect(), WARM_CONNECT_S)
            self._ready.set_result(True)
            prompt, out = await self._requests.get()
            await client.query(prompt)
            async for msg in client.receive_response():
                out.put_nowait(msg)
            out.put_nowait(_END)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — a failed CLI fails its one call, which then goes cold
            log.warning("claude warm cli failed: %s", type(exc).__name__)
            if out is not None:
                out.put_nowait(exc)
        finally:
            if not self._ready.done():
                self._ready.set_result(False)
            self._forget_file()  # first, before any await: a cancel while it disconnects never leaves the file
            if client is not None:
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(client.disconnect(), 10)

    def query(self, *, prompt: str, options: Any = None):
        """Its one call, shaped as the SDK's `query()`: the answer's messages; closing it early ends the CLI. A second
        call is refused: a CLI keeps its context, so it never takes two."""
        if self._taken:
            raise RuntimeError("a CLI started ahead takes one call")
        self._taken = True
        out: asyncio.Queue = asyncio.Queue()
        self._requests.put_nowait((prompt, out))
        task = self._task

        async def answer():
            done = False
            try:
                while True:
                    item = await out.get()
                    if item is _END:
                        done = True
                        return
                    if isinstance(item, BaseException):
                        done = True
                        raise item
                    yield item
            finally:
                if not done:
                    task.cancel()
        return answer()


def split_prompt(system: str | None, slow: str | None) -> tuple[str, str] | None:
    """v7.2 (AGORA-242) — a call's system prompt as its slow part and the rest: `(slow, rest)` when `system` starts
    with `slow` (the rest without the blank line that joined them), else None."""
    if not system or not slow or not system.startswith(slow):
        return None
    return slow, system[len(slow):].removeprefix("\n\n")


def answer_of(result: Any, parts: list[str], toolset: str | None) -> str:
    """A call's answer: with no tools, every text block in order — an answer cut at the cap is continued by the CLI
    in a second request, and its result holds that part alone; with tools (a search) the result, the last turn's."""
    if toolset is None and len(parts) > 1:
        return "".join(parts).strip()
    return (getattr(result, "result", None) or "\n".join(parts)).strip()


def client_options(system_file: str | None, *, model: str, max_output_tokens: int, config_dir: str,
                   toolset: str | None = None, effort: str | None = None, think: bool = False) -> dict[str, Any]:
    """v7.1 — the `ClaudeAgentOptions` keyword arguments of one `ClaudeClient` call: the system prompt from a file (a
    persona's prompt holds her memories, which never go on a command line, and Кіра's is longer than one argument
    may be), no settings, no MCP server, one turn, no tools (`search`: `WebSearch` alone, a few turns), the call's
    cap, no session transcript. Thinking is asked off (as Gemini Flash's `thinking_budget=0`) unless `think`: then
    adaptive (`CLAUDE_THINKING=adaptive`, the voice's calls alone); `effort` bounds it either way, since a 5.5 model
    thinks even when told not to."""
    env = {
        "CLAUDE_CODE_SKIP_PROMPT_HISTORY": "1",
        "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
        "CLAUDE_CONFIG_DIR": config_dir,
        "CLAUDE_CODE_MAX_RETRIES": "2",
        "ENABLE_CLAUDEAI_MCP_SERVERS": "false",
    }
    if max_output_tokens > 0:
        env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = str(max_output_tokens)
    tools = list(SEARCH_TOOLS) if toolset == "search" else []
    return {
        "system_prompt": {"type": "file", "path": system_file} if system_file else None,
        "tools": tools,
        "allowed_tools": list(tools),
        "disallowed_tools": list(DISALLOWED_TOOLS),
        "permission_mode": "dontAsk",
        "setting_sources": [],
        "mcp_servers": {},
        "strict_mcp_config": True,
        "max_turns": SEARCH_MAX_TURNS if toolset == "search" else 1,
        "model": model,
        "cwd": config_dir,
        "thinking": {"type": "adaptive"} if think else {"type": "disabled"},
        **({"effort": effort} if effort else {}),
        "extra_args": {"no-session-persistence": None},
        "env": env,
    }


class ClaudeClient(_Subscription):
    """v7.1 — `GeminiClient`'s calls (`agents/llm.py`) over the Agent SDK, on the owner's subscription: one stateless
    `query()` per call, on the model its kind asks for (`VOICE_KINDS` on `reply_model`, every other on `model`, the
    background one). `embed` stays Gemini's (`embedder`); `probe` is Gemini's alone. At the limit, or blocked,
    `limit_fallback` decides: `gemini` — the same call on `fallback`, its usage lines Gemini's own; `silent` — None.
    A decline (the refusal stop, or a refusal formula in an answer) is None with `LAST_BLOCK` set, as a refusal on
    Gemini is. Never a text in a log or a file but the call's own prompt file, removed after it."""

    def __init__(self, *, reply_model: str, background_model: str, config_dir: str, status_file: Path,
                 sink: Callable[..., None] | None, clock: Callable[[], int] = lambda: int(time.time() * 1000),
                 concurrency: int = CONCURRENCY, limit_fallback: str = "gemini", fallback: Any = None,
                 embedder: Any = None, query=None, options=None, thinking: str = "off", effort: str = "low",
                 sdk_client=None) -> None:
        super().__init__(model=background_model, status_file=status_file, clock=clock)
        self.reply_model = reply_model
        self.status.model = reply_model  # the panel's card names the answers' model
        self.config_dir = config_dir
        self._sink = sink
        self._gate = asyncio.Semaphore(max(1, int(concurrency)))
        # code review v7.1 #2: the voice's calls have a gate of their own — an answer never waits behind two
        # background calls (each may hold a slot for both its tries), so the turn-taking never drops it for that
        self._voice_gate = asyncio.Semaphore(max(1, int(concurrency)))
        self.limit_fallback = limit_fallback if limit_fallback in LIMIT_FALLBACKS else "gemini"
        self.fallback = fallback
        self.embedder = embedder
        self.thinking = thinking if thinking in THINKING_MODES else "off"
        self.effort = effort if effort in EFFORTS else "low"
        self._query_fn = query
        self._options = options
        self._client_cls = sdk_client  # v7.2: the SDK's `ClaudeSDKClient` (tests: a fake)
        self._warm: WarmCli | None = None
        # a test that fakes `query` and no client never starts a real CLI ahead
        self._warm_on = sdk_client is not None or query is None

    def _allowed(self, toolset: str | None) -> list[str]:
        return list(SEARCH_TOOLS) if toolset == "search" else []

    def _call_only(self, toolset: str | None) -> bool:
        return True  # a call with tools it never asked for is not used; the next one is checked again

    def model_for(self, kind: str) -> str:
        return self.reply_model if kind in VOICE_KINDS else self.model

    def thinks(self, kind: str) -> bool:
        """Whether a call is asked to think: only the voice's calls, and only with `CLAUDE_THINKING=adaptive`."""
        return self.thinking == "adaptive" and kind in VOICE_KINDS

    def effort_for(self, kind: str) -> str:
        """The effort a call runs at: `CLAUDE_EFFORT` when it thinks, else the least (`QUIET_EFFORT`) — a 5.5 model
        thinks even when told not to."""
        return self.effort if self.thinks(kind) else QUIET_EFFORT

    # --- the calls, as GeminiClient's ---------------------------------------------------------------------------
    async def generate(self, transcript: str, system_instruction: str, max_output_tokens: int = 400,
                       kind: str = "reply") -> str | None:
        out = await self.complete(transcript, system_instruction, max_output_tokens, kind)
        return out[0] if out else None

    async def complete(self, transcript: str, system_instruction: str | None, max_output_tokens: int = 400,
                       kind: str = "reply", model: str | None = None, refusal: bool = False) -> tuple[str, str] | None:
        """(text, finish) — finish "max_tokens" when the cap cut it; None on failure. `model` (a Gemini id) is never
        Claude's — the kind picks the model; it is used only on the Gemini fallback."""
        LAST_BLOCK.set(None)
        return await self._run(kind, system_instruction, transcript, max_output_tokens, answer=refusal,
                               gemini=lambda g: g.complete(transcript, system_instruction, max_output_tokens, kind,
                                                           model, refusal))

    async def reply(self, transcript: str, system_instruction: str | None, max_output_tokens: int = 400,
                    kind: str = "reply") -> tuple[str, str] | None:
        """An answer: a refusal in it is a decline (v5.13's rule)."""
        LAST_BLOCK.set(None)
        return await self._run(kind, system_instruction, transcript, max_output_tokens, answer=True,
                               gemini=lambda g: g.reply(transcript, system_instruction, max_output_tokens, kind))

    async def think(self, contents: str, system_instruction: str, model: str | None = None,
                    max_output_tokens: int = THINK_MAX_TOKENS, kind: str = "digest_voice",
                    level: str | None = None) -> str | None:
        """A long call (a digest, a talk summary): the text alone. `model` and `level` are Gemini's, for the fallback."""
        def gemini(g):
            name = model if isinstance(model, str) and model.startswith("gemini") else getattr(g, "reply_model", None)
            return g.think(contents, system_instruction, model=name or DIGEST_MODEL,
                           max_output_tokens=max_output_tokens, kind=kind, level=level)
        out = await self._run(kind, system_instruction, contents, max_output_tokens, gemini=gemini)
        return out[0] if out else None

    async def search(self, question: str, max_output_tokens: int = 800, kind: str = "sky") -> str | None:
        """A web answer — `WebSearch` alone, on the background model; the sources stay out of the answer."""
        out = await self._run(kind, None, question, max_output_tokens, toolset="search",
                              gemini=lambda g: g.search(question, max_output_tokens, kind))
        return out[0] if out else None

    async def embed(self, texts: list[str], task: str = "RETRIEVAL_DOCUMENT", kind: str = "embed") -> list | None:
        """The embeddings stay Gemini's (Anthropic has none): on `embedder`, or None without one."""
        if self.embedder is None:
            return None
        return await self.embedder.embed(texts, task=task, kind=kind)

    # Gemini's prompt-stage check has no Claude counterpart: no `probe` at all, so its callers skip the check — the
    # talk summaries are kept as written and the scan is off (code review v7.1 #1: a probe that answered None was an
    # outage to the talk writer, which then never kept a summary and tried again every 10 minutes, for good)
    probe = None

    # --- one call -------------------------------------------------------------------------------------------------
    def _unavailable(self) -> str | None:
        if self.blocked:
            return f"blocked ({self.blocked})"
        if self.muted():
            return f"rate limit (until {self.status.muted_until})"
        return None

    async def _instead(self, why: str, gemini) -> Any:
        """Decision 1: the same call on Gemini until the reset, or silence."""
        if self.limit_fallback == "gemini" and self.fallback is not None:
            log.info("on gemini: claude %s", why)
            LAST_SERVED.set("gemini")
            return await gemini(self.fallback)
        log.info("silent: claude %s", why)
        return None

    async def _run(self, kind: str, system: str | None, prompt: str, cap: int, *, answer: bool = False,
                   toolset: str | None = None, gemini) -> Any:
        LAST_SERVED.set("claude")
        why = self._unavailable()
        if why:
            out = await self._instead(why, gemini)
            return (out, "stop") if isinstance(out, str) else out
        out = await self._query(kind, system, prompt, cap, answer=answer, toolset=toolset)
        if out is _LIMIT:
            out = await self._instead(self._unavailable() or f"rate limit (until {self.status.muted_until})", gemini)
            return (out, "stop") if isinstance(out, str) else out
        return out

    def _prompt_file(self, system: str | None) -> str | None:
        """The call's system prompt in a file of its own (0600) in the CLI's config dir; None with no prompt."""
        if not system:
            return None
        folder = Path(self.config_dir) / PROMPTS_DIR
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = folder / f"{uuid.uuid4().hex}.md"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:  # code review v7.1 #7: written whole, and never left behind half written
            try:
                view = memoryview(system.encode("utf-8"))
                while view:
                    view = view[os.write(fd, view):]
            finally:
                os.close(fd)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(path)
            raise
        return str(path)

    def _report(self, kind: str, model: str, usage: Any, ok: bool, cost: Any, started: float,
                blocked: str | None = None, warm: bool | None = None) -> None:
        if self._sink is None:
            return
        latency = round((self._mono() - started) * 1000)
        extra = {k: v for k, v in (("blocked", blocked), ("warm", warm)) if v is not None}  # a 5-argument sink keeps
        try:
            self._sink(kind, model, usage, ok, cost, latency_ms=latency, **extra)
        except Exception:
            log.exception("usage accounting failed")

    async def _query(self, kind: str, system: str | None, prompt: str, cap: int, *, answer: bool,
                     toolset: str | None) -> Any:
        """(text, finish), `_LIMIT`, or None: the call, bounded and checked, tried once more when it hangs, with one
        usage line a try."""
        model, effort, think = self.model_for(kind), self.effort_for(kind), self.thinks(kind)
        if cap > 0:
            cap += THINK_HEADROOM  # the thinking never eats the answer
        timeout_s = REPLY_TIMEOUT_S if kind in ANSWER_KINDS else THINK_TIMEOUT_S
        try:  # code review v7.1 #8: a service on the wrong image fails its calls, never raises out of them
            query, make_options = self._query_fn or _default_query(), self._options or _default_options()
        except ImportError as exc:
            log.error("claude call failed: %s — the SDK is not installed", type(exc).__name__)
            self._failed(type(exc).__name__)
            return None
        try:
            path = self._prompt_file(system)
        except OSError as exc:
            log.error("claude prompt file not written (%s)", type(exc).__name__)
            return None
        try:
            options = make_options(**client_options(
                path, model=model, max_output_tokens=cap, config_dir=self.config_dir, toolset=toolset,
                effort=effort, think=think))
            # v7.2 (AGORA-243): a voice call whose slow part splits its prompt may go warm, through the CLI started
            # ahead for its key; a warm call that fails or hangs goes cold once (the next try), never silent for it
            split = split_prompt(system, PROMPT_SLOW.get()) if kind in VOICE_KINDS and toolset is None else None
            key = (split[0], model, effort, think, cap) if split else None
            warm = self._take_warm(key)
            async with (self._voice_gate if kind in VOICE_KINDS else self._gate):
                for attempt in range(1, REPLY_TRIES + 1):
                    hot = warm is not None and attempt == 1
                    started = self._mono()
                    call = (warm.query, f"{split[1]}\n\n{prompt}" if split[1] else prompt, None) if hot else \
                        (query, prompt, options)
                    try:
                        seen = await asyncio.wait_for(self._consume(call[0], call[1], call[2], toolset), timeout_s)
                    except TimeoutError:
                        log.warning("claude %s timed out after %d s (try %d of %d%s)", kind, timeout_s, attempt,
                                    REPLY_TRIES, ", warm" if hot else "")
                        self._report(kind, model, None, False, None, started, warm=hot if key else None)
                        continue
                    except Exception as exc:  # noqa: BLE001 — any SDK or CLI failure means silence
                        self._report(kind, model, None, False, None, started, warm=hot if key else None)
                        if hot:  # the CLI started ahead failed: this call goes cold once
                            log.warning("claude %s warm failed: %s — cold", kind, type(exc).__name__)
                            continue
                        log.error("claude call failed: %s", type(exc).__name__)
                        self._failed(type(exc).__name__)
                        return None
                    if key:
                        log.info("claude %s %s", kind, "warm" if hot else "cold")  # never a text
                    return self._judge(kind, model, seen, started, answer, warm=hot if key else None)
                self._failed("timeout")
                return None
        finally:
            if path:
                with contextlib.suppress(OSError):
                    os.unlink(path)
            if key:
                self._prewarm(key, make_options, model, effort, think, cap)

    # --- v7.2: the CLI started ahead ------------------------------------------------------------------------------
    def _take_warm(self, key: tuple | None) -> WarmCli | None:
        """The waiting CLI when it is ready for this very key — then it is taken (one call each); one for another
        key, or past its life, is closed; one still connecting is left for the next call."""
        warm = self._warm
        if warm is None or key is None:
            return None
        if warm.key != key or warm.stale():
            warm.close()
            self._warm = None
            return None
        if not warm.ready():
            return None
        self._warm = None
        return warm

    def _prewarm(self, key: tuple, make_options: Callable[..., Any], model: str, effort: str, think: bool,
                 cap: int) -> None:
        """After a voice call, the CLI for the next: started with this call's key, unless one for it already waits."""
        if not self._warm_on:
            return
        if self._warm is not None and self._warm.key == key and not self._warm.stale():
            return
        if self._warm is not None:
            self._warm.close()
            self._warm = None
        try:
            make_client = self._client_cls or _default_client()
            path = self._prompt_file(key[0])
        except (ImportError, OSError) as exc:
            log.warning("claude warm cli not started: %s", type(exc).__name__)
            return
        try:
            options = make_options(**client_options(path, model=model, max_output_tokens=cap,
                                                    config_dir=self.config_dir, effort=effort, think=think))
            self._warm = WarmCli(key, options, path, make_client, time.monotonic)
        except Exception as exc:  # noqa: BLE001 — no waiting CLI is a cold next call, never a failure
            log.warning("claude warm cli not started: %s", type(exc).__name__)
            with contextlib.suppress(OSError):
                os.unlink(path)

    async def close(self) -> None:
        """At the agent's stop: the waiting CLI closed and waited for."""
        warm, self._warm = self._warm, None
        if warm is not None:
            await warm.aclose()

    async def _consume(self, query, prompt: str, options: Any, toolset: str | None) -> dict[str, Any]:
        seen: dict[str, Any] = {"result": None, "parts": [], "init": False, "over_limit": False, "refused": None,
                                "toolset": toolset}
        try:
            await self._stream(query, prompt, options, toolset, seen)
        except Exception:
            # the CLI ends an error result — a refusal, a 429, an API failure — by exiting 1, and the SDK raises that
            # as `ResultError` after the result message: the result is what `_judge` reads (found 2026-11-10, when
            # Haiku's safety classifier declined a made-up prompt and the decline came out as a failure)
            if seen["result"] is None or not getattr(seen["result"], "is_error", False):
                raise
        return seen

    async def _stream(self, query, prompt: str, options: Any, toolset: str | None, seen: dict[str, Any]) -> None:
        async with contextlib.aclosing(query(prompt=prompt, options=options)) as stream:
            async for msg in stream:
                kind = type(msg).__name__
                if getattr(msg, "subtype", None) == "init" and isinstance(getattr(msg, "data", None), Mapping):
                    seen["init"] = True
                    seen["refused"] = self._check_init(msg.data, toolset)
                    if seen["refused"]:
                        break
                elif kind == "RateLimitEvent":
                    info = getattr(msg, "rate_limit_info", None)
                    self._rate_limit(info)
                    raw = getattr(info, "raw", None)
                    seen["over_limit"] = seen["over_limit"] or getattr(info, "status", None) == "rejected" or bool(
                        isinstance(raw, Mapping) and raw.get("isUsingOverage"))
                elif kind == "AssistantMessage" and not getattr(msg, "error", None):
                    seen["parts"].extend(b.text for b in getattr(msg, "content", [])
                                         if isinstance(getattr(b, "text", None), str))
                elif kind == "ResultMessage":
                    seen["result"] = msg

    def _judge(self, kind: str, model: str, seen: dict[str, Any], started: float, answer: bool,
               warm: bool | None = None) -> Any:
        """The checked call's answer — and its one usage line, `ok` only for a checked, successful, kept answer."""
        result = seen["result"]
        usage = getattr(result, "usage", None)
        cost = getattr(result, "total_cost_usd", None)
        model_usage = getattr(result, "model_usage", None)
        named = next(iter(model_usage), None) if isinstance(model_usage, Mapping) and model_usage else None
        model = named if isinstance(named, str) and named else model  # the id the CLI ran, else the alias
        checked = (result is not None and self.blocked is None and seen["init"] and not seen["over_limit"]
                   and seen["refused"] is None)
        good = checked and not getattr(result, "is_error", True)
        text = (answer_of(result, seen["parts"], seen.get("toolset")) if good else "")
        declined = None
        if checked and getattr(result, "stop_reason", None) == "refusal":  # the CLI reports it as an error result
            declined = "stop"
        elif good and answer and text:
            declined = refusal_marker(text)
        if declined:
            LAST_BLOCK.set(("refusal", declined, None))
            self._report(kind, model, usage, False, cost, started, blocked="refusal", warm=warm)
            log.warning("claude declined: reason=%s kind=%s model=%s category=%s", declined, kind, model,
                        refusal_category(result))  # never a text: the classifier's label alone
            return None
        self._report(kind, model, usage, good and bool(text), cost, started, warm=warm)
        if self.blocked:
            return _LIMIT  # code review v7.1 #4: the call that found it blocked takes decision 1, as every later one
        if seen["refused"]:
            return None  # this call's tools alone were wrong
        if seen["over_limit"]:
            self._mute_over_limit()
            log.warning("claude is over the subscription's limit — no extra usage, ever; muted until %s",
                        self.status.muted_until)
            return _LIMIT
        if getattr(result, "api_error_status", None) == 429:
            self.status.muted_until = max(int(self.status.muted_until or 0), self._now() + WARN_MUTE_S)
            self._save()
            log.warning("claude rate limited (429) — muted until %s", self.status.muted_until)
            return _LIMIT
        if not seen["init"]:
            log.error("claude: no init message — the auth source is unverified; no answer")
            return None
        if result is None or getattr(result, "is_error", True):
            log.error("claude result error: %s (http %s, stop %s, terminal %s, %s)", getattr(result, "subtype", None),
                      getattr(result, "api_error_status", None), getattr(result, "stop_reason", None),
                      getattr(result, "terminal_reason", None), cli_error_kind(result))  # names, never a text
            self._failed(f"{getattr(result, 'subtype', None)} (http {getattr(result, 'api_error_status', None)})")
            return None
        if not text:
            log.error("claude returned an empty answer (kind %s)", kind)
            return None
        if self.status.last_error:
            self.status.last_error = None
            self._save()
        return text, "max_tokens" if getattr(result, "stop_reason", None) == "max_tokens" else "stop"


SECRET_SUFFIXES = ("_PASSWORD", "_TOKEN", "_KEY", "_SECRET")  # every member's password, the registration and panel
                                                             # tokens, a service's key


def secret_vars(env: Mapping[str, str]) -> list[str]:
    """v7.1 — the secrets an agent on Claude never hands its CLI (the SDK passes the whole environment on): every
    `*_PASSWORD`, `*_TOKEN`, `*_KEY` and `*_SECRET` but the subscription's OAuth token, which the CLI needs."""
    return sorted(k for k in env if k.endswith(SECRET_SUFFIXES) and k != OAUTH_VAR)


def claude_client_for(environ: MutableMapping[str, str], *, status_file: Path, sink: Callable[..., None],
                      gemini_sink: Callable[..., None], clock: Callable[[], int], recall: bool,
                      gemini=None) -> ClaudeClient:
    """v7.1 — the client of an agent on Claude that is not Claude himself (a persona, the cat, Hermes), from its
    settings in `environ`: v4.4's layers first (refuse a forbidden variable or no OAuth token, then scrub), then every
    secret out of the environment the CLI inherits. A Gemini client beside it only when needed — `recall` (the
    embeddings) or `CLAUDE_LIMIT_FALLBACK=gemini` — with the key handed over, never left in the environment;
    `gemini` (tests) stands in for it."""
    check_startup(environ)
    scrub(environ)
    env = environ.get
    gemini_key = str(env("GEMINI_API_KEY", "")).strip()
    for name in secret_vars(environ):
        environ.pop(name, None)
    fallback = str(env("CLAUDE_LIMIT_FALLBACK", "gemini")).strip()
    if fallback not in LIMIT_FALLBACKS:
        log.warning("CLAUDE_LIMIT_FALLBACK is not one of %s — using gemini", ", ".join(LIMIT_FALLBACKS))
        fallback = "gemini"
    needs_gemini = recall or fallback == "gemini"
    if needs_gemini and gemini is None:
        if gemini_key:
            from agents.llm import GeminiClient
            gemini = GeminiClient(sink=gemini_sink, api_key=gemini_key)
        else:
            log.warning("no GEMINI_API_KEY on claude: %s", ", ".join(
                w for w, on in (("no meaning search in recall", recall),
                                ("silent at the limit", fallback == "gemini")) if on))
    thinking = str(env("CLAUDE_THINKING", "off")).strip()
    effort = str(env("CLAUDE_EFFORT", "low")).strip()
    if thinking not in THINKING_MODES:
        log.warning("CLAUDE_THINKING is not one of %s — using off", ", ".join(THINKING_MODES))
        thinking = "off"
    if effort not in EFFORTS:
        log.warning("CLAUDE_EFFORT is not one of %s — using low", ", ".join(EFFORTS))
        effort = "low"
    try:
        concurrency = int(str(env("CLAUDE_CONCURRENCY", "2")))
    except ValueError:
        log.warning("CLAUDE_CONCURRENCY is not a number — using %d", CONCURRENCY)
        concurrency = CONCURRENCY
    return ClaudeClient(
        reply_model=str(env("CLAUDE_REPLY_MODEL", "sonnet")).strip() or "sonnet",
        background_model=str(env("CLAUDE_BACKGROUND_MODEL", "haiku")).strip() or "haiku",
        config_dir=str(env("CLAUDE_CONFIG_DIR", "/tmp/claude")),
        status_file=status_file, sink=sink, clock=clock, concurrency=concurrency, limit_fallback=fallback,
        fallback=gemini if fallback == "gemini" else None, embedder=gemini if recall else None,
        thinking=thinking, effort=effort)
