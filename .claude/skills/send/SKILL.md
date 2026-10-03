---
name: send
description: Send a message to another Claude Code session by its alias (from /join-session or /spawn-session) or by its raw address. Usage - /send <alias> <message>; /send with no arguments lists the aliases and which are live.
---

# Send: <alias> <message>

**No arguments → list.** Run `.claude/session-aliases/registry.py list` and `ListAgents` (load via
ToolSearch if deferred); show `alias → address`, live or stale (a stale address is not in ListAgents), and
whether it has a role. Stop.

Otherwise:

1. **Resolve.** `.claude/session-aliases/registry.py get <alias>` → the address. Not an alias but a name
   ListAgents shows → use it as is. Neither → say so, list the aliases, stop.
2. **Live?** Check the address is in `ListAgents`. If not, say the alias is stale (that tab was closed or
   restarted) and suggest `/join-session <alias>` in that tab. Don't send.
3. **Who am I.** `ListAgents`' first line gives this session's address; `registry.py who <address>` gives
   its alias (may be empty).
4. **Send** with `SendMessage` (`to` = the address): the user's message **verbatim** as the first line, then
   a blank line and `— from <my alias>; reply with SendMessage to <my address>` (no alias → `— from
   <my address>; reply with SendMessage to <my address>`).
5. **Report in one line:** `→ <alias> (<address>)`. The reply arrives here on its own as a
   cross-session message — don't poll, don't wait; when it comes, show it to the user.
