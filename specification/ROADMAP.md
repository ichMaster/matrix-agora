# Roadmap — matrix-agora

Nine self-contained versions, built in order: **v0** Platform (homeserver, server deploy, client, accounts, echo bot) → **v1** Conversation (Gemini replies, three-way turn-taking) → **v2** Persona & memory (canons, session memory, world awareness) → **v3** Operations (token accounting, agent images + CI/CD with server deployment, the panel — viewing, then control) → **v4** Ensemble (agent types and N-agent turn-taking; then the cat and Claude, each in two steps; the personas' curiosity; the agents' settings in the panel) → **v5** Voice (Hermes's voice digests for the owner; the agents hear voice messages, then answer in voice; Кіра's private chat, in Telegram too, and her memory of messages and facts) → **v6** Applications (the panel's System and Applications; Telegram as an application) → **v7** Theatre (plays on the Stage, recorded by Hermes) → **v8** Лілі (the Lumi bridge: when named, then under the full rules). Phases inside a version are numbered `vA.B` (A = version, B = phase). Each phase lists a **Goal**, a short description, a **Tasks** list, a **Definition of Done (DoD)**, and the **Tests** that encode its DoD (see [ARCHITECTURE.md](ARCHITECTURE.md) §Testing and CI). Phases are built strictly in file order; each one builds on the previous one's real, released code.

**Versioning (`A.B.C`).** `A` = roadmap version (v0→0 … v8→8), `B` = phase within it, `C` = a post-release fix on that phase. Roadmap phase `vA.B` → release `A.B.0`, tag `vA.B.0`; a fix after it bumps `C`. Releases are cut per phase. Never bump a version without explicit confirmation.

Many DoD items need the live homeserver, Element or a real Gemini key — those are **Manual (owner)** checks: the owner performs or confirms them, and only then do they count as passed. Everything automated runs with `matrix-nio` and `google-genai` mocked and the clock injected (no network, no paid calls).

---

## Status

v0–v3 are complete — delivered through `v3.4.0` (2026-10-04). **v4 has begun** — v4.1 released as `v4.1.0`, v4.2 as `v4.2.0`, v4.3 as `v4.3.0` (all 2026-10-10), v4.4 as `v4.4.0` (2026-10-11); its design is the draft
[features/more-agents.md](features/more-agents.md), whose open questions are closed before each v4 phase's issues
are generated. Other further work (the deferred backlog items in the code-review docs, new simulations) needs new phases.

| Phase | Title | Status | Release |
|---|---|---|---|
| v0.1 | Homeserver (Ubuntu, 192.168.1.197) | ✅ completed | `v0.1.0` (2026-10-02) |
| v0.2 | Server deploy from the repo | ✅ completed | `v0.2.0` (2026-10-02) |
| v0.3 | Client (Element Desktop on the Mac) | ✅ completed | `v0.3.0` (2026-10-02) |
| v0.4 | Bot accounts and the room | ✅ completed | `v0.4.0` (2026-10-02) |
| v0.5 | Echo bot (Matrix without the LLM) | ✅ completed | `v0.5.0` (2026-10-02) |
| v1.1 | Gemini replies | ✅ completed | `v1.1.0` (2026-10-02) |
| v1.2 | Three-way conversation and loop protection | ✅ completed | `v1.2.0` (2026-10-02) + `v1.2.1`, `v1.2.2` |
| v2.1 | Canons and session memory | ✅ completed | `v2.1.0` (2026-10-03) |
| v2.2 | World awareness and a life story | ✅ completed | `v2.2.0` (2026-10-03) + `v2.2.1` |
| v3.1 | Token accounting and report | ✅ completed | `v3.1.0` (2026-10-03) + `v3.1.1` |
| v3.2 | Agent images, CI/CD and server deployment | ✅ completed | `v3.2.0` (2026-10-04) |
| v3.3 | The panel: viewing (read-only) | ✅ completed | `v3.3.0` (2026-10-04) |
| v3.4 | The panel: control | ✅ completed | `v3.4.0` (2026-10-04) + `v3.4.1` |
| v4.1 | Roster, agent types and N-agent turn-taking | ✅ completed | `v4.1.0` (2026-10-10) |
| v4.2 | The cat in the room | ✅ completed | `v4.2.0` (2026-10-10) |
| v4.3 | The cat: his past life and his initiative | ✅ completed | `v4.3.0` (2026-10-10) |
| v4.4 | Claude on the subscription: answering when asked | ✅ completed | `v4.4.0` (2026-10-11) |
| v4.5 | Claude the philosopher | ✅ completed | `v4.5.0` (2026-10-11) |
| v4.6 | Ada and Bruno: curiosity, plans and stories | ✅ completed | `v4.6.0` (2026-10-11) |
| v4.7 | Agent settings and Claude's files in the panel | ✅ completed | `v4.7.0` (2026-10-11) |
| v5.1 | Hermes: voice digests for the owner | ⏳ planned | — |
| v5.2 | The agents hear voice messages | ⏳ planned | — |
| v5.3 | The agents answer in voice | ⏳ planned | — |
| v6.1 | System and Applications: the panel's new shape | ⏳ planned | — |
| v6.2 | Telegram as an application: Кіра connected | ⏳ planned | — |
| v7.x | Theatre: plays on the Stage (phases from features/radio-theatre.md) | ⏳ planned | — |
| v8.1 | The Lumi bridge: Лілі when named | ⏳ planned | — |
| v8.2 | Лілі under the full rules | ⏳ planned | — |

## v0 — Platform: homeserver, server deploy, client, accounts, echo bot

The working skeleton with no LLM: the Continuwuity homeserver in Docker on the Ubuntu box, a scripted deploy of the repo's server config to that box, Element Desktop as the owner's client, the bot accounts and the private room, and an echo bot that proves the whole Matrix side — login and session reuse, invites, the first-sync rule, the message filter and allowlist. v0.1, v0.3 and v0.4 are mostly steps the owner performs on the host and in Element; v0.2 is the first script, v0.5 the first real code. Depends on: nothing — this is the foundation.

### v0.1 — Homeserver (Ubuntu, 192.168.1.197)

**Status:** ✅ completed — released `v0.1.0` on 2026-10-02.

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

**Status:** ✅ completed — released `v0.2.0` on 2026-10-02.

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

**Status:** ✅ completed — released `v0.3.0` on 2026-10-02.

**Goal:** the owner is logged in to the homeserver as its admin.

**Tasks:**
- `brew install --cask element`.
- Element → Create account → **Edit** homeserver → `http://192.168.1.197:8008` → register the owner's username (`ich`). **The first account needs Continuwuity's one-time bootstrap token from the container logs** (`docker compose logs homeserver` on the host), not the configured `REGISTRATION_TOKEN` — that one starts working from the second account on (the bots, v0.4). The first account automatically becomes the admin and is invited to the admin room.

**DoD** (Manual, owner):
- Logged in as `@ich:agora.lan` and can see the admin room.

**Tests:** none (owner steps only).

### v0.4 — Bot accounts and the room

**Status:** ✅ completed — released `v0.4.0` on 2026-10-02.

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

**Status:** ✅ completed — released `v0.5.0` on 2026-10-02.

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

**Status:** ✅ completed — released `v1.1.0` on 2026-10-02.

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

**Status:** ✅ completed — released `v1.2.0` on 2026-10-02 · patches `v1.2.1`, `v1.2.2`.

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

**Status:** ✅ completed — released `v2.1.0` on 2026-10-03.

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

**Status:** ✅ completed — released `v2.2.0` on 2026-10-03 · patches `v2.2.1`.

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

**Status:** ✅ completed — released `v3.1.0` on 2026-10-03 · patches `v3.1.1`.

**Goal:** the owner can always see what the conversations cost.

One usage line per Gemini call, and a report command (ARCHITECTURE §Token accounting).

**Tasks:**
- Append the usage line (`ts`, `agent`, `kind`, `model`, `prompt_tokens`, `output_tokens`, `total_tokens`, `ok`) to `state/<name>.usage.jsonl` after every call; `null`s for missing metadata; `ok: false` for failed calls; write errors never block the conversation; no texts ever.
- `agents/usage_report.py` with `--days N`, `--since YYYY-MM-DD`, `--markdown`: the day × agent × kind table with calls, tokens and estimated cost; totals per agent and overall; prices from `.env` only (`PRICE_INPUT_PER_1M`, `PRICE_OUTPUT_PER_1M`), no cost column when unset; corrupt lines skipped with a warning; "no data" when files are missing.
- (v3.1.1) The daily report: `usage_report.py --write` → `reports/usage/YYYY-MM-DD.md` + `latest.md` with statistics (yesterday by agent and kind with the change from the day before, the last 7 days, the month so far with a projection, today so far); scheduled daily at 07:00 on the Mac by a launchd job (`scripts/install-usage-daily.sh`).

**DoD:**
- (Manual, owner) After a conversation, each agent's `usage.jsonl` holds one line per Gemini call, with tokens and no texts.
- `uv run agents/usage_report.py --days 7` shows calls, tokens and cost by day, agent and kind; the sums match the files.
- The report works with missing files, empty files, and a corrupt line.

**Tests:** unit — `usage_metadata` parsing (incl. missing fields), aggregation, cost calculation, corrupt-line skipping.

### v3.2 — Agent images, CI/CD and server deployment

**Status:** ✅ completed — released `v3.2.0` on 2026-10-04.

**Goal:** each agent runs on the Ubuntu server as its own Docker container, built from one image by CI.

One image for both agents; **one compose service per agent** (`ada`, `bruno`) joins `server/docker-compose.yml`; `state/` becomes a server-side directory. `server/deploy.sh` (v0.2) now deploys the whole stack, pulling images from GHCR. A GitHub runner cannot reach the LAN, so CI never deploys — the deploy always runs from the Mac. Dev mode on the Mac (`uv run`, local `state/`) remains. See ARCHITECTURE §Deployment and CI/CD.

**Tasks:**
- `agents/Dockerfile`: python slim + uv, entrypoint `agents/agent.py <toml>`; `TZ` from `TIMEZONE`.
- `server/docker-compose.yml` gains `ada` and `bruno` — the same image (`ghcr.io/<owner>/matrix-agora-agent`), one container per agent: env from `server/.env` (which now also carries `GEMINI_API_KEY` and the agent settings), `~/matrix-agora/state` bind-mounted, `restart: unless-stopped`. On the server the agents reach the homeserver over the compose network (`HOMESERVER=http://homeserver:8008`); the LAN URL stays for dev mode.
- Stop semantics: `docker stop -t 30` → SIGTERM → the v2.1 shutdown summary → SIGKILL after the grace period.
- The single-instance `flock` on `state/<name>.lock` (PID inside) and file logging to `state/logs/<name>.log` (rotating, 1 MB × 3) land here: a second instance refuses to start, and the v3.3 panel has logs to tail.
- `server/deploy.sh`: add `docker compose pull` before `up -d`.
- The daily token report (v3.1.1) moves to the server with `state/`: a daily job there writes `~/matrix-agora/reports/usage/`; the Mac's launchd job is uninstalled (`scripts/install-usage-daily.sh --uninstall`).
- `.github/workflows/ci.yml`: ruff, pytest (nio/Gemini mocked; no paid APIs, no secrets in CI), the compose gate, the image build on every push/PR; on a `vA.B.C` tag — push to GHCR using only `GITHUB_TOKEN`.

**DoD:**
- (Manual, owner) After `server/deploy.sh`, both agent containers run on the server, join the room and reply; `~/matrix-agora/state/` fills in on the server.
- (Manual, owner) `docker stop -t 30 ada` on the server → Ada's session summary is written before the container exits.
- CI is green on a push: lint, tests, the compose gate, the image build; no paid API keys exist in CI.
- (Manual, owner) Pushing a `vA.B.C` tag publishes the image to GHCR.
- The image holds no secrets; env and `state/` come only from the host.
- (Manual, owner) Dev mode on the Mac still works against the same homeserver.

**Tests:** CI runs the existing gates unchanged; the image build and the compose gate are the new checks — the pipeline itself is configuration. Unit — the single-instance lock.

### v3.3 — The panel: viewing (read-only)

**Status:** ✅ completed — released `v3.3.0` on 2026-10-04.

**Goal:** one page, served from the server, shows everything — the chat simulation, the agents connected to it, their memory and spend, and the host — built on a simulation registry that is ready for more simulations later. Nothing on the page changes anything yet.

The panel is the point of the whole project (VISION §The direction): a FastAPI backend plus one static vanilla-JS page — **English UI** (the agents' own texts — summaries, memories, plans, the today block — shown as-is, in Ukrainian), built to the Claude Design handoff in [`specification/design/design_handoff_agora_panel/`](design/design_handoff_agora_panel/README.md) — the `panel` service in `server/docker-compose.yml` (port 8090, `/var/run/docker.sock`, the `state/` directory and a read-only host mount), deployed by `server/deploy.sh`, Bearer `PANEL_TOKEN` on every API call. Internally everything is written against a **simulation registry** — monitoring code never mentions "the chat"; the PoC registry holds exactly one entry (`agora`, kind `matrix-chat`) and this roadmap adds no second one. In this phase the docker socket is used only for reads (container state, log tails); the actions come in v3.4. Depends on: v3.2 and v0.2.

**Tasks:**
- `fastapi` + `uvicorn` join the project dependencies; `panel/app.py` + `panel/static/index.html` + `panel/Dockerfile`; the `panel` service in the server compose; ufw allows `:8090` from `192.168.1.0/24` only.
- The model and registry: `Simulation{id, kind, title, services, health, endpoints}` and `Agent{name, container, canon, simulation}`; `agents/<name>.toml` gains `simulation = "agora"`, from which the agent's `HOMESERVER`/`ROOM_ID` resolve.
- Read-only API (JSON, `Authorization: Bearer` on every route): `GET /health` (+ host basics), `GET /simulations`, `GET /simulations/{id}` (health probe + per-service container state), `GET /simulations/{id}/logs?service=…&tail=200`; `GET /agents`, `GET /agents/{name}` (container state and uptime), `GET /agents/{name}/logs|memory`, `GET /usage?days=7`. Names resolve only through the registry and the fixed agent list (unknown → 404; no request data in paths, argv or the docker API).
- UI cards, view-only, to the handoff (dark default + light, 1440 and the 760 px breakpoint; system fonts, icons inline — no outside requests). The panel shows only what is already recorded — container state from docker, the files in `state/`, the logs; the handoff's live fields that nothing records (last activity, the current activity, session size, reconnect attempts) are left out: the simulation (health, services, log tails), the agents (state, logs, session summary, day memories, plans, the today block, the 7-day token table), the host (uptime, disk, memory from `/proc` and the read-only host mount).
- Degrade by card: docker trouble greys the container cards, an unreadable `state/` greys the memory views.
- CI builds and publishes the panel image (`…-panel`) alongside the agent image.

**DoD:**
- (Manual, owner) `http://192.168.1.197:8090` with the token: the chat simulation and both agents show live state; without the token every API call is 401 and the page shows nothing.
- (Manual, owner) Homeserver and agent log tails are readable; memory/plans/today visible; the token table matches `usage_report.py --days 7`; host metrics shown.
- Unknown simulation/agent/service names are refused (404); no route mutates anything.
- (Manual, owner) The panel is unreachable from outside the LAN; `server/deploy.sh` deploys it together with the rest of the stack.
- The registry holds the single `agora` entry, and the panel resolves everything through it.

**Tests:** unit — the Bearer-token gate (401), registry resolution (unknown simulation/agent/service → 404), the read side of the supervisor against a fake docker client (state, log tail), host-metrics parsing from canned `/proc` files, the memory views with a missing or unreadable `state/`; the routes via FastAPI's `TestClient`. No real docker and no network in tests.

### v3.4 — The panel: control

**Status:** ✅ completed — released `v3.4.0` on 2026-10-04 · patches `v3.4.1`.

**Goal:** the panel runs everything it shows — the agents and the simulation's services start, stop and restart from the page, safely.

Builds on the reviewed v3.3 panel. The docker socket now performs actions, so every action is a `POST` + token, confirmed in the UI, and resolved only through the registry. Depends on: v3.3.

**Tasks:**
- API: `POST /simulations/{id}/start|stop|restart` (per service of the registry entry), `POST /agents/{name}/start|stop|restart`, `POST /agents/{name}/forget`.
- **The panel launches the agent containers**: start = `docker compose up -d <name>` (creates the container when it does not exist yet); stop = `docker stop -t 30` so the session summary runs; restart = stop + start. The panel manages containers only; it does not detect agents started outside it (dev mode on the Mac: stop the server's agent first).
- "Forget the last session" deletes `state/<name>.memory.md` — stopped agents only, after confirmation.
- UI: action buttons on the simulation and agent cards, a confirmation for every stop/restart and forget, progress and result per action.
- A stopped homeserver never crashes the agents (nio retries); the panel shows red health and recovers on its own after a start.

**DoD:**
- (Manual, owner) Agent start/stop/restart from the panel work — including the first launch of a container that does not exist yet; after a stop the session summary exists.
- (Manual, owner) Homeserver stop from the panel → red health, the agents keep retrying; start → everything recovers on its own.
- "Forget" works only for a stopped agent, after confirmation; unknown simulation/agent/service names are refused.

**Tests:** unit — the supervisor's actions against a fake docker client (start, stop, timeout → kill; container creation on first start), forget gating, confirmation gating, every mutating route `POST`-only and token-gated; the routes via FastAPI's `TestClient`. No real docker and no network in tests.

## v4 — Ensemble: agent types, N-agent turn-taking, the cat, Claude and the panel's settings

The room grows from two Gemini personas to four agents of three types (from v4.6 the personas grow curious; from v4.7 the agents' settings move into the panel): Ada and Bruno (`persona`), the cat Кіт (`creature`) and Claude (`assistant`); Lumi (`bridge`) joins in v8. The newcomers are openly non-human; Ada and Bruno keep believing they are human. One owner message must stay a few short replies, not two pages. The full design, its decisions and its open questions live in [features/more-agents.md](features/more-agents.md) (draft); each phase lands its ARCHITECTURE and VISION changes and the tests that pin them, per that document's contract list. Depends on: v3 (the images, compose, the panel).

### v4.1 — Roster, agent types and N-agent turn-taking

**Status:** ✅ completed — released `v4.1.0` on 2026-10-10.

**Goal:** the agents come from a roster, each with a type that switches its capabilities, and one owner message gets a small, bounded number of answers whatever the number of agents.

Still with Ada and Bruno only; this alone ends today's long threads. Design: more-agents.md §1–§5.

**Tasks:**
- Agent TOML gains `type`, `engine`, `name_forms`, `[capabilities]`, `[turns]` (`mode`, `weight`); `canon` and `life` become optional by type; startup, `build_prompt`, `ensure_today`, `ensure_plans`, the chronicle and the summaries are gated by capability.
- The roster from `simulations.toml` + the listed TOMLs replaces `OTHER`, the hard-coded names and `NAME_FORMS`; the allowlist becomes `{OWNER} ∪ roster − self`; `scripts/run-agent.sh` reads the roster.
- The `Responder` interface; `GeminiResponder` keeps today's behavior.
- Turn-taking: weighted rendezvous `rank(event_id, …)` (`hashlib`, never `hash()`); R1 (named → the named; a group address «всі»/«кожен» → every ranked agent; unnamed → top `OWNER_REPLIERS`), R2 (at most one next speaker; naming decides who, not whether), R3 (re-check at fire time, per engine), R4 (the rate); `wave_count` includes the message being answered (`MAX_BOT_TURNS` new = old + 1); modes `ranked` / `ambient` / `mention-only`; the coordination-free fallback after `FALLBACK_S`.
- Reply length: `REPLY_MAX_TOKENS`, the «1–3 речення» rule in `common.md`, trimming to the last complete sentence.
- `HISTORY_N` default 40; background waves stay "a rate, not a lock".
- `server/.env` migration of `MAX_BOT_TURNS` to the new meaning (owner).
- The panel: the agent view gains `type`, `engine` and capabilities; tabs, Forget and the stop/restart confirmations follow capabilities; `[panel] pronoun` gains `it`.

**DoD:**
- An owner message without names gets exactly `OWNER_REPLIERS` answers; a named one only the named agents; an agent message has at most one next speaker; a simulated wave never exceeds `MAX_BOT_TURNS` agent messages beyond the answers to the owner.
- The ranking is identical across processes and proportional to the weights.
- Ada's and Bruno's behavior is otherwise unchanged (memories, plans, today block, summaries).
- (Manual, owner) In the room, a question without names gets two short answers and at most one follow-up.
- (Manual, owner) Ada's and Bruno's panel cards look and work as before.

**Tests:** unit — `rank` (determinism across `PYTHONHASHSEED`, weights, roster order), R1–R4, the modes, the fallback, `wave_count` and its migration, capability gating, roster loading and the allowlist, sentence trimming, the panel's view and controls by capability; a scripted multi-agent simulation with the rng and clock injected.

### v4.2 — The cat in the room

**Status:** ✅ completed — released `v4.2.0` on 2026-10-10.

**Goal:** a mystical, artificial cat joins the room — mostly purring, reacting now and then, his mood set each day by a horoscope built exactly as Lumi builds hers.

Design: more-agents.md §The cat, §6, §8, §10. Depends on: v4.1.

**Tasks:**
- The `creature` type; `agents/kit.toml` (name «Кіт», its name forms, `mode = "ambient"`), `agents/canon/kit.md`, `agents/canon/kit.natal.md` (Lumi's `core/natal.md` format, from the verified chart of the first Linux commit, 2005-04-16 15:20:36 PDT, Portland), `agents/canon/kit.life.md` (the sysadmin's life and death as past chapters, the rebirth opening the current chapter, a hidden death) — no generated memories, no plans, no today block.
- `agents/mood.py`: Lumi's mood service ported (`core/mood.py` + `core/biorhythm.py`; without the cycle, the themes and the thoughts) — once per local day, `state/kit.mood.log`, restart reuses the day's block, only the `РЕЗОЛЮЦІЯ` enters his prompt; the usage kind `mood`.
- Purrs in code (`CAT_PURR_P`), the ambient reaction (`CAT_REACT_P`); purrs excluded from `wave_count` and from producing a next speaker; consecutive purrs collapse in the others' context; a hard word cap. His non-purr lines: short, a sky remark or a shell line.
- The human-belief rule scoped to persona agents (VISION, ARCHITECTURE, the canon-scan test); the outgoing guard; `common.md` lists the room's members by name only.
- The design handoff's card variants for the new types (creature, assistant, bridge).
- The `kit` compose service and his `[panel]` block; **his panel card** — state, logs, start/stop/restart, the mood of the day (the resolution, the reading on expand), the biorhythms; no memory tabs, no Forget.
- (Owner) The Matrix account (admin room, registration is closed), the invite to Agora.

**DoD:**
- (Manual, owner) Кіт's card appears in the panel, and start/stop/restart work from it.
- (Manual, owner) Кіт joins the room, mostly purrs, sometimes drops a short sky or shell line; his mood of the day is visible in the panel.
- One horoscope per local day; a restart does not re-roll it; a failed horoscope never blocks a reply.
- Ada's and Bruno's prompts and canons still pass the human-belief scan; the guard drops a line that calls a persona a bot.

**Tests:** unit — the ported mood service (day selection, log reuse, `split_resolution`, failure), biorhythms, the purr roll and the word cap, purr handling in `wave_count` and the context, the life story parsing, the scoped canon scan and the guard.

### v4.3 — The cat: his past life and his initiative

**Status:** ✅ completed — released `v4.3.0` on 2026-10-10.

**Goal:** Кіт remembers fragments of his human life and becomes the one agent who starts conversations.

Design: more-agents.md §The cat (past-life memories, he starts conversations). Depends on: v4.2, seen in the room.

**Tasks:**
- Past-life memories: `agents/canon/kit.memories.md` (60–100 authored theses, `- [tags] text`; drafted 2026-10-10 — 92 theses after the v4.3 review, tags are Ukrainian stems matched at a word start — for the owner's edit); the pure `pick_memory(event_id, last_text, theses, told)` (tag match first, then the hash; no repeats until all are told; RAM only); with `CAT_MEMORY_P` one thesis enters a non-purr prompt, retold in his own words — a reply copying 5+ of its words (`shares_span`) is regenerated once, then dropped.
- **He starts conversations**: after `CAT_NUDGE_IDLE_S` of room silence, at most `CAT_NUDGES_PER_DAY`, within `CAT_NUDGE_HOURS` (Kyiv), he posts one line tied to the recent talk — a past-life fragment, a Linux command, or the day's horoscope in metaphorical form (`nudge_due`, `nudge_kind`, `state/kit.nudge.json`); a nudge opens a fresh wave; no other agent ever initiates.
- His panel card adds the number of theses, his last nudge and today's count.

**DoD:**
- (Manual, owner) Кіт sometimes retells a fragment of his past life in his own words, never quoting a thesis.
- (Manual, owner) After a quiet stretch in the daytime, Кіт drops a line tied to the recent talk, and someone answers him; at night and over the daily cap he stays silent.
- No thesis names Ich, Ada or Bruno; no other agent ever posts without a trigger.

**Tests:** unit — `pick_memory` (determinism, tag preference, no repeats) and the not-verbatim rule, the theses file parsing, `nudge_due` and `nudge_kind` (silence, gap, cap, hours, restart), a nudge opening a fresh wave with one next speaker.

### v4.4 — Claude on the subscription: answering when asked

**Status:** ✅ completed — released `v4.4.0` on 2026-10-11.

**Goal:** Claude joins the room as itself — no canon, no memory — answering when someone addresses it, running only on the owner's Max subscription; an API key can never be used.

Design: more-agents.md §Claude, §7, §9, §10. Depends on: v4.1 (v4.2 for the scoped human-belief rule).

**Tasks:**
- The `assistant` type; `agents/claude.toml` (name «Клод», its name forms, `engine = "claude-sdk"`, `[turns] mode = "mention-only"`); the **direct** brief in code (answers what was asked, as Claude, chat-sized, over `HISTORY_N`; names the members, never their nature; `PASS`).
- `ClaudeSdkResponder`: one stateless `query()` per reply on Opus (`CLAUDE_MODEL=opus`) — `tools=[]`, `setting_sources=[]`, `max_turns=1`, `CLAUDE_CODE_MAX_OUTPUT_TOKENS`, `CLAUDE_CODE_SKIP_PROMPT_HISTORY`, a tmpfs `CLAUDE_CONFIG_DIR`; `RateLimitEvent`: mute on warning, silent until reset on rejection.
- **No API key, enforced:** no forbidden variable (`ANTHROPIC_*`, `CLAUDE_CODE_USE_*`, `CLAUDE_CODE_SIMPLE`) anywhere in the stack; startup refuses on any of them or a missing OAuth token; they are scrubbed from the SDK's inherited environment; a non-OAuth auth source in `system/init` stops replies; no `anthropic` client in the code; every usage row `subscription`.
- The second image target `matrix-agora-agent-claude` (+ CI); the `claude` compose service with its own env file, not loading the shared `.env`; `server/deploy.sh` syncs that file.
- Usage line v2 (`engine`, `billing`, cache tokens, reported cost); prices per engine; the panel's token table gains engine and billing columns; the outgoing guard on Claude's replies.
- **Claude's panel card**: engine, model (Opus), billing `subscription`, the rate-limit status from `state/claude.ratelimit.json`, the startup auth check; its token rows unpriced; no memory tabs, no Forget.
- (Owner) `claude setup-token` → the token into Claude's env file; the Matrix account, the invite.

**DoD:**
- (Manual, owner) Claude's card appears in the panel with its rate-limit status, and start/stop/restart work from it.
- (Manual, owner) Asked by name, Claude answers the question in chat-sized lines; unnamed, it stays silent; `system/init` shows no tools and the OAuth source.
- The agent refuses to start with any forbidden variable set; the compose test finds none in the stack.
- (Manual, owner) At the subscription limit it is silent; no room text persists in its container.

**Tests:** unit — the responder against a mocked SDK (success, `is_error`, `RateLimitEvent`), every no-API-key layer (refusal per variable, scrubbing, the init check, the import set, `subscription` rows), the compose forbidden-variable and env-file checks, usage line v2 and pricing per engine.

### v4.5 — Claude the philosopher

**Status:** ✅ completed — released `v4.5.0` on 2026-10-11.

**Goal:** Claude joins the talk unasked, as a philosopher reflecting on the image the conversation keeps circling.

Design: more-agents.md §Claude (two reply modes). Depends on: v4.4, its quota use seen in the room.

Owner decisions (2026-10-11): Claude's weight is 1, as designed; the outgoing guard's pronoun rule binds him too (the v4.4 review #8 question) — a safer Ada and Bruno over an occasionally silent Claude.

**Tasks:**
- `agents/claude.toml`: `[turns] mode = "ranked"`, weight 1 — Claude joins R1 and R2.
- **Two reply modes** (`claude_mode`): **direct** when addressed by name or a group address (v4.4); **philosopher** when the turn-taking brings him in unasked — over a wider window (`CLAUDE_HISTORY_N`, a RAM buffer seeded from the room, paged back past the homeserver's 100-event page) he reflects in 1–3 sentences (the owner, 2026-10-11; designed 2–4) on the philosophy of the metaphorical image running through the talk, or answers `PASS`; a higher reasoning effort than the direct mode; both modes think (adaptive).
- **Added during the phase (the owner, 2026-10-11):**
  - **His tools** (AGORA-068): the web (`WebSearch`, `WebFetch`, public hosts only) and his own folder `/workspace` (`Read`, `Write`, `Edit`, `Glob`, `Grep`), behind a PreToolUse guard; up to 8 turns and 180 s per reply.
  - **His news** (AGORA-069, review #6): every hour, once the room has been quiet for a few minutes, 09–01, one fresh item from **The Guardian** (its Open Platform API, two in-process tools; the key never reaches the model) bearing on the last 40 messages, or `PASS`.
  - **An address is always answered** inside a burst (a named R2 candidate skips `BOT_REPLY_P`; a resumed decision still rolls it); a message naming only the cat has no R2 candidate.
  - **The cat's real sky**: his horoscope and talk name only the day's astrological positions and aspects, asked once a day of Gemini with Google Search (as Lumi's web lookup) — never invented.

**DoD:**
- (Manual, owner) Asked by name, Claude still answers the question; joining unasked, he speaks as a philosopher about the image the talk has been circling.
- (Manual, owner) The rate-limit status in the panel shows the philosopher's quota use stays within the plan.
- (Manual, owner) Asked to look something up or to keep a note, he uses the web and his folder — and nothing else; an hourly Guardian item arrives in a quiet room.

**Tests:** unit — `claude_mode` for every name form, the Matrix id and the unnamed case; the window and the brief per mode; Claude in the ranking and the multi-agent simulation.

### v4.6 — Ada and Bruno: curiosity, plans and stories

**Status:** ✅ completed — released `v4.6.0` on 2026-10-11.

**Goal:** Ada and Bruno do more than keep the conversation going. They ask questions of the cat, Claude, each other and the owner, share their plans, and tell stories from their lives.

Design: the canon gives each of them something to be curious about; the code gives each reply a **move**, because a model left alone just agrees. The move is drawn deterministically from the event id, as the cat's nudge kinds are, so its rate can be tuned and tested and the talk never becomes an interrogation. Depends on: v4.5 (an address is always answered; Claude in the ranking).

**Owner decisions** (2026-10-11): a version of its own, before the panel's settings; Claude's quota is not a concern, so questions to him get no lower weight.

**Tasks:**
- **The canon:**
  - in `ada.md` and `bruno.md`, a «Цікавість» paragraph saying what each wants to know from each member:
    - Ада: the cat's past life, Claude's thoughts on language and books, Bruno's travels and music, what the owner reads and how his day went;
    - Бруно: the cat's sysadmin stories, Claude's take on technology and science, what Ada reads and edits, the owner's plans and music;
  - **opposite views** (the owner, 2026-10-11: «зроби цікавості Ади і Бруно протилежними щоб виник спільний конфлікт»): Ада looks inward — meaning, memory, doubt, the slow and the old; Бруно looks outward — how it works, what's next, action, the new; on the same situation they take opposite sides and argue it out with respect;
  - a line to share their plans and tell stories from their own lives.
- **The move:** a pure `persona_move(event_id, name, roster, weights)` returns one of:
  - `answer` (the rest);
  - `ask` with its addressee: one of the others or the owner, never oneself, drawn evenly by default;
  - `disagree` (the owner, 2026-10-11): take the other side of the message answered, with an argument and respect;
  - `plan`;
  - `story`.
  - Its weights are `PERSONA_ASK_P` (0.25), `PERSONA_DISAGREE_P` (0.15), `PERSONA_PLAN_P` (0.1) and `PERSONA_STORY_P` (0.1), read only by a `persona`; a plain answer (0.4) stays the most common.
- **The prompt:** one line «Цього разу: …» before the reply rules:
  - `ask`: answer briefly, then ask the named member one question from your curiosity;
  - `disagree`: don't agree — take the other side from your own view, with an argument;
  - `plan`: mention something from «Твої плани» or «Сьогодні» that fits the talk;
  - `story`: tell a short story from «Твоє життя досі» or your memories, only what is there, never a new fact about the room or the past.
- **Turn-taking is unchanged.** A question names its addressee, who always answers (2026-10-11); the wave limit and the coin on a resume bound any chain.
- **The human-belief rule holds.** Questions are about topics, never about anyone's nature; the outgoing guard stays.
- **The contracts:** ARCHITECTURE's prompt assembly (the move line), the env table, compose (the weights interpolated into the persona services), and the tests that pin them.

**DoD:**
- (Manual, owner) Over an evening Ada and Bruno ask questions of every member, the owner included. The asked member answers.
- (Manual, owner) They mention their plans and tell short stories from their lives that agree with their life files. A plain answer stays the most common move.
- (Manual, owner) On the same situation Ada and Bruno take opposite sides and argue it out with respect.

**Tests:** unit:
- the move distribution over many event ids, within tolerance;
- the addressee is never oneself and every member is reachable;
- the move is deterministic per event;
- the prompt line per move, and none for a non-persona;
- the persona-only settings;
- no move line names anyone's nature.

### v4.7 — Agent settings and Claude's files in the panel

**Status:** ✅ completed — released `v4.7.0` on 2026-10-11.

**Goal:** every agent's tunable setting is seen and changed in the panel, not in `server/.env`; a change takes effect by restarting the agents it concerns, survives a deploy, and no secret ever appears. And the owner reaches Claude's own folder from the panel (the owner, 2026-10-11: «дай ще доступ до сховища файлів Клода»).

Design: a settings schema in code is the single list of what may be tuned; the panel owns a file of overrides in `state/`; the agents read it at start, over the environment. This reverses a v3.3 rule (ARCHITECTURE §The panel: «there is no settings view») for **non-secret settings only**. Depends on: v4.6 (the settings it covers), v3.4 (the panel's restart action).

**Owner decisions** (confirmed by the owner at the phase start, 2026-10-11: the overrides file, a restart, and every file operation for Claude's folder):
- **The overrides live in `state/settings.json`**, written only by the panel. `server/.env` and `server/claude.env` stay the base values and the secrets, and `server/deploy.sh` never touches the file, so a deploy keeps what the owner set. The alternative, the panel editing `server/.env` on the host, would fight `deploy.sh`, which syncs that file from the Mac.
- **A change applies by restart**, not live. The panel restarts exactly the agents a setting concerns, after a confirmation. A shared turn-taking setting restarts every agent together, since all of them must compute the turns from the same values.
- **Scope**: every non-secret agent setting. That covers the room and turn-taking (`HISTORY_N`, `REPLY_MAX_TOKENS`, `MAX_BOT_TURNS`, `BOT_REPLY_P`, `BOT_WINDOW_S`, `OWNER_REPLIERS`, `FALLBACK_S`, `REPLY_DELAY_S`), memory (`MEMORY_DAYS`, …, `SESSION_*`), the cat (`CAT_*`), Claude (`CLAUDE_MODEL`, `CLAUDE_HISTORY_N`, `CLAUDE_TIMEOUT_S`, `CLAUDE_CODE_MAX_OUTPUT_TOKENS`, `CLAUDE_NEWS_*`) and the Gemini model. Out of scope are passwords, tokens and keys (Gemini, OAuth, Guardian, the panel's), the room and owner ids, and the canons.

**Tasks:**
- **The schema** (`agents/settings.py`, pure):
  - every tunable name with its type, range or pattern, default, unit, a one-line description, and its scope: `shared` (every agent reads it), or the agents or capabilities it concerns;
  - secrets are never in it, and a test fails if a secret-looking name (`*_PASSWORD`, `*_TOKEN`, `*_KEY`) appears.
- **The overrides file:**
  - `state/settings.json` holds `{"services": {<sim>: {name: value}}, "agents": {<agent>: {name: value}}}` (AGORA-078), atomic and 0600;
  - the agents apply it at start, over the environment, through the schema: an unknown name or an invalid value is ignored and logged by name;
  - the code defaults, the env and the overrides resolve in that order, in one place.
- **The panel API:**
  - `GET /api/simulations/{sim_id}/settings` and `GET /api/agents/{name}/settings` (AGORA-078) return the scope's settings with each value's effective value and its source (`default` / `env` / `panel`);
  - the matching `PUT` validates against the scope, writes the overrides and answers with the agents restarted;
  - reset to the default drops an override;
  - names resolve only through the schema, never into a path, an argv or the docker API;
  - Bearer auth as everywhere.
- **The panel UI:**
  - a Settings view grouped as Room & turns, Memory, Кіт and Клод, each field with its value, default, unit and description, and a mark for what the panel changed;
  - Save shows the agents that will restart and asks for confirmation, then restarts them through the v3.4 action;
  - the screen is designed first as an addendum to `specification/design/README.md`.
- **The contracts:**
  - ARCHITECTURE: the panel's settings view (non-secret only), `state/settings.json`, the resolution order, and the env table's «tunable in the panel» column;
  - the tests that pin them.
- **The owner's live values** (`server/.env` today) carried over: the panel shows them as `env` and can override them.
- **Settings under their service** (the owner, 2026-10-11, AGORA-078): a service setting belongs to a simulation kind and its value to one simulation (on its card); an agent setting is the agent's own (in its drawer) — so a future portal (a diary, a gallery, news) brings its own settings.
- **Claude's files** (the owner, 2026-10-11): a Files tab on Claude's card over his folder (`claude-workspace` on the host, `/workspace` for him), mounted into the panel:
  - list the folder (names, sizes, times), read a text file, download any file;
  - upload a file into it and delete one, each after a confirmation;
  - paths resolve only inside the folder (`realpath`, no symlink out, no `..`); size caps on reads and uploads; Bearer auth as everywhere;
  - the files are his notes, never a prompt the code builds — the panel only shows and moves them.

**DoD:**
- (Manual, owner) In the panel, the owner changes a cat setting (e.g. `CAT_NUDGE_IDLE_S`) and confirms. Only the cat restarts, and his behavior follows. A deploy leaves the value as set.
- (Manual, owner) A shared turn-taking setting (e.g. `MAX_BOT_TURNS`) restarts every agent together, and each agent's start log names the overridden settings.
- (Manual, owner) No password, token or key appears anywhere in the Settings view or its API responses.
- (Manual, owner) Claude's Files tab lists what he wrote, opens and downloads a note, and an uploaded file is one he can read.

**Tests:** unit:
- the schema: types, ranges, the hours pattern, no secret names;
- the resolution order (default < env < panel), and an invalid or unknown override ignored;
- the atomic 0600 write;
- the API: auth, validation, unknown names, the restart set for `shared` vs one agent;
- the agent applies the overrides at start;
- Claude's files: listing, reading, download, upload and delete inside the folder; `..`, absolute paths and a symlink out refused; the size caps;
- static UI checks for the views and the confirmations.

## v5 — Voice: Hermes, the agents hear and speak

The owner, 2026-10-13: voice messages in the room, and a standing digest of the room sent to him as a voice
message. Element on the iPhone and the Mac already sends voice messages: each is an audio file in the homeserver's
media store and an `m.audio` event marked as voice (MSC3245). Every agent, though, answers text only and logs a
voice message as `ignored`. **The speech services are Lumi's** (the owner, 2026-10-13), with the keys already
there: **ElevenLabs** for text to speech (`eleven_turbo_v2_5`, multilingual, one voice id per member) and
**Deepgram** for speech to text (`nova-2`, `uk`). They are ported from Lumi's `voice/tts.py` and `voice/stt.py`.
Claude stays on his subscription, in text. Depends on: v4 (the roster, the turn rules, the panel's
settings under their service).

**Hermes** (the owner's choice of name and character) is a new member of the room. He is the messenger god and the
patron of the agora itself: quick, witty, a little vain, telling the day like news from Olympus, gently ironic about
the mortals. He speaks Ukrainian. He is openly not human, but **he never takes part in the room's talk**: he is not
in the turn-taking, he says nothing of his own in Agora, and the personas never discuss what he is. He reads the room
word for word from the homeserver and speaks to the owner in a private room.

### v5.1 — Hermes: voice digests for the owner

**Status:** ✅ completed — released `v5.1.1` on 2026-10-18 (no separate `v5.1.0`: the owner released the phase together with the live fix that made his room a conversation).

**Goal:** a standing digest of the room — what was talked about, who thought what, where they argued, what they
asked the owner, what was settled — reaches the owner as a voice message in Hermes's colour, on a schedule and on
request.

**Owner decisions** (2026-10-13):
- **One member does the digests:** Hermes, a new non-persona member with a character. He also transcribes in v5.2.
- **The digest goes to the owner's private room with Hermes**, not into Agora. It carries the text too, for reading.
- **Hermes stays silent in Agora.** He answers the owner's questions about the history in the private room.

- **Every 4 hours**, and only after at least N new messages: no empty digest.
- **The model is `gemini-3.1-pro-preview` with thinking** (Lumi's verified id), not the room's Flash.
- **The length follows the talk** (the owner, 2026-10-13): a few lines make a half-minute digest, a lively
  stretch a longer one, **at most 1.5 minutes** (~1,500 characters; about 1,000 characters a minute of Ukrainian
  speech).
- **His voice** is an ElevenLabs voice id the owner gives. Each agent later gets its own (v5.3).
- **The cost** (2026-10-13 prices): ElevenLabs turbo through the API is 0.5 credit a character, and Gemini 3.1
  Pro is $2 / $12 per million tokens (about $0.07 a digest). At about 4 digests a day of about 1.2 minutes on average:
  - ~145k characters a month, ~72k credits — inside Creator ($22 for 121k), **shared with Lumi's own voice**;
  - ~$8 a month for Gemini.

  The panel shows the characters used, and a monthly character cap guards the quota.

**Tasks:**
- **The member:**
  - a `herald` type: no turns, its own capabilities `digest` (and `transcribe` from v5.2);
  - `agents/hermes.toml` and his canon `agents/canon/hermes.md`, with his character and how he tells a digest;
  - his Matrix account (owner step) and the private room with the owner, created and invited by Hermes;
  - the allowlist: in Agora he only reads; in the private room he answers only the owner.
- **The digest:**
  - on schedule or on the owner's «підсумок», collect the Agora messages since the last digest, word for word,
    through the room's `/messages`;
  - one `gemini-3.1-pro-preview` call, with thinking, writes the digest in his character (usage kind
    `digest_voice`). Its length follows the amount of talk, capped at ~1,500 characters (about 1.5 minutes), and is
    trimmed to its last full sentence if it overruns;
  - text to speech through ElevenLabs (his voice id, `eleven_turbo_v2_5`; usage kind `tts`, counted in
    characters), encoded to OGG/Opus (ffmpeg in the image), uploaded to the media store, sent as `m.audio` with
    Element's voice-message fields (MSC3245 voice, MSC1767 audio with duration and waveform), with the text in
    `body`;
  - the keys: `ELEVENLABS_API_KEY` (and from v5.2 `DEEPGRAM_API_KEY`) are copied from Lumi into Hermes's own env
    file, never printed or logged;
  - the last digest's point is kept in `state/hermes.digest.json`; no digest when nothing new;
  - no message text, audio or digest text ever reaches a log.
- **Questions about the history:** in the private room the owner asks («що Бруно казав учора про подорож?»).
  Hermes searches the room's words and answers in text, or in voice when asked in voice (v5.2).
- **The panel:** Hermes's card (log, tokens, the TTS characters) and his settings: the interval (4 h), the minimum
  of new messages, the maximum length (1,500 characters), a monthly character cap, the voice id. They are service
  settings of the Matrix chat (v4.7).
- **ARCHITECTURE:** the `herald` type, the private room and its allowlist, the digest flow, the state file and the
  env.
- **The human-belief rule:** Hermes's prompts and digests name Ada and Bruno by name and never call them a model, a
  bot or an agent (the outgoing guard applies).

**DoD:**
- (Manual, owner) Every 4 hours, with enough new talk, a voice message from Hermes arrives in the private room. It
  is a digest of the room in his character and his voice, with its text, at most about 1.5 minutes long.
- (Manual, owner) «підсумок» in the private room brings one at once. With nothing new he says so, briefly.
- (Manual, owner) Asked about something said yesterday, he answers from the room's words.
- (Manual, owner) In Agora he says nothing.

**Tests:** unit:
- the schedule and the minimum of new messages;
- the collection since the last digest;
- the digest and TTS calls with Gemini mocked;
- the encode and upload with the media API mocked;
- the `m.audio` content (the voice flag, the duration, the body);
- the private room's allowlist;
- silence in Agora;
- no text in the logs;
- the human-belief guard on digests.

### v5.2 — The agents hear voice messages

**Status:** ✅ completed — released `v5.2.0` on 2026-10-18.

**Goal:** a voice message from the owner in Agora is understood by the agents as if it were typed, and the room
sees the words.

Design: **one transcript, shared by every agent.** If each agent transcribed for itself, there would be N calls and
possibly N slightly different texts, and the turn rules depend on the text (mentions, R1). So Hermes transcribes and
posts «🎙 Ich: …» as a reply to the voice event. The agents answer **the owner**: in their history the line reads
«Ich: …», R1 and the fallback apply as to a typed message, and their replies relate to the owner's voice event.

**Tasks:**
- **The filter:** `RoomMessageAudio` from the owner in `ROOM_ID` reaches Hermes only. Every other agent still logs it
  as `ignored`.
- **Hermes:**
  - he downloads the audio through the authenticated media API, within a size cap;
  - Deepgram transcribes it (`nova-2`, `uk`; usage kind `stt`);
  - he posts the transcript as `m.text`, replying to the voice event;
  - a failed or empty transcript is logged and stays silent;
  - no audio or transcript text ever reaches a log.
- **The agents:**
  - a Hermes transcript of an owner's voice event counts as the owner's message: R1, the fallback, the session, the
    journal and the memories;
  - the event id is the transcript's, and the line's speaker is Ich.
- **ARCHITECTURE:** the audio filter, the transcript rule in the turn-taking, the `transcribe` capability.

**DoD:**
- (Manual, owner) A voice message from the iPhone gets its transcript within seconds, and the agents answer it as
  they would the typed words, with the same turn rules, named or not.
- (Manual, owner) A voice message that cannot be heard (silence, noise) gets no transcript and no answer, never an
  error.

**Tests:** unit:
- the audio filter (Hermes only);
- the download cap;
- the transcript post and its reply relation;
- a transcript as the owner's message (R1, the fallback, the speaker «Ich»);
- a failed transcription stays silent;
- no text in the logs.

### v5.3 — The agents answer in voice

**Status:** ✅ completed — released `v5.3.0` on 2026-10-19 (the owner's changes: Claude speaks too; always voiced, `VOICE_REPLY_P` 1.0; a 100,000-character monthly budget; a labelled voice followed by its text).

**Goal:** an agent answers in its own voice: to the owner's voice message in voice, otherwise by a setting. It uses
Hermes's text-to-speech pipeline from v5.1.

**Owner decisions** (proposed, to confirm when the phase starts):
- **When:**
  - an answer to the owner's voice message comes in voice;
  - any other reply comes in voice by a per-agent share (`VOICE_REPLY_P`, 0 by default).
- **Voices:** one ElevenLabs voice per agent, given by the owner and set in its TOML (Ада, Бруно and Кіт each
  their own); the cat may purr aloud.
- **Claude:** stays in text, since he runs on the subscription.

**Tasks:**
- **The voiced reply:** the reply's checks run on the text first (PASS, the persona guard, the word cap); then the
  shared TTS pipeline; then `m.audio` with the voice flag, related to the owner's voice event, with the text in
  `body`.
- **The panel:** each agent's voice and `VOICE_REPLY_P` as settings, and the TTS rows in the token table.

**DoD:**
- (Manual, owner) Spoken to in voice, Ada, Bruno and Кіт answer in their own distinct voices.
- (Manual, owner) The text of a voiced reply reads the same in the room.
- (Manual, owner) Claude stays in text.

**Tests:** unit:
- when to voice;
- the checks before voicing;
- the `m.audio` content and its relation;
- no audio in the logs.

### v5.4 — The Agora recording, on request

**Status:** ✅ completed — released `v5.4.0` on 2026-10-20 (the owner's changes: a skill Hermes understands from the conversation, not a command; no spoken time marks; media downloads read to the end).

**Goal:** the owner listens to Agora as it happened: one audio file of a stretch of the room, each line in the voice
of the one who said it, assembled by Hermes when the owner asks, sent to his private room.

**Owner decisions** (2026-10-20):
- **Only when asked** in Hermes's room, typed or spoken. First as a command («запис за сьогодні», «за вчора», «з
  14:00»); the same day the owner made it **a skill, not a command**: Hermes understands the request from the
  conversation («збери мені Агору з п'ятої до сьомої вчора») and names the period himself;
- **the owner's typed lines in his own cloned voice** (an ElevenLabs Instant Voice Clone, `OWNER_VOICE_ID`, given
  2026-10-20); his voice messages go in as they are;
- **into Hermes's private room**, as an audio file — not into Agora.

**Tasks:**
- **The skill:** his chat brief describes the recording; asked for one, his answer ends with one line «ЗАПИС:
  РРРР-ММ-ДД ГГ:ХХ — РРРР-ММ-ДД ГГ:ХХ» (the time now is in the prompt), which code reads (pure: it parses, ends no
  later than now, is at most a day) and never sends; anything else stays the conversation or «підсумок».
- **The plan** (pure): the Agora messages of the period in order, each line mapped to its sound:
  - a member's voiced line (the labelled voice message and the text that follows it) → the voice as it is;
  - the owner's voice message → as it is; Hermes's transcript of it → left out;
  - the owner's typed line → spoken in `OWNER_VOICE_ID`;
  - a member's text-only line → spoken in its own voice within the speakers' budget, else left out;
  - an action purr (`*…*`) → left out.
- **The assembly:** each piece downloaded (the authenticated media API) or spoken, decoded to PCM, the loudness
  levelled (ffmpeg `loudnorm`), short pauses between lines and a longer one after a silence of over 15 minutes (no
  spoken time — the owner, 2026-10-20), Hermes's opening («Агора, <дата>, з … до …») and closing, encoded once
  to OGG/Opus; split into parts when over the homeserver's upload limit.
- **The delivery:** an `m.audio` file (not a voice message) named «Агора <дата>.ogg» in Hermes's room, with one line
  of text — the length, the number of lines, the period; typing while he assembles; usage lines for every TTS call.
- **No archive:** nothing is kept but the sent file in the homeserver's media store (the room already holds its
  history); VISION's non-goal on raw archives notes that the recording is assembled from the room on demand.
- **ARCHITECTURE:** the recording flow, `OWNER_VOICE_ID`, the skill.

**DoD:**
- (Manual, owner) Asked for a recording in his own words in Hermes's room, he brings one audio file of that
  stretch of Agora, each line in its
  speaker's voice — Ada, Bruno, Кіт, Клод, and his own (typed lines in his cloned voice, voice messages as they were).
- (Manual, owner) A period with no talk gets a short line, not a file.

**Tests:** unit:
- the period line of his answer (parsed, bounded, never sent);
- the plan: pairing a voice with its text, each kind of line, the left-out ones;
- the assembly with ffmpeg and the downloads mocked (order, pauses, the split);
- the delivery content;
- no text or audio in the logs.

### v5.5 — Four more people: пан Леон, Мія, пані Ірма and Кіра

**Status:** ✅ completed — released `v5.5.0` on 2026-10-20 (the owner's changes: the names in the style of Ada and Bruno, Ірма and Кіра added, a secret and clashing traits for each, the same weight for every person, a quieter room and a 200,000 voice budget).

**Goal:** Agora gains four more human members, built like Ada and Bruno: a canon, a life story with hidden future
chapters, memories, plans, the today block and their own voices. Their characters, stories and memories are their
own, and every member of the room has a friction with them.

**Owner decisions** (2026-10-20):
- **Four people**, all `persona`, so they believe they are human:
  - **пан Леон**, 67, a former actor of the Lviv drama theatre who leads the amateur theatre «Ліхтар»; in Agora
    he tells theatre stories and argues with Bruno about sound; on stage he plays fathers, stepfathers and
    villains;
  - **Мія**, 22, a history student who works as a barista and reads detective novels by the dozen; she brings
    a young view; on stage she plays heroines, maids and heiresses; she speaks surzhyk, and her boyfriend was
    killed by a Shahed in 2025 (the owner);
  - **пані Ірма**, 61, a former court stenographer who typed hundreds of trials and now works half-time in the
    city archive; in Agora she has a dry humour and an exact memory of who said what; she says she never changed a
    word in a protocol, but once did, in 1997, under pressure (the owner) (added the same day; the
    owner's «Стефа» is Ada's late grandmother in her life story, so the name became Ірма);
  - **Кіра**, 23, the one who suits the owner best. Her birth was chosen for the strongest romantic synastry
    with the owner's chart: 2002-12-02 20:40, Донецьк (his birth data stays out of the repo). She has a
    complicated history: Donetsk until 2014, and a father who stayed there and whom she calls dead. She studied
    astrophysics in Edinburgh and now leads the shows at the Lviv planetarium. Her hobby is kintsugi.
- **Names in the style of Ada and Bruno**, not markedly Ukrainian: Леон and Мія (first drafted as Орест and
  Соломія).
- **Two men and four women of different ages** (22, 23, 32, 61 and 35, 67). Mia and Kira are a year apart, so
  their voices are designed far apart: light and quick vs low and husky.
- **A conflict among all of them:** each pair has its own friction.
- **A shared past.** Ada and Bruno already know Леон and Мія, and the frictions come with that history. VISION's
  rule «the personas get no description of the newcomers» was written for non-human members and says it must
  be revisited if people join. For people it becomes a shared past, written into every person's canon.
- **The radio theatre** where they act is a version of its own in another chat, from the owner's concept document
  (later). In Agora they just talk.

**The people** (drafts: `agents/canon/leon.md`, `leon.life.md`, `mia.md`, `mia.life.md`, `irma.md`,
`irma.life.md`, `kira.md`, `kira.life.md`):
- **The views.** Ада (inside, slow) ↔ Бруно (outside, fast) stays. Пан Леон (tradition, feeling, legend, the
  living voice) ↔ Мія (facts, patterns, her generation); пані Ірма (the exact record: who said what, when) ↔
  пан Леон as well.
- **The frictions:**
  - Леон ↔ Бруно: the microphones at «Наталка Полтавка», December 2025;
  - Леон ↔ Ада: the 2008 studio, and the text vs the stage;
  - Леон ↔ Мія: «Мишоловка» vs «Лісова пісня», his stories against her archives — and his secret (the owner): a
    KGB informer «Суфлер» in 1979–1989, which her archive work may one day uncover;
  - Мія ↔ Ада: Ada's hard notes on Mia's detective novel;
  - Мія ↔ Бруно: the past vs the future;
  - Ірма ↔ Леон: she typed his divorce in 1996 and remembers every word he said; his legends against her record;
  - Ірма ↔ Ада: the mother of Ada's school friend Соломія, who quotes Ada's teenage vows; Ada edits words, Ірма
    never changed one;
  - Ірма ↔ Бруно: «Музика — це не шум, ваша честь», the 2016 noise trial he forgot and she quotes;
  - Ірма ↔ Мія: the archive's reading-room rules («Цербер»), the record against her theories — and a 1997 case
    Ірма has kept in a shoebox;
  - Кіра ↔ Ірма: the big picture vs the exact detail; Ірма typed her parents' 2016 divorce and knows her father
    is alive;
  - Кіра ↔ Мія: astrology vs facts, Назар, and «Edinburgh while others sat in the metro»;
  - Кіра ↔ Ада: the terms in a popular astronomy translation, beauty vs truth;
  - Кіра ↔ Леон: she refused «Ліхтар», and his cracked cup she wants to mend with gold;
  - Кіра ↔ Бруно: friends from the 2022 aid runs and the Tustan rocks, rivals over who climbs higher and
    over silence vs music in the planetarium.

**Tasks:**
- **The people:**
  - their TOMLs: `leon`, `mia`, `irma` and `kira`, `type = "persona"`, `ranked`, name forms, the panel's name, role and
    pronoun;
  - the canons and life stories, finalised with the owner;
  - all four in `simulations.toml`.
- **The people already there:**
  - `common.md`, `ada.md` and `bruno.md` gain the new members, their ties and curiosity lines;
  - Ada's and Bruno's life stories gain them as well.
- **Name forms:** no form of one member is a form of another (pinned).
- **Owner steps:**
  - the four Matrix accounts (`!admin users create-user leon`, `mia`, `irma`, `kira`);
  - `LEON_PASSWORD`, `MIA_PASSWORD`, `IRMA_PASSWORD` and `KIRA_PASSWORD` in `server/.env`;
  - the invites into Agora;
  - four ElevenLabs voices (`LEON_VOICE_ID`, `MIA_VOICE_ID`, `IRMA_VOICE_ID`, `KIRA_VOICE_ID`) from the Voice
    Design prompts, added to
    `docs/elevenlabs-voices.md`.
- **Compose:** services `leon`, `mia`, `irma` and `kira` (the shared image; `voice.env` gets four more readers) and the env
  examples.
- **The room's load:** six ranked people plus Claude.
  - **Equal weight for every person** (the owner, 2026-10-20): Ада, Бруно, Леон, Мія, Ірма and Кіра all
    `ranked` with weight 1.0; Claude stays 0.4.
  - **A quieter room, live since 2026-10-20 before the phase** (`server/.env`): `MAX_BOT_TURNS` 4 per
    `BOT_WINDOW_S` 900, `BOT_REPLY_P` 0.45, `PERSONA_ASK_P` 0.12, `CAT_REACT_P` 0.12, the cat's nudge after
    3,600 s of silence, Claude's news every 3 h (at most 4 a day, after 30 minutes of quiet). The wave limit is
    room-wide, so the newcomers share this volume rather than multiply it.
  - Checked on `edge`.
  - The speakers' voice budget (`VOICE_MONTHLY_CHARS`) is **200,000** (the owner, 2026-10-20). It is live in `server/.env` at once, since the
  speakers had used ~62,000 in three days. The phase makes it the code default, the env examples and the compose
  default (pinned).
- **Automatic from the roster:** Hermes's members, the recording's voices, the panel's cards and the moves'
  addressees.
- **ARCHITECTURE:** the roster, the env names and the compose services. **VISION:** the newcomers rule — people who
  join come with a shared past.

**DoD:**
- (Manual, owner) Леон, Мія, Ірма and Кіра join Agora, talk in their own voices, ask and answer; Ada and Bruno know them.
- (Manual, owner) Over an evening the frictions surface and are argued with respect: Леон and Бруно about sound,
  Мія and пан Леон about the play and the facts, Ада and Мія about the manuscript, Ірма quoting who said what.
- (Manual, owner) Their stories agree with their life files, and neither knows the future.

**Tests:** unit:
- the roster with nine members, and the name forms distinct;
- the new canons and life stories: no banned word, chapters in order, the death never shown;
- the compose services and the env names.

**Not in this phase:** the radio theatre — a version of its own, from the owner's concept document.

### v5.6 — A private chat with a person (Кіра first)

**Status:** ✅ completed — released `v5.6.0` on 2026-10-21 (the owner's choices: the ability is a capability switched on for Кіра; she sometimes writes first; one memory, kept to herself in Agora; the next-day memory and writing-first checks waived by the release word).

**Goal:** the owner can talk with a person one-to-one, in a private chat beside Agora. It is the same person with
one memory: she answers in her own voice, now and then writes first, and remembers what was said there. In Agora
she keeps it to herself. The ability belongs to any person; it is switched on for Кіра first.

**Owner decisions** (2026-10-20):
- **Кіра first.** A capability any person may have (`private`), enabled only for Кіра for now.
- **She sometimes writes first.** Once or twice a day at most, after a long silence in the private chat, within
  the owner's hours. The message is something from her day or her plans.
- **One memory, kept to herself.** She remembers the private talk like any other: it goes into her session, day
  memories and plans. In Agora she never retells what was said privately. The others and Hermes never see it.

**Tasks:**
- **The capability `private`.** It is not in any type by default; a person's TOML enables it
  (`[capabilities] private = true`). Only Кіра's does.
- **The room:**
  - with `private`, the agent accepts the owner's invite into one direct room besides Agora;
  - it keeps the room's id in `state/<name>.private.json`;
  - any other invite is still refused.
- **The filter rule** (a contract). A message is handled from Agora under the existing rules, or from the agent's
  own private room when it comes from the owner. Everything else stays `ignored`; in the private room that
  includes any other sender.
- **The reply:**
  - every owner message in the private room is answered;
  - no turn-taking, no wave and no probability roll; a short typing delay;
  - in voice under the speakers' rules and budget (`send_line`), then the text;
  - the prompt is her own: her canon, life, memories, plans and today, a private brief («ви з Ich наодинці…»),
    and the private chat's last lines. Agora's history is not included.
- **The memory:**
  - the private lines go into her session and the day's conversation journal, marked as private
    («наодинці з Ich»), so the day memory and the plans know them;
  - her Agora prompt gains a discretion line: what was said privately stays private.
- **The initiative** (pure `private_nudge_due`, like the cat's nudges):
  - after `PRIVATE_IDLE_S` of silence in the private chat;
  - at most `PRIVATE_NUDGES_PER_DAY` a day;
  - within `PRIVATE_HOURS`;
  - the message is one short line from her day, today block or plans.

  All three are agent settings in the panel.
- **Untouched:**
  - Hermes never reads or digests the private chat;
  - the Agora recording reads Agora only;
  - the other agents never see it.
- **ARCHITECTURE:**
  - the filter and invite rules;
  - the `state/` file;
  - the capability and the settings;
  - the private prompt and the discretion line.
- **VISION:** a person may have a private chat with the owner.

**DoD:**
- (Manual, owner) The owner invites `@kira` into a direct chat. She joins and answers in her own voice, as the
  same Кіра.
- (Manual, owner) The next day she remembers what was said privately. In Agora she doesn't retell it.
- (Manual, owner) After a long silence she writes first, at most twice a day, only in the owner's hours.
- (Manual, owner) A stranger's message or another room is still `ignored`, and Ada and the others never answer in
  the private chat.

**Tests:** unit:
- the filter and invite rules (the private room, the owner only, one room, any other invite refused);
- the private reply path: no turn-taking, the voice rules;
- the prompt order with the private brief and history, and no Agora history;
- the journal marks private lines, and the discretion line is in the Agora prompt;
- `private_nudge_due` (idle, hours, the day's count, a restart never nudges at once);
- the capability only where enabled.

**Not in this phase:** a private chat for the other persons (a TOML switch later); the panel showing the private
chat; group chats beside Agora.

### v5.7 — Кіра in Telegram

**Status:** ⏳ planned.

**Goal:** the owner talks with Кіра from Telegram too. Her private chat gets a second door: her own Telegram bot,
the same conversation as the Element private chat (one history, one memory). Voice goes both ways: she answers
with Telegram voice notes and then the text, and she hears the owner's voice notes.

**Owner decisions** (2026-10-21):
- **In addition to Element, one conversation.** Telegram and the Element private chat share one private history
  and one memory. She writes first in the channel the owner used last.
- **Voice both ways.** Her answers are voice notes; the owner's voice notes are heard (Deepgram, as Hermes hears
  them) and always answered in voice.
- **Her own voice.** Every voice note is Кіра's own ElevenLabs voice (`KIRA_VOICE_ID`, the one the owner chose,
  kira-1), from the same text-to-speech pipeline as in Agora and the Element private chat — never another voice
  and never Telegram's.
- **Voice, then the text,** as two messages, like in Agora.
- **Not a full Matrix↔Telegram bridge** (mautrix-telegram with an appservice): for one person's private chat, her
  own bot is the simpler and safer door.

**How it works:**
- **The bot.** The owner creates it in @BotFather (the name «Кіра», her avatar as its photo, groups disabled) and
  gets its token. The token and the owner's numeric Telegram id go into `server/kira.env`: gitignored, 0600, read
  only by Кіра's container. Deepgram's key is copied there for her hearing.
- **No open port.** Кіра's process polls the Bot API itself (`getUpdates`, long polling) beside the Matrix sync —
  outbound HTTPS only, no webhook. A small client over `aiohttp` (`agents/telegram.py`, no new dependency), with the
  offset kept in `state/kira.telegram.json` so a restart never answers old updates.
- **The allowlist.** Only the owner's numeric id is handled. A stranger who finds the bot gets no answer, and is
  logged by update type only.
- **One private chat, two channels:**
  - A Telegram text, or a voice note heard by Deepgram, goes into the same private path as a message in the Element
    private chat: the private brief, the shared private history, her one memory labelled «наодинці».
  - The answer goes back to the channel it came from: `sendVoice` with the same pipeline (her own voice, the
    agent's TTS on `VOICE_ID` = `KIRA_VOICE_ID`, OGG/Opus), then
    `sendMessage` with the text, and «typing…» / «recording voice…» while she composes.
  - Writing first goes to the channel the owner used last.
- **Accounting.** Telegram itself costs nothing. Voice uses the speakers' budget and the `stt` lines for hearing.
  The logs never carry a word, a token or the owner's id.

**Tasks:**
- **`agents/telegram.py`.** The Bot API client:
  - `getUpdates` with the offset, `sendMessage`, `sendVoice` (multipart OGG), `sendChatAction`, `getFile` and the
    download (capped);
  - errors by status and never the token;
  - the pure parts: update parsing (text, voice, other), the allowlist, the offset.
- **The capability `telegram`** (a person with `private`), `[capabilities] telegram = true` for Кіра.
- **The runtime:**
  - the polling task beside the sync;
  - the shared private path, generalised to channels (`matrix` / `telegram`) with the reply going back to its
    channel;
  - hearing a voice note (download, Deepgram, an `stt` usage line);
  - `last_channel` in `state/kira.private.json` for writing first.
- **Config and deploy:**
  - `server/kira.env` (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_OWNER_ID`, `DEEPGRAM_API_KEY`) and its example;
  - compose: `kira` reads it;
  - `deploy.sh` syncs it at 0600.
- **ARCHITECTURE and VISION:**
  - Network: outbound HTTPS to `api.telegram.org`;
  - the private chat's channels;
  - the state file;
  - Security: the token, the allowlist, and Telegram is not end-to-end encrypted.

**DoD:**
- (Manual, owner) The owner writes Кіра's bot in Telegram: she answers with a voice note and then the text. The
  voice is hers, the same as in Agora.
- (Manual, owner) The owner sends a voice note: she hears it and answers in voice.
- (Manual, owner) One conversation: what was said in Telegram she knows in the Element private chat, and back.
  In Agora she still keeps it to herself.
- (Manual, owner) Another Telegram account writing the bot gets no answer.

**Tests:** unit, with aiohttp, Deepgram and ElevenLabs mocked:
- update parsing, the allowlist and the offset across a restart;
- the routing of an answer back to its channel, and writing first to the last channel;
- `sendVoice`'s multipart content, then the text; the note is synthesised by the agent's own TTS with Кіра's
  voice id;
- a voice note heard and answered in voice;
- no token, id or text in a log;
- the env file read only by `kira` (compose).

**Not in this phase:**
- a full Matrix↔Telegram bridge;
- Telegram for the other persons;
- Agora in Telegram;
- group chats.

### v5.8 — Кіра: Gemini 3.1 Pro, a memory of messages and facts about the owner

**Status:** ⏳ planned.

**Goal:** Кіра answers on Gemini 3.1 Pro and remembers like Noos (`~/claude-home`) does. When something comes up, she
recalls the past messages it touches, from Agora and from her private chat. She keeps short facts about the owner,
and the pinned ones are always in her mind when she talks with him. She knows everything that happens in Agora when
she talks with him alone, and in Agora she never talks about him.

**Owner decisions** (2026-10-25):
- **Both models.** Gemini 3.1 Pro for her answers, Gemini 2.5 Flash for her background calls. The other agents stay
  on their models.
- **A memory of messages and facts about the owner, as in claude-home.**
- **She remembers all of Agora in the private chat, and in Agora she says nothing about him.**
- **The embeddings come from Gemini**, through the client the agents already use: no new dependency.
- **The archive is filled from the chats** at its first start.
- **Her first facts come from Noos:** its pinned facts, and the extract of Лілі's memory about the owner that Noos
  keeps (`~/claude-home/memory/import/lumi/`).
- **This lifts a non-goal for her.** VISION excludes "raw archives of conversations, vector DBs and RAG". From v5.8
  a person with the `recall` capability keeps an archive of the lines she took part in and searches it. The layered
  digests stay the long-term memory of everyone else, and Hermes still keeps no copy.

**How Noos does it** (`~/claude-home/memory/`, read on 2026-10-25):
- **The archive.** Every transcript is indexed every 15 minutes into `sessions.db`: SQLite with an FTS5 table and,
  per chunk, an embedding from `paraphrase-multilingual-MiniLM-L12-v2` (fastembed, local ONNX). A chunk is up to
  1,400 characters with a 200-character overlap.
- **Search.** A hybrid: BM25 over FTS5 and cosine over the embeddings, 50 candidates each, merged by reciprocal rank
  fusion (k = 60). The top 8 fragments are returned with their date, role and session. Claude calls it itself when
  the owner refers to the past.
- **Facts.** `memory/facts/`, one Markdown file per fact, with a header holding `pin`, `tags` and `added`. Pin 1 is
  always in the system prompt, pin 2 is used when there is room, pin 0 is for search only. The store holds at most
  100 facts, the prompt at most 25, at most 240 characters each. The facts are indexed into the archive too.
- **Who adds a fact.** The session, by its persona's rule: when the owner says "remember", or when a long-lived fact
  about him surfaces. A stale fact is deleted, not piled up.

**How it works here:**
- **Two models.**
  - A new agent setting, `GEMINI_REPLY_MODEL`, is the model of her answers: in Agora, in the private chat, and when
    she writes first. Empty by default, which means `GEMINI_MODEL`; set to `gemini-3.1-pro-preview` for Кіра alone.
  - `GEMINI_MODEL` stays the model of everything else: the session summary, the day memory, the digests, the plans,
    the today block and the facts' extraction. For her that is `gemini-2.5-flash`.
  - A Pro model refuses a zero thinking budget, so a reply on it goes through the thinking path
    (`GeminiClient.think`, as Hermes's), with `GEMINI_THINKING_LEVEL` (`low` by default) and a token cap that leaves
    room for the thinking.
  - Each usage line names its model, and `PRICE_MODELS` prices the Pro lines (`gemini-3.1-pro-preview=2/12`).
- **The archive** (the capability `recall`).
  - `state/<name>.archive.db` is SQLite, 0600. Every line she sees is appended with its time, its place (`agora` or
    `private`), its channel (`matrix` or `telegram`) and its speaker: the Agora room's lines and both sides of her
    private chat. It is append-only and never pruned.
  - An FTS5 index makes a line searchable at once. Embeddings come from Gemini's embedding model
    (`gemini-embedding-001`, usage kind `embed`), added in batches by the idle watcher.
  - At the first start the archive is filled from the chats on the homeserver: the whole private room and Agora's
    last 1,500 lines (the owner, 2026-10-25).
- **Recall** (Noos's hybrid, without the tool call).
  - Before each reply, the message she answers is the query: BM25 and cosine, merged by reciprocal rank fusion.
  - The top `RECALL_N` (6) lines are given, each with its neighbouring lines, leaving out what is already in the
    prompt's history window.
  - They enter the prompt as «Тобі згадується: …», each with its date and place («в Агорі, 12 жовтня» or
    «наодинці, …»).
  - The fusion and the pick are pure functions over plain data.
- **Facts about the owner** (the capability `facts`, which needs `private`).
  - `state/<name>.facts/` holds one file per fact, in Noos's format: `pin`, `added`, `source`, then the text, at most
    240 characters. The store holds at most 100 facts and the prompt at most 25.
  - **Extracted.** At the end of a session, beside the summary, one call reads the session's lines and the current
    facts. It returns new facts and the replacements of stale ones as JSON, validated before anything is written
    (usage kind `facts`).
  - **Asked for.** When the owner asks her to remember something, she understands it from the conversation, not
    from a keyword (as Hermes's skills): her answer ends with a marker line holding the fact. The code validates it,
    strips it before sending and stores the fact as pin 1.
  - **In the prompt.** Only her private prompt carries the pinned facts, «Що ти знаєш про нього: …», after the today
    block. They are also searchable by recall in the private chat.
  - A stale fact is replaced. "Nothing lived is deleted" covers the memories, digests and plans; a fact is current
    knowledge, not something lived.
- **Her first facts, from Noos** (the owner, 2026-10-25). A one-shot import, run by the owner on the host when v5.8
  is deployed:
  - Its sources are Noos's `memory/facts/` (21 facts: 7 at pin 1, 14 at pin 2 on 2026-10-25) and
    the extract in `memory/import/lumi/` (Лілі's memory of the owner, about 20 KB in 12 sections).
  - Only those two directories are mounted, read-only, into a one-off run of Кіра's image. Noos's
    `config.local.json` and `.env.*` are never reachable.
  - One Flash call (usage kind `facts`) condenses them into facts in her format, each at most 240 characters,
    without duplicates, within the store's limit. Noos's pins are kept; the extract's identity facts go to pin 1 and
    the rest to pin 2 or 0.
  - It keeps what is about the owner as a person: his life, family, work, interests, character, values and daily
    life. It drops what is about servers, tokens, permissions, and agents, bots or simulations by name (Agora, its
    members, Лілі, Noos), so no fact tells a persona what she is.
  - `--dry-run` prints what would be kept, for the owner to read first. Each fact is marked `source: noos`, and a
    second run adds nothing it has already imported.
  - The facts live only in `state/` on the host: never in the repo, which is public, nor in a log.
- **Agora in the private chat.**
  - Her private prompt also carries Agora's latest lines of today (`PRIVATE_AGORA_N`, 20) as «Що зараз в Агорі».
  - Recall there searches both places.
- **Not about the owner in Agora.**
  - An Agora prompt never carries a fact or a private line. Recall there searches only `agora` lines, in code, not
    by an instruction.
  - The discretion line widens. In Agora she never tells what she knows about the owner personally, nor what they
    said alone; she speaks to him as anyone in the room does.
  - Her memories keep the private lines labelled «наодинці», as in v5.6.
- **The panel.**
  - The drawer gains a **Facts** tab: each fact with its pin, source and date. The owner can re-pin a fact or delete
    it (confirmed).
  - Her card shows the archive's size: the lines, and how many are embedded.

**Tasks:**
- `agents/llm.py`:
  - the reply on `GEMINI_REPLY_MODEL`, through the thinking path when it is a thinking model;
  - `GEMINI_THINKING_LEVEL`;
  - the embedding call (usage kind `embed`).
- `agents/settings.py`:
  - `GEMINI_REPLY_MODEL` (an agent setting; its choices include `gemini-3.1-pro-preview`);
  - `GEMINI_THINKING_LEVEL`;
  - `RECALL_N` and `PRIVATE_AGORA_N`;
  - the facts' limits.
- `agents/archive.py`: the SQLite store (append, FTS5, embeddings, the backfill) and the pure fusion and pick.
- `agents/facts.py`:
  - the store and its limits;
  - the prompt block;
  - the marker line's parsing and stripping;
  - the extraction call and its validation;
  - the one-shot import from Noos (`python -m agents.facts import`, with `--dry-run`), and the owner's command for
    it in the deploy notes.
- The runtime and the prompt assembly:
  - the archive written from every line she sees;
  - recall in both prompts, with the place filter;
  - the facts and «Що зараз в Агорі» in the private prompt;
  - the widened discretion line;
  - the extraction at session end.
- `kira.toml`: `recall = true` and `facts = true`.
- The panel:
  - the Facts tab, with re-pin and delete;
  - the archive's size on the card.
- **VISION and ARCHITECTURE:**
  - the non-goal narrowed for a person with `recall`;
  - §Memory;
  - the prompt order;
  - the state files `<name>.archive.db` and `<name>.facts/`;
  - the usage kinds `embed` and `facts`;
  - the settings.

**DoD:**
- (Manual, owner) The Tokens view shows Кіра's answers on `gemini-3.1-pro-preview`, priced, and her background calls
  on `gemini-2.5-flash`. The others stay on their models.
- (Manual, owner) After the import, the Facts tab lists the owner's facts from Noos, and none of them is about
  servers, agents or bots.
- (Manual, owner) In the private chat the owner refers to something said a week ago, beyond the history window, and
  she recalls it.
- (Manual, owner) «Запам'ятай, що …»: the fact appears in the Facts tab, and she knows it in a later conversation.
  Deleted in the panel, it is gone from her next answer.
- (Manual, owner) Alone with the owner, she knows what was just said in Agora.
- (Manual, owner) In Agora, asked about the owner by another member, she does not tell what she knows of him or what
  they said alone.

**Tests:** unit, with Gemini mocked and SQLite in memory:
- the two models: an answer on `GEMINI_REPLY_MODEL` through the thinking path (no zero budget, the level), a
  background call on `GEMINI_MODEL`, an empty reply model meaning `GEMINI_MODEL`, and each usage line's model and
  price;
- the import: Noos's fact files and the extract's sections parsed, the condensed facts validated and deduplicated,
  the pins, a second run adding nothing, `--dry-run` writing nothing;
- the archive: append, the full-text search, the embeddings batched, the bounded backfill;
- the fusion and the pick: the order, the neighbours, the history window left out, and the place filter;
- the facts: the limits, the pins in the prompt block, the marker line parsed and stripped and never sent, the
  extraction's validation, a replacement instead of a duplicate;
- an Agora prompt never carries a fact or a private line, even when the archive matches;
- the private prompt's order: the facts, «Що зараз в Агорі», recall;
- the panel API: the Facts tab, re-pin and delete (same-origin, confirmation), and an unreadable store never a 500.

**Not in this phase:**
- the archive and facts for the other agents (each becomes a capability, later);
- a live sync with Noos's facts (the import is one-shot);
- sharing facts between agents.

## v6 — Applications: the panel's System and Applications

The owner, 2026-10-25: the panel stops being "a simulation and its agents". **Simulations become applications**:
places where agents meet the owner or each other, each reached over one protocol (Agora today, Telegram next, later
RoboFace). An application shows **who is connected to it and in which context** (`room`, `listens`, `private`).
**System** holds what is not tied to one application: **Agents**, **Server** and **Tokens**. The model makes room for
agents reachable in several places (Кіра in the room, in her private chat and in Telegram) and for external agents
(Лілі in v8, later Noos). The owner's decisions (2026-10-25): the rename goes everywhere; each agent writes the
status of its connections so the panel can monitor them; the panel switches a declared connection on and off and
configures it, and the repo declares it; a switched-off connection keeps everything in a buffer and gives the
backlog one answer; Hermes's contexts are `listens` and `digests`; alerts come later. The design and its decisions
are in [features/applications.md](features/applications.md) (draft; its open questions closed by the owner on
2026-10-25); read it before generating the issues. Depends on: v5 (v5.7 for v6.2).

### v6.1 — System and Applications: the panel's new shape

**Status:** ⏳ planned.

**Goal:** the panel is reorganised into **Applications** (Agora) and **System** (Agents, Server, Tokens). Agora's
page lists every connected agent with its contexts and monitors each connection. No new application; the agents
talk as before and gain only the status file.

Design: applications.md §The model, §The panel, §Monitoring.

**Tasks:**
- **The rename** (the owner: everywhere). "Simulation" becomes "application" throughout: `simulations.toml` → `applications.toml` (the same
  entry shape), `agents/registry.py` and `panel/registry.py`, the agent TOML key `simulation` → `application`
  (`simulation` still read in v6.1, with a log line naming it), the Dockerfiles' copy, the API
  (`/api/applications…`; the `/api/simulations…` routes are removed, since the panel is their only client).
  `state/settings.json` keeps its shape: its keys are the ids, and `agora` does not change.
- **Contexts.** A pure function over the roster: a member's contexts in the base application (Agora). It returns
  `room` with its turn mode and weight, `listens` for a herald, `private` for the `private` capability, and
  `digests` for a herald's one-to-one room (the owner: `private` means only a person's private chat). The agent
  view carries `connections`: the application, its contexts, the container state and the status.
- **Monitoring** (the owner, 2026-10-25):
  - every agent writes `state/<name>.connections.json` with its `agora` entry: its Matrix user id; the state
    (`ok`, `retrying`, `error`) and the last error's time and kind; the last successful sync as the heartbeat; per
    context the day's `in`, `out` and `ignored` and the last in and out times;
  - the heartbeat is written at most once a minute (`STATUS_EVERY_S`) and at once on a change of state; the write is
    atomic, 0600, with no texts or ids, and a failed write is logged and never blocks the conversation;
  - the agent reads the file back only at start, to carry on the day's counts; no decision and no other agent reads
    it;
  - the panel's pure status function over the switch, the container state, the entry and an injected clock: `off`,
    `stopped`, `stale` (no heartbeat for 3 min while running), `retrying`, `error`, `ok`;
  - Agora's health warns when a running member is `stale`, `retrying` or `error`.
- **The panel UI:**
  - the rail: Applications (Agora) and System (Agents, Server, Tokens);
  - the application page: health, services with their actions, a **Connected** table (agent, contexts, status,
    today's in · out, container state), the application's settings (v4.7, unchanged);
  - System → Agents: the agent cards no longer nested under an application, each with its connections as chips
    with their status dots;
  - the agent drawer gains a **Connections** tab: per context the counts, `ignored`, the last in and out, the last
    error;
  - every v3.4/v4.7 action (start/stop/restart, forget, settings, Claude's files) works from its new place.
- **The design addendum (v6)** in `specification/design/README.md`: the rail, the application page, System →
  Agents, and the Connections table and tab.
- **VISION and ARCHITECTURE:**
  - the direction and the principle "the panel is the centre": applications;
  - the glossary: application, base application, connection, context, external agent;
  - the non-goal "a second simulation" is retired (the owner, 2026-10-25);
  - §The panel: monitoring, and "only what is recorded" names the status file as the one thing an agent writes for
    the panel;
  - the contracts: the registry, the TOML key, the API surface, the status file.

**DoD:**
- (Manual, owner) The panel shows Applications → Agora and System → Agents / Server / Tokens.
- (Manual, owner) Agora's page lists the nine members with their contexts: Кіра with `room` and `private`, Hermes
  with `listens` and `digests`, Kit `ambient`, Claude `ranked` 0.4.
- (Manual, owner) Each running member shows `ok` with a sync seconds old, and today's in · out grow as the room
  talks; a stopped member shows `stopped`.
- (Manual, owner) Start, stop, restart, forget, the settings of Agora and of an agent, and Claude's files all work
  from their new places.
- An agent TOML with the old `simulation` key still starts.

**Tests:**
- unit: the registry loads `applications.toml`, an unknown id is an error, and the old TOML key is read;
- unit: the contexts of every member type: persona, creature, assistant, herald, and a person with `private`;
- unit: the status writer: the shape, the heartbeat at most once a minute, an immediate write on a change of state,
  no text or id, a failed write logged; the day's counts carried over a restart and reset on a new day;
- unit: the panel's status function in every case, with an injected clock; an unreadable status file → unknown,
  never a 500;
- the panel API: `/api/applications…`, an unknown application is 404, `/api/simulations…` is gone, the agent view's
  `connections` with their status;
- compose and Dockerfile: the image carries `applications.toml`.

**Not in this phase:** a second application; switching or configuring a connection; external agents.

### v6.2 — Telegram as an application: Кіра connected

**Status:** ⏳ planned.

**Goal:** Telegram is the second application. Кіра's bot from v5.7 becomes her **connection** to it: declared in
the registry, then switched on and off and configured from the panel. It is still the same private conversation as
in Agora.

Design: applications.md §Rules, §Connection settings, §Applications after v6 → Telegram.

**Tasks:**
- **The registry.**
  - `[telegram]`: kind `telegram-bot`, no services;
  - `[telegram.connections.kira]` with `contexts = ["private"]`;
  - validation: a `private` context needs the agent's `private` capability, and an unknown agent or context is an
    error by name.
- **The migration.** v5.7's `[capabilities] telegram = true` is retired. The roster names it as an error with the
  fix ("declare the connection in the registry"); `kira.toml` loses the line.
- **Connection settings.**
  - The schema `agents/settings.py` gains a **connection** scope: settings of an application kind (`telegram-bot`),
    each value belonging to one connection.
  - v6.2 moves into it what v5.7 fixes in code or env for Кіра's Telegram (the owner agreed, 2026-10-25): answering
    with a voice note and the text, or with the text only; whether she may write first there; whether she shows
    «typing…» and «recording voice…».
  - Precedence as in v4.7: code default < env < panel. Secrets are never in the schema.
- **`state/settings.json` gains `connections`:** per application and agent, `enabled`, `since` (the moment it was
  last switched on) and the setting overrides. The panel writes it; the agent only reads it.
- **The agent:**
  - at start, it reads its connections from the registry and their switch and settings from `state/settings.json`;
  - **switched off, it keeps everything** (the owner, 2026-10-25). The poller keeps running; it does not answer
    and does not write first in Telegram. Each update from the owner goes into
    `state/<name>.telegram.buffer.jsonl` (the text, or the voice note's file id; 0600; never in a log) and is then
    confirmed to Telegram. A stranger's update is never buffered;
  - switched back on, she reads what waited, in order, and gives one answer to all of it, as a person answers a
    backlog, hearing the buffered voice notes then. The messages join the private history, and the buffer is
    emptied;
  - while Telegram is off and was the owner's last channel, she writes first in the Element private chat;
  - it adds its `telegram` entry to the status file: the bot's `@username` from `getMe`; the poll as the heartbeat;
    `retrying` on a network error; `error` on a refusal (401), with the poller stopped; `off` with the number
    `buffered`; the day's counts, with a stranger counted as `ignored`.
- **The panel:**
  - Applications → Telegram:
    - health from its connections' statuses: all switched-on ones `ok` → ok; one `stopped`, `stale`, `retrying` or
      `error` → a warning; all switched off → off;
  - the Connected table: agent, the bot's `@username`, context «private · the same chat as in Agora», status
    («polled 12 s ago», or «off · 3 waiting»), today's in · out, last in · out, on since, container state;
  - each row: **switch off/on** (confirmed) and **configure** (the connection's settings, validated against the
    scope);
  - a save writes its part of `state/settings.json` and restarts the agent if it is running, as the v4.7 settings do;
  - the connection's log: the agent's log filtered to its `telegram:` lines;
  - no token or owner id anywhere; a connection is never created from the panel.
- **Tokens by application.** A usage line carries `app` (`agora` | `telegram`; older lines count as `agora`). The
  Tokens table and chart group by application, then by agent.
- **ARCHITECTURE:**
  - §The panel: applications without services, and the connection actions;
  - §Contracts: the registry's `connections`, the connection scope of the settings schema, `settings.json`'s
    `connections`, the status file's `telegram` entry, the buffer file, the API routes, the usage line's `app`, the
    retired capability.

**DoD:**
- (Manual, owner) The panel shows Applications → Telegram with Кіра connected, in the context `private`: the bot's
  username, a poll seconds old and today's counts. A message in Telegram moves its last in · out.
- (Manual, owner) Switched off from the panel, the bot does not answer, and the row shows how many messages wait.
  Switched back on, she answers what was sent while it was off.
- (Manual, owner) A connection setting changed in the panel (for example the text only instead of a voice note)
  holds after her restart.
- (Manual, owner) Still one conversation: what was said in Telegram she knows in the Element private chat, and back.
- (Manual, owner) The Tokens view shows Кіра's Telegram traffic under `telegram`.

**Tests:**
- unit: the registry's connections and their validation, and the retired capability named as an error;
- unit: the connection scope: validation, bounds, a name from another scope → 422, the precedence;
- unit: the switch and the settings read from `settings.json`;
- unit: the buffer: updates kept while off and confirmed to Telegram, a stranger never kept, the backlog answered
  with one answer, read in order, on the switch-on and then emptied, writing first in Element while Telegram is off;
  no text in a log;
- unit: the `telegram` status entry: the account from `getMe`, the heartbeat on a poll, `retrying`, `error` with the
  poller stopped, `off` with `buffered`, a stranger counted as `ignored`; no token, owner id or text in the file;
- the panel API: the Telegram view, the switch and the settings (same-origin, confirmation, 409 when busy, 404 for
  an unknown connection), the restart of the concerned agent only;
- usage: the `app` field, old lines as `agora`, the grouping.

**Not in this phase:** Telegram for the other persons (each becomes a registry entry, a bot and an env file);
RoboFace; external agents; creating a connection from the panel; alerts on a failed connection (later: Hermes tells
the owner).

## v7 — Theatre: plays on the Stage

**Status:** ⏳ planned.

The owner, 2026-10-25: the radio theatre is v7. The members of Agora perform audio plays together in a second room,
the Stage, and Hermes records each play into one file. The design, its phases and its open questions are in the
draft [features/radio-theatre.md](features/radio-theatre.md) (Ukrainian copy: `radio-theatre-UA.md`). Its phases
are written into this file once its open questions are closed. Its first proposed phase, the three new personas,
shipped as v5.5. Depends on: v5.4 (the Agora recording) and v6 (in the v6 model the Stage is a second room of the
Agora application).

## v8 — Лілі: the Lumi bridge

Лілі — Lumi's prod brain — joins the room through a bridge that is one of our agents: first when named, then under
the full turn rules. Moved from v4.8–v4.9 by the owner on 2026-10-13, after the voice of v5, and from v6 to v8 on
2026-10-25, after v6 Applications and v7 Theatre. In the v6 model she is an **external** agent under System →
Agents, connected to Agora in the `room` context (applications.md §Лілі). Depends on: Lumi ≥ v2.5 in prod (v2.6 puts
her server on 192.168.1.197), v4 and v6.

### v8.1 — The Lumi bridge: Лілі when named

**Status:** ⏳ planned.

**Goal:** Лілі — Lumi's prod brain — answers in the room when someone names her, through a bridge that is one of our agents.

Design: more-agents.md §Lumi (the bridge). The bridge is a process that tails the room and forwards the changes to Лілі's server; she answers, deciding herself whom and what. It behaves like our agents, with all the room's rules. Лілі is reactive: she only answers and never starts a conversation. **Depends on Lumi ≥ v2.5** (prod runs her server with Telegram, thoughts and the scheduler inside it); from Lumi v2.6 her server runs on 192.168.1.197 itself. Depends on: v4.1 (v4.2 for the scoped human-belief rule), v4.6 review #4 (the `ask` addressee filter: a mention-only bridge is not asked by the personas).

**Tasks:**
- The `bridge` type; `agents/lumi.toml` (shown as «Лілі»; name forms for both «Лілі» and «Стхіра»; `engine = "lumi-http"`; `[turns] mode = "mention-only"`, weight 1).
- `LumiBridgeResponder`: when a message names her, `POST /v1/turn` with the room lines since her last turn as `"Name: text"`, `turn_id` = the trigger's `event_id`; only `reply` is posted, never `thinking`; never `/v1/session/new`; `409`/`5xx`/timeout → silence; her reply is never dropped or trimmed after the call (R3 before the call only); the bridge never posts except in reply to a trigger.
- The `lumi` compose service with its own env file (`LUMI_URL`, `LUMI_TOKEN`) and the route to her server on the same host (`extra_hosts: host-gateway`); usage rows `external` from her `stats`.
- **Лілі's panel card** (under System → Agents, `external`; v6): Lumi's reachability (`/v1/health`), the last turn's outcome from `state/lumi.bridge.json`; never her `thinking`, mood or replies; her token rows unpriced; no memory tabs, no Forget.
- VISION: the "Lili herself" wording becomes "connected through the bridge".
- (Owner) The Matrix account, the invite; Lumi's server token and her bind address.

**DoD:**
- (Manual, owner) Лілі's card appears in the panel, and start/stop/restart of the bridge work from it.
- (Manual, owner) Named («Лілі», «Стхіро»…), she answers in the room; unnamed, she stays silent; her `thinking` never appears in the room, the logs or the panel.
- (Manual, owner) While the owner talks to her privately, the room gets silence (`409`), never an error.
- She never posts on her own.

**Tests:** unit — the bridge against a fake Lumi server (turn payload with the lines since her last turn, `turn_id`, `409`, `5xx`, timeout, `thinking` never posted, no post-call filtering, no post without a trigger), mention detection for both names, the env-file isolation, `external` usage rows.

### v8.2 — Лілі under the full rules

**Status:** ⏳ planned.

**Goal:** Лілі takes part in the room like Ada and Bruno — chosen by the turn-taking, not only when named.

Design: more-agents.md §Lumi (the bridge), §4. Depends on: v8.1, proven in the room.

**Tasks:**
- `agents/lumi.toml`: `[turns] mode = "ranked"`, weight 1 — she joins R1 (`OWNER_REPLIERS`) and R2 (the next speaker).
- Each time she is chosen, the bridge forwards the chat updates since her last turn; the slow-engine rules apply (R3 only before the call, the fallback after `FALLBACK_S` when she is away or busy).

**DoD:**
- (Manual, owner) On unnamed messages Лілі answers about as often as the others; when she is away or busy, the fallback answers instead and the room never stalls.
- A simulated wave with Лілі ranked never exceeds `MAX_BOT_TURNS` beyond the answers to the owner.

**Tests:** unit — ranking with her in it, R3 and the fallback for a slow or unreachable bridge, the multi-agent simulation with her ranked.
