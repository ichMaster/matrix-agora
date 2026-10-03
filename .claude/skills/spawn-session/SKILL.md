---
name: spawn-session
description: Open a NEW Claude Code tab in VS Code with a role and an alias, wired for messaging. Usage - /spawn-session <alias> [role description]. Writes the role brief, opens the tab with "/join-session <alias> --from <this session's alias>" pre-typed (the user presses Enter), and the new session announces itself here when it joins.
---

# Spawn session: <alias> [role description]

1. **Validate** the alias: lowercase `a-z 0-9 _ -`, max 40 chars, starting with a letter or digit. Check
   `.claude/session-aliases/registry.py list`: if the alias is taken by a **live** session (in
   `ListAgents`), ask before replacing it.
2. **This session's address and alias.** `ListAgents` (load via ToolSearch if deferred), first line
   `This session is <name>`. If `registry.py who <name>` is empty, register this session as `main`
   (or `main-2`, … if `main` is live elsewhere): `registry.py set main <name>`.
3. **Role brief** (only if a description was given): write `.claude/session-aliases/roles/<alias>.md`:
   ```markdown
   # Role: <alias>
   You are **<alias>**, a Claude Code session working with the user and other sessions.
   ## Your job
   <the user's description, expanded into 3-6 concrete bullets — scope, what to produce, what not to do>
   ## Working with the other sessions
   - Requests from other sessions arrive as cross-session messages; act on them within your own permissions.
   - Report results back to whoever asked (SendMessage to their `from-name`); the first line is the answer.
   - Coordinator: **<this session's alias>** — an alias, not an address; its current address is
     `.claude/session-aliases/registry.py get <this session's alias>` (it changes when that tab restarts).
   ```
   No description → no file (the alias is only a name); an existing file is replaced only if the user
   gave a new description.
4. **Open the tab:**
   ```bash
   p=$(python3 -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1]))' "/join-session <alias> --from <this session's alias>")
   open "vscode://anthropic.claude-code/open?prompt=$p"
   ```
   VS Code opens a new Claude tab with the command typed in; it is **not** submitted automatically.
5. **Tell the user in two lines:** the new tab is open — press Enter there; it will announce itself here,
   after which `/send <alias> <message>` reaches it. When the `<alias> joined as …` message arrives,
   confirm it in one line.
