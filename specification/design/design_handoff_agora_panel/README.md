# Handoff: Agora panel (v3.3 view · v3.4 control)

## Overview
The web panel of **matrix-agora**: a private, LAN-only control room for agent simulations. Today it shows one simulation (**Agora**, kind `matrix-chat`) with two agents (**Ada**, **Bruno**), their memories/plans/today block, token usage, host health and logs, and, from v3.4, start/stop/restart actions with confirmations. Source brief: `specification/design/panel-brief.md`. Architecture: `specification/ARCHITECTURE.md` §The panel; phases: `specification/ROADMAP.md` §v3.3–v3.4.

**UI language: English.** This overrides §9 of the brief, which asked for Ukrainian. Content the agents write themselves (session summaries, day memories, digests, plans, today block) is shown as-is (Ukrainian). The panel never translates it.

## About the design files
The files in `prototype/` are **design references built in HTML**. They show the intended look and behaviour and are not production code. Rebuild them in the panel's real stack: **one static page, plain HTML + CSS + vanilla JS, served by FastAPI at `panel/static/`**, with no framework and no build step (ARCHITECTURE §The panel). `agora-panel.css` is a ready starter stylesheet taken 1:1 from the prototype; use it as `panel/static/panel.css`.

To view the prototype, open `prototype/Agora Panel.dc.html` in a browser served over http (e.g. `python -m http.server` in `prototype/`). It has a Tweaks panel (theme, phase, screen, scenario, cost column, open-on-load overlays) that drives every state described below.

## Fidelity
**High-fidelity.** Final colours, type, spacing, states and copy. Recreate it pixel-perfectly.

---

## Design tokens
All values are in `agora-panel.css`. Theme is set by `data-theme="dark|light"` on `<html>`, persisted in `localStorage`, and defaults to dark. Derived roles (`--muted`, `--line`, status colours) **must be declared on the `[data-theme]` element** so they resolve against that theme's `--color-text`.

| Role | Dark | Light |
|---|---|---|
| `--color-bg` (ground) | `#161826` | `#e4e7f5` |
| `--color-surface` (cards, drawer) | `#232532` | `#f3f5fe` |
| `--color-text` | `#e9e9ed` | `#232532` |
| `--muted` (secondary text) | text 64% | text 64% |
| `--faint` (disabled tab) | text 40% | text 40% |
| `--line` (hairline fills, skeletons, code chips) | text 9% | text 9% |
| `--color-divider` (rules, outlines) | text 16% | text 16% |
| `--color-accent` (lines, outlines, bars) | `#9184d9` | `#5d5294` |
| `--accent-ink` (accent as text) | `#d2cefd` | `#5d5294` |
| `--accent-tint` (avatar bg, active rail item) | accent 15% | accent 15% |
| `--inset` (service row, log, plan boxes) | = bg | = bg |
| `--scrim` (drawer/dialog backdrop) | neutral-900 62% | neutral-700 38% |

**Status colours** (dot / text / tint = dot at 15–17% via `color-mix(in oklab, …)`):

| State | Dark dot · text | Light dot · text |
|---|---|---|
| ok, running | `oklch(.78 .14 155)` · `oklch(.86 .10 155)` | `oklch(.60 .13 155)` · `oklch(.42 .10 155)` |
| work (busy, pulses) | `#b5abfc` · `#d2cefd` | `#796cbf` · `#5d5294` |
| warn (reconnecting) | `oklch(.82 .13 78)` · `oklch(.88 .10 82)` | `oklch(.72 .14 70)` · `oklch(.46 .10 62)` |
| err (down) | `oklch(.70 .16 25)` · `oklch(.82 .10 25)` | `oklch(.58 .18 25)` · `oklch(.47 .16 25)` |
| stop (neutral) | `#9397ab` · `#cfd3e5` on `--line` | `#75798c` · `#595d6c` on `--line` |
| unknown | transparent, 1px **dashed** `--st-stop` border, dashed hollow dot | same |
| none (not created) | transparent, 1px solid divider border, hollow solid dot | same |

**Type:** Inter 400/500 (headings never above 500), with system mono for logs, ids, kinds and the token field.
- 26/500: gate title
- 18/500: simulation title, drawer title
- 17/500: agent name
- 15/500: card titles
- 16 and 17 at line-height 1.7: reading text (summaries, memories, today)
- 13–14: body, values, table
- 12/500: pills, meta
- 11/500 uppercase, letter-spacing .08em: field labels and section labels
- 12.5 mono at line-height 1.7: log
- 24/500 tabular: token total

Use tabular numbers for all figures.

**Radius:** 4 (chips, skeleton) · 6 (pills, notices) · 8 (cards, buttons, inset rows) · 10 (avatars, toast) · 14 (gate card, dialog).

**Elevation:**
- Cards: `--shadow-sm`, a 1px edge only.
- Toast and gate card: `--shadow-md`.
- Drawer and dialog: `--shadow-lg`.

**Rules:** freestanding rules **fade to transparent over 48px at each end** (`.rule-b` / `.rule-t`), which is the Nocturne signature. Box outlines stay solid.

**Icons:** Phosphor *regular* (phosphoricons.com), inline SVG on `currentColor`. Used:
- `arrow-clockwise`, `sun` / `moon`, `sign-out`, `squares-four`, `hard-drives`, `coins`
- `play`, `stop`, `scroll`, `arrow-right`, `plugs`, `cube`, `database`, `terminal-window`
- `x`, `arrow-line-down`, `clock`, `eraser`, `caret-down` / `caret-right`, `eye-slash`
- `check-circle`, `warning-circle`, `house-line`, `package`, `circle-notch`

No brand logos (Matrix, Element, Docker, Gemini, Anthropic).

---

## Screens

### 1. Token gate
- **Layout:** full viewport. Centred card, `min(380px,100%)` wide, padding 28, gap 20, radius 14, `--shadow-md`.
- **Background:** two radial "dusk" glows below the horizon: accent 22% (ellipse 85%×50% at 50% 112%) and warm `--st-warn` 10% (50%×26% at 50% 104%).
- **Card contents:**
  - Brand row: a 30px outlined "A" mark and "Agora · panel" in muted text.
  - Title "Sign in".
  - Field "Owner token": `type=password`, mono, letter-spacing .12em, height 40.
  - Button "Sign in": primary outline, full width, height 40.
  - Footer note above a fading rule: house-line icon + "The panel is available only on the home network".
- **Error:** field border `--st-err`, then below it a warning-circle icon + "Invalid token" in `--st-err-fg`, with `role=alert`. The error clears on input.
- **Behaviour:**
  - Without a valid token nothing else renders.
  - The token is sent as `Authorization: Bearer` on every API call; any 401 returns to the gate.
  - Store the token in `sessionStorage`.

### 2. Dashboard (1440 desktop)
**Top bar:** 54px tall, padding 10/24, fading bottom rule. Contents, left to right:
- 28px brand mark and "Agora · panel".
- **Global status pill:** "All systems running" (ok) / "Matrix unreachable" (err) / "Docker unreachable" (unknown) / "Memory unavailable" (warn).
- Flexible spacer.
- "updated 12 s ago": 12px, muted, tabular, ticks every second; "updated just now" right after a fetch.
- Refresh icon button (32px): spins once (.8s) on each refresh.
- Theme icon button: shows a sun when dark, a moon when light.
- "Sign out" secondary button, 32px tall.

**Left rail:** 228px, padding 18/12, fading right rule.
- Label "Simulations".
- Active item "Agora": `--accent-tint` background, squares-four icon, status dot.
- Nested agent links (indent 36): name + status dot; clicking one opens the drawer.
- Label "System", with "Server" and "Tokens" links that smooth-scroll the main column.
- Bottom: the phase string in mono ("v3.3 · view only" / "v3.4 · control").
- The rail is built from the simulation registry, so it is ready for more simulations.

**Main column:** scrolls, padding 18/24/28, max-width 1360, vertical gap 18.

**a) Section "Simulations": simulation card** (padding 16, gap 14)
- **Header row**, left: "Agora" (18/500), mono tag `matrix-chat`, and muted "private Matrix room · agora.lan".
- **Header row**, right: health pill "Healthy" / "Unreachable", then muted "42 ms · checked 18 s ago".
- **Banner** when the homeserver is down: err notice, plugs icon, "Matrix server unreachable — agents are waiting".
- **Two columns** (wrap): **Services** (flex 999 1 520) and **Agents** (flex 1 1 220).
- **Service row** (inset background, radius 8, padding 6/6/6/12; design for 1–5 rows):
  - name `homeserver` (mono 13), image `continuwuity` (mono 12, muted), state pill, "uptime 39 h".
  - Right side: ghost button "Log" (opens the log viewer).
  - **v3.4 only:** 28px icon buttons Start / Stop / Restart.
- When Docker is down, an unknown notice "Docker unreachable — container state unknown" appears above the rows.
- **Agents column:** 26px monogram squares + "2 agents · both running". Variants: "waiting for the server", "state unknown", or counts such as "1 stopped · 1 not created". Clicking scrolls to the agent cards.

**b) Section "Agents" (+ muted "in Agora"):** grid `repeat(auto-fit, minmax(min(360px,100%),1fr))`, gap 14. **Agent card** (padding 16, gap 14):
- **Header:** 40px avatar (monogram "A" / "B" in accent-ink on accent tint, inset accent 35% ring), name (17/500), role (13 muted: "editor, 32, Lviv" / "sound engineer, 35, Lviv"), state pill on the right.
- **Optional notice:**
  - Docker down: unknown style, "Docker unreachable — state unknown"; the fields fade to 50%.
  - Terminal agent in v3.4: stop style, "Controlled from a terminal on the Mac — the panel won’t start a second instance".
- **Field grid** `repeat(auto-fit,minmax(124px,1fr))`, gap 10/16, uppercase labels:
  - **Runs on:** "server · container `ada`" or "Mac · terminal `PID 48211`"; the value is a mono code chip.
  - **Uptime:** e.g. "2 h 14 min".
  - **Last activity:** e.g. "replied 3 min ago".
  - **Session:** "active session: 6 messages" / "session ended at 13:26".
- **Today:** label + the first line of the today block, 14px (agent text, Ukrainian). If `state/` is unreadable: database icon + "Memory unavailable".
- **Footer**, above a fading top rule:
  - Left: muted "7 days · 268 calls · 1.3M tokens · $0.46". Variants: "No data yet" when empty; the cost part is omitted when prices are unset.
  - **v3.4 only:** secondary buttons Start / Stop / Restart, 30px tall, with icons.
  - Primary outline "Details →" (opens the drawer).
- **Button enablement (v3.4):**
  - Start: only when stopped or not created. On "not created" its tooltip reads "Creates the container and starts it".
  - Stop and Restart: only when running.
  - All disabled while busy, when Docker is down, or when the agent runs in a terminal.

**c) Row: Server + Tokens** (flex wrap, gap 14)
- **Server card** (flex 1 1 300):
  - Title "Server"; mono muted "Ubuntu · 192.168.1.197" on the right.
  - Two-column grid (96px label / value), gap 14/12:
    - **Uptime:** 39 h
    - **Disk:** "32 GB free of 98 GB" + a 5px meter at 67% used (accent fill on `--line`)
    - **Memory:** "2.1 / 7.7 GB" + meter at 27%
    - **Load:** "0.12 · 0.20 · 0.18" + muted "1 · 5 · 15 min"
    - **Containers:** "4 running" (or an "unknown" pill when Docker is down)
- **Tokens card** (flex 999 1 560):
  - **Header:** "Tokens, last 7 days", muted range "Sep 28 – Oct 4", and on the right a segmented filter "All · Ada · Bruno".
  - **Summary row:** the total (24/500, "2.6M tokens") with a muted line below ("521 calls · 2,540,559 in · 54,294 out · $0.90").
  - **Per-day chart:** 7 stacked bars, 26px wide, 44px max height. Ada is solid accent at the bottom; Bruno is accent at 42% on top. Day labels ("Mo 28" … "Su 4") are 10px; today's label is full text colour. A small legend sits beside it.
  - **Table:** scroll container `flex:1 1 0; min-height:190px`; the table has `min-width:600px` so it scrolls inside the card on phones.
    - Columns: **day · agent · kind · calls · input · output · cost $**. Numbers are right-aligned and tabular; kind is mono 12.
    - Rows run newest day first, then agent (ada, bruno), then kind order `reply, summary, plan, day_memory, digest, today`. The day is printed only on a day's first row.
    - The header is sticky.
    - Footer rows: "total · ada", "total · bruno", and a sticky **"total"** row (500 weight).
  - **Cost column** only when prices are configured (`PRICE_INPUT_PER_1M` / `PRICE_OUTPUT_PER_1M`). Without it, the column is removed and a muted note reads "Prices are not configured — cost is not calculated."
  - **Empty state:** coins icon, "No data yet", muted "The square is still quiet. The table fills in after the first model call." (faint accent glow from the bottom-left).
  - **`state/` unreadable:** dashed box, "Memory unavailable".

### 3. Phone (below 760px)
- The rail is hidden.
- Top bar row 1: brand + icon buttons (refresh, theme, sign-out icon).
- Top bar row 2: global pill + "updated…".
- Padding becomes 14.
- Every card stacks into one column; the usage table scrolls horizontally inside its card.
- The drawer is full screen (`width:100%`).
- The toast spans the bottom (left/right/bottom 12).

### 4. Agent drawer
- **Shell:**
  - Scrim: `--scrim`, fades in over .2s; clicking it closes the drawer.
  - Panel: right-anchored, `min(680px,94%)`, surface background, `--shadow-lg`, slides in from +28px over .22s ease-out. Esc closes it.
- **Header:** 40px avatar, name (18/500), role, state pill, 34px close button.
- **Tabs:** Log · Last session · Memories · Plans · Today · Tokens.
  - 13/500, padding 10/10/11.
  - Active: text colour + 2px accent underline (`inset 0 -2px 0`).
  - Inactive: muted. Hover: `--line` background. Fading bottom rule under the tab row.
  - When `state/` is unreadable, every tab except Log turns `--faint` with a small database icon, and its body shows a dashed box: "Memory unavailable" / "state/ cannot be read — memories, plans and tokens appear as soon as it is back."
- **Log:**
  - Toolbar: muted "last 200 lines · docker logs ada" (terminal agent: "state/logs/bruno.log"), plus a "Follow" toggle button (`aria-pressed`; on = accent-ink + accent border).
  - Log box: inset background, radius 8, mono 12.5 at line-height 1.7; **newest at the bottom**.
  - Columns: time (muted), source (muted, min 92px), level (min 56px; WARNING in warn-fg, ERROR in err-fg), message.
  - While following: auto-scroll to the bottom on each poll, new lines fade in (.5s), and a pulsing line "following new lines" sits at the end.
  - Scrolling up more than 12px turns Follow off.
  - Unavailable states: "Container not created — no log yet" (package icon) or "Docker unreachable" (cube icon).
  - Logs carry events only, never message text.
- **Last session:**
  - Meta: clock icon + "written today at 13:26 · 29 words".
  - The summary: 16px at line-height 1.7, max 64ch.
  - **v3.4:** below a fading rule, a secondary button "Forget last session" (eraser icon) + a muted note.
    - Enabled only when the agent is **stopped**; otherwise the note reads "Stopped agents only".
    - After forgetting: "No summary — the next one is written when a session ends."
- **Memories:**
  - "Digests" rows (grid 96px / 1fr, fading row rules): Year, Month and Week, each with its period and a 13px excerpt. A missing layer shows muted "not composed yet — written on January 1".
  - "Days": newest first, each an accordion row with a caret, date (14/500), weekday (muted) and word count on the right.
  - Expanded rows get an inset background and the text at 15px / 1.7. The newest day opens by default.
- **Plans:**
  - Grid `auto-fit minmax(250px,1fr)`, gap 12: four inset boxes **Year · Month · Week · Day**, each with its period and a bulleted list (14px).
  - An item may carry a quiet **"deviation"** badge: 11px, 1px divider border, muted, with a tooltip.
  - Footnote: eye-slash icon + "“deviation” marks a plan that departs from the character’s life story. Only you see it — never the characters."
- **Today:** meta "updated at 14:00 · refreshed hourly", then the block at 17px / 1.7, max 62ch.
- **Tokens:**
  - The agent's total + per-day bars (single series).
  - Table: kind · calls · input · output · cost $, with a "total" footer.
  - Empty: "No data yet".

### 5. Log viewer (service)
The same drawer shell. Header: scroll icon tile, title "Log · homeserver", sub "continuwuity · container homeserver", service pill. No tabs; the log toolbar and box are as above. It opens from "Log" on a service row.

### 6. Degraded states
- **Homeserver down:**
  - Health pill "Unreachable" (err), latency "no response", red banner.
  - Service pill "crashed" (err), or "stopped" (neutral) if stopped from the panel.
  - Running agents switch to "reconnecting" (warn) with "reconnect attempt 4 s ago".
  - Their logs append WARNING "sync failed: homeserver unreachable; retry in 10s".
  - Global pill "Matrix unreachable".
- **Docker unreachable:**
  - Container pills show "unknown" (dashed); agent fields fade to 50% with the notice.
  - Host containers show "unknown"; container logs are unavailable.
  - Every action is disabled. The health probe (HTTP) still works.
  - Global pill "Docker unreachable".
- **`state/` unreadable:**
  - Agent "Today" and the tokens line show "Memory unavailable".
  - The usage card shows the dashed box; drawer memory tabs are greyed.
  - Global pill "Memory unavailable" (warn).
- **Agent stopped:**
  - Pill "stopped"; uptime "—"; "last reply at 13:41"; "session ended at 13:52".
- **Container not created:**
  - Pill "container not created" (outline only).
  - Start is enabled and its busy label reads "creating container…".
- **Running in a terminal:**
  - Pill "running in terminal"; Runs on "Mac · terminal `PID 48211`" (detected via `state/<name>.lock`).
  - Every action is disabled, with the notice (v3.4).

### 7. Control (v3.4)
- **Confirmation dialog:** Nocturne `.dialog`, max 440, radius 14, `--shadow-lg`, over the scrim; it rises in from 8px over .18s.
  - Buttons: "Cancel" (secondary) and the confirm button (primary outline with icon).
  - **Forget** uses the err outline instead.
- **Dialog texts:**
  - **Stop agent:** "Stop Ada?" / "She will write a session summary — up to 30 seconds." (Bruno: "He…")
  - **Restart agent:** "Restart Bruno?" / "The current session will end with a summary."
  - **Forget:** "Forget Ada’s last session?" / "The summary will be deleted; day memories stay. Stopped agents only."
  - **Stop homeserver:** "Stop homeserver?" / "Agents will keep reconnecting until it is back."
  - **Restart homeserver:** "Restart homeserver?" / "Agents will reconnect briefly."
- **Start** runs without confirmation.
- **In progress:**
  - The pill turns "work" (pulsing dot) with "stopping… writing summary" / "starting…" / "restarting… writing summary" / "creating container…".
  - All of that row's buttons are disabled.
  - Keep polling until the container state changes. Stop can take up to 30s (`docker stop -t 30`).
- **Toast:** bottom-right, surface background, `--shadow-md`, radius 10, padding 8/8/8/14, rises in over .2s, auto-dismisses after 4.5s, with a close button.
  - Success: check-circle in `--st-ok`, e.g. "Ada stopped", "Bruno started", "homeserver restarted", "Ada’s last session forgotten".
  - Error: warning-circle in `--st-err`, "Failed: Docker unreachable".

### 8. Loading / empty
- **First load:** skeleton cards in the same layout (`--line` blocks, 1.4s opacity shimmer); the top bar reads "loading…" with the refresh icon spinning.
- **Later refreshes** never show spinners; only the "updated N s ago" counter resets.

---

## Status logic (derive the agent pill)
```
busy (action in flight)                        → work  "<busy label>"
docker unreachable && not terminal             → unknown "unknown"
(running || terminal) && homeserver != ok      → warn  "reconnecting"
running && currently replying/writing memory   → work  "working… replying" / "writing summary"
running                                        → ok    "running"
terminal (lock held, no container)             → ok    "running in terminal"
stopped                                        → stop  "stopped"
no container                                   → none  "container not created"
```
Simulation health: probe ok → "Healthy"; probe failed → "Unreachable"; no probe data → "Unknown" (unknown style). Never use colour alone: always a dot **and** the word.

## State (vanilla JS)
`token, theme, lastFetchAt, data{simulations[], agents[], host, usage[]}, busy{id:label}, drawer{id, tab}, follow, dialog{act,id}, toast{kind,text}, usageFilter, expandedDays{}`.
- Poll the dashboard every ~10 s, the open log every 2–4 s (only while Follow is on), and the drawer content on open plus every 30 s.
- Read routes are `GET`; actions are `POST` with Bearer auth and a same-origin `Origin`.
- An unknown name returns 404, which should be shown as an error toast.

## Formatting
- Numbers use en-US grouping ("270,115").
- Cost per row uses 4 decimals ("0.0863"); per-agent and overall totals use "$0.46".
- Millions use one decimal ("1.3M").
- Durations: "2 h 14 min", "39 h", "12 s ago".
- Days are ISO in the table (`2026-10-03`) and "October 3 · Saturday" in memories.

## Files
- `agora-panel.css`: production starter stylesheet (tokens, both themes, every component, motion, the responsive breakpoint at 759px).
- `prototype/Agora Panel.dc.html`: the full interactive reference. All copy, sample data and state logic are in its `<script data-dc-script>` class (`renderVals`, `agentView`, `initial`).
- `prototype/support.js`, `prototype/_ds/…/styles.css`: runtime and Nocturne stylesheet, needed only to open the prototype.

Sample content (memories, plans, summaries) is invented for the mockup, so render real `state/` files in production.
