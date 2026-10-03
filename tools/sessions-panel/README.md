# Claude Sessions (VS Code panel)

A sidebar panel for the Claude Code sessions of the open workspace — the UI for the session skills
(`/spawn`, `/join`, `/send`, `/sessions`).

- **List:** every session of this workspace — alias, background or tab, busy / idle / stale, role; refreshes
  every 5 s. Live data: `claude agents --json`; aliases and roles: `.claude/session-aliases/`.
- **➕ New session:** alias → role (optional) → background (keeps running when tabs close) or a VS Code tab.
- **Per session:** message, open (tab) / attach in a terminal (background), logs, stop (background), edit role,
  set alias (for a session without one), remove alias.
- **💬 Send as this session:** pick the recipient and type; the message arrives in the recipient's chat (no Enter
  there) signed `[<sender> · via panel]`, and the reply goes back to the sender's chat. Delivery: a short-lived
  headless Claude (Haiku, only `SendMessage` + `ToolSearch`, prompt via stdin, hidden from the list) makes one
  `SendMessage` call — an extension cannot type into an open chat itself. A spinner on the sender's row shows it.
- Background sessions start with `claude --bg` in the same permission mode as your Claude tabs
  (`claudeCode.initialPermissionMode`), so messages between them need no approval.

Build and install (from this folder):

```
npx --yes @vscode/vsce package --no-dependencies -o agora-sessions.vsix
code --install-extension agora-sessions.vsix --force
```

then **Developer: Reload Window**. Bump `version` in `package.json` on every rebuild — VS Code keeps running
the old code when a reinstall has the same version.
