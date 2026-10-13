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

## Addendum (v4.2): card variants for the new agent types

From v4 the room holds agents of four types, and a card follows its agent's type and capabilities (ARCHITECTURE
§The panel). The variants reuse the handoff's components and Nocturne tokens and add no new token. Only `creature`
is built in v4.2; the other two are fixed here so later phases build to them.

| Type | Card body (under "Runs on" / "Uptime") | Drawer tabs | Actions |
|---|---|---|---|
| `persona` (Ada, Bruno) | "Today": the today block's first line | Log · Last session · Memories · Plans · Today · Tokens | start / stop / restart; stop/restart promise a session summary; Forget |
| `creature` (Кіт, v4.2) | "Mood of the day": the horoscope resolution's first line (`today-line`, `lang="uk"`); "No horoscope yet — it is cast once a day" until it exists; from v4.3 a `muted` 12 px line under it — «92 theses · last nudge 14:05 · 2 today» (another day's nudge with its date, «Oct 7, 21:40»; «no nudge yet» before the first) | Log · Mood · Tokens. Mood: (v4.3) the same line in a `meta-line` on top, then the resolution as `read` text, the date in the `meta-line`, the three biorhythms (name, value, label) as a plain list, the full reading under a collapsed `<details>` | start / stop / restart; no summary promise; no Forget |
| `assistant` (Claude, v4.4) | One line: engine · model · billing, e.g. "claude-sdk · opus · subscription"; below it the rate-limit status as a pill (ok / warn when muted / err when rejected or the auth check failed, with the reset time) and the auth check («OAuth ✓ (no API key)», «blocked: …», «refused: …») — from `state/<name>.ratelimit.json` | Log · Tokens; the token table's billing column shows `subscription` and «—» for its cost | start / stop / restart; no summary promise; no Forget |
| `bridge` (Лілі, v6.1) | One line: Lumi reachable / unreachable (a status dot, the `/v1/health` probe), and the last turn's outcome and time (ok / busy / error / timeout) | Log · Tokens | start / stop / restart (the bridge container); no summary promise; no Forget |

**The token chart for N agents (v4.2):** the stacked bars and the legend show every agent. The series take the
accent at 100 % (`a`), 42 % (`b`), 70 % (`c`), 24 % (`d`), then the text colour at 35 % (`e`). These are tints of
existing tokens, so both themes follow.

## Addendum (v4.7): Settings and Claude's files

The screens reuse the handoff's drawer, card, field, pill, dialog and toast components and the Nocturne tokens. They
add no new token; there are four new icons drawn in the same grid (sliders, folder, upload, trash).

**Settings, under their service (AGORA-078 — the owner, 2026-10-11).** A service's settings open from a **Settings** button on its simulation card, in a drawer titled «Settings · Agora» with the subtitle «matrix-chat · the service's settings · a save restarts the agents it concerns». The groups are Room & turns · Ада і Бруно: ходи · Кіт у кімнаті · Клод у кімнаті · Сесії розмови. An agent's own settings sit in a **Settings** tab on its drawer, with the groups Пам'ять · Плани · Життя · Модель. There is no global entry, so a future portal adds its own card. Everything below holds in both places.
- **Groups:** one collapsible card per group, in the order above; a card's open state survives the 10 s poll.
- **Each field:**
  - a label: the schema's Ukrainian description, then the variable name in mono;
  - an input: a number with its bounds, `HH-HH` text, a select for the choices, or text;
  - the unit;
  - a 12 px muted line: `default <value> · runs: <value> · <source>`. When the agents differ, each value is listed
    with its agents;
  - an override shows an `ok` pill «panel» and a **Reset** button. Reset is pending until Save, shown as
    «reset → server value» with **Undo**.
- **Footer:** sticky, with **Save (n)** and «restarts Ada, Bruno, Кіт, Клод».
- **The confirmation dialog:**
  - title: «Save n settings?»;
  - body: the names, then «Restarts: … — each writes its session summary first.» or «No agent needs a restart.»;
  - button: **Save and restart**.
- **The result toast:** «Saved … · restarted … · skipped kit (not running)». An invalid value comes back as «Not
  saved: NAME: why».
- **No redraw while typing:** typed values live in the page's state; the poll redraws the open settings only when nothing is pending, and the cards behind a service's drawer stay live.

**Claude's files: a Files tab on Claude's drawer (engine `claude-sdk` only).**
- **The list:** relative path, size and time, newest first, with «Empty — nothing written yet» when there is none.
- **Each row:** **Open** (text files ≤ 256 KB, shown in a mono block), **Download** and **Delete**. Delete asks «Delete
  <path>? Claude loses this note.»
- **Upload:** a file picker with an optional folder path. Replacing an existing file asks «Replace <path>?» first.
  The cap is 5 MB, and a refusal shows the server's reason.
