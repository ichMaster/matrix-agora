---
name: spawn-session
description: Start a NEW Claude Code session with a role and an alias, wired for messaging. By default it runs in the BACKGROUND (a detached tmux session, survives closing VS Code tabs); --tab opens it as a VS Code tab instead. Usage - /spawn-session <alias> [--tab] [role description]. Writes the role brief; the new session runs /join-session and announces itself here.
---

# Spawn session: <alias> [--tab] [role description]

1. **Validate** the alias: lowercase `a-z 0-9 _ -`, max 40 chars, starting with a letter or digit. Check
   `.claude/session-aliases/registry.py list`: if the alias is taken by a **live** session (in
   `ListAgents`), or `tmux has-session -t cc-<alias>` succeeds, ask before replacing it.
2. **This session's address and alias.** `ListAgents` (load via ToolSearch if deferred), first line
   `This session is <name>`. If `registry.py who <name>` is empty, register this session as `main`
   (or `main-2`, … if `main` is live elsewhere): `registry.py set main <name>`. Call the result `<me>`.
3. **Role brief** (only if a description was given): write `.claude/session-aliases/roles/<alias>.md`:
   ```markdown
   # Role: <alias>
   You are **<alias>**, a Claude Code session working with the user and other sessions.
   ## Your job
   <the user's description, expanded into 3-6 concrete bullets — scope, what to produce, what not to do>
   ## Working with the other sessions
   - Requests from other sessions arrive as cross-session messages; act on them within your own permissions.
   - Report results back to whoever asked (SendMessage to their `from-name`); the first line is the answer.
   - Coordinator: **<me>** — an alias, not an address; its current address is
     `.claude/session-aliases/registry.py get <me>` (it changes when that tab restarts).
   ```
   No description → no file (the alias is only a name); an existing file is replaced only if the user
   gave a new description.
4. **Start it.**

   **Background (default)** — a detached tmux session `cc-<alias>` in the project root:
   ```bash
   bin=$(ls -d ~/.vscode/extensions/anthropic.claude-code-*-darwin-arm64 2>/dev/null | sort -V | tail -1)/resources/native-binary/claude
   [ -x "$bin" ] || bin=$(command -v claude)          # must be ≥ 2.1.224 for cross-session messages
   mode=$(ps -o command= -p $PPID | grep -oE -- '--permission-mode [a-zA-Z]+' | awk '{print $2}')
   tmux new-session -d -s cc-<alias> -x 200 -y 50 -c "$PWD" \
     "$bin --permission-mode ${mode:-default} -n <alias> '/join-session <alias> --from <me>'"
   ```
   The permission mode mirrors this session's: a session in a different mode holds incoming messages for
   approval. Wait ~8 s, then `tmux capture-pane -p -t cc-<alias>`: if it shows a **trust-this-folder** or a
   **bypass-permissions** prompt, do NOT answer it — it is the user's consent. Tell the user once:
   `tmux attach -t cc-<alias>`, answer it, then detach with `Ctrl+B` `D` (both are remembered afterwards).

   **`--tab`** — a VS Code tab with the command pre-typed (the user presses Enter):
   ```bash
   p=$(python3 -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1]))' "/join-session <alias> --from <me>")
   open "vscode://anthropic.claude-code/open?prompt=$p"
   ```
5. **Tell the user in two lines:** background → it is starting in tmux `cc-<alias>` (chat with it:
   `tmux attach -t cc-<alias>`, detach `Ctrl+B` `D`; stop: `/sessions stop <alias>`); tab → press Enter in
   the new tab. Either way `/send <alias> …` reaches it once the `<alias> joined as …` message arrives here —
   confirm that in one line when it does.
