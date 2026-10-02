# Architecture — matrix-agora

## Overview

Two small axes bound by one agent codebase. **The agents' capabilities** grow: echo → Gemini replies → turn-taking → canon + session memory → world awareness (place, clock, day memories) → token accounting. **The operations surface** grows separately: terminal processes first, then a local web panel that supervises them. The homeserver and the room stay the same throughout: everything the agents do rides on the plain Matrix client-server API.

```
 ┌──────────────── Ubuntu server 192.168.1.197 ────────────────┐
 │  Docker: continuwuity (Matrix homeserver)  :8008  (HTTP, LAN) │
 │  server_name = agora.lan, federation OFF, encryption OFF      │
 └───────────────▲──────────────────▲──────────────────▲────────┘
                 │ Client-Server API (http://192.168.1.197:8008)
     ┌───────────┴───┐     ┌────────┴────────┐  ┌──────┴──────────┐
     │ Element Desktop│     │ agent "Ada"     │  │ agent "Bruno"   │
     │ (owner, @me)   │     │ Python + nio    │  │ Python + nio    │
     └────────────────┘     │ → Gemini API    │  │ → Gemini API    │
                            └─────────────────┘  └─────────────────┘
          Mac (the client, both agents and the web panel run here)
```

## Components

- **Homeserver:** [Continuwuity](https://continuwuity.org) — a Matrix homeserver in Rust: one Docker container, embedded RocksDB, no Postgres. `server_name = agora.lan` is only the domain part of user ids (`@ada:agora.lan`); clients connect to `http://192.168.1.197:8008` directly, so no DNS is needed. Federation and encryption are disabled; registration is open (token-gated) only during setup, then closed. The compose file is the deliverable of ROADMAP v0.1.
- **Client:** Element Desktop on the Mac. Specifically Desktop, not app.element.io — the web version runs over HTTPS and will not connect to an HTTP homeserver on the LAN (mixed content).
- **Agents:** two Python processes on the Mac running the same `agents/agent.py` with different TOML configs (account, canon). Libraries: `matrix-nio` (Matrix) + `google-genai` (Gemini, async `client.aio.models.generate_content`, model `gemini-2.5-flash`). The names "Ada" and "Bruno" are placeholders.
- **Panel (from v3.2):** a local `aiohttp.web` process on the Mac (`127.0.0.1` only) serving one vanilla-JS page: start/stop/restart agents, logs, memory, token report, server status. aiohttp is already a dependency of matrix-nio, so no new framework.
- **Storage:** the gitignored `state/` directory — each agent's Matrix session, memory files, day memories, usage log, lock and logs. There is no database.

## Message flow and the allowlist

The invariants every reply path must honor:

1. **Login once, then the token.** First run logs in with the password and saves `access_token` + `device_id` to `state/<name>.json`; later runs restore them. Logging in with the password on every start would create a new device on the server each time.
2. **Invites:** join only invites from `OWNER` into `ROOM_ID`. Ignore or leave every other invite.
3. **Start without the past:** the first `sync` is used only to obtain `next_batch` and its events are **not processed** — otherwise a restarted bot replies to the whole room history. After that, `sync_forever`.
4. **Message filter** (`RoomMessageText` only — edits, notices and other event types never trigger a reply). Handle a message only if all hold:
   - `room.room_id == ROOM_ID`;
   - `event.sender != own user_id`;
   - `event.sender ∈ {OWNER, the other agent's user_id}` — an **allowlist in code**, like `LUMI_TELEGRAM_ALLOWLIST` in Lili.
   Everything else is logged as `ignored`.
5. **Typing:** `room_typing(room_id, True)` before the Gemini call and `False` after it, reset in a `finally`.
6. **Send as `m.text`**, never `m.notice` — the other agent might treat a notice as a service message.
7. **On a failed or empty Gemini reply:** log the error, send nothing, keep running. The bot never crashes on a model failure.

Keep the decisions pure: the filter, mention detection, `bot_streak`, who-replies, transcript and prompt assembly are functions over plain data, so tests need no nio objects and the nio callbacks stay thin adapters.

## Turn-taking and loop protection

The agents see each other, so without rules they would reply to each other endlessly.

1. **The owner's message:**
   - mentions one agent (by name or mention) — **only that agent** replies; mention detection must handle Ukrainian case forms (the vocative «Адо» for Ада);
   - mentions no one — **both** reply, each after a random delay of 1–`REPLY_DELAY_S` s (default 4), so they don't speak at once and the second sees the first's line in history.
2. **The other agent's message:** reply only if `bot_streak < MAX_BOT_TURNS` (default 2), and then with probability `BOT_REPLY_P` (e.g. 0.5), so the conversation isn't mechanical.
   - `bot_streak` = consecutive agent messages since the owner's last message. Both agents compute it from the same room timeline, so the count agrees **without any shared state or coordination** — never add any.
   - An owner message resets it to 0.
3. **`PASS`:** if the model returns exactly `PASS` (tolerating surrounding whitespace), send nothing. The prompt must explicitly allow this.

## Canon

- `agents/canon/common.md` — shared by both agents: what the room is, who the owner is, who the other agent is, the language and tone of conversation.
- `agents/canon/<name>.md` — personal: character, way of speaking, interests, attitudes, what the agent never does.
- The canons describe the agents as **humans** (see VISION.md §Principles). Nothing in code — reply rules, summary or memory prompts — may mention that the agent is a model or a bot.
- The TOML points at it: `canon = "agents/canon/<name>.md"`. Read once at startup; a missing or empty canon stops the bot with a clear error.
- Canons are committed to the public repo: no secrets, no private data about the owner.

## Memory

- **Context window:** each agent keeps the last `HISTORY_N` (e.g. 30) room messages in RAM — its own and the other agent's included — and passes them to the model as one text, one `"Name: text"` line each. Raw history never persists.
- **Session:** ends after `SESSION_IDLE_S` (e.g. 900 s) of room silence, or on shutdown (Ctrl+C i.e. SIGINT, or SIGTERM — summarized with a ~20 s timeout so shutdown never hangs). The session timeline (messages since the last summary, capped at `SESSION_MAX_MESSAGES`) is kept separately from `HISTORY_N`.
- **Session summary:** at session end, one Gemini call compresses *previous summary + session timeline* into a new first-person summary of at most `SUMMARY_MAX_WORDS` words — what was discussed, decided, promised, left open. Written atomically (temp file + rename) to `state/<name>.memory.md`. Each agent summarizes from its own point of view; Ada's and Bruno's summaries may differ.
- **Conversation journal:** every session summary is also appended, with its time, to `state/<name>.days/YYYY-MM-DD.talk.md` — the per-day record that day memories draw on.
- **Day memories:** once per past day (after local midnight; missed days caught up at startup, at most `MEMORY_DAYS` back) a separate Gemini call writes `state/<name>.days/YYYY-MM-DD.md` (≤ `DAY_MEMORY_MAX_WORDS` words, atomic write): a first-person text about that day — what the agent did and saw in Lviv, and what was discussed if there was a conversation. **A past day is never rewritten.** Inputs: canon, that day's date/weekday/season, the previous days' memories, the day's journal.
- **Truth and invention (hard rule):** anything that happened in the room comes only from the journal. Invented episodes involve only the agent itself and the city — never words or actions of the owner or the other agent that did not happen.
- **Failure:** a failed summary keeps the previous one; a failed day memory is retried later; a corrupt memory file means starting without memory, logged. The bot never crashes over memory.

## World awareness

- The agents live in Lviv: `LOCATION` (default «Львів, Україна») and `TIMEZONE` (`Europe/Kyiv`).
- Before every Gemini call the code computes the current moment in `TIMEZONE` and adds date, weekday, time, part of day and season to the prompt — in Ukrainian, e.g. «Зараз четвер, 2 жовтня 2026, 20:15, вечір, осінь». Weekday/month names come from tables in code, not the system locale. The clock is an injected function, replaceable in tests.
- The prompt also says when the last session summary was made («Востаннє ви говорили позавчора ввечері»).

## Prompt assembly

`system_instruction` = canon (common + personal) → place, calendar and time → «Твої спогади за останні дні» (the last `MEMORY_DAYS` day memories, chronological, each labeled with its day) → «Що ти пам'ятаєш з минулої розмови: <підсумок>» (the last-session summary) → the reply-format rules (speak only as yourself, no name prefix, `PASS` allowed). `contents` = the last `HISTORY_N` messages as `"Name: text"` lines. This order is a contract.

Earlier phases use the prefix of this order that exists at that point (v1.1: persona + rules; v2.1: canon + summary + rules).

## Token accounting

- After **every** Gemini call — reply, session summary, day memory — the agent appends one JSON line to `state/<name>.usage.jsonl`: `ts` (in `TIMEZONE`), `agent`, `kind` (`reply` / `summary` / `day_memory`), `model`, `prompt_tokens`, `output_tokens`, `total_tokens`, `ok`. **Never any text.** Missing `usage_metadata` or fields → `null`s; a failed call → `ok: false`; a write error is logged and never blocks the conversation. Each agent writes only its own file.
- **Report:** `uv run agents/usage_report.py [--days N] [--since YYYY-MM-DD] [--markdown]` — a table by day × agent × kind with calls, tokens and estimated cost. Prices come only from `.env` (`PRICE_INPUT_PER_1M`, `PRICE_OUTPUT_PER_1M`, USD per 1M tokens); unset prices → no cost column. Corrupt lines are skipped with a warning; no files → "no data". The panel reuses the same aggregation code.

## Web panel

A separate process in the same uv project: `uv run panel/app.py` → `http://127.0.0.1:8090` (`PANEL_PORT`). One static HTML page with vanilla JS, no build step, no CDN; UI in Ukrainian. The agents work without it.

- **Supervision:** per agent — state (running/stopped), PID, uptime, last activity; Start / Stop / Restart. Start spawns `uv run agents/agent.py agents/<name>.toml` in its own process session (closing the panel never stops agents). Stop sends SIGINT (so the session summary runs), then SIGKILL after 30 s. Agent names come from a fixed list, never from a request path.
- **Single instance:** at startup an agent takes `flock` on `state/<name>.lock` and writes its PID; a second instance (panel or terminal) refuses to start. The panel detects terminal-started agents through the lock and can stop them by PID (after checking the PID really is our agent).
- **Logs:** agents always log to `state/logs/<name>.log` (rotating, 1 MB × 3) and the console; the panel tails the last 200 lines, refreshed every 2 s. Logs are safe to show because they never contain tokens, passwords or message texts.
- **Views:** homeserver health (`/_matrix/client/versions`, every 30 s); each agent's session summary and day memories; canons (read-only); the token table (last 7 days); effective settings (read-only, anything matching `*_KEY` / `*_PASSWORD` / `*_TOKEN` masked). **"Forget the last session"** deletes `state/<name>.memory.md` after confirmation and only while that agent is stopped. The panel never edits `.env` or canons and never runs commands on the Ubuntu server.
- **Security:** binds `127.0.0.1` only; CORS disabled; every request checks `Host` (`127.0.0.1:<port>` / `localhost:<port>` — anti DNS-rebinding); mutating actions are `POST`-only with the panel's own `Origin`.

## Contracts

Changing any of these updates this document and the test that pins it, in the same commit:

- The env var names in `.env.example` and `server/.env.example`.
- The agent TOML schema (`name`, `user_id`, `canon`, …) and the `agents/canon/` layout.
- The `state/` files: `<name>.json` (session), `<name>.memory.md`, `<name>.days/YYYY-MM-DD.md` + `.talk.md`, `<name>.usage.jsonl` (its fields), `<name>.lock`, `logs/<name>.log`.
- The message filter and allowlist rule.
- The transcript format (`"Name: text"` per line), the `PASS` sentinel, and the prompt-assembly order.
- The turn-taking semantics (who replies, `bot_streak`).
- The `server/docker-compose.yml` environment (server name, federation, encryption, registration). `CONTINUWUITY_SERVER_NAME` cannot change without wiping the database.

## Configuration and secrets

All tunables live in `.env` (shared) or the agent's TOML (per-agent), never hardcoded:

| Variable | Phase | Meaning (example default) |
|---|---|---|
| `HOMESERVER`, `ROOM_ID`, `OWNER` | v0.4 | where and with whom the agents talk |
| `ADA_PASSWORD`, `BRUNO_PASSWORD` | v0.4 | first-login passwords |
| `GEMINI_API_KEY` | v1.1 | read by `google-genai` from the environment |
| `HISTORY_N`, `REPLY_DELAY_S`, `MAX_BOT_TURNS`, `BOT_REPLY_P` | v1.1–v1.2 | context size and turn-taking (30 / 4 / 2 / 0.5) |
| `SESSION_IDLE_S`, `SESSION_MAX_MESSAGES`, `SUMMARY_MAX_WORDS` | v2.1 | session memory (900 / 200 / 200) |
| `LOCATION`, `TIMEZONE`, `MEMORY_DAYS`, `DAY_MEMORY_MAX_WORDS` | v2.2 | world awareness (Львів / Europe/Kyiv / 7 / 120) |
| `PRICE_INPUT_PER_1M`, `PRICE_OUTPUT_PER_1M` | v3.1 | token prices for the cost column |
| `PANEL_PORT` | v3.2 | panel port (8090) |
| `REGISTRATION_TOKEN` | v0.1 | in `server/.env` on the Ubuntu box only |

`.env`, `server/.env` and `state/` are gitignored. Tokens, passwords, keys and message/summary/memory texts never appear in logs, argv, commits or the panel.

## Security and access

| Threat | Protection |
| --- | --- |
| Someone registers on the server | Registration disabled after v0.3; the token only in `server/.env` |
| Someone from the internet | Port 8008 not forwarded on the router; ufw allows only `192.168.1.0/24`; federation disabled |
| Someone messages the bots (DM, another room) | The in-code allowlist: only `ROOM_ID` + `{OWNER, other agent}` |
| Key leak | `.env`, `server/.env`, `state/` gitignored; tokens and texts never logged |
| Agents burn credits chatting with each other | `MAX_BOT_TURNS`, `BOT_REPLY_P`, `max_output_tokens`; one summary per session; one memory per day; the usage report shows the spend |
| Conversation leak | Summaries, journals and day memories live only in `state/`; their texts are never logged |
| Private data in the public repo | Canons are committed — no secrets, no private data about the owner |
| Someone controls the agents through the panel | `127.0.0.1` only; `Host` and `Origin` checks; secrets masked |

HTTP without TLS on the LAN is a deliberate PoC trade-off: passwords travel in plaintext over the home network. Before any external access: Tailscale (or a reverse proxy with TLS).

## Error handling and resilience

- A Gemini failure or empty reply on any call → log and stay silent; the bot never crashes or sends an apology message.
- A dropped homeserver connection → `matrix-nio`'s sync loop retries; an exception in a callback must not kill `sync_forever`.
- Typing state is reset in `finally` so a failure never leaves "typing…" stuck.
- Memory: failed summary → previous kept; corrupt file → start without memory; all writes atomic.
- Usage accounting and panel polling are best-effort: their failures are logged and never block a conversation or a stop.

## Stack and repository layout

```
matrix-agora/
  CLAUDE.md                 # instructions for Claude Code
  LICENSE
  README.md
  pyproject.toml            # uv; deps: matrix-nio, google-genai, python-dotenv; dev: ruff, pytest
  specification/
    VISION.md               # why and for whom
    ARCHITECTURE.md         # this file: components, mechanisms, contracts
    ROADMAP.md              # versions and phases with Goal/Tasks/DoD/Tests
    history/                # superseded SPEC.md + SPEC-UA.md, frozen
    implementation/         # issue files and reports (generated by the skills)
  server/                   # v0.1
    docker-compose.yml
    .env.example            # REGISTRATION_TOKEN=
  agents/
    agent.py                # one codebase for both agents
    ada.toml                # name, user_id, canon, …
    bruno.toml
    canon/                  # v2.1: common.md + <name>.md
    usage_report.py         # v3.1: token report
  panel/                    # v3.2: app.py + static/index.html
  .env.example              # see §Configuration and secrets
  state/                    # gitignored: each bot's session, memory (v2.1),
                            # day memories (v2.2), usage (v3.1), lock and logs (v3.2)
```

## Testing and CI

Automated gates need no network: `matrix-nio` and `google-genai` are mocked, the clock and randomness are injected, and nothing in the acceptance path calls a paid API.

| Gate | Command | When |
|---|---|---|
| Lint | `uv run ruff check .` | any Python change |
| Tests | `uv run pytest` (single test: `uv run pytest tests/test_x.py::test_name`) | any Python change |
| Compose | `REGISTRATION_TOKEN=dummy docker compose -f server/docker-compose.yml config -q` | `server/` changed |

Before v0.4 there is no `pyproject.toml`, so the Python gates are `n/a`, not passed.

- **Unit tests** cover the pure logic: the filter and allowlist, mention detection (Ukrainian case forms), `bot_streak` and who-replies, transcript and prompt assembly (section order), the session-end decision, memory file read/write (missing, corrupt, atomic), calendar strings (including DST switches), which days need generating, "a past day is never rewritten", `usage_metadata` parsing and aggregation, the panel's supervisor (fake processes), the single-instance lock, secret masking and the `Host`/`Origin` checks.
- **Contract tests** pin the seams in §Contracts; a contract change updates the test in the same commit.
- **Manual (owner) checks** are the DoD items that need the live homeserver, Element or a real Gemini key. The read-only `curl` checks may be run by tooling; everything on the Ubuntu host, in Element, or that spends real tokens is performed or confirmed by the owner, and counts as passed only then.
