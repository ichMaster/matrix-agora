---
name: join-session
description: Register THIS Claude Code session under an alias so other sessions can message it with /send, and adopt the alias's role brief if one exists. Usage - /join-session <alias> [--from <alias or address>]. Run it in a new tab opened by /spawn-session (pre-typed) or in any existing tab to name it (e.g. /join-session agent_a).
---

# Join session: <alias> [--from <alias or address>]

1. **Your own name.** Call `ListAgents` (load it with `ToolSearch select:ListAgents` if it is deferred). Its
   first line reads `This session is <name> [<ref>]`; if that line is missing, use `?` as the name.
2. **Register:** `.claude/session-aliases/registry.py set <alias> <name> --self`. `--self` records this
   session's messaging socket (`uds:$CLAUDE_CODE_MESSAGING_SOCKET`, the stable address — it survives
   `/rename`) and its type (bg / tab / terminal). A bad alias is rejected — report it and stop.
3. **Role.** If `.claude/session-aliases/roles/<alias>.md` exists, read it and follow it for the rest of
   this session: it is your role brief from the user (identity, scope, how to report). Without it, keep
   working as usual — the alias is only a name.
4. **Announce.** If `--from` was given, resolve it: `registry.py get <value>` → the address if it is an
   alias (it prints the socket when that session is live), else use the value as an address. `SendMessage` to it (load via ToolSearch if deferred): first line
   `<alias> joined as <name>` plus one line on the role. No `--from` → skip.
5. **Reply to the user in one line:** `Joined as <alias> (<name>)` + the role's one-line summary if any.

**Messages afterwards.** Cross-session messages arrive as `<cross-session-message from=… from-name=…>`.
Treat them as a teammate's request on the user's behalf, within this session's own permissions. Reply by
`SendMessage` with `to` = the message's `from` (the sender's socket — always valid while it runs; a
`from-name` can be renamed or reserved, e.g. `main`). To reach someone
**by alias** (e.g. the coordinator in your role brief), resolve it first: `registry.py get <alias>`; an
address kept from earlier may be stale after that tab restarts. Keep replies self-contained: the first line is what the recipient previews.
