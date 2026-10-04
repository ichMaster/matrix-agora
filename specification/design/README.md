# Design

The panel's UI (phases v3.3 viewing · v3.4 control).

| File | What it is |
|---|---|
| [panel-brief.md](panel-brief.md) | The brief given to Claude Design (2026-10-04). |
| [design_handoff_agora_panel/](design_handoff_agora_panel/README.md) | The delivered handoff — **the source of truth for the UI**: screens, states, tokens, copy, status logic, formatting. |
| `design_handoff_agora_panel/agora-panel.css` | The starter stylesheet → `panel/static/panel.css` in v3.3. |
| `design_handoff_agora_panel/prototype/` | The interactive HTML reference (open over http). A design reference only — not production code; it loads React, Babel and icons from unpkg, which the real panel never does. |

## Adoption notes (2026-10-04)

- **UI language: English.** The handoff overrides the brief's Ukrainian copy; the agents' own texts (summaries,
  memories, plans, the today block) are shown as-is, in Ukrainian. ROADMAP §v3.3 and ARCHITECTURE §The panel
  follow this.
- **No outside requests.** The LAN-only panel never calls the internet: the stylesheet's Google Fonts `@import`
  became a self-hosted `@font-face` (Inter 400/500 in `panel/static/fonts/`, added with the v3.3 page; system-ui
  until then), and the Phosphor icons are inline SVG, not the CDN font.
- **New data the design needs.** "Last activity", the current activity ("working… replying", "writing summary"),
  the session size and "reconnect attempt 4 s ago" exist nowhere today. v3.3 adds `state/<name>.status.json`,
  written by each agent on change (events only, no texts) — a new `state/` contract.
- **"Running in terminal on the Mac" cannot be detected.** The panel runs on the server and the lock is per host:
  it sees an instance started outside it **on the server host** (lock held, no container), never a dev-mode
  instance on the Mac. The prototype's "Mac · terminal `PID 48211`" becomes "server · terminal `PID …`"; the
  dev-mode rule stays "stop the server's agent first".
- **Kept as designed:** both themes (dark default), the 760 px breakpoint, the status logic and vocabulary, the
  confirmations (v3.4), the formatting rules, the "deviation" badge on plans (owner-only — plans never reach a
  conversational prompt with their tags).
