#!/usr/bin/env python3
"""Session alias registry: alias -> Claude Code session address (the name ListAgents shows).

usage: registry.py set <alias> <address> [--cwd DIR] [--type tab|bg|terminal] | get <alias> | who <address>
       | list | rm <alias>
The type is detected from the calling session's environment unless --type is given: bg = a background
session in tmux (cc-<alias>), tab = a VS Code tab, terminal = a plain terminal session.
Data: registry.json next to this file (gitignored: addresses are per machine); roles/<alias>.md hold
optional role briefs. Run from the project root: .claude/session-aliases/registry.py …
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


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    cmd, args, data = argv[0], argv[1:], load()
    if cmd == "set" and len(args) >= 2:
        alias, address = args[0].lower(), args[1]
        if not ALIAS.match(alias):
            print(f"bad alias {alias!r}: use a-z 0-9 _ - (max 40)", file=sys.stderr)
            return 2
        cwd = args[args.index("--cwd") + 1] if "--cwd" in args else os.getcwd()
        for other in [a for a, e in data.items() if e["address"] == address and a != alias]:
            del data[other]  # one alias per session: the newest wins
        role = HOME / "roles" / f"{alias}.md"
        kind, tmux = detect_type()
        if "--type" in args:
            kind, tmux = args[args.index("--type") + 1], (f"cc-{alias}" if args[args.index("--type") + 1] == "bg"
                                                          else None)
        data[alias] = {"address": address, "type": kind, "tmux": tmux, "cwd": cwd,
                       "role": str(role) if role.exists() else None,
                       "joined": datetime.datetime.now().astimezone().isoformat(timespec="seconds")}
        save(data)
        print(f"{alias} -> {address} ({kind}{', tmux ' + tmux if tmux else ''})")
    elif cmd == "get" and len(args) == 1:
        key = args[0].lower()
        hits = [key] if key in data else [a for a in data if a.startswith(key)]  # a unique prefix works too
        if len(hits) != 1:
            print(f"no alias {args[0]!r}" + (f" (ambiguous: {', '.join(sorted(hits))})" if hits else ""),
                  file=sys.stderr)
            return 1
        print(data[hits[0]]["address"])
    elif cmd == "who" and len(args) == 1:
        print(next((a for a, e in data.items() if e["address"] == args[0]), ""))
    elif cmd == "rm" and len(args) == 1:
        data.pop(args[0].lower(), None)
        save(data)
    elif cmd == "list":
        for alias, e in sorted(data.items()):
            print(f"{alias}\t{e.get('type', '?')}\t{e['address']}\t{e.get('tmux') or '-'}\t"
                  f"{'role' if e.get('role') else '-'}\t{e['cwd']}\t{e['joined']}")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
