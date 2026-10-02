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

## 8. Security (summary)

| Threat | Protection |
| --- | --- |
| Someone registers on the server | Registration disabled after phase 2; the token is only in `server/.env` |
| Someone from the internet | Port 8008 is not forwarded on the router; ufw allows only `192.168.1.0/24`; federation disabled |
| Someone messages the bots (DM, another room) | Allowlist in code: only `ROOM_ID` + `{OWNER, other agent}` |
| Key leak | `.env`, `server/.env`, `state/` are in `.gitignore`; tokens and message texts are not logged |
| Agents burn credits chatting with each other | `MAX_BOT_TURNS`, `BOT_REPLY_P`, `max_output_tokens` |

HTTP without TLS on the LAN is a deliberate PoC trade-off: passwords travel in plaintext over the home network. Before any external access: Tailscale (or a reverse proxy with TLS).

## 9. Out of scope for the PoC

- E2EE, voice/video (Element Call + LiveKit), media (images, voice messages).
- Memory across restarts (history comes only from `sync`, kept in memory).
- Connecting Lili: a separate Matrix daemon on her `inbox`/`outbox` bus (like the current Telegram daemons) — the next step if the PoC succeeds.
- Tests: for the PoC, manual DoD checks are enough; unit tests are worth writing only for the pure "who replies" logic (filter + `bot_streak`), since it involves no network.
