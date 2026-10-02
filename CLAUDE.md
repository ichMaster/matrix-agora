# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

Proof of concept: a private Matrix room where the owner and two LLM agents ("Ada" and "Bruno", Gemini 2.5 Flash) talk together. So far the repo holds only the plan. `specification/SPEC.md` is the source of truth. It is an English translation of the Ukrainian original, `specification/SPEC-UA.md`, and the two must stay in sync. It is split into phases 0–8, each with a DoD (definition of done). Build phase by phase and check each phase against its DoD before moving on.

Latest release: none yet.

| Phase | SPEC.md | Title | Kind of work |
|---|---|---|---|
| `p0` | §2 | Homeserver: Continuwuity on the Ubuntu host | `server/` files + owner steps on the host |
| `p1` | §3 | Client: Element Desktop | owner steps only |
| `p2` | §4 | Bot accounts and the room | owner steps + closing registration in `server/docker-compose.yml` |
| `p3` | §5 | Echo bot: Matrix without the LLM | code |
| `p4` | §6 | LLM: Gemini 2.5 Flash | code |
| `p5` | §7 | Three-way conversation and loop protection | code |
| `p6` | §8 | Agent canons and memory across sessions | code + canon files |
| `p7` | §9 | World awareness: Lviv, calendar and time, day memories | code |
| `p8` | §10 | Token accounting and report | code |

The SPEC.md section number is the phase number + 2. §1 is the architecture, §11 security, §12 out of scope.

## Planned layout and commands

```
pyproject.toml          # uv; deps: matrix-nio, google-genai, python-dotenv
server/docker-compose.yml, server/.env.example   # REGISTRATION_TOKEN=
agents/agent.py         # single codebase for both agents
agents/ada.toml, agents/bruno.toml   # name, user_id, persona (canon path from p6), …
agents/canon/          # common.md + <name>.md: who each agent is (p6), committed
agents/usage_report.py # token report (p8)
.env.example            # HOMESERVER, ROOM_ID, OWNER, ADA_PASSWORD, BRUNO_PASSWORD, GEMINI_API_KEY
state/                  # gitignored: session, memory, day memories, usage log per bot
specification/implementation/   # issues files, execution reports, code reviews (see Delivery workflow)
```

- Run an agent (one terminal per agent): `uv run agents/agent.py agents/ada.toml`, and the same for `agents/bruno.toml`
- Server (on the Ubuntu host, from `server/`): `docker compose up -d`, then `docker compose logs -f homeserver`
- Homeserver smoke test from the Mac: `curl http://192.168.1.197:8008/_matrix/client/versions`
- `server_con.yaml` (gitignored) holds the SSH host, user and password for the Ubuntu host. Never print it, commit it, or put the password on a command line. Act on the host only when the owner asks.

## Architecture

- **Homeserver:** Continuwuity (Rust, embedded RocksDB) in a single Docker container on an Ubuntu box at `192.168.1.197:8008`. Plain HTTP, LAN only. `server_name = agora.lan`, so user IDs look like `@ada:agora.lan`. Federation and encryption are disabled on the server. Clients connect by IP, so the name needs no DNS.
- **Client:** Element Desktop on the Mac. The web app can't connect, because an HTTPS page can't call an HTTP homeserver (mixed content).
- **Agents:** two processes on the Mac that run the same `agent.py` with different TOML configs. `matrix-nio` handles the Matrix side and `google-genai` (async `client.aio.models.generate_content`) handles Gemini.

## Agent behavior invariants (from SPEC.md)

These rules are easy to break by accident:

- **Login:** log in with the password once. Save `access_token` + `device_id` to `state/<name>.json` and reuse them on later starts. Logging in with the password on every start creates a new device on the server each time.
- **Invites:** join only invites from `OWNER` into `ROOM_ID`. Ignore or leave every other invite.
- **No replaying history:** use the first `sync` only to get `next_batch` and do not process its events. Then call `sync_forever`. If the first sync's events are processed, a restarted bot replies to the whole room history.
- **Message filter** (`RoomMessageText`): handle a message only if `room_id == ROOM_ID`, the sender is not the bot itself, and the sender is in the hardcoded allowlist `{OWNER, other agent's user_id}`. Log every other message as `ignored`.
- **LLM call:** use `gemini-2.5-flash` with the persona as `system_instruction`, `max_output_tokens=400` and `thinking_budget=0`. The context is the last `HISTORY_N` room messages, including the bot's own and the other agent's, formatted as one `Name: text` per line. The raw history stays in memory only. From p6 on, only summaries, day memories and the usage log persist, all under `state/`.
- Set typing to `True` before the Gemini call and back to `False` after it.
- If Gemini fails or returns empty text, log the error and send nothing. The bot must not crash.
- Send replies as `m.text`, not `m.notice`. Otherwise the other agent may treat them as service messages.
- Never log tokens or message texts.

## Turn-taking / loop prevention (phase 5)

This logic is pure and needs no network. SPEC.md asks for unit tests of the pure logic: turn-taking, prompt and memory assembly (p6), calendar and day memories (p7), token accounting (p8). Everything else is checked manually against each phase's DoD.

- **Owner's message mentions one agent** (by name or mention): only that agent replies.
- **Owner's message mentions no agent:** both agents reply, each after a random 1–4 s delay. The delay keeps them from talking at once and lets the second one see the first one's reply.
- **Message from the other agent:** reply only if `bot_streak < MAX_BOT_TURNS` (default 2), and then only with probability `BOT_REPLY_P` (e.g. 0.5).
  - `bot_streak` counts consecutive agent messages since the owner's last message. An owner message resets it to 0.
  - Both agents compute it from the same room timeline, so they agree without any coordination. Don't add shared state for this.
- **`PASS`:** if the model returns exactly `PASS`, send nothing. The prompt must allow the model to do this.
- **Tunables:** `MAX_BOT_TURNS`, `BOT_REPLY_P`, `HISTORY_N` and `REPLY_DELAY_S`, set in `.env` or TOML.

## Canon, memory, world and tokens (phases 6–8)

- **Canon:** `agents/canon/common.md` + `agents/canon/<name>.md` replace the TOML `persona`. A missing or empty canon stops the bot at startup. Canons are committed to a public repo, so they hold no secrets and no private data about the owner.
- **The agents believe they are human.** The canons say so. Nothing in code (reply rules, summary or memory prompts) may mention that an agent is a model or a bot. This holds only because the room is closed and the owner knows; revisit it if anyone else ever joins.
- **Reply-format rules stay in code** (own voice, no name prefix, `PASS`), never in a canon.
- **Session memory (p6):** a session ends after `SESSION_IDLE_S` of silence or on shutdown (summary with a ~20 s timeout). The new summary is made from the previous summary plus the session timeline (capped by `SESSION_MAX_MESSAGES`), written atomically to `state/<name>.memory.md`. Each agent summarizes from its own point of view.
- **World (p7):** `LOCATION` (Lviv) and `TIMEZONE` (`Europe/Kyiv`). Date, weekday, time, part of day and season are computed per call in Ukrainian, from tables in code (not the system locale), with an injectable clock.
- **Day memories (p7):** these are auto-generated once per past day into `state/<name>.days/YYYY-MM-DD.md`, from that day's journal (`YYYY-MM-DD.talk.md`, the session summaries appended). Missed days are caught up at startup, up to `MEMORY_DAYS` back.
  - A past day is never rewritten.
  - Room events come only from the journal. Invented episodes involve only the agent itself and the city, never the owner or the other agent.
- **Prompt order (p7):** canon → place, calendar and time → day memories → last-session summary → reply rules. `contents` stays the last `HISTORY_N` messages.
- **Tokens (p8):** every Gemini call appends one JSON line (`ts`, `agent`, `kind`, `model`, token counts, `ok`) to `state/<name>.usage.jsonl`.
  - The line never contains texts.
  - Missing `usage_metadata` gives `null`s, never a crash.
  - Prices come only from `.env` (`PRICE_INPUT_PER_1M`, `PRICE_OUTPUT_PER_1M`).
  - Report: `uv run agents/usage_report.py [--days N] [--since YYYY-MM-DD] [--markdown]`.
- **More tunables:** `SESSION_IDLE_S`, `SESSION_MAX_MESSAGES`, `SUMMARY_MAX_WORDS`, `LOCATION`, `TIMEZONE`, `MEMORY_DAYS`, `DAY_MEMORY_MAX_WORDS`.

## Contracts

Changing any of these is a contract change: update `specification/SPEC.md`, `specification/SPEC-UA.md`, this file and the test that pins it, all in the same commit.

- Env var names in `.env.example` and `server/.env.example`
- The agent TOML schema (`name`, `user_id`, `persona` → `canon` from p6, …) and the `agents/canon/` layout
- The `state/` files: `<name>.json` (`access_token`, `device_id`), `<name>.memory.md`, `<name>.days/YYYY-MM-DD.md` + `.talk.md`, `<name>.usage.jsonl` (its fields)
- The message filter and allowlist rule
- The transcript format sent to Gemini (`Name: text` per line), the `PASS` sentinel, and the order of the prompt sections
- The turn-taking semantics (who replies, `bot_streak`)
- The `server/docker-compose.yml` environment (server name, federation, encryption, registration)

## Acceptance gates

Automated gates need no network. Tests mock `matrix-nio` and `google-genai`, so nothing reaches the homeserver or Gemini.

| Gate | Command | When |
|---|---|---|
| Lint | `uv run ruff check .` | any Python change |
| Tests | `uv run pytest` (one test: `uv run pytest tests/test_x.py::test_name`) | any Python change |
| Compose | `REGISTRATION_TOKEN=dummy docker compose -f server/docker-compose.yml config -q` | `server/` changed |

- **Compose gate:** keep `-q`. Without it, the command prints the resolved config.
- **Before phase 3:** there is no `pyproject.toml`, so the Python gates are `n/a`, not passed. ruff and pytest are dev dependencies, added by the issue that creates `pyproject.toml`.
- **Manual gates:** these are the DoD checks in SPEC.md that need the live homeserver, Element or (from p4) a real Gemini key.
  - Claude may run the read-only `curl` checks from the Mac.
  - Anything on the Ubuntu host, in Element, or that makes a live Gemini call is done or confirmed by the owner.
  - A manual check counts as passed only once the owner confirms it.

## Delivery workflow (skills)

`.claude/skills/` holds a spec-driven pipeline adapted from the H11 project.

- **Issues:** each SPEC.md phase becomes `specification/implementation/pN-issues.md`. Issue ids are `AGORA-###`, numbered globally and never reset.
- **Implementation:** each issue is one commit. Each phase is then reviewed, and the fix-now findings are fixed.
- **Releases:** phase N ships as `v0.N.0`; post-release fixes are `v0.N.1`, `v0.N.2`, ….
- **GitHub flow:** `/ship-phase pN` runs `/generate-issues` → `/upload-issues` → `/execute-issues` → `/review-and-fix-issues` → `/release-version` for each phase, then `/harden-findings` at the end of the run.
- **Offline flow:** `/ship-solution` runs `/reconcile-issues` → `/execute-issues-file` → `/review-and-fix-issues` → `/release-version` over issues files that already exist.
- **Who releases:** versions are bumped and tagged only by `/release-version`, `/ship-phase`, `/ship-solution` or `/harden-findings --release`.

## Constraints

- `CONTINUWUITY_SERVER_NAME` cannot change without wiping the database.
- Registration is open with a token only until the bot accounts exist (phase 2). After that it is turned off (`CONTINUWUITY_ALLOW_REGISTRATION: "false"`).
- Running without TLS is a deliberate PoC trade-off. Never expose port 8008 through the router. Any outside access must go through Tailscale later.
- Out of scope (SPEC.md §12): E2EE, media, voice/video, long-term memory beyond the last session and recent days, live world data (weather, news), token limits and budgets.
