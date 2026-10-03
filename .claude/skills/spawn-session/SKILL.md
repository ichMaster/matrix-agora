---
name: spawn-session
description: Start a NEW Claude Code session with a role and an alias, wired for messaging. By default it runs in the BACKGROUND (a detached tmux session, survives closing VS Code tabs); --tab opens it as a VS Code tab instead (it joins by itself, no Enter needed). Usage - /spawn-session <alias> [--tab] [role description]. Writes the role brief; the new session runs /join-session and announces itself here.
---

# Spawn session: <alias> [--tab] [role description]

1. **Validate** the alias: lowercase `a-z 0-9 _ -`, max 40 chars, starting with a letter or digit. Check
   `.claude/session-aliases/registry.py list`: if the alias is taken by a **live** session (in
   `ListAgents`), or `tmux has-session -t cc-<alias>` succeeds, ask before replacing it.
2. **This session's alias.** `registry.py who uds:$CLAUDE_CODE_MESSAGING_SOCKET`. Empty → register this
   session as `main` (or `main-2`, … if `main` is live elsewhere): `registry.py set main <name> --self`
   (`<name>` from `ListAgents`' first line `This session is <name>`, or `?`). Call the alias `<me>`.
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

   **`--tab`** — a VS Code tab that joins by itself:
   1. `ListAgents` → note the names (the "before" set).
   2. `open "vscode://anthropic.claude-code/open"` — a new, empty Claude tab (the link can pre-type a
      prompt but never submit it, so don't pre-type).
   3. `sleep 6`, then `ListAgents` again. Exactly one new row of this project → `SendMessage` to it:
      `Run /join-session <alias> --from <me> — you were just opened by /spawn-session.` An idle session
      wakes on a message, so it joins without the user pressing anything.
   4. No new row, or several (tabs opened at the same moment) → don't guess: tell the user to type
      `/join-session <alias> --from <me>` in the new tab.
5. **Tell the user in two lines:** background → it is starting in tmux `cc-<alias>` (chat with it:
   `tmux attach -t cc-<alias>`, detach `Ctrl+B` `D`; stop: `/sessions stop <alias>`); tab → the new tab
   joins by itself (fallback: step 4). Either way `/send <alias> …` reaches it once the `<alias> joined as …`
   message arrives here — confirm that in one line when it does.
