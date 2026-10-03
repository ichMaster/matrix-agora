#!/usr/bin/env python3
"""Session alias registry: alias -> a Claude Code session, addressable by SendMessage.

usage: registry.py set <alias> <name> [--self] [--socket uds:PATH] [--type tab|bg|terminal] [--cwd DIR]
       registry.py get <alias|unique prefix>   -> the address to send to (the socket if live, else the name)
       registry.py who <name|uds:PATH>         -> the alias of that session (empty if none)
       registry.py list | rm <alias>

--self: the calling session registers itself; its messaging socket ($CLAUDE_CODE_MESSAGING_SOCKET) and its
type are taken from its environment. The socket (uds:/tmp/cc-socks/<pid>.sock, the `from` of its messages)
is the stable address: it survives /rename and dies with the session. Type: bg = a background session in
tmux (cc-<alias>), tab = a VS Code tab, terminal = a plain terminal. Data: registry.json next to this file
(gitignored: addresses are per machine); roles/<alias>.md hold optional role briefs. Run from the project
root: .claude/session-aliases/registry.py …
"""
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HOME = Path(__file__).resolve().parent
REG = HOME / "registry.json"
ALIAS = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")


def load() -> dict:
    try:
        return json.loads(REG.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def save(data: dict) -> None:
    fd, tmp = tempfile.mkstemp(dir=HOME, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, REG)


def detect_type() -> tuple[str, str | None]:
    """(type, tmux session) of the session running this script — it inherits that session's environment."""
    if os.environ.get("TMUX"):
        try:
            name = subprocess.run(["tmux", "display-message", "-p", "#S"], capture_output=True, text=True,
                                  timeout=5).stdout.strip() or None
        except (OSError, subprocess.SubprocessError):
            name = None
        return "bg", name
    if os.environ.get("CLAUDE_CODE_ENTRYPOINT") == "claude-vscode":
        return "tab", None
    return "terminal", None


def live(entry: dict) -> str:
    """live / stale by the session's socket file; unknown when no socket was recorded."""
    sock = entry.get("socket")
    if not sock:
        return "unknown"
    return "live" if Path(sock.removeprefix("uds:")).exists() else "stale"


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    cmd, args, data = argv[0], argv[1:], load()
    if cmd == "set" and len(args) >= 2:
        alias, name = args[0].lower(), args[1]
        if not ALIAS.match(alias):
            print(f"bad alias {alias!r}: use a-z 0-9 _ - (max 40)", file=sys.stderr)
            return 2

        def opt(flag: str) -> str | None:
            return args[args.index(flag) + 1] if flag in args else None

        kind, tmux, sock = "?", None, opt("--socket")
        if "--self" in args:
            kind, tmux = detect_type()
            env_sock = os.environ.get("CLAUDE_CODE_MESSAGING_SOCKET")
            sock = sock or (f"uds:{env_sock}" if env_sock else None)
        if opt("--type"):
            kind = opt("--type")
            tmux = tmux or (f"cc-{alias}" if kind == "bg" else None)
        for other in [a for a, e in data.items() if a != alias and (e["address"] == name
                                                                  or (sock and e.get("socket") == sock))]:
            del data[other]  # one alias per session: the newest wins
        role = HOME / "roles" / f"{alias}.md"
        data[alias] = {"address": name, "socket": sock, "type": kind, "tmux": tmux, "cwd": opt("--cwd") or os.getcwd(),
                       "role": str(role) if role.exists() else None,
                       "joined": datetime.datetime.now().astimezone().isoformat(timespec="seconds")}
        save(data)
        print(f"{alias} -> {name} ({kind}{', tmux ' + tmux if tmux else ''}{', ' + sock if sock else ''})")
    elif cmd == "get" and len(args) == 1:
        key = args[0].lower()
        hits = [key] if key in data else [a for a in data if a.startswith(key)]  # a unique prefix works too
        if len(hits) != 1:
            print(f"no alias {args[0]!r}" + (f" (ambiguous: {', '.join(sorted(hits))})" if hits else ""),
                  file=sys.stderr)
            return 1
        entry = data[hits[0]]
        print(entry["socket"] if live(entry) == "live" else entry["address"])
    elif cmd == "who" and len(args) == 1:
        print(next((a for a, e in data.items() if args[0] in (e["address"], e.get("socket"))), ""))
    elif cmd == "rm" and len(args) == 1:
        data.pop(args[0].lower(), None)
        save(data)
    elif cmd == "list":
        for alias, e in sorted(data.items()):
            print(f"{alias}\t{e.get('type', '?')}\t{e['address']}\t{live(e)}\t{e.get('tmux') or '-'}\t"
                  f"{'role' if e.get('role') else '-'}\t{e.get('socket') or '-'}\t{e['joined']}")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
