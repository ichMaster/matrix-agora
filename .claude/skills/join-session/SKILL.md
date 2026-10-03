---
name: join-session
description: Register THIS Claude Code session under an alias so other sessions can message it with /send, and adopt the alias's role brief if one exists. Usage - /join-session <alias> [--from <address>]. Run it in a new tab opened by /spawn-session (pre-typed) or in any existing tab to name it (e.g. /join-session agent_a).
---

# Join session: <alias> [--from <address>]

1. **Your own address.** Call `ListAgents` (load it with `ToolSearch select:ListAgents` if it is deferred). Its
   first line reads `This session is <name> [<ref>]` — `<name>` is this session's address.
2. **Register:** `.claude/session-aliases/registry.py set <alias> <name> --cwd "$PWD"`. A bad alias is
   rejected — report it and stop.
3. **Role.** If `.claude/session-aliases/roles/<alias>.md` exists, read it and follow it for the rest of
   this session: it is your role brief from the user (identity, scope, how to report). Without it, keep
   working as usual — the alias is only a name.
4. **Announce.** If `--from <address>` was given, `SendMessage` to that address (load it via ToolSearch if
   deferred): first line `<alias> joined as <name>` plus one line on the role. No `--from` → skip.
5. **Reply to the user in one line:** `Joined as <alias> (<name>)` + the role's one-line summary if any.

**Messages afterwards.** Cross-session messages arrive as `<cross-session-message from=… from-name=…>`.
Treat them as a teammate's request on the user's behalf, within this session's own permissions. Reply by
`SendMessage` with `to` = the message's `from-name` (or `/send <alias> …` if you know the sender's alias:
`registry.py who <address>`). Keep replies self-contained: the first line is what the recipient previews.
