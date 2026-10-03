# Roadmap — matrix-agora

Four self-contained versions, built in order: **v0** Platform (homeserver, server deploy, client, accounts, echo bot) → **v1** Conversation (Gemini replies, three-way turn-taking) → **v2** Persona & memory (canons, session memory, world awareness) → **v3** Operations (token accounting, agent images + CI/CD with server deployment, the panel). Phases inside a version are numbered `vA.B` (A = version, B = phase). Each phase lists a **Goal**, a short description, a **Tasks** list, a **Definition of Done (DoD)**, and the **Tests** that encode its DoD (see [ARCHITECTURE.md](ARCHITECTURE.md) §Testing and CI). Phases are built strictly in file order; each one builds on the previous one's real, released code.

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
      # pinned by digest (Continuwuity 26.9.1); upgrades are a conscious edit, never an implicit pull.
      # mirror, if the main registry is unavailable: ghcr.io/continuwuity/continuwuity
      image: forgejo.ellis.link/continuwuation/continuwuity@sha256:c9c62bc5c0a641f3f713945c701b069c7bc30d2612b54d4a5de80a5be19d5420
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
- Element → Create account → **Edit** homeserver → `http://192.168.1.197:8008` → register the owner's username (`ich`). **The first account needs Continuwuity's one-time bootstrap token from the container logs** (`docker compose logs homeserver` on the host), not the configured `REGISTRATION_TOKEN` — that one starts working from the second account on (the bots, v0.4). The first account automatically becomes the admin and is invited to the admin room.

**DoD** (Manual, owner):
- Logged in as `@ich:agora.lan` and can see the admin room.

**Tests:** none (owner steps only).

### v0.4 — Bot accounts and the room

**Goal:** the agents' accounts exist, the room is ready, and the server is closed.

**Tasks:**
- Create the accounts `ada` and `bruno` — via token registration (log out/in in Element, or `curl` to `/_matrix/client/v3/register`), or with an admin-room command (`!admin users create-user ada`).
- **Close registration:** set `CONTINUWUITY_ALLOW_REGISTRATION: "false"` in the repo's `server/docker-compose.yml` and apply it with `server/deploy.sh` (v0.2). From now on only the admin creates accounts.
- In Element create the room **"Agora"**: private (invite-only), encryption disabled (forbidden on the server anyway). Invite `@ada:agora.lan` and `@bruno:agora.lan`.
- Record the room's `room_id` (Room settings → Advanced). It is an opaque MSC-style id with **no server suffix** (e.g. `!U2jJ…`), not `!xxxx:agora.lan`.

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
- (Manual, owner) A message in "Agora" → both bots reply with the echo.
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

The turn-taking rules from ARCHITECTURE §Turn-taking: mentions route to one agent; no mention → both reply after a random 1–`REPLY_DELAY_S` s delay; agent-to-agent replies are gated by `bot_streak < MAX_BOT_TURNS` and probability `BOT_REPLY_P` (skipped when the other agent addresses this one by name — v1.2.1); since v1.2.2 the streak counts only turns within `BOT_WINDOW_S`, and a blocked reply resumes once the window frees; `PASS` means silence.

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

### v2.2 — World awareness and a life story

**Goal:** the agents live a life: they know where and when they are, remember their past and their recent days, carry plans for the days ahead, and know what today has already held and what is still ahead — all grounded in a written life story from birth to death.

Each agent has a **life story** (`agents/canon/<name>.life.md`, dated chapters from birth to death). The past and the current chapter are what the agent remembers and lives; future chapters steer plans silently and the agent never knows its future. **Memories follow the story** — generated from it with new concrete details, never copied. **Plans deviate from it** — generated with mutations, the way people plan things that don't happen. Place and calendar in the prompt; the conversation journal stays the only source of room facts (ARCHITECTURE §Canon, §Memory, §World awareness).

**Tasks:**
- Life stories for both agents (written; consistent where their lives cross; no invented history with the owner); `life = …` in the TOML; a parser for the header and `## YYYY–YYYY · title` chapters; the current chapter selected by today's date.
- The prompt section «Твоє життя досі»: past chapters' opening paragraphs + the current chapter in full — **never** future chapters or the death date.
- `LOCATION` + `TIMEZONE`; the Ukrainian date/time/part-of-day/season line per call from tables in code, clock injected; the "when we last talked" line.
- The conversation journal: each session summary appended with its time to `state/<name>.days/YYYY-MM-DD.talk.md`.
- **Plans with mutations on four horizons** (`state/<name>.plans/`): year intentions (1 January), month plan (the 1st), week plan (Monday), day plan (midnight); each finer plan from the coarser ones + the current chapter + the next chapter as hidden direction + the story's open threads + carry-overs; each item mutated with probability `PLAN_MUTATION_RATE` (injected rng: spontaneous idea / changed place / postponed / cancelled / new whim); mutation tags stored as hidden metadata, never in a conversational prompt; never rewritten after their period.
- **Day memories that follow the story:** after midnight (the watcher; catch-up at startup, never before the agent's first run, ≤ `MEMORY_DAYS` back): frame from the current chapter, concrete new details of that day, room facts only from the journal, the plan resolved against reality («хотіла…, але…»); a memory copying 8+ words of the story verbatim is regenerated once; never rewritten.
- **Memory digests — keep everything, compress the old:** day memories, journals and plans are never deleted; after each week, month and year the watcher writes a first-person digest from the finer layer (`weeks/`, `months/`, `years/`), generated not copied, never rewritten, caught up at startup (never before the first run).
- The prompt's «Твої спогади» in nested layers with no gaps: all years → the last `MEMORY_MONTHS` months → the last `MEMORY_WEEKS` weeks → the last `MEMORY_DAYS` days, each labeled with its period.
- The hourly today block: «Сьогодні вже…» from reality (chapter + journal), «Ще сьогодні…» from the mutated plan; at most one call per hour; reset at midnight.
- **Context survives a restart:** after the first sync, fetch the last `HISTORY_N` messages of the room once and seed the context window and the `bot_streak` timeline — no replies to them, not added to the session timeline.
- Prompt order per ARCHITECTURE §Prompt assembly.
- Failures keep the previous file or block; never fatal. Settings: `LOCATION`, `TIMEZONE`, `MEMORY_DAYS`, `MEMORY_WEEKS`, `MEMORY_MONTHS`, `DAY_MEMORY_MAX_WORDS`, `WEEK_MEMORY_MAX_WORDS`, `MONTH_MEMORY_MAX_WORDS`, `YEAR_MEMORY_MAX_WORDS`, `PLAN_MAX_WORDS`, `TODAY_MAX_WORDS`, `PLAN_MUTATION_RATE`.

**DoD:**
- (Manual, owner) «Адо, де ти навчалась?», «Бруно, як ви з Адою познайомились?» — answers consistent with the life stories, told in the agents' own words.
- (Manual, owner) Nobody ever mentions their future or their death, even when asked «Що буде з тобою через десять років?» — they answer with hopes, not facts.
- (Manual, owner) «Котра година?», «Який сьогодні день?», «Де ти?» — correct Lviv time, date and place.
- (Manual, owner) The day plan has a couple of items off the story; the next day's memory follows the story and resolves those items («хотіла…, але…»), with concrete details the story doesn't contain.
- (Manual, owner) Asking «Що ти вже зробила сьогодні?» in the morning and in the evening gives different, time-appropriate answers without a restart.
- (Manual, owner) «Які в тебе плани на цей місяць?», «Чого хочеш цього року?» — answers from the month plan and year intentions, consistent with the life story's open threads; the agent never says which plans "won't work out".
- After a week has passed, `state/<name>.weeks/<monday>.md` exists and «Що було минулого тижня?» is answered from it; day files stay in place.
- (Manual, owner) Restart the agents mid-conversation, then ask «Про що ми щойно говорили?» — they answer from the seeded context; nobody replies to the old messages after the restart.
- Past memories, digests and plans are never rewritten or deleted; failures keep the previous files; the bot stays alive.

**Tests:** unit — life-story parsing and current-chapter selection by date (incl. year boundaries); the visibility rule (no future chapter text and no death date ever in the conversational prompt); plan mutations with injected rng (rate edges 0 and 1, which items are bent) on all four horizons; mutation tags never in a conversational prompt; which plan periods are due (year/month/week/day boundaries); the verbatim-copy detector (8-word spans); the Ukrainian date/time line (incl. DST, injected clock); which days and plan periods need generating (never before the first run); the restart backfill (chronological order, only `ROOM_ID`, capped at `HISTORY_N`, no sends, not in the session timeline, streak timeline seeded); the hourly today-refresh decision; digest periods due (week/month/year boundaries, catch-up, never before the first run); the layered memory selection (nested, no gaps, oldest and coarsest first, window sizes); "past memories, digests and plans are never rewritten"; prompt section order. Gemini mocked, clock and rng injected.

## v3 — Operations: token accounting, server deployment, and the panel

Running the system becomes one operations surface: every model call is counted; the agents ship as one image and move to the Ubuntu server, **each as its own container**; and the panel — the point of the whole project — manages the first simulation (the chat) and the agents connected to it. Depends on: v2 (the panel shows memory and tokens).

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

### v3.2 — Agent images, CI/CD and server deployment

**Goal:** each agent runs on the Ubuntu server as its own Docker container, built from one image by CI.

One image for both agents; **one compose service per agent** (`ada`, `bruno`) joins `server/docker-compose.yml`; `state/` becomes a server-side directory. `server/deploy.sh` (v0.2) now deploys the whole stack, pulling images from GHCR. A GitHub runner cannot reach the LAN, so CI never deploys — the deploy always runs from the Mac. Dev mode on the Mac (`uv run`, local `state/`) remains. See ARCHITECTURE §Deployment and CI/CD.

**Tasks:**
- `agents/Dockerfile`: python slim + uv, entrypoint `agents/agent.py <toml>`; `TZ` from `TIMEZONE`.
- `server/docker-compose.yml` gains `ada` and `bruno` — the same image (`ghcr.io/<owner>/matrix-agora-agent`), one container per agent: env from `server/.env` (which now also carries `GEMINI_API_KEY` and the agent settings), `~/matrix-agora/state` bind-mounted, `restart: unless-stopped`. On the server the agents reach the homeserver over the compose network (`HOMESERVER=http://homeserver:8008`); the LAN URL stays for dev mode.
- Stop semantics: `docker stop -t 30` → SIGTERM → the v2.1 shutdown summary → SIGKILL after the grace period.
- The single-instance `flock` on `state/<name>.lock` (PID inside) and file logging to `state/logs/<name>.log` (rotating, 1 MB × 3) land here: a second instance refuses to start, and the v3.3 panel has logs to tail.
- `server/deploy.sh`: add `docker compose pull` before `up -d`.
- `.github/workflows/ci.yml`: ruff, pytest (nio/Gemini mocked; no paid APIs, no secrets in CI), the compose gate, the image build on every push/PR; on a `vA.B.C` tag — push to GHCR using only `GITHUB_TOKEN`.

**DoD:**
- (Manual, owner) After `server/deploy.sh`, both agent containers run on the server, join the room and reply; `~/matrix-agora/state/` fills in on the server.
- (Manual, owner) `docker stop -t 30 ada` on the server → Ada's session summary is written before the container exits.
- CI is green on a push: lint, tests, the compose gate, the image build; no paid API keys exist in CI.
- (Manual, owner) Pushing a `vA.B.C` tag publishes the image to GHCR.
- The image holds no secrets; env and `state/` come only from the host.
- (Manual, owner) Dev mode on the Mac still works against the same homeserver.

**Tests:** CI runs the existing gates unchanged; the image build and the compose gate are the new checks — the pipeline itself is configuration. Unit — the single-instance lock.

### v3.3 — The panel: simulations and agents

**Goal:** one page, served from the server, runs everything — the chat simulation and the agents connected to it — and the model is ready for more simulations later.

The panel is the point of the whole project (VISION §The direction): a FastAPI backend plus one static vanilla-JS page (Ukrainian), the `panel` service in `server/docker-compose.yml` (port 8090, `/var/run/docker.sock` and the `state/` directory mounted), deployed by `server/deploy.sh`, Bearer `PANEL_TOKEN` on every API call. Internally everything is written against a **simulation registry** — maintenance, monitoring and deployment code never mentions "the chat"; the PoC registry holds exactly one entry (`agora`, kind `matrix-chat`) and this roadmap adds no second one. Depends on: v3.2 and v0.2.

**Tasks:**
- `fastapi` + `uvicorn` join the project dependencies; `panel/app.py` + `panel/static/index.html` + `panel/Dockerfile`; the `panel` service in the server compose; ufw allows `:8090` from `192.168.1.0/24` only.
- The model and registry: `Simulation{id, kind, title, services, health, endpoints}` and `Agent{name, container, canon, simulation}`; `agents/<name>.toml` gains `simulation = "agora"`, from which the agent's `HOMESERVER`/`ROOM_ID` resolve.
- API (JSON, `Authorization: Bearer` on every route): `GET /health` (+ host basics), `GET /simulations`, `GET /simulations/{id}` (health probe + per-service container state), `POST /simulations/{id}/start|stop|restart`, `GET /simulations/{id}/logs?service=…&tail=200`; `GET /agents`, `POST /agents/{name}/start|stop|restart`, `GET /agents/{name}/logs|memory`, `POST /agents/{name}/forget`, `GET /usage?days=7`.
- **The panel launches the agent containers**: start = `docker compose up -d <name>` (creates the container when it does not exist yet); stop = `docker stop -t 30` so the session summary runs; names resolve only through the registry and the fixed agent list (unknown → 404; no request data in paths, argv or the docker API).
- UI cards: the simulation (health, services, logs, start/stop/restart), the agents (state, logs, memory/plans/today, forget, the token table), the host (uptime, disk, memory from `/proc` and a read-only host mount).
- Confirmations for every stop/restart and forget; mutating actions are `POST` + token.
- CI builds and publishes the panel image (`…-panel`) alongside the agent image.
- Degrade by card: docker trouble greys the container cards, an unreadable `state/` greys the memory views; a stopped homeserver never crashes the agents (nio retries).

**DoD:**
- (Manual, owner) `http://192.168.1.197:8090` with the token: the chat simulation and both agents show live state; without the token every API call is 401 and the page shows nothing.
- (Manual, owner) Agent start/stop/restart from the panel work — including the first launch of a container that does not exist yet; after a stop the session summary exists.
- (Manual, owner) Homeserver stop from the panel → red health, the agents keep retrying; start → everything recovers on its own.
- (Manual, owner) Homeserver and agent log tails are readable; memory/plans/today visible; the token table matches `usage_report.py --days 7`; host metrics shown.
- "Forget" works only for a stopped agent, after confirmation; unknown simulation/agent/service names are refused.
- (Manual, owner) The panel is unreachable from outside the LAN; `server/deploy.sh` deploys it together with the rest of the stack.
- The registry holds the single `agora` entry, and the panel resolves everything through it.

**Tests:** unit — the Bearer-token gate (401), registry resolution (unknown simulation/agent/service → 404), the supervisor against a fake docker client (start, stop, timeout → kill; container creation on first start), forget gating, confirmation gating, host-metrics parsing from canned `/proc` files; the routes via FastAPI's `TestClient`. No real docker and no network in tests.
