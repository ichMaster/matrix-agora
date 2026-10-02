# Roadmap — matrix-agora

Four self-contained versions, built in order: **v0** Platform (homeserver, server deploy, client, accounts, echo bot) → **v1** Conversation (Gemini replies, three-way turn-taking) → **v2** Persona & memory (canons, session memory, world awareness) → **v3** Operations (token accounting, agent images + CI/CD, web panel). Phases inside a version are numbered `vA.B` (A = version, B = phase). Each phase lists a **Goal**, a short description, a **Tasks** list, a **Definition of Done (DoD)**, and the **Tests** that encode its DoD (see [ARCHITECTURE.md](ARCHITECTURE.md) §Testing and CI). Phases are built strictly in file order; each one builds on the previous one's real, released code.

**Versioning (`A.B.C`).** `A` = roadmap version (v0→0 … v3→3), `B` = phase within it, `C` = a post-release fix on that phase. Roadmap phase `vA.B` → release `A.B.0`, tag `vA.B.0`; a fix after it bumps `C`. Releases are cut per phase. Never bump a version without explicit confirmation.

Many DoD items need the live homeserver, Element or a real Gemini key — those are **Manual (owner)** checks: the owner performs or confirms them, and only then do they count as passed. Everything automated runs with `matrix-nio` and `google-genai` mocked and the clock injected (no network, no paid calls).

---

## v0 — Platform: homeserver, server deploy, client, accounts, echo bot

The working skeleton with no LLM: the Continuwuity homeserver in Docker on the Ubuntu box, a scripted deploy of the repo's server config to that box, Element Desktop as the owner's client, the bot accounts and the private room, and an echo bot that proves the whole Matrix side — login and session reuse, invites, the first-sync rule, the message filter and allowlist. v0.1, v0.3 and v0.4 are mostly steps the owner performs on the host and in Element; v0.2 is the first script, v0.5 the first real code. Depends on: nothing — this is the foundation.

### v0.1 — Homeserver (Ubuntu, 192.168.1.197)

**Goal:** a Matrix homeserver on the home network that survives a reboot and is invisible from outside.

Continuwuity in one Docker container: embedded RocksDB, federation and encryption off, registration temporarily open behind a token. `server_name = agora.lan` is only the domain part of user ids — no DNS needed, clients connect by IP. It **cannot be changed later without wiping the database**.

**Tasks:**
- Install Docker Engine + the compose plugin (Docker's official Ubuntu repository).
- Create `server/docker-compose.yml` (deployed at `~/matrix-agora/server/` on the host):

  ```yaml
  services:
    homeserver:
      image: forgejo.ellis.link/continuwuation/continuwuity:latest
      # mirror, if the main registry is unavailable: ghcr.io/continuwuity/continuwuity:latest
      restart: unless-stopped
      ports:
        - "8008:8008"
      volumes:
        - db:/var/lib/continuwuity
      environment:
        CONTINUWUITY_SERVER_NAME: agora.lan        # CANNOT be changed without wiping the DB
        CONTINUWUITY_DATABASE_PATH: /var/lib/continuwuity
        CONTINUWUITY_ADDRESS: 0.0.0.0
        CONTINUWUITY_PORT: 8008
        CONTINUWUITY_ALLOW_FEDERATION: "false"     # fully closed off from the Matrix network
        CONTINUWUITY_ALLOW_ENCRYPTION: "false"     # no E2EE rooms at all — simpler for the bots
        CONTINUWUITY_ALLOW_REGISTRATION: "true"    # temporarily, until v0.4
        CONTINUWUITY_REGISTRATION_TOKEN: "${REGISTRATION_TOKEN}"
  volumes:
    db:
  ```

- `REGISTRATION_TOKEN` in `server/.env` next to it (a long random string, `openssl rand -hex 24`), never committed; ship `server/.env.example`.
- Firewall: `sudo ufw allow from 192.168.1.0/24 to any port 8008 proto tcp`.
- `docker compose up -d`; check `docker compose logs -f homeserver`.

**DoD** (Manual, owner):
- From the Mac: `curl http://192.168.1.197:8008/_matrix/client/versions` returns JSON with a list of versions.
- `curl http://192.168.1.197:8008/_matrix/federation/v1/version` does not respond as a federation endpoint.
- After `sudo reboot` the container comes back up on its own.

**Tests:** the compose gate — `REGISTRATION_TOKEN=dummy docker compose -f server/docker-compose.yml config -q` passes. The rest is the manual DoD.

### v0.2 — Server deploy from the repo

**Goal:** any configuration under `server/` reaches the Ubuntu host with one command — never by hand-editing files on the host.

The repo is the source of truth for the server. A deploy script reads the gitignored `server_con.yaml` (SSH host, user, password), syncs `server/` to `~/matrix-agora/server/` on the host and applies it with `docker compose up -d`. From now on every server-config change (e.g. closing registration in v0.4) goes through this script.

**Tasks:**
- `server/deploy.sh`:
  - Preflight: `REGISTRATION_TOKEN=dummy docker compose -f server/docker-compose.yml config -q` locally; abort on failure.
  - One-time key setup: if key auth to the host fails, run `ssh-copy-id` (the owner types the password interactively). After that, key auth only; the password from `server_con.yaml` never appears on a command line, in logs or in output.
  - Sync `server/docker-compose.yml` and `server/.env` to `~/matrix-agora/server/` (rsync over ssh).
  - Apply: `ssh <host> 'cd ~/matrix-agora/server && docker compose up -d'`.
  - Verify: poll `http://<host>:8008/_matrix/client/versions` with bounded retries; report success or failure.
- `--dry-run`: show what would be copied and run, change nothing.
- Idempotent: re-running with no changes does nothing but the verify.

**DoD:**
- (Manual, owner) Change a comment in `server/docker-compose.yml`, run `server/deploy.sh` → the file lands on the host, `docker compose up -d` runs there, and the homeserver still answers.
- (Manual, owner) `server/deploy.sh --dry-run` changes nothing on the host.
- The password never appears in the script's output, argv (`ps`) or logs.

**Tests:** the compose gate (the script's preflight). The rest is the manual DoD.

### v0.3 — Client (Element Desktop on the Mac)

**Goal:** the owner is logged in to the homeserver as its admin.

**Tasks:**
- `brew install --cask element`.
- Element → Create account → **Edit** homeserver → `http://192.168.1.197:8008` → register `me` with `REGISTRATION_TOKEN`. The first account automatically becomes the admin and is invited to the admin room.

**DoD** (Manual, owner):
- Logged in as `@me:agora.lan` and can see the admin room.

**Tests:** none (owner steps only).

### v0.4 — Bot accounts and the room

**Goal:** the agents' accounts exist, the room is ready, and the server is closed.

**Tasks:**
- Create the accounts `ada` and `bruno` — via token registration (log out/in in Element, or `curl` to `/_matrix/client/v3/register`), or with an admin-room command (`!admin users create-user ada`).
- **Close registration:** set `CONTINUWUITY_ALLOW_REGISTRATION: "false"` in the repo's `server/docker-compose.yml` and apply it with `server/deploy.sh` (v0.2). From now on only the admin creates accounts.
- In Element create the room **«Агора»**: private (invite-only), encryption disabled (forbidden on the server anyway). Invite `@ada:agora.lan` and `@bruno:agora.lan`.
- Record the room's `room_id` (Room settings → Advanced, of the form `!xxxx:agora.lan`).

**DoD** (Manual, owner):
- Registering a new account without the admin is refused.
- The room contains the owner + two pending invites (the bots accept them in v0.5).

**Tests:** the compose gate again (registration flag changed). The rest is the manual DoD.

### v0.5 — Echo bot (Matrix without the LLM)

**Goal:** the whole Matrix side proven separately from any LLM.

The first code: the uv project, one `agents/agent.py` for both agents, TOML configs, and the session/invite/filter discipline from ARCHITECTURE §Message flow. The reply is a literal echo. Run: `uv run agents/agent.py agents/ada.toml` (and the same for `bruno.toml` in a second terminal).

**Tasks:**
- `pyproject.toml` (uv; deps `matrix-nio`, `google-genai`, `python-dotenv`; dev `ruff`, `pytest`), `.env.example` (`HOMESERVER`, `ROOM_ID`, `OWNER`, `ADA_PASSWORD`, `BRUNO_PASSWORD`, `GEMINI_API_KEY`), `agents/ada.toml` + `agents/bruno.toml`.
- Login: password on first run → save `access_token` + `device_id` to `state/<name>.json`; restore on later runs.
- Invites: join only `OWNER`'s invites into `ROOM_ID`; leave/ignore the rest.
- First sync only for `next_batch` (events not processed), then `sync_forever`.
- The message filter and allowlist (ARCHITECTURE §Message flow), everything else logged as `ignored`.
- Echo reply: `"<name> чує: <text>"` (Ukrainian for "<name> hears: <text>" — the literal format the bot sends).

**DoD:**
- (Manual, owner) A message in «Агора» → both bots reply with the echo.
- (Manual, owner) Restarting a bot: it does not reply to old messages and does not create a new device.
- (Manual, owner) A message in another room or a DM is ignored (visible in the log as `ignored`).

**Tests:** unit — the filter/allowlist over plain data (own message, foreign sender, foreign room, DM), session save/restore (`state/<name>.json`), the first-sync skip decision; lint green. nio is mocked throughout.

## v1 — Conversation: Gemini replies and three-way turn-taking

The echo becomes a character, and the room becomes a three-way conversation that does not loop. Depends on: v0.

### v1.1 — Gemini replies

**Goal:** each agent replies in its own character, with context.

**Tasks:**
- Replace the echo with an async `google-genai` call:

  ```python
  from google import genai
  from google.genai import types

  client = genai.Client()  # reads GEMINI_API_KEY from the environment
  resp = await client.aio.models.generate_content(
      model="gemini-2.5-flash",
      contents=transcript,  # the last HISTORY_N messages, one "Name: text" per line
      config=types.GenerateContentConfig(
          system_instruction=persona,
          max_output_tokens=400,
          thinking_config=types.ThinkingConfig(thinking_budget=0),  # faster and cheaper for chat
      ),
  )
  reply = resp.text
  ```

- Context: the last `HISTORY_N` (e.g. 30) room messages from `sync`, including the agent's own and the other agent's, plus the instruction «Ти — <name>. Відповідай лише від себе, коротко, без префікса з іменем» ("You are <name>. Reply only on your own behalf, briefly, without a name prefix").
- Persona: 3–5 sentences of character in `<name>.toml`, so the agents differ noticeably (replaced by the canon in v2.1).
- Typing on before the call, off after (in `finally`); send as `m.text`; on failure or empty reply — log and stay silent, never crash.

**DoD:**
- (Manual, owner) Each agent replies in its own character, taking previous lines into account.
- (Manual, owner) While an agent thinks, Element shows "typing…".
- (Manual, owner) Without `GEMINI_API_KEY`, or with an invalid one, the bot stays alive and logs the error.

**Tests:** unit — transcript assembly (`"Name: text"` lines, `HISTORY_N` cap), the empty/failed-reply path (no message sent, no crash), typing reset on failure. Gemini is mocked.

### v1.2 — Three-way conversation and loop protection

**Goal:** one owner message produces a bounded, natural exchange — never an endless bot loop.

The turn-taking rules from ARCHITECTURE §Turn-taking: mentions route to one agent; no mention → both reply after a random 1–`REPLY_DELAY_S` s delay; agent-to-agent replies are gated by `bot_streak < MAX_BOT_TURNS` and probability `BOT_REPLY_P`; `PASS` means silence.

**Tasks:**
- Mention detection (names incl. Ukrainian case forms, and Matrix mentions); route the owner's message accordingly.
- `bot_streak` derived from the shared room timeline; reset on an owner message; no shared state.
- The random delay and `BOT_REPLY_P` coin flip, both injectable for tests.
- Allow `PASS` in the instruction; send nothing when the model returns exactly `PASS`.
- Settings: `MAX_BOT_TURNS`, `BOT_REPLY_P`, `HISTORY_N`, `REPLY_DELAY_S` in `.env` / toml.

**DoD:**
- (Manual, owner) One owner message with no mentions → at most `2 + MAX_BOT_TURNS` agent replies, then silence until the owner writes again.
- (Manual, owner) «Адо, що думаєш?» ("Ada, what do you think?" — the Ukrainian vocative «Адо») — only Ada replies.
- (Manual, owner) The agents refer to each other's lines.
- Unit tests green for the whole who-replies logic.

**Tests:** unit — mention detection (incl. vocative), who-replies for every sender/mention case, `bot_streak` counting and reset from a message sequence, the `MAX_BOT_TURNS`/`BOT_REPLY_P` gate with injected randomness, `PASS` handling with surrounding whitespace.

## v2 — Persona & memory: canons, session memory, world awareness

The agents become people with a stable identity, memory of past conversations, and a sense of place, time and their own days. Depends on: v1.

### v2.1 — Canons and session memory

**Goal:** each agent knows who it is and remembers the last conversation across restarts.

Canons (ARCHITECTURE §Canon) replace the TOML persona; the agents believe they are human. Session memory (ARCHITECTURE §Memory): a rolling first-person summary of the last session, written at session end and injected into the prompt after a restart.

**Tasks:**
- `agents/canon/common.md` + `agents/canon/<name>.md`; the canons describe humans; `canon = "agents/canon/<name>.md"` in the TOML replaces `persona`; missing/empty canon → the bot refuses to start with a clear error.
- Reply-format rules stay in code; no prompt mentions a model or a bot.
- Session end detection (`SESSION_IDLE_S` of silence, or shutdown via SIGINT/SIGTERM with a ~20 s summary timeout); the session timeline kept apart from `HISTORY_N`, capped by `SESSION_MAX_MESSAGES` (early summary + clear).
- The summary call (previous summary + timeline → ≤ `SUMMARY_MAX_WORDS` words, first person, language of the conversation); atomic write to `state/<name>.memory.md`.
- Prompt: canon + «Що ти пам'ятаєш з минулої розмови: <підсумок>» + rules; summary read at startup (first sync still unprocessed).
- Failures: failed summary keeps the previous one; corrupt memory file → start without memory; both logged, never fatal.
- Settings: `SESSION_IDLE_S`, `SESSION_MAX_MESSAGES`, `SUMMARY_MAX_WORDS`.

**DoD:**
- (Manual, owner) «Адо, хто ти?» ("Ada, who are you?") — the answer matches `agents/canon/ada.md` and Ada speaks of herself as a person; Bruno answers per his canon.
- (Manual, owner) Talk about a topic and stop both agents → `state/ada.memory.md` and `state/bruno.memory.md` appear, within the word limit, with no tokens or passwords.
- (Manual, owner) Without stopping: after `SESSION_IDLE_S` of silence the summary updates on its own.
- (Manual, owner) After a restart: «Про що ми говорили минулого разу?» ("What did we talk about last time?") — each agent recalls the topic.
- (Manual, owner) A Gemini failure during summarization leaves the old summary intact and the bot alive.
- Memory files never reach git; message and summary texts are never logged.

**Tests:** unit — prompt assembly (canon + summary + rules, in order), the session-ended decision (idle and shutdown, injected clock), memory file read/write (missing, corrupt, atomic), the timeline cap. Gemini mocked.

### v2.2 — World awareness

**Goal:** the agents know they are in Lviv, know the date and time, and remember their recent days.

Place and calendar in the prompt; auto-generated day memories bounded by the conversation journal (ARCHITECTURE §World awareness, §Memory). Nobody writes memories by hand.

**Tasks:**
- `LOCATION` + `TIMEZONE`; the Ukrainian date/time/part-of-day/season line computed per call from tables in code, clock injected.
- "When we last talked" line from the summary's timestamp.
- The conversation journal: append each session summary with its time to `state/<name>.days/YYYY-MM-DD.talk.md`.
- Day-memory generation: once per past day after local midnight, catch-up at startup (≤ `MEMORY_DAYS` back); inputs canon + that day's date/weekday/season + previous memories + the day's journal; ≤ `DAY_MEMORY_MAX_WORDS` words, atomic write to `state/<name>.days/YYYY-MM-DD.md`; a past day is never rewritten; room facts only from the journal, invention only about the agent and the city.
- Prompt order per ARCHITECTURE §Prompt assembly («Твої спогади за останні дні» before the session summary).
- Failures: a failed day memory is retried later; never fatal.
- Settings: `LOCATION`, `TIMEZONE`, `MEMORY_DAYS`, `DAY_MEMORY_MAX_WORDS`.

**DoD:**
- (Manual, owner) «Котра година?», «Який сьогодні день?» — correct time, date and weekday in Lviv; «Де ти?» — the agent knows it is in Lviv.
- (Manual, owner) After midnight `state/<name>.days/<yesterday>.md` appears; «Що ти робила вчора?» — Ada answers from her memory and mentions yesterday's conversation if there was one.
- (Manual, owner) After 3 days off, memories for the missed days appear at startup (≤ `MEMORY_DAYS`), old files unchanged.
- Invented episodes contain no words or actions of the owner or the other agent that did not happen.
- (Manual, owner) A Gemini failure while generating a memory leaves the bot alive; the day is generated later.

**Tests:** unit — the Ukrainian date/time line (incl. DST switches, injected clock), which days need generating, "a past day is never rewritten", prompt section order, journal appending. Gemini mocked, clock injected.

## v3 — Operations: token accounting, agent images + CI/CD, and the web panel

Running the agents becomes observable and convenient: every model call is counted, the agents ship as one Docker image with CI behind every push, and a local web panel starts, stops and watches everything. Depends on: v2 (the panel shows memory and tokens).

### v3.1 — Token accounting and report

**Goal:** the owner can always see what the conversations cost.

One usage line per Gemini call, and a report command (ARCHITECTURE §Token accounting).

**Tasks:**
- Append the usage line (`ts`, `agent`, `kind`, `model`, `prompt_tokens`, `output_tokens`, `total_tokens`, `ok`) to `state/<name>.usage.jsonl` after every call; `null`s for missing metadata; `ok: false` for failed calls; write errors never block the conversation; no texts ever.
- `agents/usage_report.py` with `--days N`, `--since YYYY-MM-DD`, `--markdown`: the day × agent × kind table with calls, tokens and estimated cost; totals per agent and overall; prices from `.env` only (`PRICE_INPUT_PER_1M`, `PRICE_OUTPUT_PER_1M`), no cost column when unset; corrupt lines skipped with a warning; "no data" when files are missing.

**DoD:**
- (Manual, owner) After a conversation, each agent's `usage.jsonl` holds one line per Gemini call, with tokens and no texts.
- `uv run agents/usage_report.py --days 7` shows calls, tokens and cost by day, agent and kind; the sums match the files.
- The report works with missing files, empty files, and a corrupt line.

**Tests:** unit — `usage_metadata` parsing (incl. missing fields), aggregation, cost calculation, corrupt-line skipping.

### v3.2 — Agent images and CI/CD

**Goal:** the agents run on the Mac as Docker containers built from one image, and every push is linted, tested and built by CI.

One image for both agents (the TOML picks the identity), a Mac compose file with services `ada` and `bruno`, and a GitHub Actions pipeline: the gates on every push/PR, the image published to GHCR on a release tag. A GitHub runner cannot reach the home LAN, so nothing deploys from CI — deploys run from the Mac (`docker compose pull && docker compose up -d` for the agents; the server side stays v0.2's script). See ARCHITECTURE §Deployment and CI/CD.

**Tasks:**
- `agents/Dockerfile`: one image for both agents — python slim + uv, the project installed, entrypoint running `agents/agent.py` with the TOML given per container; `TZ` set from `TIMEZONE`.
- `compose.yml` at the repo root: services `ada` and `bruno` from the same image; `env_file: .env` (marked `required: false`, so the config gate passes without a local `.env`); `./state` bind-mounted so memory, usage and logs stay host-side files (the v3.1 report and the v3.3 panel keep reading them); `restart: unless-stopped`.
- Stop semantics: `docker stop -t 30` sends SIGTERM → the v2.1 shutdown summary runs before SIGKILL.
- Logs still land in `state/logs/<name>.log` (via the mount) as well as `docker logs`.
- `.github/workflows/ci.yml`: on every push/PR — ruff, pytest (nio/Gemini mocked; no paid APIs, no secrets in CI), both compose config gates, and the image build. On a `vA.B.C` tag — push the image to GHCR (`ghcr.io/<owner>/matrix-agora-agent`, tagged with the version and `latest`) using only `GITHUB_TOKEN`.
- README: the Mac deploy commands (`docker compose pull && docker compose up -d`); terminal mode `uv run agents/agent.py …` keeps working for development.

**DoD:**
- (Manual, owner) `docker compose up -d` on the Mac starts both agents from the image; they join the room and reply; the `state/` files appear on the host as before.
- (Manual, owner) `docker stop -t 30 ada` → Ada's session summary is written before the container exits.
- CI is green on a push: lint, tests, both compose gates, image build; no paid API keys exist in CI.
- (Manual, owner) Pushing a `vA.B.C` tag publishes the image to GHCR.
- The image contains no secrets; `.env` and `state/` come only from the host.

**Tests:** CI runs the existing gates unchanged (everything mocked); the image build and the compose config gates are the new checks — the pipeline itself is configuration, not unit-tested code.

### v3.3 — Web panel on the Mac

**Goal:** agents are started, stopped and observed from one local page instead of two terminals and raw files.

The panel from ARCHITECTURE §Web panel: `aiohttp.web` on `127.0.0.1:8090`, one vanilla-JS page, Ukrainian UI. Supervision of the v3.2 agent containers (start/stop/restart, single-instance lock, logs), views (memory, canons, tokens, settings, server health) and the panel security rules.

**Tasks:**
- `panel/app.py` + `panel/static/index.html`; bind `127.0.0.1` (`PANEL_PORT`); `Host` check on every request; mutating actions `POST`-only with the panel's `Origin`; no CORS.
- The supervisor drives the v3.2 containers: Start = `docker compose up -d <name>`, Stop = `docker stop -t 30 <name>` (SIGTERM → the v2.1 shutdown summary, SIGKILL after the grace period); agent names from a fixed list. It also detects terminal-started (`uv run`) agents via the lock file and can stop them by verified PID.
- The single-instance `flock` on `state/<name>.lock` (in the agent), with the PID inside.
- Agent file logging: `state/logs/<name>.log`, rotating 1 MB × 3, alongside the console; the panel tails 200 lines, refresh 2 s.
- Views: homeserver health (30 s), session summary + day memories per agent, canons read-only, the 7-day token table (shared aggregation code), masked settings.
- «Забути останню сесію» ("Forget the last session"): deletes `state/<name>.memory.md`, confirmation required, stopped agents only.

**DoD:**
- (Manual, owner) `uv run panel/app.py` → `http://127.0.0.1:8090` shows both agents with state; unreachable from another device.
- (Manual, owner) Start/Stop/Restart work; after Stop a fresh session summary exists.
- A second instance of an agent refuses to start, from the panel or a terminal.
- (Manual, owner) A terminal-started agent shows as running; closing the panel stops nothing.
- (Manual, owner) Logs visible and refreshing, with no tokens, passwords or message texts.
- (Manual, owner) Homeserver container stopped → red indicator.
- "Forget" works only for a stopped agent, after confirmation.
- The token table matches `usage_report.py --days 7`; secrets are masked; foreign `Origin`/`Host` requests are refused.

**Tests:** unit — the supervisor against a fake docker client and fake processes (start, stop, timeout → kill), the single-instance lock, secret masking, `Host`/`Origin` checks; the API handlers via the aiohttp test client.
