# matrix-agora — PoC specification

> English translation of [SPEC-UA.md](SPEC-UA.md) (the Ukrainian original). Keep the two in sync.

A self-hosted Matrix server on the home network, where **you and two simple LLM agents** (Gemini 2.5 Flash) talk in a single room. The agents see both you and each other; nobody from outside can message them.

The goal of the PoC is to validate the setup itself (server → client → bots → three-way conversation) before connecting real agents such as Lili to it. Simplicity matters more than completeness.

## 1. Architecture

```
 ┌──────────────── Ubuntu server 192.168.1.197 ────────────────┐
 │  Docker: continuwuity (Matrix homeserver)  :8008  (HTTP, LAN) │
 │  server_name = agora.lan, federation OFF, encryption OFF      │
 └───────────────▲──────────────────▲──────────────────▲────────┘
                 │ Client-Server API (http://192.168.1.197:8008)
     ┌───────────┴───┐     ┌────────┴────────┐  ┌──────┴──────────┐
     │ Element Desktop│     │ agent "Ada"     │  │ agent "Bruno"   │
     │ (you, @me)     │     │ Python + nio    │  │ Python + nio    │
     └────────────────┘     │ → Gemini API    │  │ → Gemini API    │
                            └─────────────────┘  └─────────────────┘
                 Mac (the client and both agents run here)
```

- **Server:** [Continuwuity](https://continuwuity.org) — a Matrix homeserver written in Rust: a single container, embedded DB (RocksDB), no Postgres.
- **Client:** Element Desktop on the Mac. Specifically Desktop, not app.element.io: the web version runs over HTTPS and will not connect to an HTTP server on the LAN (mixed content).
- **Agents:** two Python processes on the Mac, one and the same code, different configs (name, persona, account). Libraries: `matrix-nio` (Matrix) + `google-genai` (Gemini).
- **Panel (from phase 9):** a local web panel on the Mac (`127.0.0.1`) for starting the agents and administration.
- **TLS:** none, since this is a PoC on the home network. External access only later, via Tailscale; **do not open** a port on the router.

The agent names "Ada" and "Bruno" are placeholders; replace them with your own.

## 2. Phase 0 — server (Ubuntu, 192.168.1.197)

### Tasks

1. Install Docker Engine + the compose plugin (from Docker's official repository for Ubuntu).
2. Create `~/matrix-agora/server/docker-compose.yml` (in the repository: `server/docker-compose.yml`):

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
         CONTINUWUITY_ALLOW_REGISTRATION: "true"    # temporarily, for phase 2
         CONTINUWUITY_REGISTRATION_TOKEN: "${REGISTRATION_TOKEN}"
   volumes:
     db:
   ```

   `REGISTRATION_TOKEN` lives next to it in `server/.env` (a long random string, `openssl rand -hex 24`) and is never committed to git.
3. Firewall: `sudo ufw allow from 192.168.1.0/24 to any port 8008 proto tcp` — the port is reachable only from the home network.
4. `docker compose up -d`, check the logs: `docker compose logs -f homeserver`.

`server_name` is only the "domain" part of user names (`@ada:agora.lan`). No DNS is needed for it, because clients connect to `http://192.168.1.197:8008` directly. If the server's IP ever changes, only the URL in the configs changes; the names stay the same.

### DoD

- From the Mac: `curl http://192.168.1.197:8008/_matrix/client/versions` returns JSON with a list of versions.
- `curl http://192.168.1.197:8008/_matrix/federation/v1/version` does not respond as a federation endpoint (federation is disabled).
- After `sudo reboot` of the server, the container comes back up on its own.

## 3. Phase 1 — client (Mac)

### Tasks

1. `brew install --cask element`.
2. Element → Create account → **Edit** homeserver → `http://192.168.1.197:8008` → register yourself (`me`) with `REGISTRATION_TOKEN`. The first account on the server automatically becomes the admin and receives an invite to the admin room.

### DoD

- You are logged in as `@me:agora.lan` and can see the admin room.

## 4. Phase 2 — bot accounts and the room

### Tasks

1. Create the accounts `ada` and `bruno` — either via registration with the token (log out / log in in Element, or `curl` to `/_matrix/client/v3/register`), or with a command in the admin room (`!admin users create-user ada`).
2. **Close registration:** `CONTINUWUITY_ALLOW_REGISTRATION: "false"`, `docker compose up -d`. From now on, only the admin creates new accounts.
3. In Element, create the room **"Agora"**: private (invite-only), encryption disabled (it is forbidden on the server anyway). Invite `@ada:agora.lan` and `@bruno:agora.lan`.
4. Write down the room's `room_id` (Room settings → Advanced, of the form `!xxxx:agora.lan`).

### DoD

- An attempt to register a new account without the admin is refused.
- The room contains you + two invites (the bots will accept them in phase 3).

## 5. Phase 3 — echo bot (Matrix without LLM)

The goal is to verify the Matrix part separately from the LLM.

### Project structure

```
matrix-agora/
  SPEC.md
  README.md
  pyproject.toml            # uv; deps: matrix-nio, google-genai, python-dotenv
  server/
    docker-compose.yml
    .env.example            # REGISTRATION_TOKEN=
  agents/
    agent.py                # one codebase for both agents
    ada.toml                # name, user_id, persona, …
    bruno.toml
  .env.example              # HOMESERVER, ROOM_ID, OWNER, ADA_PASSWORD, BRUNO_PASSWORD, GEMINI_API_KEY
  state/                    # access token + device_id of each bot (gitignored)
```

Run: `uv run agents/agent.py agents/ada.toml` (and the same for `bruno.toml` in a separate terminal).

### Behavior

1. **Login:** on the first run, log in with the password and save `access_token` + `device_id` to `state/<name>.json`. Subsequent runs use the token (otherwise every start creates a new "device" on the server).
2. **Invites:** accept (`join`) **only** invites from `OWNER` to the room `ROOM_ID`. All others: `leave`/ignore.
3. **Start without the past:** the first `sync` is only for obtaining `next_batch` — **do not process** events from it (otherwise, after a restart, the bot will reply to the entire history). After that, `sync_forever`.
4. **Message filter** (`RoomMessageText`): process a message only if all conditions are met:
   - `room.room_id == ROOM_ID`;
   - `event.sender != own user_id`;
   - `event.sender ∈ {OWNER, user_id of the other agent}` — an **allowlist in code**, like `LUMI_TELEGRAM_ALLOWLIST` in Lili.
5. **Echo:** reply with `"<name> чує: <text>"` (Ukrainian for "<name> hears: <text>"; this literal format is what the bot sends).

### DoD

- You write in "Agora" — both bots reply with an echo.
- Restarting a bot: it does not reply to old messages and does not create a new device.
- A message in another room / in a DM to the bot is ignored (shown in the log as `ignored`).

## 6. Phase 4 — LLM (Gemini 2.5 Flash)

### Tasks

1. Replace the echo with a Gemini call via `google-genai` (async):

   ```python
   from google import genai
   from google.genai import types

   client = genai.Client()  # reads GEMINI_API_KEY from the environment
   resp = await client.aio.models.generate_content(
       model="gemini-2.5-flash",
       contents=transcript,  # see below
       config=types.GenerateContentConfig(
           system_instruction=persona,
           max_output_tokens=400,
           thinking_config=types.ThinkingConfig(thinking_budget=0),  # faster and cheaper for chat
       ),
   )
   reply = resp.text
   ```

2. **Context:** each agent keeps in memory the last `HISTORY_N` (e.g. 30) room messages from `sync` — **including its own and the other agent's**. They are passed to the model as a single text, one `"Name: text"` per line, plus the instruction: "You are <name>. Reply only on your own behalf, briefly, without a name prefix."
3. **Persona:** in `<name>.toml` — 3–5 sentences describing the character, so that the agents differ noticeably.
4. **Typing:** `room_typing(room_id, True)` before the Gemini call, `False` after it.
5. **Errors:** if Gemini fails or returns an empty response — log it, and do not send a short service message (stay silent); the bot does not crash.
6. Send as `m.text` (not `m.notice`) — otherwise the other agent may treat it as a service message.

### DoD

- You write — each agent replies in its own character, taking previous lines into account.
- While an agent is thinking, Element shows "typing…".
- Without `GEMINI_API_KEY`, or with an invalid one, the bot stays alive and writes the error to the log.

## 7. Phase 5 — three-way conversation and loop protection

The agents see each other, so without rules they will reply to each other endlessly.

### Who replies

1. **Your message:**
   - mentions one agent (by name or mention) — **only that agent** replies;
   - mentions no one — **both** reply, each after a random delay of 1–4 s (so they don't speak at the same time, and the second one has already seen the first one's line in the history).
2. **A message from the other agent:** reply only if `bot_streak < MAX_BOT_TURNS` (default **2**), and with probability `BOT_REPLY_P` (e.g. 0.5) — so that the conversation is not mechanical.
   - `bot_streak` is the number of consecutive agent messages **after your last** message. Both agents compute it from the same room timeline, so the count is consistent without any coordination.
   - Your message resets `bot_streak` to 0.
3. An agent may decide "nothing to add here": if the model returned exactly `PASS`, send nothing (allow this in the instruction).

### Settings

In `.env` / toml: `MAX_BOT_TURNS`, `BOT_REPLY_P`, `HISTORY_N`, `REPLY_DELAY_S`.

### DoD

- You write one message with no mentions — at most `2 + MAX_BOT_TURNS` agent replies, then silence until you write again.
- "Адо, що думаєш?" ("Ada, what do you think?" — note the Ukrainian vocative «Адо») — only Ada replies.
- The agents refer to each other's lines (it is evident that they see each other).

## 8. Phase 6 — agent canons and memory across sessions

Right now an agent knows only a 3–5 sentence persona about itself and remembers the conversation only while its process runs. Phase 6 gives each agent a **canon** — a stable description of who it is — and **memory of the previous session**: a short summary of the last conversation that goes into the prompt after a restart.

### Canons

1. A **canon** is a markdown file in the repository, the source of truth about the agent:
   - `agents/canon/common.md` — shared by both: what this room is, who the owner (`OWNER`) is, who the other agent is, the language and tone of the conversation;
   - `agents/canon/<name>.md` — personal: character, way of speaking, interests, attitude towards the owner and the other agent, what the agent never does.
   - The canons describe the agents as **humans**: Ada and Bruno believe they are people and do not know they are LLM agents. This is the owner's game in a closed room — the owner is the only person they talk to and knows the truth, so there is no outsider to mislead. If other people ever join the room, this rule must be revisited.
2. The canon **replaces** the `persona` field from phase 4: in `<name>.toml` it becomes `canon = "agents/canon/<name>.md"`.
3. The canon is read once at startup. If the file is missing or empty, the bot does not start and logs a clear error.
4. The reply-format rules (only on your own behalf, no name prefix, `PASS` allowed) stay **in code**, not in the canon, so that editing a canon cannot accidentally break them. These rules and the summary and memory prompts never mention that the agent is a model or a bot.
5. Canons live in the public git repository, so they contain **no secrets and no private data** about the owner.

### Session memory

1. A **session** is a stretch of conversation in the room. It ends when the room has been silent for longer than `SESSION_IDLE_S` (e.g. 900 s) or when the bot is stopped (Ctrl+C / SIGTERM).
2. The **session timeline** is every room message since the last summary, kept separately from `HISTORY_N`. If it grows beyond `SESSION_MAX_MESSAGES` (e.g. 200), the summary is made early and the timeline is cleared.
3. **Summary:** at the end of a session, if there were new messages since the last summary, the agent makes a separate Gemini call: previous summary + session timeline → a new summary of at most `SUMMARY_MAX_WORDS` (e.g. 200) words. This way old topics don't vanish at once but get compressed.
4. **Summary content** — in the agent's first person, in the language of the conversation: what was discussed, what was decided, what the owner said about themselves, which questions remain open, what the agent promised.
5. **Storage:** `state/<name>.memory.md` (the `state/` folder is in `.gitignore`). The write is atomic (temporary file + rename), so an interruption never leaves half a file.
6. **Prompt:** `system_instruction` = canon (shared + personal) + a section "What you remember from the last conversation: <summary>" + the reply-format rules. `contents` is, as before, the last `HISTORY_N` messages.
7. **Startup:** the summary is read from the file. The first `sync` is, as before, not processed — memory comes from the summary, not from the room history.
8. **Errors:** if Gemini fails to produce a summary, the previous one is kept, the error is logged, and the bot does not crash. A corrupt memory file — the bot starts without memory and logs it.
9. Each agent summarizes **on its own, from its own point of view**: Ada's and Bruno's summaries may differ, and that is fine.
10. On shutdown the summary is made with a timeout (e.g. 20 s), so Ctrl+C does not hang.

### Settings

In `.env` / toml: `SESSION_IDLE_S`, `SESSION_MAX_MESSAGES`, `SUMMARY_MAX_WORDS`.

### DoD

- "Адо, хто ти?" ("Ada, who are you?") — the answer is consistent with `agents/canon/ada.md`, and Ada speaks of herself as a person; Bruno answers the same question according to his canon.
- Talk about some topic and stop both agents — `state/ada.memory.md` and `state/bruno.memory.md` appear, no longer than `SUMMARY_MAX_WORDS` words, with no tokens or passwords.
- Without stopping: after `SESSION_IDLE_S` of silence the summary updates on its own.
- After a restart: "Про що ми говорили минулого разу?" ("What did we talk about last time?") — each agent recalls the topic.
- Gemini fails during summarization — the old summary is intact, the bot is alive.
- Memory files never get into git; message and summary texts are not logged.
- Unit tests without network (Gemini mocked): prompt assembly (canon + summary + rules), the "session ended" decision, reading and writing the memory file (missing file, corrupt file, atomic write).

## 9. Phase 7 — world awareness

The agents know where they are and what time it is, and they remember past days — day by day. All of it goes into the prompt; the memories are generated automatically, nobody writes them by hand.

### Place and time

1. **Place:** the agents live in Lviv. `LOCATION` (default "Львів, Україна") and `TIMEZONE` (`Europe/Kyiv`) are in `.env` / toml.
2. **Calendar and time:** before every Gemini call the code computes the current moment in `TIMEZONE` and adds to the prompt the date, day of the week, time, part of the day (morning / day / evening / night) and season — in Ukrainian, e.g. «Зараз четвер, 2 жовтня 2026, 20:15, вечір, осінь» ("It is Thursday, 2 October 2026, 20:15, evening, autumn").
3. Day and month names come from tables in code, not from the Mac's system locale. The clock is replaceable in tests (a function that returns "now").
4. **Last conversation:** the prompt says when the last session summary (phase 6) was made, e.g. «Востаннє ви говорили позавчора ввечері» ("You last talked the evening before yesterday").

### Memories by day

1. A **day memory** is a short first-person text by the agent about one day: what it did and saw in Lviv that day, and what was discussed in the room, if there was a conversation.
2. **Generated automatically,** once for every past day, with a separate Gemini call. Input: the agent's canon, that day's date, day of the week and season, the previous days' memories (for continuity) and that day's conversation journal.
3. **The day's conversation journal:** every session summary (phase 6) is additionally appended, with its time, to `state/<name>.days/YYYY-MM-DD.talk.md`.
4. **Truth and invention:** what happened in the room comes **only** from the conversation journal. Invented episodes of the day involve only the agent itself and the city — no words or actions by the owner or the other agent that did not happen (otherwise Ada's and Bruno's memories would contradict each other).
5. **When:** after midnight in `TIMEZONE` the bot generates the memory for yesterday. At startup it catches up on missed days (while the bot was off), but no further back than `MEMORY_DAYS` days.
6. **Storage:** `state/<name>.days/YYYY-MM-DD.md`, at most `DAY_MEMORY_MAX_WORDS` (e.g. 120) words, atomic write. A past day's memory is **never rewritten** — memories are stable.
7. **Prompt:** a section "Your memories of the last days" — the last `MEMORY_DAYS` (e.g. 7) memories in chronological order, each labeled with its day («вчора, середа, 1 жовтня: …» — "yesterday, Wednesday, 1 October: …").
8. **Errors:** if Gemini fails, the day stays without a memory, the attempt is retried later, and the bot does not crash.

### Prompt order

`system_instruction` = canon → place, calendar and time → memories of the last days → last-session summary → reply-format rules. `contents` is, as before, the last `HISTORY_N` messages.

### Settings

In `.env` / toml: `LOCATION`, `TIMEZONE`, `MEMORY_DAYS`, `DAY_MEMORY_MAX_WORDS`.

### DoD

- "Котра година?", "Який сьогодні день?" ("What time is it?", "What day is it today?") — the correct time, date and day of the week in Lviv.
- "Де ти?" ("Where are you?") — the agent knows it is in Lviv.
- After midnight `state/ada.days/<yesterday>.md` and `state/bruno.days/<yesterday>.md` appear; asked "Що ти робила вчора?" ("What did you do yesterday?"), Ada answers from her memory, and if there was a conversation yesterday, mentions it too.
- The bot was off for 3 days — at startup memories for the missed days appear (no more than `MEMORY_DAYS`), and old files are unchanged.
- Invented episodes contain no words or actions by the owner or the other agent that did not happen in the room.
- Gemini fails while generating a memory — the bot is alive, and the day is generated later.
- Unit tests without network (Gemini mocked, clock replaced): date and time in Ukrainian (including the switch to and from daylight saving time), which days need generating, "a past day is never rewritten", the order of the prompt sections.

## 10. Phase 8 — token accounting and report

To see what the conversations cost, every Gemini call is recorded with its token counts, and a separate command builds a report.

### Accounting

1. After **every** Gemini call — a reply, a session summary (phase 6), a day memory (phase 7) — the agent takes `resp.usage_metadata` and appends one JSON line to `state/<name>.usage.jsonl`.
2. Line fields: `ts` (time in `TIMEZONE`), `agent`, `kind` (`reply` / `summary` / `day_memory`), `model`, `prompt_tokens`, `output_tokens`, `total_tokens`, `ok`. **No texts** of messages, prompts or replies.
3. Each agent writes only to its own file, so the two processes never share a file.
4. If `usage_metadata` is missing or lacks fields, the line is written with `null`s and the bot does not crash. A failed call is written with `ok: false`.
5. Accounting never blocks the conversation: a write error is logged and the bot carries on.

### Report

1. Command: `uv run agents/usage_report.py [--days N] [--since YYYY-MM-DD] [--markdown]`.
2. It reads every `state/*.usage.jsonl` and prints a table by day × agent × call kind: number of calls, input and output tokens, total, and estimated cost. At the bottom: totals per agent and overall.
3. **Cost** is computed from prices in `.env`: `PRICE_INPUT_PER_1M`, `PRICE_OUTPUT_PER_1M` (USD per 1M tokens, from the Gemini price list). There are no prices in code, because they change. If no prices are set, the report has no cost column.
4. A corrupt line is skipped with a warning; if there are no files, the report says there is no data.
5. `--markdown` prints the same table as markdown, so it can be pasted into notes.

### Settings

In `.env`: `PRICE_INPUT_PER_1M`, `PRICE_OUTPUT_PER_1M`.

### DoD

- After a conversation, `state/ada.usage.jsonl` and `state/bruno.usage.jsonl` hold one line per Gemini call, with token counts and no texts.
- `uv run agents/usage_report.py --days 7` shows calls and tokens by day, agent and kind, plus the estimated cost; the sums match the lines in the files.
- The report works when the files are missing, when they are empty, and when one line is corrupt.
- Unit tests without network: parsing `usage_metadata` (including missing fields), aggregation, cost calculation, skipping corrupt lines.

## 11. Phase 9 — web panel on the Mac

So that you don't have to keep two terminals open or dig through files in `state/`, a local web panel runs on the Mac. It starts and stops the agents and shows logs, memory, tokens and the server status.

### How it works

1. A separate process in the same uv project: `uv run panel/app.py`, then a browser at `http://127.0.0.1:8090` (`PANEL_PORT`).
2. The server is `aiohttp.web`: aiohttp is already a dependency of `matrix-nio`, so no new framework is needed. The page is a single HTML file with vanilla JS, no build step and no CDN. The interface is in Ukrainian.
3. The panel listens **only on `127.0.0.1`** — other devices on the network cannot see it.
4. The agents also work without the panel: starting them from the terminal, as in phase 3, still works.

### Agents

1. For each agent the panel shows its state (running / stopped), PID, uptime and last activity, plus **Start**, **Stop** and **Restart** buttons.
2. **Start:** the panel runs `uv run agents/agent.py agents/<name>.toml` in a separate process session, so stopping the panel itself does not stop the agents.
3. **Stop:** SIGINT (the agent has time to make its session summary, phase 6); if the process has not exited after 30 s — SIGKILL.
4. **Single instance:** at startup the agent takes a lock on `state/<name>.lock` (flock) and writes its PID there. A second instance of the same agent — from the panel or from the terminal — does not start and logs a clear error. Otherwise two Adas would reply twice.
5. An agent started from the terminal is detected by the panel through its lock file, shown as "running", and can be stopped (SIGINT by PID).

### Logs

1. The agent always writes its log to `state/logs/<name>.log` (rotation: 1 MB × 3 files) and to the console.
2. The panel shows the last 200 log lines of each agent and refreshes them every 2 s.
3. As before, logs contain no tokens, passwords or message texts, so they are safe to show.

### Administration

1. **Server:** an indicator of whether the homeserver answers (`/_matrix/client/versions`), refreshed every 30 s.
2. **Memory (phases 6–7):** for each agent — the last-session summary and the day memories. The **"Forget the last session"** button deletes `state/<name>.memory.md` after confirmation, and only while the agent is stopped (otherwise it would rewrite the file from its own memory). The panel does not change day memories.
3. **Canons (phase 6):** view `agents/canon/*.md`, read-only — they are edited in an editor and committed.
4. **Tokens (phase 8):** the same report as `usage_report.py`, as a table for the last 7 days, sharing the aggregation code.
5. **Settings:** the effective values from `.env` and toml, read-only; anything that looks like a secret (`*_KEY`, `*_PASSWORD`, `*_TOKEN`) is masked.

### Panel security

1. Only `127.0.0.1`, CORS disabled.
2. Every request checks the `Host` header: only `127.0.0.1:<port>` or `localhost:<port>` — protection against DNS rebinding.
3. Actions that change something (start, stop, forget) are `POST`-only with the panel's own `Origin`, so a third-party site in the browser cannot press a button on your behalf.
4. The panel does not run commands on the Ubuntu server.

### Settings

In `.env`: `PANEL_PORT`.

### DoD

- `uv run panel/app.py` → `http://127.0.0.1:8090` shows both agents with their state; from another device on the network the panel is unreachable.
- Start, Stop and Restart work; after Stop there is a fresh session summary (phase 6).
- A second instance of an agent does not start, neither from the panel nor from the terminal.
- An agent started from the terminal is shown in the panel as "running"; closing the panel does not stop the agents.
- Logs are visible and refresh; they contain no tokens, passwords or message texts.
- The homeserver container is stopped → the server indicator is red.
- "Forget the last session" works only for a stopped agent and only after confirmation.
- The token table matches `uv run agents/usage_report.py --days 7`.
- Secrets are masked in the settings view.
- A `POST` with a foreign `Origin` or a request with a foreign `Host` is refused.
- Unit tests without network: the process supervisor on fake processes (start, stop, timeout → kill), the single-instance lock, secret masking, the `Host` / `Origin` checks, the API handlers via the aiohttp test client.

## 12. Security (summary)

| Threat | Protection |
| --- | --- |
| Someone registers on the server | Registration disabled after phase 2; the token is only in `server/.env` |
| Someone from the internet | Port 8008 is not forwarded on the router; ufw allows only `192.168.1.0/24`; federation disabled |
| Someone messages the bots (DM, another room) | Allowlist in code: only `ROOM_ID` + `{OWNER, other agent}` |
| Key leak | `.env`, `server/.env`, `state/` are in `.gitignore`; tokens and message texts are not logged |
| Agents burn credits chatting with each other | `MAX_BOT_TURNS`, `BOT_REPLY_P`, `max_output_tokens`; one summary call per session; one memory per day; the token report (phase 8) shows the spend |
| Conversation leak | Summaries, day journals and day memories live only in `state/` (in `.gitignore`); their texts are not logged |
| Private data in the public repo | Canons are committed — no secrets and no private data about the owner |
| Someone controls the agents through the panel | The panel is only on `127.0.0.1`; `Host` and `Origin` checks; secrets masked in the settings view |

HTTP without TLS on the LAN is a deliberate PoC trade-off: passwords travel in plaintext over the home network. Before any external access: Tailscale (or a reverse proxy with TLS).
