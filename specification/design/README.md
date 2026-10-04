# Design

The panel's UI (phases v3.3 viewing · v3.4 control).

| File | What it is |
|---|---|
| [panel-brief.md](panel-brief.md) | The brief given to Claude Design (2026-10-04). |
| [design_handoff_agora_panel/](design_handoff_agora_panel/README.md) | The delivered handoff — **the source of truth for the UI**: screens, states, tokens, copy, status logic, formatting. |
| `design_handoff_agora_panel/agora-panel.css` | The starter stylesheet → `panel/static/panel.css` in v3.3. |
| `design_handoff_agora_panel/prototype/` | The interactive HTML reference (open over http). A design reference only — not production code; it loads React, Babel and icons from unpkg, which the real panel never does. |

## Adoption notes (2026-10-04, decided by the owner)

1. **UI language: English.** The handoff overrides the brief's Ukrainian copy; the agents' own texts (summaries,
   memories, plans, the today block) are shown as-is, in Ukrainian.
2. **System fonts only.** No webfont: the design's Inter becomes the platform UI font stack in `agora-panel.css`
   (`system-ui`, SF Pro, Segoe UI, Roboto, Ubuntu, …); icons are inline SVG. The LAN-only panel makes no outside
   requests.
3. **Only what is recorded.** The handoff's live agent fields that nothing records — "Last activity", the
   current activity ("working… replying", "writing summary"), the session size, "reconnect attempt 4 s ago" —
   are left out. The cards show container state and uptime (docker), the `state/` files and the logs. In the status
   logic the "work" row for a replying agent is dropped; "reconnecting" stays (derived from the simulation's own
   health probe), and "work" remains for v3.4 actions in flight.
4. **No "running in terminal".** The terminal state, its notice and lock-based detection are removed: the panel
   manages containers only. Dev mode on the Mac keeps its rule — stop the server's agent first.

5. **One refresh for everything, every 10 s** — the dashboard, an open log and an open agent's memory load together
   (the handoff's 2–4 s log / 30 s drawer polling is dropped); the page redraws only when something changed, and
   the drawer's slide-in plays once when it opens.

Everything else is kept as designed: both themes (dark default), the 760 px breakpoint, the status vocabulary,
the confirmations (v3.4), the formatting rules, the owner-only "deviation" badge on plans.
