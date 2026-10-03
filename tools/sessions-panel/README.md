# Claude Sessions (VS Code panel)

A sidebar panel for the Claude Code sessions of the open workspace — the UI for the session skills
(`/spawn`, `/join`, `/send`, `/sessions`).

- **List:** every session of this workspace — alias, background or tab, busy / idle / stale, role; refreshes
  every 5 s. Live data: `claude agents --json`; aliases and roles: `.claude/session-aliases/`.
- **➕ New session:** alias → role (optional) → background (keeps running when tabs close) or a VS Code tab.
- **Per session:** message, open (tab) / attach in a terminal (background), logs, stop (background), edit role,
  set alias (for a session without one), remove alias.
- Background sessions start with `claude --bg` in the same permission mode as your Claude tabs
  (`claudeCode.initialPermissionMode`), so messages between them need no approval.

Build and install (from this folder):

```
npx --yes @vscode/vsce package --no-dependencies -o agora-sessions.vsix
code --install-extension agora-sessions.vsix --force
```

then **Developer: Reload Window**.
