---
name: sessions
description: List the session aliases (alias → Claude Code session address, role, live or stale) plus the open sessions that have no alias. Usage - /sessions; /sessions prune removes the stale aliases; /sessions rm <alias> removes one.
---

# Sessions [prune | rm <alias>]

1. Run `.claude/session-aliases/registry.py list` (tab-separated: alias, address, role, cwd, joined) and
   `ListAgents` (load via ToolSearch if deferred; its first line `This session is <name>` is this tab).
2. **`rm <alias>`:** `registry.py rm <alias>`, then show the list.
   **`prune`:** `registry.py rm` every alias whose address is not this session and not in `ListAgents`,
   then show the list. (A role brief in `roles/` is kept — `/join-session <alias>` reattaches it.)
3. **Show one table:** `alias | session | role | status`, where status is `this tab`, `open`, or
   `stale — run /join-session <alias> in that tab`. Below it, one line with the open sessions of this
   project (`ListAgents` names sharing this project's prefix) that have no alias, if any.
4. Nothing else — no advice beyond the stale hint.
