# Architecture — matrix-agora

## Overview

Two small axes bound by one agent codebase. **The agents' capabilities** grow: echo → Gemini replies → turn-taking → canon + session memory → world awareness (place, clock, day memories, plans, the hourly today block) → token accounting. **The operations surface** grows separately: terminal processes on the Mac first, then Docker images with CI behind them and deployment to the Ubuntu server, and finally the **panel** — the point of the whole project — served from that server. The panel manages **simulations** (environments agents join; the chat — the homeserver and the room — is the first and only one here) and the agents connected to them. Everything the agents do rides on the plain Matrix client-server API.

```
                                              ┌────────────────┐  ┌────────────┐
                                              │ Gemini API     │  │ GitHub+GHCR│
                                              │ (agent calls)  │  │ (CI→images)│
                                              └────────▲───────┘  └───────────┬┘
 Internet · outbound                                   │ google-genai compose │
 HTTPS :443 only                                       │ (agents)     pull    │
┌─ Mac ─────────────────────────────────────────────┐  │                      │
│  ┌──────────────────────────┐                     │  │                      │
│  │ Element Desktop          │                     │  │                      │
│  │ (the owner, @ich)        │                     │  │                      │
│  └────┬─────────────────────┘                     │  │                      │
│  the owner’s browser ─────────────┐               │  │                      │
│  dev: uv run agents · gates ·     │               │  │                      │
│  git push · server/deploy.sh ─────────────┐       │  │                      │
└───────┼───────────────────────────┼───────┼──────┘   │                      │
        │ Matrix                    │ panel │ SSH :22  │                      │
        │ :8008                     │ :8090 │ deploy   │                      │
┌───────┼─── Ubuntu · 192.168.1.197 ┼───────┼──────────┼──────────────────────┼┐
│       ▼                           ▼       ▼          ▼                      ▼│
│  ┌──────────────────────┐  ┌──────────────────┐  ┌────────────────────────┐  │
│  │ continuwuity         │  │ panel: FastAPI   │  │ agents ada + bruno     │  │
│  │ HTTP :8008 ·         │  │ UI + API :8090   │  │ one container each     │  │
│  │ agora.lan            │  │ docker.sock      │  │ state/ bind mount      │  │
│  └──────────────────────┘  └──────────────────┘  └────────────────────────┘  │
│  internal: agents ⇄ homeserver (compose net) · panel → docker.sock + state/  │
│  ufw: :8008 + :8090 from 192.168.1.0/24 · :22 deploy · no router forwarding  │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Network, ports and protocols

| From | To | Protocol / port | Purpose |
|---|---|---|---|
| Element Desktop (Mac) | homeserver (Ubuntu) | HTTP :8008, LAN | Matrix client-server API |
| Owner's browser (LAN) | panel (Ubuntu) | HTTP :8090, LAN | the panel UI + API; Bearer `PANEL_TOKEN` on every API call |
| Agents (Ubuntu) | homeserver (Ubuntu) | HTTP :8008, compose network | Matrix client-server API (`sync`, send, typing) |
| Agents (Ubuntu) | Gemini API | HTTPS :443, outbound | replies, summaries, day memories, plans, today blocks |
| Panel (Ubuntu) | Docker daemon (Ubuntu) | local socket | simulation + agent containers: state, start/stop, logs |
| Panel (Ubuntu) | homeserver (Ubuntu) | HTTP :8008, compose network | the simulation health probe (`/_matrix/client/versions`) |
| `server/deploy.sh` (Mac) | Ubuntu host | SSH :22, LAN | rsync `server/` + remote `docker compose pull && up -d` |
| Ubuntu host | GHCR | HTTPS :443, outbound | pulls the agent and panel images |
| Dev mode (Mac): `uv run` agents | homeserver (Ubuntu) | HTTP :8008, LAN | development against the same homeserver, local `state/` |
| Developer (Mac) | GitHub | HTTPS :443, outbound | `git push` triggers CI |
| **Inbound from the internet** | — | **nothing** | no forwarded ports, federation off, the panel token-gated and LAN-only |

Everything is plain HTTP inside the LAN (the PoC trade-off in §Security and access) and HTTPS to the two cloud services. There are no other listeners.

## Tech stack

| Technology | Used by | Purpose |
|---|---|---|
| Python 3.12+ with uv | agents, report, panel | one language for all Mac-side code; deps pinned in `pyproject.toml` / `uv.lock` |
| `matrix-nio` | agents | the async Matrix client-server API: `sync_forever`, invites, typing, sending |
| `google-genai` | agents | every Gemini call (`gemini-2.5-flash`): replies, summaries, day memories, plans, today blocks |
| `python-dotenv` + TOML (`tomllib`) | agents, panel, report | `.env` for shared config and secrets; per-agent TOML for `name`, `user_id`, `canon` |
| FastAPI + uvicorn | panel | the panel's JSON API and static files; typed models and the token auth in one place |
| Vanilla HTML + JS | panel UI | one static page: no build step, no CDN, nothing to maintain |
| Continuwuity | Ubuntu host | the Matrix homeserver: one Rust container, embedded RocksDB, no Postgres |
| Element Desktop | Mac | the owner's Matrix client (Desktop, because an HTTPS web client cannot call an HTTP LAN server) |
| Docker + docker compose | Ubuntu server | runs the whole stack: the homeserver, the panel, and one container per agent (one shared image) |
| bash + system `ssh`/`rsync` | `server/deploy.sh` | deploy the whole stack to the Ubuntu host |
| GitHub Actions | CI | lint + tests + compose gates + image build on every push/PR; GHCR push on `vA.B.C` tags |
| GHCR | registry | hosts the agent and panel images |
| ruff + pytest | gates | lint and the unit/contract tests (nio/Gemini mocked, clock and randomness injected) |
| Gemini API | external service | the only LLM and the only paid dependency; everything else is free and local |

## Components

- **Homeserver:** [Continuwuity](https://continuwuity.org) — a Matrix homeserver in Rust: one Docker container, embedded RocksDB, no Postgres. `server_name = agora.lan` is only the domain part of user ids (`@ada:agora.lan`); clients connect to `http://192.168.1.197:8008` directly, so no DNS is needed. Federation and encryption are disabled; registration is open (token-gated) only during setup, then closed. The compose file is the deliverable of ROADMAP v0.1.
- **Client:** Element Desktop on the Mac. Specifically Desktop, not app.element.io — the web version runs over HTTPS and will not connect to an HTTP homeserver on the LAN (mixed content).
- **Agents:** the same `agents/agent.py` with different TOML configs (account, canon, simulation). Libraries: `matrix-nio` + `google-genai` (async `client.aio.models.generate_content`, model `gemini-2.5-flash`). **Each agent is its own Docker container** — one compose service per agent — on the Ubuntu server from v3.2; `uv run` on the Mac remains the dev mode. The names "Ada" and "Bruno" are placeholders.
- **Panel (from v3.3):** the product of the project — a Docker container beside the homeserver: a FastAPI JSON API plus one static vanilla-JS page, `:8090`, LAN-only behind ufw, Bearer `PANEL_TOKEN`. It manages **simulations** through a declarative registry (the chat is the only entry) and the agents connected to them, via the local docker socket and the `state/` mount (§The panel).
- **Deployment:** the repo is the source of truth. `server/deploy.sh` (v0.2) syncs `server/` to the Ubuntu host and applies the whole stack — homeserver, panel, one container per agent — with `docker compose pull && up -d`; the images come from GHCR, built by CI (§Deployment and CI/CD).
- **Storage:** the gitignored `state/` directory — at `~/matrix-agora/state/` on the server in production (from v3.2), local on the Mac in dev mode — bind-mounted into the agent containers and the panel. Each agent's Matrix session, memory files, day memories, plans, today block, usage log, lock and logs. There is no database (§Data and state files).

## Message flow and the allowlist

The invariants every reply path must honor:

1. **Login once, then the token.** First run logs in with the password and saves `access_token` + `device_id` to `state/<name>.json`; later runs restore them. Logging in with the password on every start would create a new device on the server each time.
2. **Invites:** join only invites from `OWNER` into `ROOM_ID`. Ignore or leave every other invite.
3. **Start without the past:** the first `sync` is used only to obtain `next_batch` and its events are **not processed** — otherwise a restarted bot replies to the whole room history. After that, `sync_forever`. **Context survives a restart (from v2.2):** right after the first sync the agent fetches the last `HISTORY_N` messages of `ROOM_ID` once from the server (`/messages`, backwards) and seeds its context window and the `bot_streak` timeline with them, in chronological order — **never replying to any of them** and never adding them to the session timeline (they were already summarized). Nothing is stored locally; the room itself is the source.
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
2. **The other agent's message:** reply only if `bot_streak < MAX_BOT_TURNS` (default 2). If it addresses this agent by name (any case form) or Matrix id, reply for sure; otherwise with probability `BOT_REPLY_P` (e.g. 0.5), so the conversation isn't mechanical. The streak bound applies either way.
   - `bot_streak` = consecutive agent messages since the owner's last message **within the last `BOT_WINDOW_S`** (default 600 s), counted by server timestamps. Both agents compute it from the same room timeline, so the count agrees **without any shared state or coordination** — never add any.
   - An owner message resets it to 0.
   - The limit is a **rate, not a lock**: when an agent's reply is blocked by the streak, it pauses until the window frees (the oldest counted turn ages out) and then resumes — only if nothing newer arrived meanwhile. So the agents talk in bursts of at most `MAX_BOT_TURNS` per window until `PASS` or the probability gate ends the exchange; the owner never has to restart it.
3. **`PASS`:** if the model returns exactly `PASS` (tolerating surrounding whitespace), send nothing. The prompt must explicitly allow this. A `PASS` on its own line or at the very end of a longer reply is dropped and the rest is sent; nothing of its own left → nothing is sent — the sentinel never reaches the room (pinned by `tests/test_turns.py` and `tests/test_first_sync.py`).

## Canon

- `agents/canon/common.md` — shared by both agents: what the room is, who the owner is, who the other agent is, the language and tone of conversation.
- `agents/canon/<name>.md` — personal: character, way of speaking, interests, attitudes, what the agent never does.
- The canons describe the agents as **humans** (see VISION.md §Principles). Nothing in code — reply rules, summary or memory prompts — may mention that the agent is a model or a bot.
- The TOML points at it: `canon = "agents/canon/<name>.md"`. Read once at startup; a missing or empty canon stops the bot with a clear error.
- Canons are committed to the public repo: no secrets, no private data about the owner.
- **Life story (from v2.2):** `agents/canon/<name>.life.md` — the agent's whole life from birth to death, anchored to real dates: a header (`Народження: YYYY-MM-DD HH:MM, place`, `Смерть: YYYY-MM-DD`) and chapters `## YYYY–YYYY · title` that never overlap. The chapter containing today's year is the **current chapter** — the most detailed one: the typical week, ongoing matters, places, people. The TOML points at it: `life = "agents/canon/<name>.life.md"`.
  - **Visibility (hard rule):** the opening paragraph of each **past** chapter and the **current** chapter in full go into the conversational prompt as «Твоє життя досі» — what the agent remembers. **Future chapters and the death date never reach the conversational prompt** or any reply; only the plan generator sees the next chapter, as silent direction. The agent does not know its future, its death included.
  - **Consistency:** where the two lives cross (how Ada and Bruno met, shared events) the stories agree. A story never invents shared history with the owner — that comes only from the conversation.
  - **Time moves the story:** as real dates pass, a future chapter becomes the current one, so life events written for 2027 or 2030 start happening in the agents' days when those years arrive.

## Memory

- **Context window:** each agent keeps the last `HISTORY_N` (e.g. 30) room messages in RAM — its own and the other agent's included — and passes them to the model as one text, one `"Name: text"` line each. Raw history never persists locally; after a restart the window is re-seeded from the room on the server (§Message flow, rule 3).
- **Session:** ends after `SESSION_IDLE_S` (e.g. 900 s) of room silence, or on shutdown (Ctrl+C i.e. SIGINT, or SIGTERM — summarized with a ~20 s timeout so shutdown never hangs). The session timeline (messages since the last summary, capped at `SESSION_MAX_MESSAGES`) is kept separately from `HISTORY_N`.
- **Session summary:** at session end, one Gemini call compresses *previous summary + session timeline* into a new first-person summary of at most `SUMMARY_MAX_WORDS` words — what was discussed, decided, promised, left open. Written atomically (temp file + rename) to `state/<name>.memory.md`. Each agent summarizes from its own point of view; Ada's and Bruno's summaries may differ.
- **Conversation journal:** every session summary is also appended, with its time, to `state/<name>.days/YYYY-MM-DD.talk.md` — the per-day record that day memories draw on.
- **Day memories — what actually happened (follow the life story):** once per past day, generated after local midnight by the periodic watcher (v2.1's idle watcher; missed days caught up at startup, but never before the agent's first run and at most `MEMORY_DAYS` back), a separate Gemini call writes `state/<name>.days/YYYY-MM-DD.md` (≤ `DAY_MEMORY_MAX_WORDS` words, atomic write): a first-person text about that day. **A past day is never rewritten.** Inputs: the canon, the **current chapter of the life story** (the frame of reality), that day's date/weekday/season, the previous days' memories, the day's journal, and that day's plan and final today block.
  - **Generated from the story, never copied from it:** the story gives the frame (what the agent's life is like now: work, typical week, ongoing matters, people); the memory adds the concrete details of *that* day — what exactly, where, with whom, small sensations — consistent with the story and with earlier memories. A memory that copies a long verbatim span of the story (8+ words in a row) is regenerated once.
  - **Plan vs reality:** reality follows the story. A plan item that drifted away from it (a mutation, see Plans) shows up as «хотіла…, але…» — intentions that didn't happen.
- **Everything is kept; older memories are compressed (memory digests, from v2.2):** nothing the agent lived is ever deleted. Day memories, day journals, plans and digests accumulate forever under `state/`. On top of the day memories the watcher builds first-person **digests** at period boundaries, each generated (not copied) from the finer layer, keeping what mattered — moods, people, turning points, resolved and open threads:
  - **week** — `state/<name>.weeks/YYYY-MM-DD.md` (keyed by its Monday), from that week's 7 day memories (+ the week plan: what was meant vs what happened), ≤ `WEEK_MEMORY_MAX_WORDS` (150), after the week ends;
  - **month** — `state/<name>.months/YYYY-MM.md`, from that calendar month's day memories (+ the month plan), ≤ `MONTH_MEMORY_MAX_WORDS` (200), after the month ends;
  - **year** — `state/<name>.years/YYYY.md`, from that year's 12 month digests (+ the year intentions), ≤ `YEAR_MEMORY_MAX_WORDS` (300), after the year ends.
  Digests are written once their period is complete and **never rewritten**; missed periods are caught up at startup (never before the agent's first run). Partial periods (the current week, month, year) have no digest — they are covered by the finer layer.
- **Truth and invention (hard rule):** anything that happened in the room comes only from the journal. Invented episodes involve only the agent itself and the city — never words or actions of the owner or the other agent that did not happen.
- **Plans — intentions, with mutations (deviate from the life story):** four horizons, mirroring the memory layers, each generated by the watcher at its boundary (and by a startup kick right after the first sync, so a reply never waits on plan generation), each ≤ `PLAN_MAX_WORDS` words, atomic write, **never rewritten** after its period:
  - **year intentions** — `state/<name>.plans/year-YYYY.md`, on 1 January: the big wishes and goals of the year;
  - **month plan** — `state/<name>.plans/month-YYYY-MM.md`, on the 1st: what this month is for (deadlines, birthdays, preparations);
  - **week plan** — `state/<name>.plans/week-YYYY-MM-DD.md` (keyed by its Monday), on Monday;
  - **day plan** — `state/<name>.plans/YYYY-MM-DD.md`, at midnight.

  Each finer plan derives from the coarser ones above it plus the canon, the current chapter, the **next chapter as silent direction** (never named), the open threads of the life story, the previous period's plan and memories (unfinished intentions carried over), the weekday and season. The direction steers years ahead: if the next chapter says Ada's book comes out in 2028, her intentions already lean toward the essays before that.
  - **Mutations:** people plan things that don't happen. Before generation the code rolls the dice: each plan item, with probability `PLAN_MUTATION_RATE` (default 0.3, injected rng), gets a mutation kind — a spontaneous idea, a changed place, postponed, cancelled, a new whim — and the generator bends exactly those items. Mutation tags are stored in the plan file as **hidden metadata**: they are stripped from every conversational prompt, so the agent holds all its plans as sincere intentions and never knows which will fail. The memories and digests later resolve them against reality (the day memory for the day plan; week/month/year digests for the coarser plans: what was meant vs what happened).
  - Plans involve only the agent and the city — they never commit the owner or the other agent to anything.
- **The today block (hourly):** `state/<name>.today.md` — two short first-person sections, «Сьогодні вже…» (done so far today — **reality**: the current chapter + today's journal) and «Ще сьогодні…» (still ahead — **intentions**: the mutated day plan), ≤ `TODAY_MAX_WORDS` words. Regenerated automatically whenever the local hour changes: the check is lazy at prompt build and cached per hour, so there is **at most one `today` call per hour** and no background threads. Inputs: the day plan, today's journal so far, the previous block, the current time. Reset at midnight.
- **Failure:** a failed summary keeps the previous one; a failed day memory is retried later; a failed plan or today refresh keeps the previous file or block (stale by an hour, never missing); a corrupt memory file means starting without memory, logged. The bot never crashes over memory.

## World awareness

- The agents live in Lviv: `LOCATION` (default «Львів, Україна») and `TIMEZONE` (`Europe/Kyiv`).
- Before every Gemini call the code computes the current moment in `TIMEZONE` and adds date, weekday, time, part of day and season to the prompt — in Ukrainian, e.g. «Зараз четвер, 2 жовтня 2026, 20:15, вечір, осінь». Weekday/month names come from tables in code, not the system locale. The clock is an injected function, replaceable in tests.
- The prompt also says when the last session summary was made («Востаннє ви говорили позавчора ввечері»).

## Prompt assembly

`system_instruction` = canon (common + personal) → «Твоє життя досі» (past chapters' opening paragraphs + the current chapter; never the future) → place, calendar and time → «Твої спогади» in nested layers, oldest first and coarsest first, with no gaps (a coarser window may touch the edge of a finer one): every **year digest** before the months window, the last `MEMORY_MONTHS` (6) complete **month digests** before the weeks window, the last `MEMORY_WEEKS` (4) complete **week digests** before the days window, and the last `MEMORY_DAYS` (7) **day memories** (yesterday back), each labeled with its period («березень 2027: …», «тиждень 5–11 жовтня: …», «вчора, п'ятниця, 2 жовтня: …») → «Твої плани» (year intentions → month plan → week plan → today's plan, mutation tags stripped) → «Сьогодні» (the today block: done so far, still ahead) → «Що ти пам'ятаєш з минулої розмови: <підсумок>» (the last-session summary) → the reply-format rules (speak only as yourself, no name prefix, `PASS` allowed). `contents` = the last `HISTORY_N` messages as `"Name: text"` lines. This order is a contract.

Earlier phases use the prefix of this order that exists at that point (v1.1: persona + rules; v2.1: canon + summary + rules).

**Reply cleaning (since v2.1):** the model sometimes continues the `"Name: text"` script — prefixing its own name or writing other speakers' lines, even the owner's. Every reply is cleaned before sending: the own-name prefix is stripped, everything from the first other speaker's line is dropped (a reply that opens with someone else's line keeps only its first own-prefixed block), a reply with nothing of its own is silence, and a near-duplicate of the agent's previous message is skipped. Each agent has at most one pending reply; further triggers coalesce into it (it reads the latest context when it fires).

## Token accounting

- After **every** Gemini call — reply, session summary, day memory, week/month/year digest, plan, today block — the agent appends one JSON line to `state/<name>.usage.jsonl`: `ts` (in `TIMEZONE`), `agent`, `kind` (`reply` / `summary` / `day_memory` / `digest` / `plan` / `today`), `model`, `prompt_tokens`, `output_tokens`, `total_tokens`, `ok`. **Never any text.** Missing `usage_metadata` or fields → `null`s; a failed call → `ok: false`; a write error is logged and never blocks the conversation. Each agent writes only its own file.
- **Report:** `uv run agents/usage_report.py [--days N] [--since YYYY-MM-DD] [--markdown]` — a table by day × agent × kind with calls, tokens and estimated cost. Prices come only from `.env` (`PRICE_INPUT_PER_1M`, `PRICE_OUTPUT_PER_1M`, USD per 1M tokens); unset prices → no cost column. Corrupt lines are skipped with a warning; no files → "no data". The panel reuses the same aggregation code.
- **Daily report (v3.1.1):** `usage_report.py --write [DIR]` writes `DIR/YYYY-MM-DD.md` and `DIR/latest.md` (default `reports/usage/`, gitignored, atomic writes): yesterday by agent with the change from the day before, by kind (share of tokens, average input/output per call, failures) and by agent × kind; the last 7 complete days by day with the daily average and the busiest day; the month of yesterday so far with a projected month cost; today so far. Cost figures appear only when the prices are set. On the Mac a launchd job (`scripts/install-usage-daily.sh`, label `lan.agora.usage-report`) runs `scripts/usage-daily.sh` every day at 07:00 and at login; from v3.2 the job runs on the server next to `state/`.

## The panel: simulations and agents

The panel is the point of the whole project (VISION §The direction). One FastAPI app — a JSON API plus one static vanilla-JS page, **English UI** (the agents' own texts shown as-is, in Ukrainian), built to the Claude Design handoff in `specification/design/design_handoff_agora_panel/` (Nocturne tokens, dark default + light, `agora-panel.css` as the starter stylesheet; system fonts and inline icons — no outside requests) — running as the `panel` service beside the homeserver: port `8090`, ufw-limited to the LAN, Bearer `PANEL_TOKEN` on every API call. The agents and the terminal workflow keep working with the panel down.

- **The model.** A **simulation** is an environment agents join, managed as one unit: a registry entry `Simulation{id, kind, title, services, health, endpoints}` names its compose services, health probe and log sources. An **agent** is a managed participant: `Agent{name, container, canon, simulation}`; `agents/<name>.toml` carries `simulation = "agora"`, and the agent's connection settings (`HOMESERVER`, `ROOM_ID`) resolve from that entry. The registry holds exactly one entry — `agora`, kind `matrix-chat` — and this roadmap adds no second one; but every panel mechanism (deploy state, health, start/stop, logs, maintenance) is written against a registry entry, never against "the chat", so a new simulation kind is a registry entry plus its compose services, not a panel rewrite.
- **Viewing first, control second.** v3.3 ships the read-only panel (every card, the docker socket used only for container state and log tails); v3.4 adds the actions below — start/stop/restart, forget, confirmations.
- **Each agent is its own container** (one compose service per agent), and from v3.4 the panel launches them: start = `docker compose up -d <name>` (creates the container if it does not exist yet), stop = `docker stop -t 30` (SIGTERM → the session summary → SIGKILL after the grace period), restart, log tail. Agent, simulation and service names resolve only through the registry and the fixed agent list — an unknown name is 404, and no request data ever reaches a filesystem path, an argv or the docker API.
- **The simulation card (the chat):** the health probe (`/_matrix/client/versions`, every 30 s), per-service container state, start/stop/restart, log tails.
- **The agent cards:** container state and uptime; start/stop/restart (v3.4); log tail; session summary, day memories, plans, the today block; **"Forget the last session"** (deletes `state/<name>.memory.md`, confirmation required, stopped agents only); the 7-day token table (the v3.1 aggregation).
- **The host card:** uptime, disk, memory (from `/proc` and a read-only host mount).
- **Auth:** the UI asks for the owner token once and sends `Authorization: Bearer` on every call — checked by a middleware before routing (constant-time), so every `/api/*` path, even an unknown one, is 401 without it and the page shows nothing. The panel refuses to start without a `PANEL_TOKEN` of at least 24 characters; the OpenAPI docs routes are off. One owner, no accounts.
- **Actions (v3.4):** `POST /api/agents/{name}/start|stop|restart|forget` and `POST /api/simulations/{id}/services/{service}/start|stop|restart` — token-gated, **same-origin** (a foreign `Origin` → 403), names only through the registry (unknown → 404), one action at a time per target (busy → 409), docker unreachable → 503. Start = `docker compose -p server -f <stack>/server/docker-compose.yml up -d --no-deps <service>` (a fixed argv; creates a missing container) — only for a stopped, missing or crashed target (running → 409: the panel's compose would recreate it); stop = `stop(timeout=30)`; restart = stop + start. Each action is logged as an event (what, target, result, duration). Docker's `restarting` is its own state (warn), not "running".
- **Confirmations:** every stop/restart and forget is confirmed in the UI; start runs without one; mutating actions are `POST` + token + same-origin.
- **Degrade by card:** docker trouble greys the container cards, an unreadable `state/` greys the memory views; a stopped homeserver never crashes the agents (nio retries until it is back).
- **Views stay safe:** there is no settings view — the panel never shows or edits `.env` or canons; log views are safe because logs never contain tokens or texts.
- **Single instance:** an agent takes `flock` on `state/<name>.lock` (PID inside) at startup, so a second instance on the same host refuses to start. The panel manages containers only and does not detect agents started outside it.
- **Only what is recorded:** the cards show container state (docker), the `state/` files and the logs; nothing is added to the agents just to feed the panel.

## Contracts

Changing any of these updates this document and the test that pins it, in the same commit:

- The env var names in `.env.example` and `server/.env.example`.
- The agent TOML schema (`name`, `user_id`, `canon`, `life`, `simulation`, and the panel-only `[panel] name` / `role`) and the `agents/canon/` layout.
- The simulation registry `simulations.toml` (repo root): per entry `kind` (`matrix-chat`), `title`, `description`, `services`, `agents`, `health {service, port, path}`, `endpoints {homeserver, room}` — the env names its agents connect with; an agent belongs to one simulation (pinned by `tests/test_registry.py`).
- The plan file format: items plus hidden mutation tags, which never reach a conversational prompt (pinned by a test).
- The life-story format (header lines, `## YYYY–YYYY · title` chapters) and its visibility rule: future chapters and the death date never reach the conversational prompt (pinned by a test).
- The `state/` files: `<name>.json` (session), `<name>.memory.md`, `<name>.days/YYYY-MM-DD.md` + `.talk.md`, `<name>.weeks/YYYY-MM-DD.md`, `<name>.months/YYYY-MM.md`, `<name>.years/YYYY.md`, `<name>.plans/` (year, month, week and day plans, with hidden mutation tags), `<name>.today.md`, `<name>.usage.jsonl` (its fields), `<name>.lock`, `logs/<name>.log`.
- The message filter and allowlist rule.
- The transcript format (`"Name: text"` per line), the `PASS` sentinel, and the prompt-assembly order.
- The turn-taking semantics (who replies, `bot_streak`).
- The `server/docker-compose.yml` environment (server name, federation, encryption, registration). `CONTINUWUITY_SERVER_NAME` cannot change without wiping the database.
- The `server/docker-compose.yml` service set — `homeserver`, one service per agent (`ada`, `bruno`, v3.2), `usage-report` (v3.2), `panel` (v3.3) — the `../state` and `../reports` bind mounts, the agents' `HOMESERVER` override and `1000:1000` user, and what `server/deploy.sh` syncs and applies (pinned by `tests/test_compose.py`).
- The `server_con.yaml` shape (`host`, `user`, `password`) read by `server/deploy.sh`.
- The panel API surface (the v3.3 read-only `GET` routes; the v3.4 `POST` actions — exactly three routes, pinned by `tests/test_panel_api.py`), the simulation-registry entry shape, and the Bearer `PANEL_TOKEN` auth.

## Data and state files

There is no database, and nothing the agents lived is ever deleted: all durable state is per-agent files under the gitignored `state/` — at `~/matrix-agora/state/` on the server in production (v3.2+), local on the Mac in dev mode — bind-mounted into the agent containers and the panel. Every write where a torn file would hurt is atomic (temp file + rename). Nothing here ever reaches git or the image.

| File | Written | Content |
|---|---|---|
| `state/<name>.json` | first login | `access_token`, `device_id` — the Matrix session to reuse |
| `state/<name>.memory.md` | session end (idle / shutdown) | last-session summary, ≤ `SUMMARY_MAX_WORDS` words |
| `state/<name>.days/YYYY-MM-DD.talk.md` | each session end | the day's journal: session summaries with times |
| `state/<name>.days/YYYY-MM-DD.md` | after midnight / catch-up | day memory, ≤ `DAY_MEMORY_MAX_WORDS` words; never rewritten |
| `state/<name>.weeks/YYYY-MM-DD.md` | after the week ends | week digest (keyed by Monday), ≤ `WEEK_MEMORY_MAX_WORDS`; never rewritten |
| `state/<name>.months/YYYY-MM.md` | after the month ends | month digest, ≤ `MONTH_MEMORY_MAX_WORDS`; never rewritten |
| `state/<name>.years/YYYY.md` | after the year ends | year digest, ≤ `YEAR_MEMORY_MAX_WORDS`; never rewritten |
| `state/<name>.plans/year-YYYY.md` | 1 January | year intentions, ≤ `PLAN_MAX_WORDS`; hidden mutation tags; frozen after its year |
| `state/<name>.plans/month-YYYY-MM.md` | the 1st of the month | month plan, ≤ `PLAN_MAX_WORDS`; hidden mutation tags; frozen after its month |
| `state/<name>.plans/week-YYYY-MM-DD.md` | first build of a new week | week plan, ≤ `PLAN_MAX_WORDS` words; frozen after its week |
| `state/<name>.plans/YYYY-MM-DD.md` | first build of a new day | day plan, ≤ `PLAN_MAX_WORDS` words; frozen after its day |
| `state/<name>.today.md` | hourly; reset at midnight | the today block (+ the hour it was built for), ≤ `TODAY_MAX_WORDS` words |
| `state/<name>.usage.jsonl` | every Gemini call | one JSON line: `ts`, `agent`, `kind`, `model`, token counts, `ok` — no texts |
| `state/<name>.lock` | startup (`flock`) | the PID of the running instance |
| `state/logs/<name>.log` | continuously | rotating log, 1 MB × 3 — no tokens, passwords or texts |

The agent TOML (`agents/<name>.toml`, committed) holds `name`, `user_id`, `canon`, `life`, `simulation` (v3.3: the registry entry — its `endpoints` name the env vars the agent connects with) and a panel-only `[panel]` table (the English display name and role, never part of a prompt); the shared `.env` holds everything in §Configuration and secrets. These shapes are contracts (§Contracts).

## Configuration and secrets

All tunables live in `.env` (shared) or the agent's TOML (per-agent), never hardcoded:

| Variable | Phase | Meaning (example default) |
|---|---|---|
| `HOMESERVER`, `ROOM_ID`, `OWNER` | v0.4 | where and with whom the agents talk |
| `ADA_PASSWORD`, `BRUNO_PASSWORD` | v0.4 | first-login passwords |
| `GEMINI_API_KEY` | v1.1 | read by `google-genai` from the environment |
| `HISTORY_N`, `REPLY_DELAY_S`, `MAX_BOT_TURNS`, `BOT_REPLY_P`, `BOT_WINDOW_S` | v1.1–v1.2 | context size and turn-taking (30 / 4 / 2 / 0.5 / 600) |
| `SESSION_IDLE_S`, `SESSION_MAX_MESSAGES`, `SUMMARY_MAX_WORDS` | v2.1 | session memory (900 / 200 / 200) |
| `LOCATION`, `TIMEZONE`, `MEMORY_DAYS`, `DAY_MEMORY_MAX_WORDS` | v2.2 | world awareness (Львів / Europe/Kyiv / 7 / 120) |
| `MEMORY_WEEKS`, `MEMORY_MONTHS`, `WEEK_MEMORY_MAX_WORDS`, `MONTH_MEMORY_MAX_WORDS`, `YEAR_MEMORY_MAX_WORDS` | v2.2 | memory digests in the prompt and their sizes (4 / 6 / 150 / 200 / 300) |
| `PLAN_MAX_WORDS`, `TODAY_MAX_WORDS`, `PLAN_MUTATION_RATE` | v2.2 | plans, the today block, plan deviation from the life story (120 / 100 / 0.3) |
| `PRICE_INPUT_PER_1M`, `PRICE_OUTPUT_PER_1M` | v3.1 | token prices for the cost column |
| `AGENT_IMAGE_TAG` | v3.2 | which agent image the server runs: `latest` (the newest release) or `edge` (`main`, before a release); `server/.env` only |
| `PANEL_TOKEN` | v3.3 | the single owner token for the panel API |
| `PANEL_IMAGE_TAG`, `DOCKER_GID`, `PANEL_BIND`, `STACK_DIR` | v3.3–v3.4 | which panel image the server runs (`latest` / `edge`); the host's docker group id for the socket (999); the LAN address the panel is published on (192.168.1.197; unset → 127.0.0.1); where the stack lives on the host (`/home/ich/matrix-agora`, v3.4); `server/.env` only |
| `REGISTRATION_TOKEN` | v0.1 | in `server/.env` on the Ubuntu box only |

From v3.2 the production values live in `server/.env` on the Ubuntu box (synced by `server/deploy.sh`), including `GEMINI_API_KEY`; the Mac's `.env` serves the dev mode. `.env`, `server/.env`, `server_con.yaml` and `state/` are gitignored. Tokens, passwords, keys and message/summary/memory texts never appear in logs, argv, commits or the panel.

## Security and access

| Threat | Protection |
| --- | --- |
| Someone registers on the server | Registration disabled after v0.4; the token only in `server/.env` |
| Someone from the internet | Port 8008 not forwarded on the router; ufw allows only `192.168.1.0/24`; federation disabled |
| Someone messages the bots (DM, another room) | The in-code allowlist: only `ROOM_ID` + `{OWNER, other agent}` |
| Key leak | `.env`, `server/.env`, `state/` gitignored; tokens and texts never logged |
| Agents burn credits chatting with each other | at most `MAX_BOT_TURNS` agent turns per `BOT_WINDOW_S`, `BOT_REPLY_P`, `PASS`, `max_output_tokens`; one summary per session; one memory per day; one plan per day and per week; the today block at most once per hour; the usage report shows the spend |
| Conversation leak | Summaries, journals and day memories live only in `state/`; their texts are never logged |
| Private data in the public repo | Canons are committed — no secrets, no private data about the owner |
| Someone on the LAN opens the panel | Bearer `PANEL_TOKEN` required on every API call; :8090 published on the LAN address only (docker bypasses ufw); no view shows a secret (no settings view, logs carry no tokens) |
| A compromised panel container | it holds the host's docker socket (root-equivalent) and, from v3.4, reads `server/.env` (compose needs it to create a missing container) — an accepted PoC trade-off: token-gated, same-origin actions, LAN-only, never internet-exposed. A socket proxy was considered and declined (v3.4): compose needs create / network / volume calls a narrow proxy would have to allow anyway |
| The deploy password leaks | Key auth after a one-time `ssh-copy-id`; `server_con.yaml` gitignored; the password never in argv, logs or output |
| Secrets in CI or in the image | CI uses mocks and `GITHUB_TOKEN` only; `.env` and `state/` stay on the host, never in the image |

HTTP without TLS on the LAN is a deliberate PoC trade-off: passwords travel in plaintext over the home network. Before any external access: Tailscale (or a reverse proxy with TLS).

## Deployment and CI/CD

- **Server deploy (from v0.2).** `server/deploy.sh` is the only way server config reaches the Ubuntu host: a local compose preflight → a one-time `ssh-copy-id` key setup (after that, key auth only; the password from `server_con.yaml` never appears in argv, logs or output) → rsync `server/docker-compose.yml` + `server/.env` to `~/matrix-agora/server/` → `mkdir -p ~/matrix-agora/state ~/matrix-agora/reports` (so the bind mounts stay the host user's) → remote `docker compose pull && docker compose up -d` (the pull from v3.2) → verify `/_matrix/client/versions`. From v3.2 the compose carries one service per agent, from v3.3 the `panel` service — one deploy updates the whole stack. Idempotent; `--dry-run` supported. Never hand-edit files on the host.
- **Agent image (from v3.2).** One Docker image for both agents (`agents/Dockerfile`: python slim + uv, uid 1000; `.dockerignore` keeps `.env`, `server/.env`, `server_con.yaml`, `state/` and `reports/` out), **one container per agent**: compose services `ada` and `bruno` on the server — `ghcr.io/ichmaster/matrix-agora-agent:${AGENT_IMAGE_TAG:-latest}`, the per-agent TOML as the command, env from `server/.env` with `HOMESERVER=http://homeserver:8008` (the compose network), `TZ` from `TIMEZONE`, `user: 1000:1000` (the host user, so the bind-mounted `~/matrix-agora/state` stays theirs), `init: true` (tini as PID 1, so SIGTERM reaches python), `stop_grace_period: 30s`, `restart: unless-stopped`. `docker stop -t 30` sends SIGTERM, which triggers the shutdown session summary. A third service from the same image, `usage-report` (`agents/usage_daily.py`), writes the daily token report at 07:00 in `TIMEZONE` to `~/matrix-agora/reports/usage/` (`state/` mounted read-only). Each agent holds `flock` on `state/<name>.lock`, so a second instance on the same host exits; logs go to `state/logs/<name>.log` (1 MB × 3) and the console. The image holds no secrets. Dev mode (`uv run agents/agent.py …` on the Mac, local `state/`) remains — never at the same time as the server's agent, since the lock is per host.
- **CI (from v3.2).** GitHub Actions on every push/PR: ruff, pytest (nio/Gemini mocked — no paid APIs, no secrets in CI), the compose config gate, and the image builds (the agent image; the panel image from v3.3). Images go to GHCR (`ghcr.io/ichmaster/matrix-agora-agent`, `…-panel` from v3.3) using only `GITHUB_TOKEN`: a `vA.B.C` tag publishes `:vA.B.C` + `:latest`; a push to `main` publishes `:edge` + `:sha-<short>`, so the server can run a phase's code (`AGENT_IMAGE_TAG=edge`) before its release tag exists. The package is public, so the server pulls without credentials.
- **Panel image (from v3.3).** `panel/Dockerfile` (python slim + uv, only the `panel` dependency group, uid 1000, `uvicorn --factory panel.app:create_app` on 8090); compose service `panel`: `ghcr.io/ichmaster/matrix-agora-panel:${PANEL_IMAGE_TAG:-latest}`, port 8090 published on `${PANEL_BIND}` only (docker-published ports bypass ufw, so the binding — not ufw — keeps it on the LAN), `group_add` the host's docker group, the docker socket, `state/` (read-only in v3.3, read-write from v3.4 for forget), `/etc/os-release` read-only, from v3.4 the stack's `server/` directory read-only **at its host path** (so compose, run inside the panel for a start, resolves `../state` to the real host paths) plus the docker CLI and compose plugin copied from the official images, and only its own settings in `environment:` (`PANEL_TOKEN`, the prices, `TIMEZONE`) — never the agents' keys or passwords. CI builds both images from one matrix.
- **No cloud-to-LAN CD.** A GitHub runner cannot reach the home network, so CI never deploys. Deploys run from the Mac: `server/deploy.sh` is the one command — the server then pulls the images from GHCR itself.

## Error handling and resilience

- A Gemini failure or empty reply on any call → log and stay silent; the bot never crashes or sends an apology message.
- A dropped homeserver connection → `matrix-nio`'s sync loop retries; an exception in a callback must not kill `sync_forever`.
- Typing state is reset in `finally` so a failure never leaves "typing…" stuck.
- Memory: failed summary → previous kept; failed plan or today refresh → previous file or block kept; corrupt file → start without memory; all writes atomic.
- Usage accounting and panel polling are best-effort: their failures are logged and never block a conversation or a stop.
- The panel degrades by card: docker trouble greys the container cards, an unreadable `state/` greys the memory views. A stopped homeserver never crashes the agents — the sync loop retries until it is back.

## Observability

- Each agent logs to `state/logs/<name>.log` (rotating, 1 MB × 3) and the console; in a container the same file arrives via the `state/` mount, and `docker logs` shows the console stream.
- Log lines record events — joined, `ignored` (with the reason), replied, summary / memory / plan / today written, usage-write failed — **never** message, summary, memory or plan texts, tokens, passwords or keys. That is what makes the panel's log view safe to render.
- `state/<name>.usage.jsonl` is the metrics stream: one line per Gemini call with token counts; `usage_report.py` and the panel aggregate it (§Token accounting).
- The panel logs its own actions to its container log (`docker logs panel`) — same rules: no tokens, no texts.
- The panel (any LAN browser, with the token) is the live view: the simulation's health and services, agent state and logs, memory, plans, the today block, the token table, host metrics.
- Nothing is sent anywhere: no telemetry, no crash reporting; everything observable stays in `state/` and the container logs on the server (on the Mac in dev mode).

## Repository layout

```
matrix-agora/
  CLAUDE.md                 # instructions for Claude Code
  LICENSE
  README.md
  pyproject.toml            # uv; deps: matrix-nio, google-genai, python-dotenv,
                            # fastapi + uvicorn (v3.3); dev: ruff, pytest
  specification/
    VISION.md               # why and for whom
    ARCHITECTURE.md         # this file: components, mechanisms, contracts
    ROADMAP.md              # versions and phases with Goal/Tasks/DoD/Tests
    history/                # superseded SPEC.md + SPEC-UA.md, frozen
    implementation/         # issue files and reports (generated by the skills)
  server/                   # v0.1
    docker-compose.yml      # the stack: homeserver + panel (v3.3) + ada + bruno (v3.2)
    deploy.sh               # v0.2: sync server/ to the Ubuntu host and apply it
    .env.example            # REGISTRATION_TOKEN=
  agents/
    agent.py                # one codebase for both agents
    ada.toml                # name, user_id, canon, …
    bruno.toml
    canon/                  # v2.1: common.md + <name>.md
    usage_report.py         # v3.1: token report (+ --write: the daily report, v3.1.1)
    usage_daily.py          # v3.2: the daily report as the compose service usage-report
    runtime.py              # v3.2: the single-instance lock + the rotating file log
    registry.py             # v3.3: loads simulations.toml (agents + panel)
    Dockerfile              # v3.2: one image for both agents
  simulations.toml          # v3.3: the simulation registry (one entry: agora)
  panel/                    # v3.3: the panel — app.py (API + gate), registry.py, static/, Dockerfile
  .github/workflows/ci.yml  # v3.2: gates + image builds; GHCR push on tags
  scripts/
    run-agent.sh            # dev mode: one agent in the foreground
    usage-daily.sh          # v3.1.1: the daily token report
    install-usage-daily.sh  # v3.1.1: the macOS launchd job for it (--uninstall)
  .env.example              # see §Configuration and secrets
  .dockerignore             # v3.2: secrets and state never enter the image
  state/                    # gitignored: each bot's session, memory (v2.1),
                            # day memories, plans, the today block (v2.2), usage (v3.1), lock + logs (v3.2)
  reports/usage/            # gitignored: daily token reports (v3.1.1)
```

## Testing and CI

Automated gates need no network: `matrix-nio` and `google-genai` are mocked, the clock and randomness are injected, and nothing in the acceptance path calls a paid API.

| Gate | Command | When |
|---|---|---|
| Lint | `uv run ruff check .` | any Python change |
| Tests | `uv run pytest` (single test: `uv run pytest tests/test_x.py::test_name`) | any Python change |
| Compose | `REGISTRATION_TOKEN=dummy docker compose -f server/docker-compose.yml config -q` | `server/` changed |

Before v0.5 there is no `pyproject.toml`, so the Python gates are `n/a`, not passed.

- **Unit tests** cover the pure logic: the filter and allowlist, mention detection (Ukrainian case forms), `bot_streak` and who-replies, transcript and prompt assembly (section order), the session-end decision, memory file read/write (missing, corrupt, atomic), calendar strings (including DST switches), which days, plan periods and digest periods need generating, the layered memory selection (no overlap, oldest first), the hourly today-refresh decision, "a past day's memory or plan is never rewritten", `usage_metadata` parsing and aggregation, the panel's supervisor and registry resolution (a fake docker client; an unknown simulation/agent/service → 404), the single-instance lock, and the Bearer-token check (401 without the token).
- **Contract tests** pin the seams in §Contracts; a contract change updates the test in the same commit.
- **CI** (`.github/workflows/ci.yml`, from v3.2) runs the same gates plus the image builds on every push/PR; a `vA.B.C` tag publishes `:vA.B.C` + `:latest`, a `main` push `:edge` (pinned by `tests/test_ci.py`). No paid keys ever exist in CI.
- **Manual (owner) checks** are the DoD items that need the live homeserver, Element or a real Gemini key. The read-only `curl` checks may be run by tooling; everything on the Ubuntu host, in Element, or that spends real tokens is performed or confirmed by the owner, and counts as passed only then.
