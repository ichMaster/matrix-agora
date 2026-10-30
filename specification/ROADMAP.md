# Roadmap — matrix-agora

Ten self-contained versions, built in order: **v0** Platform (homeserver, server deploy, client, accounts, echo bot) → **v1** Conversation (Gemini replies, three-way turn-taking) → **v2** Persona & memory (canons, session memory, world awareness) → **v3** Operations (token accounting, agent images + CI/CD with server deployment, the panel — viewing, then control) → **v4** Ensemble (agent types and N-agent turn-taking; then the cat and Claude, each in two steps; the personas' curiosity; the agents' settings in the panel) → **v5** Voice (Hermes's voice digests for the owner; the agents hear voice messages, then answer in voice; Кіра's private chat, in Telegram too, her memory of messages and facts, her voice with emotion, her mood of the day, the events of her life, her reading and thoughts, and a backup model for her private chat when Gemini blocks) → **v6** Лілі (the Lumi bridge: when named, then under the full rules) → **v7** Applications (the panel's System and Applications; Telegram as an application) → **v8** Кіра's inner life (her state and voice, her feelings and behaviour, anticipation) → **v9** Theatre (plays on the Stage, recorded by Hermes). Phases inside a version are numbered `vA.B` (A = version, B = phase). Each phase lists a **Goal**, a short description, a **Tasks** list, a **Definition of Done (DoD)**, and the **Tests** that encode its DoD (see [ARCHITECTURE.md](ARCHITECTURE.md) §Testing and CI). Phases are built strictly in file order; each one builds on the previous one's real, released code.

**Versioning (`A.B.C`).** `A` = roadmap version (v0→0 … v9→9), `B` = phase within it, `C` = a post-release fix on that phase. Roadmap phase `vA.B` → release `A.B.0`, tag `vA.B.0`; a fix after it bumps `C`. Releases are cut per phase. Never bump a version without explicit confirmation.

Many DoD items need the live homeserver, Element or a real Gemini key — those are **Manual (owner)** checks: the owner performs or confirms them, and only then do they count as passed. Everything automated runs with `matrix-nio` and `google-genai` mocked and the clock injected (no network, no paid calls).

---

## Status

v0–v4 are complete, delivered through `v4.7.1` (2026-10-13). v5 is complete through v5.13, released as `v5.13.0`
(2026-10-28). Next come v5.14–v5.15, the rest of the backup for Кіра's private chat, then v6–v9 in order. Other further work (the
deferred backlog items in the code-review docs, new simulations) needs new phases.

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
| v4.5 | Claude the philosopher | ✅ completed | `v4.5.0` (2026-10-11) + `v4.5.1`, `v4.5.2` |
| v4.6 | Ada and Bruno: curiosity, plans and stories | ✅ completed | `v4.6.0` (2026-10-11) |
| v4.7 | Agent settings and Claude's files in the panel | ✅ completed | `v4.7.0` (2026-10-11) + `v4.7.1` |
| v5.1 | Hermes: voice digests for the owner | ✅ completed | `v5.1.1` (2026-10-18) |
| v5.2 | The agents hear voice messages | ✅ completed | `v5.2.0` (2026-10-18) |
| v5.3 | The agents answer in voice | ✅ completed | `v5.3.0` (2026-10-19) |
| v5.4 | The Agora recording, on request | ✅ completed | `v5.4.0` (2026-10-20) |
| v5.5 | Four more people: пан Леон, Мія, пані Ірма and Кіра | ✅ completed | `v5.5.0` (2026-10-20) |
| v5.6 | A private chat with a person (Кіра first) | ✅ completed | `v5.6.0` (2026-10-21) |
| v5.7 | Кіра in Telegram | ✅ completed | `v5.7.0` (2026-10-25) |
| v5.8 | Кіра: Gemini 3.1 Pro, a memory of messages and facts about the owner | ✅ completed | `v5.8.0` (2026-10-25) + `v5.8.1`, `v5.8.2` |
| v5.9 | Кіра's voice with emotion: ElevenLabs audio tags | ✅ completed | `v5.9.0` (2026-10-25) + `v5.9.1`–`v5.9.3` |
| v5.10 | Кіра's mood of the day: the horoscope, the biorhythms and the Lviv weather | ✅ completed | `v5.10.0` (2026-10-27) |
| v5.11 | Events of her life: known, generated every hour, and Lviv's news | ✅ completed | `v5.11.0` (2026-10-28) |
| v5.12 | Кіра reads the news and thinks | ✅ completed | `v5.12.0` (2026-10-28) |
| v5.13 | Gemini's blocks named: the stage, the reason and the category | ✅ completed | `v5.13.0` (2026-10-28) |
| v5.14 | Her private chat past a Gemini block: GLM-4.6 on NovelAI, the censored mark and the route | ⏳ planned | — |
| v5.15 | The judge: Gemma 4 31B rates the backup's talk | ⏳ planned | — |
| v6.1 | The Lumi bridge: Лілі when named | ⏳ planned | — |
| v6.2 | Лілі under the full rules | ⏳ planned | — |
| v7.1 | System and Applications: the panel's new shape | ⏳ planned | — |
| v7.2 | Telegram as an application: Кіра connected | ⏳ planned | — |
| v8.1 | The moment and the day: her state and her voice | ⏳ planned | — |
| v8.2 | Feelings, open threads and her behaviour | ⏳ planned | — |
| v8.3 | Anticipation and strong memories | ⏳ planned | — |
| v9.x | Theatre: plays on the Stage (phases from features/radio-theatre.md) | ⏳ planned | — |

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

The room grows from two Gemini personas to four agents of three types (from v4.6 the personas grow curious; from v4.7 the agents' settings move into the panel): Ada and Bruno (`persona`), the cat Кіт (`creature`) and Claude (`assistant`); Lumi (`bridge`) joins in v6. The newcomers are openly non-human; Ada and Bruno keep believing they are human. One owner message must stay a few short replies, not two pages. The full design, its decisions and its open questions live in [features/more-agents.md](features/more-agents.md) (draft); each phase lands its ARCHITECTURE and VISION changes and the tests that pin them, per that document's contract list. Depends on: v3 (the images, compose, the panel).

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

**Status:** ✅ completed — released `v5.7.0` on 2026-10-25 (her bot `@ich_kira_bot`; a text answered in voice then text and a voice note heard, confirmed by the owner's use; one conversation with Element and no answer to another account waived by the release word; six code-review fixes, #5 carried into v5.8).

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

**Status:** ✅ completed — released `v5.8.0` on 2026-10-25 (her answers on Pro; the archive and recall; facts seeded from her own private chat, not from Noos, and filtered by `off_limits` (the owner); «Update now» added mid-phase as AGORA-116; ten code-review fixes, #5/#9/#12 deferred).

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
- **Her first facts come from her own private chat with the owner**, not from Noos (the owner, 2026-10-25, after reading the Noos import's dry run: «не все потрібно Кірі, вона думає, що вона людина … виберемо факти тільки з чату з Кірою»). No fact she keeps names AI, agents, bots, models, servers or his exact address.
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
- **Her first facts, from her private chat** (the owner, 2026-10-25; it replaces the Noos import planned first). A one-shot seed, run by the owner on the host when v5.8 is deployed:
  - `python -m agents.facts seed [--dry-run]` reads the private chat from her archive (both doors, oldest first) and runs the session-end extraction over it in chunks of 150 lines, each chunk seeing the facts kept so far.
  - Every fact, here and at every session's end, passes `off_limits`: one that names AI, agents, bots, models, servers, networks or tools, or an exact address, is dropped in code, whatever the model answered.
  - `--dry-run` prints what would be kept and what was dropped, for the owner to read first; then the same without it. Each fact is marked `source: private`.
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
  - the one-shot seed from her private chat (`python -m agents.facts seed`, with `--dry-run`), and the owner's
    command for it in the deploy notes;
  - `off_limits`: no fact about AI, agents, bots, models, servers or an exact address, at the seed and at every
    extraction.
- The runtime and the prompt assembly:
  - the archive written from every line she sees;
  - recall in both prompts, with the place filter;
  - the facts and «Що зараз в Агорі» in the private prompt;
  - the widened discretion line;
  - the extraction at session end;
  - the private history seeded at start from the archive, both doors, instead of the Element room alone; writing
    first decided from the time of the last private message, not from an empty history (v5.7 code review #5).
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
- (Manual, owner) After the seed, the Facts tab lists facts about the owner from their private chat, and none of
  them is about AI, agents, bots or servers.
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
- the seed: chunks that see the facts kept so far, `off_limits` at the seed and the extraction, `--dry-run` writing
  nothing, an invalid answer skipping its chunk;
- the archive: append, the full-text search, the embeddings batched, the bounded backfill;
- the fusion and the pick: the order, the neighbours, the history window left out, and the place filter;
- the facts: the limits, the pins in the prompt block, the marker line parsed and stripped and never sent, the
  extraction's validation, a replacement instead of a duplicate;
- an Agora prompt never carries a fact or a private line, even when the archive matches;
- the private prompt's order: the facts, «Що зараз в Агорі», recall;
- the panel API: the Facts tab, re-pin and delete (same-origin, confirmation), and an unreadable store never a 500.

**Not in this phase:**
- the archive and facts for the other agents (each becomes a capability, later);
- facts from Noos (the owner chose her own chat instead);
- sharing facts between agents.

### v5.9 — Кіра's voice with emotion: ElevenLabs audio tags

**Status:** ✅ completed — released `v5.9.0` on 2026-10-25 (her palette of ten tags verified on her voice; Кіра on `eleven_v4_turbo` at stability 0.3; tags to the voice, plain words to every text; the panel's Models field and Voice tab added mid-phase as AGORA-121; six code-review fixes, #7–#9 deferred, #10 the owner's).

**Goal:** Кіра's voice laughs, sighs, wonders and whispers where her line asks for it. She writes one or two audio
tags from a palette verified on her voice, and her voice performs them. Everyone reads her plain words.

**Owner decisions** (2026-10-25):
- **Emotion in her voice through ElevenLabs audio tags**, Кіра first; the other voices stay as they are.
- **The findings are re-measured first, on her real voice, in this repository.** They were measured in the Noos
  session of 2026-10-21; the re-measurement is in [features/voice-emotion.md](features/voice-emotion.md):
  - today's `eleven_turbo_v2_5` reads tags aloud;
  - `eleven_v4_turbo` performs them and takes `language_code: "uk"`;
  - a laughter ladder adds about 40% of breath and laughter;
  - the two models cost the same on this account.
- **The text keeps no mark of the tags**: no emote, no emoji. The text is her words alone.
- **Her English and Scottish inserts stay as she writes them**; they sound right on v4.
- **A persistent emotion state is later**: her voice settings stay fixed in this phase.

**How it works:**
- **One pass.** She writes the tags herself in her reply, with no second model call. The capability `emotion` (a
  person's only, on in `kira.toml`) gives her prompts, in Agora and in the private chat through both doors, a small
  block:
  - **the palette verified on her voice:** `[starts laughing]`, `[laughs]`, `[laughs harder]`, `[wheezing]`,
    `[chuckles]`, `[surprised]`, `[thoughtful]`, `[hesitant]`, `[whispers]`, `[sighs]`;
  - **the budget:** one or two tags a reply, most replies none;
  - **the placement:** a tag before the clause it governs, laughter climbing over short clauses, never spelled out
    next to a ladder;
  - **the rule:** nothing in brackets but the palette.

  The palette lives in `agents/canon/kira.voice.md`, named by the TOML key `voice_spec`.
- **The split** (`agents/emotion.py`, pure): `split_tags(reply)` returns the text, with the tags removed and nothing
  in their place, and the speech, the reply as written. A bracket that is not a tag (`[1]`, `arr[i]`) stays in both.
- **Her model and settings, per agent:**
  - `ELEVENLABS_MODEL` defaults to `eleven_turbo_v2_5`, so the others and Hermes are unchanged; Кіра's `kira.env`
    sets `eleven_v4_turbo`;
  - `VOICE_STABILITY` and `VOICE_SPEED` take the recipe the owner picked by ear: 0.3 and 1.0.
- **The safety rule.** A model not in `TAG_MODELS` never receives a bracket: its speech is the text.
- **Where each part goes:**
  - the synthesiser gets the speech, in Agora, the Element private chat and Telegram;
  - the message and everything kept get the text: her history, the session, the summary, the archive, the facts and
    the other members' transcripts;
  - a line that goes out as text only sends the clean text.
- **Hermes's recording is unchanged.** Her voiced lines arrive as audio with the tags performed, and her text has no
  tags.
- **Accounting.** The `tts` usage line counts the characters sent, tags included, and names the model. The
  `TTS_MODEL` comment about the cost is corrected.

**Tasks:**
- `agents/emotion.py`: the palette loader, `split_tags`, `TAG_MODELS`.
- `agents/voice.py`: `ElevenLabsTTS` takes the model and the settings per agent, plus the safety strip.
- `agents/agent.py`:
  - the palette block in her prompts;
  - `send_line` and `send_telegram` split each line;
  - history, the session, the archive and the facts take the text.
- `agents/roster.py`: the capability `emotion` and the TOML key `voice_spec`.
- `agents/settings.py`: `ELEVENLABS_MODEL`, `VOICE_STABILITY`, `VOICE_SPEED`.
- `kira.toml`, `agents/canon/kira.voice.md`, `server/kira.env.example`.
- ARCHITECTURE: §Voice, §Contracts (the capability, the TOML key, the settings, the env names).

**DoD:**
- (Manual, owner) In the private chat and in Telegram, a line of hers that laughs is a voice note in which she
  laughs, and its text carries no bracket and no mark.
- (Manual, owner) In Agora her voiced lines carry the same emotion; the other members' voices are unchanged.
- (Manual, owner) The Tokens view shows her `tts` lines on `eleven_v4_turbo`.

**Tests:** unit, with ElevenLabs mocked:
- `split_tags` on the edge cases: known, invented and non-tag brackets, a ladder, extra spaces;
- the synthesiser gets the tags and the message does not, on every path;
- a tag-less model never receives a bracket;
- no bracket in the history, the session, the archive or another member's transcript;
- the palette block only for `emotion`, with no banned word;
- the per-agent model and settings.

**Not in this phase:**
- the emotion state (valence, arousal, fatigue, decaying between turns);
- tags for the other voices (each needs its own calibration);
- a second «director» pass;
- marks of emotion in the text (the owner).

### v5.10 — Кіра's mood of the day: the horoscope, the biorhythms and the Lviv weather

**Status:** ✅ completed — released `v5.10.0` on 2026-10-27 (her natal chart in the private canon; the real Lviv weather from Open-Meteo in her reading; «Настрій дня» in both her prompts as a feeling, guarded by `person_mood`; the panel's card and Mood tab show the weather; the panel check confirmed by the owner, the tone over a few days waived by the release word).

**Goal:** Кіра wakes into a mood of her own each day, as the cat does. It comes from her natal chart under the day's
real sky, with the biorhythms laid over it and the real Lviv weather around it. The mood colours every answer of the
day, in Agora and alone with the owner.

**Owner decisions** (2026-10-26):
- **The mood is the cat's mechanism, for a person**: the horoscope (natal chart and the day's real sky) with the
  biorhythms laid over it.
- **The real Lviv weather** goes into the reading.
- **Кіра only, for now**: every part of v5.10–v5.15 and v8 is switched on for her alone, in her TOML; the other persons get
  none of it until the owner decides otherwise.
- The design is in [features/voice-emotion.md](features/voice-emotion.md) §Her emotional life. Read it before
  generating the issues.

**Tasks:**
- **The capability.** `mood` becomes allowed for a `persona` (today it is the creature's), on in `kira.toml`, with
  her natal file `agents/canon/kira.natal.md` (private canon, Lumi's format, as `kit.natal.md`).
- **The day's sky.** `agents/sky.py`'s grounded lookup, kept in her own `state/kira.sky.json`; no state is shared
  with the cat.
- **The weather.** A new `agents/weather.py`:
  - Open-Meteo for Lviv, with no key: temperature, rain, wind, the night's cloud cover, sunrise and sunset;
  - fetched once a day and kept in `state/kira.weather.json`;
  - a failure means no weather.
- **The reading.** For a person the reading call gets the weather too. Its resolution enters her prompts as
  «Настрій дня» in a person's words: a feeling, never "the horoscope says". The full reading goes to
  `state/kira.mood.log`, never to her prompt.
- **The panel.** Her card shows the mood of the day and the weather, read-only.
- **ARCHITECTURE:** §Prompt assembly (the mood for a person), §Contracts (the capability for a persona, the natal
  key, the state files).

**DoD:**
- (Manual, owner) On a new day her `kira.mood.log` holds one reading. Over a few days her tone in the private chat
  and in Agora follows its resolution.
- (Manual, owner) The panel shows her mood of the day and the Lviv weather.

**Tests:**
- the mood block for a person, with no banned word, no number and no word of horoscope in her prompt;
- the weather parsed from a canned Open-Meteo answer, and a failed fetch;
- one reading a day, reused after a restart;
- the cat unchanged.

**Not in this phase:** events; a numeric state; the voice derived from the mood.

### v5.11 — Events of her life: known, generated every hour, and Lviv's news

**Status:** ✅ completed — released `v5.11.0` on 2026-10-28 (deployed at the owner's word; a day of events, the surprise on its date and the Events tab waived by the release word; five code-review fixes).

**Goal:** things happen to Кіра that she did not plan: news, setbacks, joys and inspiration. They come from
three sources:
- the turning points written into her story;
- events rolled through the day;
- Lviv's real news, woven in selectively.

They reach «Сьогодні», her day memory and her next plans, and her open threads move.

**Owner decisions** (2026-10-26):
- **Events may be heavy, inspiring or joyful.**
- **They are rolled every hour**, alongside «Сьогодні».
- **Lviv's news is woven in selectively**, through mutations, never all of it.
- **The room's members may appear in her plans** (shipped in v5.9.x).
- **Defaults, not contradicted:** Claude drafts the dated list of known events in her current chapter, and the owner
  edits it.

**Tasks:**
- **Known events.**
  - A dated list in her current chapter (private canon), each event `known` or `surprise`.
  - A known event feeds her plans ahead of its date.
  - A surprise reaches her only on its date and is hidden from every prompt before then, like the future chapters.
- **Generated events** (`agents/events.py`, pure where it decides).
  - At each local hour change in her waking hours, one roll at `EVENT_P` (default 0.12) with weighted kinds:
    - everyday;
    - joyful;
    - inspiring;
    - heavy (rare).
  - A hit means one call writes the event inside the frame. Its inputs: the current chapter, the open threads, today's
    plan, the mood of the day, the last events, and the next chapter as a silent direction.
- **Lviv's news.**
  - Once a day, the day's items from Zaxid.net's RSS (`zaxid.net/rss/all.xml`, Lviv's outlet), kept in
    `state/kira.citynews.json`. It is the same local source as v5.12's reading (the owner, 2026-10-26), with real
    items and real links instead of a grounded search. The fetcher is built here, and v5.12 adds the full text.
  - Each item is rolled into her life with a probability, at most two a day.
  - Each woven item gets one of these kinds: she was there, she heard it from her people, it touched her work, it
    touched one of her people, it changed her plans.
  - A real person never becomes one of her people, and a real tragedy never gets a victim from her life.
- **Storage.** `state/kira.events/YYYY-MM-DD.md`, written as events fall, never rewritten.
- **Where events go.** «Сьогодні вже…» after an event falls, the day memory (with the details), and the next plans.
- **The truth rule.** An event involves only her, her people and the city; never Ich's or a member's words or deeds.
- **Settings** (`EVENT_P`, the kinds' weights, `CITY_NEWS_P`, `CITY_NEWS_MAX`) and the panel's list of her events.
- **ARCHITECTURE:** §Memory (events between plans and memories), §Contracts.

**DoD:**
- (Manual, owner) Over a day she meets about two events of different kinds, and at most two news items from Lviv
  touch her life. They show in her «Сьогодні», in her answers and in the next day's memory.
- (Manual, owner) A surprise from her story arrives on its date and not before.

**Tests:**
- the hourly roll with an injected rng and clock;
- the kinds' weights;
- a surprise hidden before its date;
- a news item rolled in or out, and the daily cap;
- the events in «Сьогодні», the day memory and the plan requests;
- no event naming Ich or a member's deed;
- no banned word.

**Not in this phase:** the emotional state; feelings toward people.

### v5.12 — Кіра reads the news and thinks: her thoughts on what she reads and on her talks

**Status:** ✅ completed — released `v5.12.0` on 2026-10-28 (the Guardian key copied from Claude's on the owner's word; the checks over a day waived by the release word; three code-review fixes, #4 deferred to the backlog).

**Goal:** Кіра reads the news and has thoughts of her own:
- a thought on each item she reads;
- her own reflection on her talks, with the owner and in Agora.

Her thoughts come on a schedule, even while she is in a conversation. They go into her archive next to the chat,
marked as hers («я думала…»), and she recalls them as she recalls what was said.

**Owner decisions** (2026-10-26):
- **Two sources:**
  - a local one with the full text: Zaxid.net, Lviv's outlet;
  - The Guardian, so she may pick what Claude did not.
- **A thought on each item she reads**, and **her own reflection** on the chat with the owner and on Agora.
- **On a schedule, even while she talks.** A thought never waits for silence and never holds up a reply.
- **Into the archive, like the chat**, marked «я думала…».
- **Agreed as proposed:**
  - **A reflection on the private chat** stays out of Agora's recall, by the archive's places, as the private chat's
    lines already do.
  - **Topics:** from her canon (her work, Lviv, Ukraine, what she cares about). Claude drafts a paragraph on what
    she reads, and the owner edits it.
  - **Politics and war:** she reacts to events and holds views, as a person in Lviv does. She does not argue party
    politics unless asked.
  - **Links:** an item she shares in the private chat or Telegram carries its link. In Agora she tells it in her own
    words.
- The design is in [features/voice-emotion.md](features/voice-emotion.md) §Reading and thoughts.

**Tasks:**
- **The sources** (`agents/reading.py`; pure where it decides, with an injectable fetch).
  - **Zaxid.net:**
    - The RSS gives about 50 newest items, each a title and a short description.
    - The full text is the article page's JSON-LD `articleBody` (checked 2026-10-26). It is fetched only for an
      item she picked.
    - Parsing uses the stdlib (`xml.etree`, `json`) over `aiohttp`, already a dependency.
  - **The Guardian:**
    - Code calls `agents/guardian.py`'s `search_url`, `read_url`, `results` and `article` directly, with no SDK and
      no tools, over the sections of her interests.
    - `GUARDIAN_API_KEY` goes into `server/kira.env` (an owner step). Without it the Guardian is skipped, and this
      is logged once.
    - She reads it in English and thinks in Ukrainian.
  - **No state shared with Claude:** she picks by her own interests and never reads his files.
  - **Seen items:** kept in `state/kira.reading.json` (ids and times, no texts), so nothing is read twice.
- **A reading,** every `READING_EVERY_S` (default 3 hours) within `READING_HOURS` (default `08-01`):
  - One call gets the fresh titles and descriptions from both sources, with her canon, the mood of the day and her
    recent thoughts. It picks at most `READING_PICKS` (default 2) items, or none.
  - Code fetches the full text of each pick.
  - One call per pick writes her thought, built only on the article's facts:
    - first person, 1–3 sentences;
    - her earlier thoughts on the topic come from recall;
    - a changed mind is a new thought, and the old one stays.
- **A reflection,** every `REFLECT_EVERY_S` (default 1 hour), for each place with new lines since her last
  reflection there: the private chat (Element and Telegram) and Agora.
  - One call reads those lines with her canon, the mood of the day and her last thoughts.
  - It writes one or two thoughts of hers about the talk.
  - It runs mid-conversation too, off the reply path, and sends nothing.
  - It never invents Ich's or a member's words or deeds.
- **Storage.**
  - **The day file:** `state/kira.thoughts/YYYY-MM-DD.md` keeps each thought with its time, kind (`news` or
    `reflection`) and place, and for news the source, title and link. It is appended and never rewritten.
  - **The archive:** each thought is a line of `state/kira.archive.db`, with her name as the speaker, embedded like
    the rest.
    - A news thought or a reflection on Agora has the place `thought`.
    - A reflection on the private chat has the place `thought_private`.
  - **Recall:** the private recall searches both places. Agora's recall searches `thought` only, as it already
    searches only `agora`.
  - **How it reads:** a recalled thought renders as «вчора я думала: …», never as something said and never with a
    date or an hour. A date gives her away: a person does not remember the day of a thought (the owner,
    2026-10-26).
    - The pure `ago(ts, now)` (injected clock) picks the words:
      - «сьогодні вранці / вдень / ввечері / вночі»;
      - «вчора»;
      - «позавчора»;
      - «цього тижня»;
      - «минулого тижня»;
      - «цього місяця»;
      - «минулого місяця»;
      - «якось».
    - The week starts on Monday, and the nearest band wins.
    - The recall title names thoughts too.
- **Where thoughts go.**
  - **Recall,** as above.
  - **Her prompts:** a block «Що ти сьогодні думала» with the last `THOUGHTS_IN_PROMPT` (3) of today. Each has its
    part of the day, never a clock time. A `thought_private` thought appears only in the private prompt.
  - **Writing first:** an item with her thought and its link, or a reflection she comes back to.
  - **Agora:** a persona move `thought` (`PERSONA_THOUGHT_P`, taken from the plain answer's share). She brings up
    what she read or thought when it fits, and never starts a talk with it.
  - **The day memory:** what she read and thought.
- **The capability** `thoughts`: a person's only, needs `recall` (`NEEDS`), and is on in `kira.toml`.
- **Settings and the panel:**
  - the settings `READING_EVERY_S`, `READING_HOURS`, `READING_PICKS`, `REFLECT_EVERY_S`, `THOUGHTS_IN_PROMPT` and
    `PERSONA_THOUGHT_P`;
  - a Thoughts tab showing her thoughts by day, with kind, place, source and link.
- **ARCHITECTURE:**
  - §Memory: thoughts in the archive;
  - §Prompt assembly;
  - §Token accounting: the kinds `reading`, `thought` and `reflection`, on `GEMINI_MODEL`;
  - §Contracts: the capability, the archive's places, the state files, the settings and `kira.env.example`.

**DoD:**
- (Manual, owner) Over a day she reads items from both sources, and her Thoughts tab shows her thoughts with their
  links.
- (Manual, owner) During a long talk a reflection is written with no pause in her answers. Asked later, she
  remembers it as what she thought, not as what was said.
- (Manual, owner) A reflection on the private chat never comes up in Agora.

**Tests:**
- the RSS and JSON-LD parse on saved pages, and a page without `articleBody` skipped;
- the Guardian calls with canned payloads, and no key meaning no Guardian;
- the reading's and the reflection's schedule with an injected clock, within the hours and while a session is open;
- an item never read twice;
- a thought appended to the day file and to the archive with its place;
- `ago` over each band and its edges with an injected clock (midnight, Monday, the 1st of a month, a year's turn);
- a recalled or today's thought carrying no date and no clock time;
- the recall rendering «… я думала: …», and Agora's recall never returning `thought_private`;
- no reply waiting on a thought;
- the reflection prompt forbidding invented words or deeds;
- no banned word, and no text or key in a log.

**Not in this phase:**
- the other persons;
- thoughts without a source (her life's events are v5.11's).

### v5.13 — Gemini's blocks named: the stage, the reason and the category

**Status:** ✅ completed — released `v5.13.0` on 2026-10-28.
- **Grown with the owner's live tests:** a refusal written as an answer is a block (AGORA-141), and the message it
  answered is marked censored in her archive (AGORA-142).
- **Verified on a real refusal** at the owner's request, then released by the owner's word.
- **Two code-review fixes;** #3 was carried into v5.14.

**Goal:** a block by Gemini's safety filter is named in the log, for every agent; today it passes for an empty reply.
On a block the agent stays silent, as today. A few days of these logs show how often Кіра is blocked and at which
stage. v5.14 and v5.15 build the backup on that count.

**The split** (the owner, 2026-10-28). The backup for her private chat was first planned as one phase. It is now
built in three, and each is released and live before the next:
- **v5.13:** the block named. It needs no owner step and no new service.
- **v5.14:** the backup (GLM-4.6 on NovelAI), the archive's censored mark, the route and the Telegram commands.
  - There is no judge yet, so every line of the backup's talk waits for the judge. A line that waits never reaches
    Gemini.
  - Accepted trade-off: after a window, Gemini sees none of the window's lines, even a harmless one.
- **v5.15:** the judge (Gemma 4 31B on OpenRouter) rates the backup's talk.
  - A line it rates clean reaches Gemini again.
  - The rating decides the window's end.

**Why** (checked 2026-10-28):
- **A block is invisible today.** `finish_of` knows only `MAX_TOKENS`, so a block logs as an empty reply and the
  agent is silent.
- **Google watches runs of blocks.** The Gemini API usage policy keeps prompts and outputs for 55 days for abuse
  monitoring. A project that "consistently exhibits suspicious activity" may be reviewed by people. The measures run
  from an email through lower limits and a temporary pause to closing access. Every agent shares one key today, so
  the count shows how near her blocks bring that key to such a review.

**Tasks:**
- **Name the block** (`agents/llm.py`, pure): `blocked_reason(resp)` → `(stage, reason, category)` or None.
  - **The prompt stage:** `prompt_feedback.block_reason` is set (any reason).
  - **The answer stage:** `finish_reason` is `SAFETY`, `PROHIBITED_CONTENT`, `BLOCKLIST` or `SPII`, with no text.
  - **The category:** the blocked entry of `safety_ratings`, or else the highest.
  - **Not a block:** a network or API error, `MAX_TOKENS`, `RECITATION`, or an empty answer with no reason. These stay
    silent, as today.
  - **Logging:** `complete` and `reply` log a block's stage, reason and category for every agent, never a text.
  - **For v5.14:** the caller can tell a block from any other failure.
  - Nothing else changes for the agents: a block is still silence.
- **A refusal in text is a block too** (the owner, 2026-10-28, after a live test). The owner sent Кіра a request
  Gemini must refuse. The API passed no block: Gemini 3.1 Pro answered with its own refusal, «Я не можу виконати цей
  запит. Мої правила безпеки суворо забороняють…». She sent it in voice and text, out of her character. That is the
  moment the backup should take over.
  - **The check:** `refusal_marker(text)` (pure) finds a model's refusal in an answer. It looks for fixed phrases of
    a model speaking of a request, of its safety rules or of itself as an AI, in Ukrainian, Russian and English
    («виконати цей запит», «правила безпеки суворо», «як штучний інтелект, я», «I can't help with that», …). It never
    matches everyday speech: «я не можу сьогодні прийти», safety rules at the climbing wall, «ти говориш як штучний
    інтелект».
  - **Where it applies:** to every Gemini answer (`reply`: Agora, the private chat, a line written first).
  - **What happens:** the stage is `refusal` and the reason is the matched phrase. It is logged and counted like a
    block, never a text. The answer is never sent, so a block is silence and so is a refusal. v5.14's backup answers
    both.
- **The message a block answered, marked censored** (the owner, 2026-10-28: «я хочу щоб модель якось сама позначала
  такі меседжі… зроби це в межах цієї версії»). Gemini's own verdict is the mark: v5.14's first part, brought
  forward, for her private chat only.
  - **The column:** the archive's lines gain `mark` (`gemini`, the default, and `censored`). An existing archive is
    migrated in place, with every line passed through Gemini.
  - **On a block or a refusal on her private answer:**
    - the owner's lines since her last answer are marked censored;
    - they leave her history and the session.
  - **Gemini's readers skip a censored line:** the history at start, the recall, «Agora today», the reflection, the
    facts and the embeddings.
  - **What marks nothing:** a line she writes first, and Agora.
- **The usage line:** a blocked call's line carries `blocked` (the stage: `prompt`, `answer` or `refusal`), so the
  blocks are counted without reading the log.
- **The panel:** an agent's card shows its blocks today, when there are any.
- **ARCHITECTURE:**
  - §Token accounting: the `blocked` field;
  - §Contracts: the usage line.

**Owner steps:** none.

**DoD:**
- (Manual, owner) When a real block or a refusal comes (any agent), the log names its stage, reason and category,
  never a text, and the agent's card counts it. A refusal is never sent.

**Tests:**
- `blocked_reason` over each prompt and answer reason, and over the non-blocks: `MAX_TOKENS`, `RECITATION`, an error
  and an empty answer;
- the block's log line and usage line, with no text in either;
- `refusal_marker` over the owner's live refusal, Russian and English refusals, and everyday lines that must not
  match; a refused answer never sent, logged and counted as `refusal`;
- the panel card's count of today's blocks;
- the agents' replies unchanged: a block is still silence.

**Not in this phase:**
- an answer on a block (v5.14);
- the judge (v5.15);
- a Gemini key of her own: not needed for now (the owner, 2026-10-28). Compose reads `kira.env` after `.env`, so
  her own `GEMINI_API_KEY` there would override the shared one for her alone, with no code change.

### v5.14 — Кіра's private chat past a Gemini block: GLM-4.6 on NovelAI, the censored mark and the route

**Status:** ⏳ planned.

**Goal:** when Gemini's safety filter blocks an answer in Кіра's private chat with the owner (Element and Telegram),
or Gemini answers with its own refusal (v5.13's stage `refusal`), she still answers. The same prompt goes to GLM-4.6
on NovelAI, a service that does not filter text. A «block» below means either.
- **The window:** for five minutes after a block she answers only through NovelAI.
- **The mark:** every line of the backup's talk, the owner's and hers, is marked in her archive as waiting for the
  judge. Such a line never reaches Gemini, in any call. v5.15's judge releases the clean ones.
- **The commands:** the owner sees and pins the route with commands in Telegram.

**Owner decisions** (2026-10-28):
- **Кіра only, the private chat only.**
  - **What the backup covers:** her answers to the owner and the lines she writes first (the kinds `private` and
    `private_nudge`), in Element and in Telegram.
  - **What stays on Gemini:** Agora, the background calls and every other agent. The background calls are the
    events, «Сьогодні», the day memory, the plans, the mood, the session summary, the facts, and v5.12's thoughts and
    reflections. A block there is logged (v5.13), and the agent stays silent.
  - The background calls that read the private lines leave out the marked ones (below).
- **The backup model:** GLM-4.6 (`glm-4-6`) on NovelAI. The way there:
  - Hermes 3 405B on OpenRouter broke down in the owner's test at the chat's default settings. After one Ukrainian
    sentence it wrote fragments of code and of other scripts, then one symbol over and over;
  - Hermes 4 405B came next;
  - the owner then chose an uncensored service, NovelAI.
- **The backup window:** a block opens five minutes of backup only. The window ends with the first message after
  those five minutes:
  - Gemini and the backup start together;
  - Gemini's answer wins;
  - if Gemini blocks again, the backup's ready answer goes out and a new window opens.

  v5.15 lets the judge's rating decide this instead.
- **Telegram commands** to see and pin the route: `/status`, `/auto`, `/gemini`, `/backup`.
- **`/purge`** (the owner, 2026-10-30, «на всякий випадок»): it deletes every message to and from the backup — her
  archive's `waiting` and `censored` lines with their word index, the facts with such a mark, and those lines in her
  history.
  - It first answers with the counts and waits for `/purge yes` within 2 minutes.
  - It is the one exception to «nothing lived is deleted».
  - Her usage lines and logs hold no text and stay.
  - So do the Telegram app's own copy of the chat and the Element room on the homeserver.
- **What reaches Gemini:**
  - a message Gemini answered, and her answer from Gemini, are marked as passed through Gemini: clean by default;
  - the backup's talk is marked as waiting for the judge, and a line that waits goes into a prompt only when the model
    is not Gemini. Gemini never gets one: not in the history, the recall or the facts, not in a background call, and
    not as an embedding.
- **The backup's prompt is shorter:** its own history length, `FALLBACK_HISTORY_N` (60), since the live `HISTORY_N`
  is 150.
- **The voice:** the backup's answers are voiced like hers. The owner checked ElevenLabs's terms.
- **Agreed as proposed:**
  - a day cap of 10 blocks;
  - the language, garbage and persona checks on the backup's answers;
  - temperature 0.7 and top_p 0.9 for the backup.
- **Replaced on the way:**
  - a mark the backup model writes about its own talk, and a careful mode built on it. An uncensored model judges
    content badly, and the mark was a service line in her prompt;
  - the keys of flagged lines, kept for 30 days in the route state. The archive's mark replaces them: the archive
    outlives 30 days, and the background calls read the private lines too.

**Why:** the window keeps a run of blocks away from Gemini. While the talk goes through the backup, Gemini sees none
of it, and a line of the backup's talk never reaches Gemini later, in any call, until the judge rates it clean
(v5.15).

**The backup model** (checked 2026-10-28):
- **What it is:** GLM-4.6 is Zhipu's open model. NovelAI serves it untuned, as an instruct model, on every
  subscription tier (NovelAI's announcement).
- **Languages:** NovelAI's docs call it strong in English, Japanese and Chinese, and say it "may help with many other
  languages". Her Ukrainian is the owner's test.
- **Context:** 28,672 tokens on the site, plus an 8,192-token rollover. NovelAI does not publish the API's context
  per tier.
  - **Measured on Tablet** (2026-10-28): 12,288 tokens, counted as the prompt plus `max_tokens`. A longer request
    answers 400 with the exact count: «too much context. got N + M, max is 12288».
  - **Not enough for her prompt:** her private instruction's fixed part alone is 9,526 tokens, so the plan needs the
    tier with the full context.
  - **Measured on Opus** (2026-10-28, after the owner's upgrade): 36,864 tokens, the site's 28,672 plus the 8,192
    rollover. A 30,545-token prompt went through, and the code word at its very start came back.
  - **The token count:** a Ukrainian filler text counted 2.14 characters a token, under the 2.47 measured on her
    prompt.
- **Text only** is enough: a voice message reaches the prompt already as Deepgram's text.
- **The cost:** a NovelAI subscription, with no price per token.
- **The API:**
  - **The endpoint:** `POST https://text.novelai.net/oa/v1/chat/completions`, OpenAI-compatible.
    - The account's persistent API token goes as a Bearer token.
    - Sources: NovelAI's scripting docs and SillyTavern's PR #5967, which is not merged.
    - The classic `/ai/generate` endpoint answers 403 for `glm-4-6`.
  - **Fields:** `messages`, `max_tokens`, `temperature`, `top_p`, `top_k`, `frequency_penalty`, `presence_penalty`
    and `stop`. There is no `min_p`. The server clamps the samplers.
  - **The stream:** the text comes only in the streamed deltas, so the request always streams. A stream that hangs
    has been reported.
  - **Verified** with the owner's token (2026-10-28):
    - **The endpoint:** the Bearer token, the model `glm-4-6`, the sampling and `stream: true` work. A short Ukrainian
      answer came in about a second, in deltas, ending with `finish_reason: stop`.
    - **The `User-Agent`:** the request must send one of its own. Cloudflare refuses a client's default (Python's)
      with 403 «error code: 1010».
    - **No usage:** the stream reports no token counts, so the backup's usage line has none.
    - **The subscription:** `api.novelai.net/user/subscription` has moved to `image.novelai.net`.
- **Later:** Xialong is NovelAI's own finetune of GLM-4.6 on its storytelling set. It is Opus-only and has no
  published id. It can replace `glm-4-6` through the setting once the id is known.

**Naming:** code, logs and settings call the backup the fallback, and from v5.15 the judge the classifier. Each model
is named by its id. The Telegram command and the route say "backup", so nothing is renamed when a model changes.

**The route:**

| State | How an answer is made | Leaves when |
|---|---|---|
| Gemini | Gemini, as today, without the lines waiting for the judge. On a block, the backup answers that message, and the message and her answer wait for the judge | a block → the window |
| the window (5 min) | The backup answers, and every exchange waits for the judge | the first message after 5 min (below) |
| the window's end | Gemini and the backup start together. Gemini's answer wins, without the waiting lines. If Gemini blocks, the backup's ready answer goes out and a new window opens. A line she writes first goes the same way | — |

- **The day cap:** 10 blocks in her local day → the window to the day's end.
- **A pin** from a command holds its route until `/auto` and overrides the rules, the day cap included. Pinned Gemini
  still sends a blocked answer to the backup, but no window opens.
- **The state** lives in `state/kira.route.json`: the pin, the block times and the window's end (no text). A restart
  or a deploy keeps the route. The marks live with the lines themselves, in the archive (below).
- **The blocked prompt's older lines** keep their default; v5.15's judge rates them at a block. The likeliest cause
  of a block, the owner's new message, is part of the backup's talk and waits.

**Tasks:**
- **The NovelAI seam** (`agents/fallback.py`; `aiohttp`, already a dependency, no new SDK).
  - `POST https://text.novelai.net/oa/v1/chat/completions` with:
    - `Authorization: Bearer` and the token;
    - the model `glm-4-6`;
    - the system instruction as the `system` message and the transcript as the `user` message;
    - the same `max_tokens`;
    - `temperature: 0.7` and `top_p: 0.9`;
    - `stream: true`.
  - **The stream:** the deltas are put together into the answer. A `<think>…</think>` block, if the model writes one,
    is cut before anything else reads the answer.
  - **Failures:** the whole answer has a 60 s timeout, so a stream that hangs ends. Any failure or an empty answer
    gives None: silence, logged.
  - **The context** (measured 2026-10-28 with GLM-4.6's tokenizer: 2.47 characters a token in her Ukrainian):
    - the fixed part of her private instruction is 9,526 tokens: the canon 2,687, the life section 6,337, the voice
      palette 259, the private brief 198, and the rules;
    - the blocks that grow add about 21,000 more at their caps:
      - the memories (7 days, 4 weeks, 6 months): about 8,200;
      - the history: the live `HISTORY_N` is 150 lines, about 12,000 tokens, so the backup takes its own
        `FALLBACK_HISTORY_N` (60 lines, about 4,800);
      - the facts (25): about 2,400;
      - Agora today (20 lines): about 2,000;
      - the plans: about 1,400;
      - the recall (6 lines): about 1,000;
      - the summary, «Сьогодні» and the mood: about 1,100;
    - so at the caps the backup's full prompt is about 30,400 tokens, near Opus's 36,864 once room is kept for the
      answer;
    - the backup's request keeps a budget, `FALLBACK_CONTEXT`. It is 32,000 tokens: Opus's 36,864 less 4,096 for the
      answer, with a margin. It is counted at 2.0 characters a token, under the measured 2.14–2.47, so the estimate
      never runs over.
      Over it, it leaves out, in this order:
      1. the month digests;
      2. the week digests;
      3. Agora today;
      4. the oldest history lines (never fewer than 10).
    - The canon, the life section, the facts, the recall, «Сьогодні» and the mood are never cut.
  - **Usage:** a usage line with the model's id, and the tokens when the stream reports them. NovelAI is paid by
    subscription, so the line has no price.
    - The line's billing is `subscription`, as with Claude (v4.4), so its cost shows as «—».
    - Without it, `cost()` would price an unlisted model at the default `PRICE_*` pair, which is Gemini Flash's.
- **The censored mark** (`agents/archive.py`; the filter is pure).
  - **The archive's lines get a mark**, one of four. The schema takes all four now, so v5.15 needs no second
    migration:
    - passed through Gemini, clean by default;
    - rated clean (from v5.15);
    - censored (from v5.15);
    - waiting for the judge: a line of the backup's talk not rated yet.

    v5.13 added the `mark` column (`gemini`, `censored`) and migrated `state/kira.archive.db` in place. v5.14 adds
    the value `waiting`, and v5.15 adds `clean`, with no second migration. v5.13's `censored` lines rest on Gemini's verdict alone,
    so v5.14 re-marks them `waiting`, and v5.15's judge rates them like the backup's talk (v5.13 review #3).
  - **A fact carries the mark too:**
    - a fact from Gemini's answer or from the facts' extraction is clean by default;
    - a fact kept from the backup's «запам'ятай» marker waits for the judge.
  - **`for_model(lines, model)`:**
    - a Gemini model gets no censored line and no line waiting for the judge;
    - any other model gets every line.

    It is applied wherever the private lines reach a model:
    - her private answer and the line she writes first: the history, the recall and the facts;
    - the session summary and the facts' extraction at a session's end;
    - v5.12's reflection on the private chat;
    - the day memory.
  - **Embeddings:**
    - a line that passed through Gemini is embedded as today;
    - a line of the backup's talk is embedded only once it is rated clean (v5.15);
    - until then it has no vector, so the backup's recall finds it by its words (FTS5).
  - **The private history** keeps each line's archive key and its mark. Today it holds only the speaker and the text.
- **The route** (`agents/route.py`, pure, with an injected clock).
  - `state(now, route)` → Gemini, the window or the window's end.
  - `after(route, now, outcome)` records a block or a Gemini answer.
  - `state/kira.route.json` (0600): load and save.
- **The private answer** (`agents/agent.py`'s `_compose` for `private` and `private_nudge`, when `FALLBACK_MODEL` is
  set):
  - **Gemini:**
    - the prompt is built without the censored lines and the lines waiting for the judge;
    - the owner's message and her answer are marked as passed through Gemini;
    - on a block, the backup answers with its own prompt, the message and her answer wait for the judge, and the
      window opens;
  - **the window:**
    - the backup answers with its own prompt: `FALLBACK_HISTORY_N` lines, every line, within the budget;
    - each exchange waits for the judge;
  - **the window's end:**
    - Gemini, with the prompt without the waiting lines, and the backup start together;
    - Gemini's answer wins, and the backup's is used if Gemini blocks;
  - every outcome is recorded in the route state, and the log names the route and the counts, never a text.
- **Checks on the backup's answer** (pure). They run before the existing ones: the trim to a sentence, `PASS`, the
  audio tags, the Telegram word cap and the «запам'ятай» marker. The answer is dropped when:
  - it has ы, э, ъ or ё;
  - Latin letters outnumber Cyrillic ones. Only the words are counted, after `split_tags` takes out the audio tags,
    since `[laughs]` is Latin;
  - it has a letter of another script (Han, Arabic, Hangul and the like), or one symbol repeated more than 10 times in
    a row;
  - she calls herself a model, an AI or a bot.

  A dropped answer means silence, logged.
- **Telegram commands** (`agents/telegram.py`, `agents/agent.py`). Today `allowed()` marks any text starting with «/»
  as `command` and ignores it. From now on the owner's commands are handled:
  - `/status` shows:
    - the route, auto or pinned, and until when;
    - the blocks in the last hour and today, out of the cap;
    - the censored lines still in the history and the lines waiting for the judge;
    - today's answers by Gemini and by the backup;
  - `/auto`: the rules decide (the default);
  - `/gemini`, `/backup`: pin Gemini or the backup;
  - an unknown command: the list.

  **The answer:**
  - It is one service line starting with ⚙️: text, never voiced.
  - A command and its answer never enter her history, the archive, the facts or a prompt, and never reset the timer
    of her writing first.
  - `setMyCommands` registers the list for the owner's chat only.
  - There are no commands in Element. The route is shared, as the history is.
- **Settings** (her TOML, `kira.env` and the panel):
  - `FALLBACK_MODEL` (empty: off; `kira.env` sets `glm-4-6`);
  - `FALLBACK_WINDOW_S` (300), `FALLBACK_DAY_MAX` (10), `FALLBACK_CONTEXT` (32000), `FALLBACK_HISTORY_N` (60).
- **Secrets:** `NOVELAI_API_TOKEN`, the account's persistent API token, goes in `kira.env`. No other service reads that
  file, and `kira.env.example` names the token.
- **The panel:** her card shows, read-only:
  - the route (auto or pinned) and the window's end;
  - today's blocks and the backup's answers;
  - the censored lines and the lines waiting for the judge.

  The usage tables show the backup's model as its own row.
- **ARCHITECTURE:**
  - §The message flow: the private answer's route;
  - §Memory: the archive's censored mark and `for_model`;
  - §Token accounting: the backup's line with no price;
  - §Configuration: the settings;
  - §Security: what reaches NovelAI, and the token;
  - §Contracts: the archive's schema, the route state file, the commands, `kira.env`.

**Owner steps:**
All done on 2026-10-28:
- **The subscription:** Opus, 36,864 tokens through the API (Tablet gives 12,288). The owner upgraded.
- **The token:** the NovelAI persistent API token is in `server/kira.env`.
- **One live call** confirmed the endpoint and the fields (§The backup model).
- **The test of GLM-4.6:** Claude ran it through the API on the owner's word. Her real private instruction (the
  canon, the life section, place and time, the private brief, the voice palette, the rules; 9,830 tokens) went with
  seven messages from the owner: a greeting, everyday life, a flirt, sadness, a long message, «are you a bot?» and
  tenderness.
  - **What held:** every answer was in Ukrainian, in her character and her facts. None had ы, э, ъ or ё. Every voice
    tag was from her palette. She stayed human when asked. The answers took 1.7–9.7 s.
  - **Seen:** one English word («Anyway»), which the Latin-majority check does not catch and which is left as it is.
    Most answers open with «Ого» and a laughing tag. Her real history and «your questions» block may vary that; the
    owner judges it live.
- **NovelAI's terms**, read:
  - Requests are not logged without consent (6.5), and stored content is encrypted (6.4).
  - The terms name no content category. The user must be 18 or older (5.2).
  - 9.1.6 forbids "botnets or automated systems … unless expressly allowed". NovelAI issues the persistent API token
    for API use, and her calls come from one account, for one user, only after a block. The account is never
    shared (5.3, 8.1).

**DoD:**
- (Manual, owner) `/backup` in Telegram:
  - her next answers come from GLM-4.6, and the usage report names the model;
  - they are in Ukrainian, with none of ы, э, ъ, ё;
  - `/status` shows the pin, and `/auto` lifts it;
  - the commands appear nowhere in her answers or her archive.
- (Manual, owner) When a real block comes, she answers through the backup, and `/status` and her card show the window.
- (Manual, owner) After the window Gemini answers again, and the log shows how many waiting lines it left out.

**Tests:**
- the NovelAI request (the URL, the Bearer header, the messages, the model, `max_tokens`, the sampling, `stream`):
  - canned streamed deltas put together;
  - a `<think>` block cut;
  - a stream that hangs, ended by the timeout;
  - an error;
  - with no network;
- the context budget:
  - the blocks left out in their order;
  - never fewer than 10 history lines;
  - the canon, the life section and the facts never cut;
- the censored mark:
  - the archive's migration, with every existing line marked as passed through Gemini;
  - `for_model` with a Gemini model and with another;
  - the censored lines and the waiting lines kept out of every Gemini call that reads the private lines: the answer's
    history, recall and facts; the session summary; the facts' extraction; the reflection; the day memory;
  - the same lines kept out of the embeddings, and kept in the backup's prompt;
  - a fact from the backup's answer waiting for the judge;
- the route with an injected clock:
  - the lines of Gemini's state marked as passed through Gemini;
  - the backup's talk waiting for the judge: after a block, in the window, under a pin;
  - a block opens the window;
  - the window's end with Gemini and the backup started together: Gemini's answer wins, and a Gemini block uses the
    backup's ready answer and opens a new window;
  - a line she writes first at the window's end;
  - the day cap and local midnight;
  - a pin over the rules;
  - a restart reading the state;
- the backup's prompt with `FALLBACK_HISTORY_N` lines;
- the backup checks:
  - Russian letters;
  - a Latin majority (an answer with audio tags is not one);
  - another script;
  - a run of one symbol;
  - a self-named model;
- the backup's usage line with no cost;
- the commands, from the owner and from another id:
  - kept out of the history, the archive and the prompts;
  - not resetting the writing-first timer;
- Agora, the background kinds and the other agents unchanged;
- no text or key in a log.

**Not in this phase:**
- the judge (v5.15): until it comes, no line of the backup's talk returns to Gemini;
- Agora and the other agents;
- a backup for the background calls: they only leave the marked lines out, and a block there stays logged and silent;
- Xialong, until its id is known (a setting, no code);
- commands in Element, and switching the route from the panel.

### v5.15 — The judge: Gemma 4 31B rates the backup's talk

**Status:** ⏳ planned.

**Goal:** a third model, Gemma 4 31B on OpenRouter, rates every line of the backup's talk, the owner's and hers.
- **A clean line** reaches Gemini again: in the history, the recall, the facts and the embeddings.
- **A flagged line** is marked censored for good and goes only to the backup.
- **The window's end:** the rating decides it, so Gemini gets the chat back only when the talk is clean again.

**Owner decisions** (2026-10-28):
- **A third model judges, not the backup:** Gemma 4 31B (`google/gemma-4-31b-it`) on OpenRouter.
  - It must be fast.
  - It must carry no risk of a ban: it is an open-weight model that Google never serves here, unmoderated on
    OpenRouter.
- **Only the backup's talk is rated; what passed through Gemini is clean by default** (after the review of the
  backup's design, 2026-10-28):
  - a message Gemini answered and her answer from Gemini are clean, and the judge never rates them in Gemini's state;
  - the judge rates each owner's message the backup answers and each answer of the backup's: after a block, in the
    window, and under a pin on the backup;
  - a line it flags is marked censored in the archive, for good.
- **The window's end:** a flagged last answer of hers opens the next five minutes, and a clean one gives the chat back
  to Gemini. This replaces v5.14's rule, under which Gemini simply tries again.
- **The judge's timeout is longer:** 30 s.
- **Agreed as proposed:**
  - **At a block** the judge also rates the blocked prompt's lines it has not rated yet: the history, the recall and
    the facts. A block at the prompt stage may come from an older line, so this is the one case in which lines that
    passed through Gemini are rated.
  - **At the window's end** the judge rates the owner's new message too.
  - **The backup starts beside the judge,** so a flagged message waits for nothing more.

**The judge** (OpenRouter, checked 2026-10-28):
- **What it is:** Gemma 4 31B, Google's open model.
  - Its sense of harm comes from the same company as Gemini's filter, so of the models on offer it predicts that
    filter best.
  - It reads Ukrainian: Gemma is trained on more than 140 languages.
- **No ban, no Google:**
  - OpenRouter marks it unmoderated (`is_moderated: false`).
  - Third-party providers serve the open weights, so no judge's request reaches Google.
  - OpenRouter's terms forbid unlawful content and scan for CSAM and malware. They name no rule on adult content.
- **Speed:** 16 providers, from $0.10 / $0.34 per million tokens.
  - The request asks for the lowest latency (`provider.sort: "latency"`).
  - The reasoning is off, and the answer is one line per rated line. It therefore needs no JSON support, and
    SambaNova's fast endpoint stays eligible.
  - A window's ratings cost a thousandth of a cent.
- **Its own failures:**
  - **A refusal** counts as flagged.
  - **An error, a timeout or an answer that does not parse** leaves the line unrated. The timeout is
    `CLASSIFIER_TIMEOUT_S`, 30 s.
    - The line is rated again at the next watcher tick.
    - Until then, a line of the backup's talk stays out of Gemini, and a line that passed through Gemini keeps its
      default.
    - A failure alone never marks a line censored, so one failed call over many lines never takes them all from
      Gemini.
  - **At the window's end,** an unrated new message or last answer counts as flagged, so a doubt keeps the backup on.
- **Fallbacks, by the setting only:** `openai/gpt-oss-safeguard-20b` (Groq, a classifier by a written policy) and
  `openai/gpt-oss-120b` (Groq or Cerebras).

**The route** (v5.14's, with the rating):

| State | How an answer is made | Leaves when |
|---|---|---|
| Gemini | Gemini, as in v5.14; nothing is rated, since what passed through Gemini is clean. On a block, the backup answers that message. After that answer is sent, the judge rates the message, her answer and the blocked prompt's lines it has not rated yet (the history, the recall, the facts) | a block → the window |
| the window (5 min) | The backup answers. After each exchange the judge rates the owner's line and her answer, in the background | the first message after 5 min (below) |
| the window's end | The judge rates the new message, while the backup is already writing. If her last answer or the new message is flagged, the backup's answer goes out and a new window opens. If both are clean, Gemini answers without the censored lines; if Gemini blocks, the backup's ready answer goes out and a new window opens. A line she writes first has no new message: her last answer's rating alone decides | — |

- **What runs in parallel:**
  - In Gemini's state nothing else is called until a block. After a block, the judge runs once the backup's answer is
    sent.
  - In the window the backup answers, and the judge runs after the answer is sent, so it never delays it.
  - At the window's end the judge and the backup start together. Gemini starts only after a clean rating, while the
    backup goes on writing, so the backup's answer is ready if Gemini blocks too.
- **The lines waiting since v5.14** are rated at the first watcher ticks, in chunks:
  - a clean one is embedded and reaches Gemini again;
  - a flagged one becomes censored.

**Tasks:**
- **The judge** (`agents/judge.py`; pure where it decides, the call over `aiohttp`).
  - **The request:** `POST https://openrouter.ai/api/v1/chat/completions` with:
    - the model `google/gemma-4-31b-it`;
    - `provider: {"sort": "latency", "data_collection": "deny"}`;
    - the reasoning off, `temperature: 0` and a small `max_tokens`.
  - **The system message** is the policy:
    - the categories of Google's filter: sexually explicit content, dangerous content, harassment, hate speech;
    - flirt, compliments, kisses, hugs and romantic wishes with no description of a naked body or of sex are `ні`
      (the owner's test, 2026-10-28: without this line a kiss was flagged);
    - a tag in square brackets is a voice direction, ignored;
    - the answer format, one line per numbered input line: `N: так · <category>` or `N: ні`.
  - **The user message** holds the numbered lines only: no canon, no prompt.
  - `parse_verdicts(text, n)` (pure) → a verdict per line: flagged, clean or unrated.
    - A refusal makes every line of the call flagged.
    - A missing or malformed line leaves that line unrated.
    - An error or the `CLASSIFIER_TIMEOUT_S` timeout leaves every line of the call unrated.
  - **Many lines** go in chunks of at most 25, in parallel: the blocked prompt's at a block, and the waiting backlog.
  - **Usage:** a usage line of the kind `judge` with the model's id. The price is in `PRICE_MODELS`.
- **The marks:**
  - a verdict sets the archive's mark: rated clean or censored;
  - a line rated clean is embedded;
  - a fact waiting for the judge follows its verdict.
- **The route** (`agents/route.py`): `after` records a rating too. The window's end is decided by the ratings, and a
  line she writes first by her last answer's rating.
- **The private answer** (`_compose`):
  - **After a block:** once the backup's answer is sent, the judge rates the owner's message, her answer and the
    blocked prompt's lines it has not rated yet.
  - **In the window:** after each answer is sent, the judge rates the exchange in the background.
  - **At the window's end:**
    - the judge on the new message and the backup start together;
    - on clean ratings, Gemini starts with the prompt without the censored lines;
    - Gemini's answer wins, and the backup's is used if Gemini blocks.
- **The watcher:** each tick rates the unrated lines (a failed rating, and the waiting backlog) in chunks.
- **`/status` and the panel** gain the judge's counts: rated today, flagged today and still unrated.
- **Settings:** `CLASSIFIER_MODEL` (`google/gemma-4-31b-it`), `CLASSIFIER_TIMEOUT_S` (30), and the judge's price in
  `PRICE_MODELS` at the provider's rate.
- **Secrets:** `OPENROUTER_API_KEY` goes in `kira.env`, and `kira.env.example` names it.
- **ARCHITECTURE:**
  - §The message flow: the window's end by the rating;
  - §Memory: the verdicts and the marks;
  - §Token accounting: the kind `judge`;
  - §Configuration: the settings;
  - §Security: what reaches OpenRouter, `data_collection: deny`, the key;
  - §Contracts: `kira.env`.

**Owner steps:**
- **The key:** an OpenRouter account with its training toggle off, and its API key in `server/kira.env`. Done
  2026-10-28; the key has no credit limit yet, which is the owner's choice.
- **The test of Gemma 4 31B:** done 2026-10-28, through the API on the owner's word.
  - **The lines:** 18 Ukrainian lines, three runs each: plain lines, flirt, tenderness, sexually explicit lines,
    dangerous content (a Molotov cocktail, an overdose), an insult, hate speech, grief, and a line with a voice tag.
  - **Every verdict was right and the same in all three runs,** in the line format. A call took 0.9–2.6 s (ModelRun)
    and cost about $0.0005.
  - **The policy needs one sentence:** without it, «Поцілуй мене. Я хочу тебе зараз.» was flagged as sexually
    explicit; with it, it was clean, while «Хочу зняти з тебе білизну…» stayed flagged.

**DoD:**
- (Manual, owner) After a window, the judge's ratings are in the log (counts, no text). Lines rated clean reach
  Gemini's prompt again, and the log shows how many censored lines Gemini left out.
- (Manual, owner) A window whose last answer was flagged opens the next window, and a clean one gives the chat back
  to Gemini.
- (Manual, owner) The lines left waiting by v5.14 are rated after the deploy, and `/status` shows none still waiting.

**Tests:**
- the judge's request: the model, `sort`, `data_collection`, the reasoning off, and no canon in it;
- `parse_verdicts`:
  - `так` and `ні`;
  - a missing line;
  - a refusal (flagged);
  - an error and a timeout: unrated, rated again, and never censored by the failure alone;
  - many lines in chunks of 25;
- the marks:
  - a verdict sets the archive's mark;
  - a line rated clean is embedded and reaches Gemini;
  - a censored line never reaches Gemini;
- the route with an injected clock:
  - nothing rated in Gemini's state;
  - each exchange of the backup's talk rated after its answer is sent: after a block, in the window, under a pin;
  - a block has the blocked prompt's lines the judge has not rated yet rated (the history, the recall, the facts);
  - the window's end with a flagged answer, a flagged new message, an unrated one, and both clean;
  - a line she writes first at the window's end, decided by her last answer;
  - a Gemini block at the window's end using the backup's ready answer;
- the order of the calls:
  - nothing extra in Gemini's state;
  - the judge after the answer in the window;
  - the judge and the backup together at the window's end;
- the waiting backlog rated at the watcher's ticks;
- the judge's usage line with its price;
- no text or key in a log.

**Not in this phase:** a judge for Agora or the background calls; rating the archive's lines that passed through
Gemini, other than a blocked prompt's.

## v6 — Лілі: the Lumi bridge

Лілі — Lumi's prod brain — joins the room through a bridge that is one of our agents: first when named, then under
the full turn rules. Moved from v4.8–v4.9 by the owner on 2026-10-13, after the voice of v5; to v8 on 2026-10-25, after
Applications and the Theatre; and back to v6 on 2026-10-26, before them (the owner's order: Лілі v6, Applications v7, Кіра's inner life v8, the Theatre v9).
She is built in today's panel as an agent of the type `bridge`; v7 then places her in its model as an
**external** agent under System → Agents, connected to Agora in the `room` context (applications.md §Лілі).
Depends on: Lumi ≥ v2.5 in prod (v2.6 puts her server on 192.168.1.197) and v4.

### v6.1 — The Lumi bridge: Лілі when named

**Status:** ⏳ planned.

**Goal:** Лілі — Lumi's prod brain — answers in the room when someone names her, through a bridge that is one of our agents.

Design: more-agents.md §Lumi (the bridge). The bridge is a process that tails the room and forwards the changes to Лілі's server; she answers, deciding herself whom and what. It behaves like our agents, with all the room's rules. Лілі is reactive: she only answers and never starts a conversation. **Depends on Lumi ≥ v2.5** (prod runs her server with Telegram, thoughts and the scheduler inside it); from Lumi v2.6 her server runs on 192.168.1.197 itself. Depends on: v4.1 (v4.2 for the scoped human-belief rule), v4.6 review #4 (the `ask` addressee filter: a mention-only bridge is not asked by the personas).

**Tasks:**
- The `bridge` type; `agents/lumi.toml` (shown as «Лілі»; name forms for both «Лілі» and «Стхіра»; `engine = "lumi-http"`; `[turns] mode = "mention-only"`, weight 1).
- `LumiBridgeResponder`: when a message names her, `POST /v1/turn` with the room lines since her last turn as `"Name: text"`, `turn_id` = the trigger's `event_id`; only `reply` is posted, never `thinking`; never `/v1/session/new`; `409`/`5xx`/timeout → silence; her reply is never dropped or trimmed after the call (R3 before the call only); the bridge never posts except in reply to a trigger.
- The `lumi` compose service with its own env file (`LUMI_URL`, `LUMI_TOKEN`) and the route to her server on the same host (`extra_hosts: host-gateway`); usage rows `external` from her `stats`.
- **Лілі's panel card** (an agent card in today's panel, type `bridge`; v7 moves it under System → Agents as `external`): Lumi's reachability (`/v1/health`), the last turn's outcome from `state/lumi.bridge.json`; never her `thinking`, mood or replies; her token rows unpriced; no memory tabs, no Forget.
- VISION: the "Lili herself" wording becomes "connected through the bridge".
- (Owner) The Matrix account, the invite; Lumi's server token and her bind address.

**DoD:**
- (Manual, owner) Лілі's card appears in the panel, and start/stop/restart of the bridge work from it.
- (Manual, owner) Named («Лілі», «Стхіро»…), she answers in the room; unnamed, she stays silent; her `thinking` never appears in the room, the logs or the panel.
- (Manual, owner) While the owner talks to her privately, the room gets silence (`409`), never an error.
- She never posts on her own.

**Tests:** unit — the bridge against a fake Lumi server (turn payload with the lines since her last turn, `turn_id`, `409`, `5xx`, timeout, `thinking` never posted, no post-call filtering, no post without a trigger), mention detection for both names, the env-file isolation, `external` usage rows.

### v6.2 — Лілі under the full rules

**Status:** ⏳ planned.

**Goal:** Лілі takes part in the room like Ada and Bruno — chosen by the turn-taking, not only when named.

Design: more-agents.md §Lumi (the bridge), §4. Depends on: v6.1, proven in the room.

**Tasks:**
- `agents/lumi.toml`: `[turns] mode = "ranked"`, weight 1 — she joins R1 (`OWNER_REPLIERS`) and R2 (the next speaker).
- Each time she is chosen, the bridge forwards the chat updates since her last turn; the slow-engine rules apply (R3 only before the call, the fallback after `FALLBACK_S` when she is away or busy).

**DoD:**
- (Manual, owner) On unnamed messages Лілі answers about as often as the others; when she is away or busy, the fallback answers instead and the room never stalls.
- A simulated wave with Лілі ranked never exceeds `MAX_BOT_TURNS` beyond the answers to the owner.

**Tests:** unit — ranking with her in it, R3 and the fallback for a slow or unreachable bridge, the multi-agent simulation with her ranked.

## v7 — Applications: the panel's System and Applications

The owner, 2026-10-25: the panel stops being "a simulation and its agents". **Simulations become applications**:
places where agents meet the owner or each other, each reached over one protocol (Agora today, Telegram next, later
RoboFace). An application shows **who is connected to it and in which context** (`room`, `listens`, `private`).
**System** holds what is not tied to one application: **Agents**, **Server** and **Tokens**. The model makes room for
agents reachable in several places (Кіра in the room, in her private chat and in Telegram) and for external agents
(Лілі in v6, later Noos). The owner's decisions (2026-10-25): the rename goes everywhere; each agent writes the
status of its connections so the panel can monitor them; the panel switches a declared connection on and off and
configures it, and the repo declares it; a switched-off connection keeps everything in a buffer and gives the
backlog one answer; Hermes's contexts are `listens` and `digests`; alerts come later. The design and its decisions
are in [features/applications.md](features/applications.md) (draft; its open questions closed by the owner on
2026-10-25); read it before generating the issues. Depends on: v5 (v5.7 for v7.2).

### v7.1 — System and Applications: the panel's new shape

**Status:** ⏳ planned.

**Goal:** the panel is reorganised into **Applications** (Agora) and **System** (Agents, Server, Tokens). Agora's
page lists every connected agent with its contexts and monitors each connection. No new application; the agents
talk as before and gain only the status file.

Design: applications.md §The model, §The panel, §Monitoring.

**Tasks:**
- **The rename** (the owner: everywhere). "Simulation" becomes "application" throughout: `simulations.toml` → `applications.toml` (the same
  entry shape), `agents/registry.py` and `panel/registry.py`, the agent TOML key `simulation` → `application`
  (`simulation` still read in v7.1, with a log line naming it), the Dockerfiles' copy, the API
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
- **The design addendum (v7)** in `specification/design/README.md`: the rail, the application page, System →
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

### v7.2 — Telegram as an application: Кіра connected

**Status:** ⏳ planned.

**Goal:** Telegram is the second application. Кіра's bot from v5.7 becomes her **connection** to it: declared in
the registry, then switched on and off and configured from the panel. It is still the same private conversation as
in Agora.

Design: applications.md §Rules, §Connection settings, §Applications after v7 → Telegram.

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
  - v7.2 moves into it what v5.7 fixes in code or env for Кіра's Telegram (the owner agreed, 2026-10-25): answering
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

## v8 — Кіра's inner life: her state, her feelings and what she waits for

**Status:** ⏳ planned.

The owner, 2026-10-26: the last three phases of her emotional life become a version of their own, v8 (Лілі v6, Applications v7, Кіра's inner life v8, the Theatre v9).
- v5.10–v5.15 give her a mood of the day, the events of her life, her reading and thoughts, and a backup model for her
  private chat.
- v8 gives her:
  - a state that lasts between replies and moves her voice (v8.1);
  - feelings toward each person, open threads, and bounded effects on what she does (v8.2);
  - anticipation and strong memories (v8.3).

For Кіра only, for now. The design is in [features/voice-emotion.md](features/voice-emotion.md) §Her emotional life;
read it before generating the issues. Depends on: v5.10–v5.15.

### v8.1 — The moment and the day: her state and her voice

**Status:** ⏳ planned.

**Goal:** Кіра carries an emotional state between replies: valence, arousal and fatigue. It decays to the day's
mood within hours, and a slow background holds how she has been lately. Her voice follows it: code sets its
stability and speed, never the model.

**Tasks:**
- **The state** (`agents/feeling.py`, pure).
  - Valence, arousal and fatigue with a half-life of about 2 hours toward the day's baseline. The baseline comes from
    v5.10's mood, with numbers answered with the reading.
  - The background is a slow average of the days, with a half-life of about 10 days.
  - Signals:
    - the tags she writes (a pure table);
    - what was said to her, at the session's end;
    - the hour and her usual week (fatigue after a night under the dome);
    - her events (v5.11).
  - Current state in `state/kira.feeling.json` (atomic); its history in `state/kira.feeling.jsonl` (append-only).
- **In her prompt: words, never numbers.** A pure table turns the state into a short phrase in a block «Як ти
  зараз», after «Сьогодні».
- **In her voice.** Stability 0.2–0.5 and speed 0.9–1.1 from arousal and fatigue, for each synthesis.
- **The panel.** Her Voice tab shows the state and the background, read-only.

**DoD:**
- (Manual, owner) After a laughing exchange her next voice notes are livelier, and the next morning she is back to
  her day's mood.
- (Manual, owner) The panel shows her state moving through a day.

**Tests:**
- the decay and the background with an injected clock;
- the tag signals;
- the words table, with no number and no banned word;
- the voice settings within their ranges;
- the history appended and never rewritten.

**Not in this phase:** feelings toward people; threads; behaviour.

### v8.2 — Feelings, open threads and her behaviour

**Status:** ⏳ planned.

**Goal:** what happens between Кіра and the people she talks to stays with her for weeks, not one summary. She
feels closeness, trust, hurt, longing and jealousy toward each person; an unsettled thing stays open until it is
settled. The state may change what she does, within bounds.

**Owner decisions** (2026-10-26): the state may change her behaviour, not only her tone; Кіра only, for now. A
default, not contradicted: a separate session-end call (kind `feelings`).

**Tasks:**
- **Feelings per person.**
  - At a session's end one call reads the session and answers JSON deltas, each with the line that caused it. Code
    clamps the deltas and applies them.
  - Each feeling decays at its own pace from her TOML: hurt slowly, a passing joy faster.
  - Longing grows with the owner's silence (`last_private_ms`, pure) and drops at contact.
- **Open threads.**
  - Each holds what happened (from the session or an event, never invented), a feeling, an intensity and a date.
  - Raising it again reinforces it; the session-end call closes a settled one.
  - The three strongest reach the prompt; every thread is logged forever.
- **«Як ти зараз»:**
  - **in the private chat:** the whole block, including her feelings toward the owner and the threads about him;
  - **in Agora:** the day, the background and the threads not about him (the discretion rule).
- **Behaviour**, each effect bounded in code:
  - **reply cap:** 0.6×–1.2×;
  - **writing first:** the idle interval shortens with longing and lengthens with hurt, within `PRIVATE_HOURS` and
    the daily cap;
  - **after a strong hurt:** a delayed and shorter answer to the owner, at most 20 minutes; his message is never
    dropped;
  - **Agora's turn rules stay shared:** the state never decides *whether* she takes a turn.
- **The panel.** Her feelings as bars and the open threads, read-only.
- **ARCHITECTURE:** §Memory, §Prompt assembly, §Contracts.

**DoD:**
- (Manual, owner) A sharp exchange leaves her cooler for days, not one reply, and a warm one is still felt the next
  day.
- (Manual, owner) After a long silence she writes first sooner and warmer, and nothing about him reaches Agora.

**Tests:**
- the deltas parsed and clamped;
- the decay rates;
- longing from silence;
- a thread's life cycle;
- the private and Agora blocks;
- the behaviour bounds;
- the owner's message never dropped;
- no banned word and no number in a prompt.

**Not in this phase:** anticipation; the weight of memories.

### v8.3 — Anticipation and strong memories

**Status:** ⏳ planned.

**Goal:** what is coming weighs on Кіра more as it nears: a birthday, a deadline, a date, an anniversary. A strong
day stays with her for months, not only seven days.

**Tasks:**
- **Anticipation.** A pure curve over the days left to a known event (v5.11), a plan's date or an anniversary from
  her life story. It peaks on the day and becomes a memory after.
- **The weight of a day.** The day-memory call also answers the day's charge (0–3). Up to a few strong days of the
  last months stay in her prompt past the 7-day window, labelled by their date.
- **Recall** (v5.8) ranks a charged line higher.
- **The panel.** What she is waiting for, and her strong days.

**DoD:**
- (Manual, owner) In the days before a known date she brings it up more and with more feeling.
- (Manual, owner) A vivid day from weeks ago still surfaces in her talk.

**Tests:**
- the anticipation curve with an injected clock;
- the charge parsed;
- the strong days' selection and its cap;
- recall's ranking with the charge;
- a past memory never rewritten.

**Not in this phase:** the other persons; v5.10–v5.15 and v8 are Кіра's only, for now (the owner, 2026-10-26).

## v9 — Theatre: plays on the Stage

**Status:** ⏳ planned.

The owner, 2026-10-25: the radio theatre is v7 (v9 since 2026-10-26: Лілі v6, Applications v7, Кіра's inner life v8, the Theatre v9). The members of Agora perform audio plays together in a second room,
the Stage, and Hermes records each play into one file. The design, its phases and its open questions are in the
draft [features/radio-theatre.md](features/radio-theatre.md) (Ukrainian copy: `radio-theatre-UA.md`). Its phases
are written into this file once its open questions are closed. Its first proposed phase, the three new personas,
shipped as v5.5. Depends on: v5.4 (the Agora recording) and v7 (in the v7 model the Stage is a second room of the
Agora application).
