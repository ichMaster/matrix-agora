---
name: send
description: Send a message to another Claude Code session by its alias (from /join or /spawn), a unique alias prefix, or its raw address. Usage - /send <alias> <message>; /send with no arguments lists the aliases and which are live.
---

# Send: <alias> <message>

**No arguments → list.** Run `.claude/session-aliases/registry.py list` and `ListAgents` (load via
ToolSearch if deferred); show `alias → address`, live or stale (a stale address is not in ListAgents), and
whether it has a role. Stop.

Otherwise:

1. **Resolve.** `.claude/session-aliases/registry.py get <alias>` → the address (a unique prefix of an
   alias also resolves, e.g. `sea` → `searcher`): the session's socket `uds:…` when it is live, else its
   name. Not an alias but a name ListAgents shows → use it as is. Neither → say so, list the aliases, stop.
2. **Live?** A `uds:` address is live (the registry checked its socket). A plain name must be in
   `ListAgents`; if not, say the alias is stale (that session was closed or restarted) and suggest
   `/join <alias>` there. Don't send.
3. **Who am I.** `echo uds:$CLAUDE_CODE_MESSAGING_SOCKET` is this session's address;
   `registry.py who <that>` gives its alias (may be empty).
4. **Send** with `SendMessage` (`to` = the address): `[<my alias>] ` + the user's message **verbatim** as the
   first line (no alias → no prefix; the header shows only session names, so the prefix is how the recipient
   sees who wrote), then
   a blank line and `— from <my alias>; reply with SendMessage to <my socket>` (no alias → `— from
   <my socket>; …`).
5. **Report in one line:** `→ <alias> (<address>)`. The reply arrives here on its own as a
   cross-session message — don't poll, don't wait; when it comes, show it to the user.
