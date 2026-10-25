# Feature: applications and connections — the panel's v6 concept

> **Status: draft, 2026-10-25; its open questions are closed.** A proposal, not a contract. It designs ROADMAP
> **v6 Applications**, phases v6.1–v6.2. v5.7 (Кіра in Telegram) is built first, as planned, with no panel change; v6 then brings it into this
> model. v7 is the Theatre ([radio-theatre.md](radio-theatre.md)), and Лілі (the Lumi bridge) moves from v6 to
> **v8**. ARCHITECTURE.md does not link here yet; the changes in [What changes where](#what-changes-where) land with
> the v6 phases.
>
> Sources: the owner's messages of 2026-10-25 (the decisions below are the owner's unless marked *proposed*), the
> matrix-agora code at v5.6.0, the RoboFace repo (`~/development/roboface`, v2.6.2), the Lumi repo
> (`~/development/lumi`, v2.7.0) and the Noos repo (`~/claude-home` on the server, read-only).

## The owner's brief (2026-10-25)

- The panel gets a place that manages the agents' connections to other APIs: Telegram first, then RoboFace, then
  outside agents such as Lumi and Noos.
- It is not a "Bridge" subsection: it sits on the same level as Agora.
- **"Simulations" become "Applications".**
- **System** holds **Agents**, **Server** and **Tokens**. An **application** shows who is connected to it and with
  what context.
- A whole new version, v6, for this change of the panel's concept. v5.7 stays as designed: Кіра's Telegram bot,
  no panel change.
- The radio theatre is v7, so Лілі moves to v8.

The owner's answers to the first open questions (2026-10-25):

- **The rename goes everywhere:** the registry, the TOML key, the code, the API, the UI and the docs.
- **An agent writes the status of its connections, for monitoring.** The first answer was "nothing is added to an
  agent just to feed the panel"; the owner changed it the same day so that the connections can be monitored
  ([Monitoring](#monitoring)). The status file is the one thing an agent writes for the panel, and the panel only
  reads it.
- **The panel switches a connection on and off, and configures it.** The repo declares the connection.
- **A switched-off connection keeps everything in a buffer** and answers it once switched back on (rule 4).
- **Yes** to the first Telegram connection settings and to tokens by application.
- **RoboFace and Noos are deferred.**
- **The last three proposals are accepted:** Hermes's one-to-one room is the context `digests`; alerts come later,
  through Hermes; a backlog gets one answer.

## Summary

Today the panel's model is "a simulation and the agents in it": `simulations.toml` holds one entry, `agora`, every
agent belongs to exactly one simulation, and the left rail nests the agents under it. That model has no place for
an agent that is reachable in more than one place: from v5.6 Кіра talks in the Agora room and in a private chat,
and from v5.7 the same private chat is also reachable from Telegram.

v6 replaces it with three nouns:

- **Agent**: who. The agent's identity, canon, memory, voice and engine. Agents are listed under **System →
  Agents**, independent of where they are connected.
- **Application**: where. A place where agents meet the owner or each other, reached over one protocol: Agora (a
  Matrix room on our homeserver), Telegram (the Bot API), later RoboFace (the desk device).
- **Connection**: one agent in one application, with its **contexts**. Each application's page lists its
  connections.

The panel's rail becomes:

```
APPLICATIONS
  ▣ Agora        ●
  ▣ Telegram     ●      (v6.2)
SYSTEM
  ◉ Agents
  ▤ Server
  ◎ Tokens
```

## Today (v5.6, with v5.7 planned)

- **The registry.** `simulations.toml` holds one entry, `agora`, of kind `matrix-chat`: `services`, `agents`,
  `health`, `endpoints`. The agent TOML carries `simulation = "agora"`. "An agent belongs to one simulation" is
  pinned by `tests/test_registry.py`. The file is copied into the agent image, and `agents/config.py` resolves
  `HOMESERVER` and `ROOM_ID` through it.
- **The panel.** The rail shows "Simulations → Agora" with the agents nested under it, plus "System → Server,
  Tokens" (`panel/static/app.js`, `railHtml`). The API is `/api/simulations…` and `/api/agents…`. The service
  settings live on the simulation's card; an agent's own settings live in its drawer.
- **The private chat (v5.6).** The `private` capability in `kira.toml`: a one-to-one Matrix room with the owner on
  the same homeserver, with its own brief, its own history and memories labelled «наодинці».
- **Telegram (v5.7, planned).** A Bot API client inside Кіра's process (`agents/telegram.py`), switched on by
  `[capabilities] telegram = true`, with its secrets in `server/kira.env`. The panel sees it only in her log.

## The model

### Context

A **context** is the conversation an agent takes part in through a connection, together with what that
conversation brings: the brief, the history it reads, how its memories are labelled, and the rule that decides
when it speaks.

| Context | The conversation | Brief | History | Memories | When it speaks |
|---|---|---|---|---|---|
| `room` | the application's group room | the room prompt (canon, world, today) | the room transcript | the day's memory of the room | the turn-taking: `ranked`, `ambient` or `mention-only`, with its weight |
| `listens` | the same room, read only | none in the room | the room transcript | the herald's digest points | never in the room (a herald) |
| `private` | one-to-one with the owner | the private brief | **the private history: one for every application that carries it** | labelled «наодинці» | answers the owner, may write first, and keeps it to itself in the room |
| `digests` | a herald's one-to-one room with the owner | the digest brief | the room's lines since the last digest | none | a digest on his schedule or on «підсумок», and answers to the owner's questions |

The `private` row carries the rule v5.7 already sets: **one conversation, several applications.** Кіра's private chat
is one history and one memory, whether the owner writes from Element or from Telegram.

### The base application

**Agora is the base application.** Every agent has its Matrix account there, and the roster and the turn-taking
are computed there. *Proposed:* Agora's contexts are derived from the agent's own TOML rather than declared twice:

- `room` with its turn mode for every member that has `[turns]`;
- `listens` for a herald;
- `private` for the `private` capability;
- `digests` for a herald's one-to-one room (the owner, 2026-10-25: `private` means only a person's private chat).

Every other application lists its connections explicitly in the registry.

What the panel will show on Agora's page, from today's TOMLs:

| Agent | Contexts in Agora |
|---|---|
| Ada, Bruno, Leon, Mia, Irma | `room` · ranked, weight 1 |
| Kira | `room` · ranked, weight 1 · `private` |
| Kit | `room` · ambient |
| Claude | `room` · ranked, weight 0.4 |
| Hermes | `listens` · `digests` |

After v6.2 Telegram's page shows one connection: Kira · `private`, the same conversation as her private chat in
Agora.

### Internal and external agents

- **Internal.** Our code runs in our container: the engines `gemini` and `claude-sdk`. These are all the members
  today.
- **External.** The agent runs in another system, and our container is a bridge that applies our rules and forwards
  the traffic. Examples: Лілі (`lumi-http`, v8) and later Noos. System → Agents marks them `external`. Their card
  shows reachability and the last turn's outcome (from the bridge's status file, [Monitoring](#monitoring)), never
  their memory or their texts: their memory belongs to their own system and its own panel.

### Two directions of a connection

1. **Our agent in another application** (Telegram, RoboFace). The adapter runs inside the agent's own process, as
   in v5.7: Кіра's container polls Кіра's bot. There is no central gateway holding every bot's token, and the agents
   share no state and do not coordinate (the turn-taking invariant).
2. **Another system's agent in our application** (Lumi and Noos in Agora). A bridge agent in our compose stack has
   all the room's rules: the allowlist, the first-sync rule, the turn-taking, typing, `m.text`, silence on failure.
   It forwards the room lines to the other system and posts the answer.

"Bridge" stays the name of that adapter in code and in the architecture. In the panel nothing is called a bridge:
the owner sees applications and agents.

### Rules

1. **The repo declares; the panel switches and configures** (the owner, 2026-10-25).
   - Connections live in the registry in the repo.
   - The panel shows every declared connection, switches it off and on, and changes its settings
     ([Connection settings](#connection-settings)). A switch is confirmed, and a save restarts the agent, as the
     v4.7 settings do.
   - The panel never creates a connection and never sees its secret. A new connection means a repo change, an env
     file and a deploy.
2. **A context needs its capability.** A `private` context needs the agent's `private` capability; the registry
   loader rejects anything else by name.
3. **Secrets stay in the agent's own env file** (`server/kira.env` from v5.7), read only by that agent's container
   and synced at 0600. The panel never reads or shows one.
4. **A switched-off connection keeps everything** (the owner, 2026-10-25: "everything must be kept in a buffer").
   - Switched off, the agent stops answering there and does not write first there, but it keeps receiving. Each
     update from the owner goes into its buffer, `state/<name>.telegram.buffer.jsonl` (the text, or the voice note's
     file id; 0600; never in a log), and is then confirmed to Telegram.
   - Switched back on, she reads what waited, in order, and gives one answer to all of it, as a person answers a
     backlog (the owner, 2026-10-25); the buffered voice notes are heard then. The buffered messages then join the private
     history like any other, and the buffer is emptied.
   - A stranger's update is never buffered: the allowlist comes first.
   - While Telegram is off and was the owner's last channel, she writes first in the Element private chat instead
     (*proposed*).
   - When the agent itself is stopped, nothing polls: Telegram keeps the unconfirmed updates for up to 24 hours, and
     the agent takes them from its offset at the next start. Older ones are lost (a Bot API limit).
5. **The human-belief rule holds in every application.** In Telegram Кіра is the same persona as in Agora.
6. **Each agent writes the status of its connections, for monitoring** (the owner, 2026-10-25, revising "nothing is
   added to an agent just to feed the panel"). One file per agent, `state/<name>.connections.json`, read only by the
   panel ([Monitoring](#monitoring)). No other agent reads it, and no decision does, so the turn-taking stays
   derived from the shared inputs. Everything else the panel shows comes from what already exists:
   - the registry: the connection and its contexts;
   - `state/settings.json`, which the panel writes itself: the switch, `since` and the setting overrides;
   - docker: the agent's container state;
   - the agent's log: its `telegram:` lines, shown as the connection's log;
   - the agent's own state files, written for its own work (v5.6's `<name>.private.json`, v5.7's
     `<name>.telegram.json`), read as they are.

## The panel

### Applications → one application

```
Agora · matrix-chat · ● healthy                                 private Matrix room · agora.lan
──────────────────────────────────────────────────────────────────────────────────────────────
Services     homeserver   ● running 8 d                                [restart] [stop]  [log]
Connected 9  agent    contexts                    status                 today in · out   container
             Ada      room · ranked 1             ● ok · synced 4 s ago  41 · 6           ● running 4 d
             Kira     room · ranked 1 · private   ● ok · synced 2 s ago  44 · 10          ● running 4 d
             Kit      room · ambient              ◐ stale · 6 min        12 · 3           ● running 4 d
             Hermes   listens · digests           ● ok · synced 3 s ago  41 · 2           ● running 4 d
             …
Settings     the room's turns, the cat, Claude's news …               (v4.7, unchanged)
```

```
Telegram · telegram-bot · ● ok                                 one bot per agent · private chats
──────────────────────────────────────────────────────────────────────────────────────────────
Connected 1  agent  account   context   status                  today in · out   last in · out
             Kira   @<bot>    private   ● ok · polled 12 s ago  7 · 9            14:31 · 14:32
                    the same chat as in Agora · on since 10-25 14:02 · container ● running 4 d
                    [configure] [switch off] [log]
```

Switched off, the same row reads `○ off · 3 waiting`: the messages kept in the buffer (rule 4).

- **Health** ([Monitoring](#monitoring) gives each connection its status):
  - Agora: the homeserver probe, and a warning when a running member's connection is `stale`, `retrying` or
    `error`;
  - an application with no service of its own (Telegram): ok when every switched-on connection is `ok`; a warning
    when one is `stopped`, `stale`, `retrying` or `error`; off when all are switched off.
- **The connection's log** is the agent's log filtered to that connection's lines (`telegram:`).
- **Configure** opens the connection's settings ([Connection settings](#connection-settings)).
- A row's agent opens the agent's drawer at its **Connections** tab.
- **Agora's own connections are shown, not switched.** An agent leaves the room by being stopped, as today.
  Switching a `room` context off would change the roster the other agents compute their turns from.

### Monitoring

The owner, 2026-10-25: the panel must show whether a connection works, not only whether its container runs. A
container can run while its Matrix sync or its Telegram poller is stuck, retrying or refused.

**The status file** `state/<name>.connections.json`, written by the agent (*proposed* shape; the final names come
with the issues):

```json
{"updated_ms": 1761397320000,
 "connections": {
   "agora":    {"account": "@kira:agora.lan", "state": "ok", "started_ms": 1761050000000,
                "heartbeat_ms": 1761397318000, "last_error": null,
                "contexts": {"room":    {"day": "2026-10-25", "in": 44, "out": 6, "ignored": 0,
                                         "last_in_ms": 1761397310000, "last_out_ms": 1761397200000},
                             "private": {"day": "2026-10-25", "in": 3, "out": 4, "ignored": 0,
                                         "last_in_ms": 1761390000000, "last_out_ms": 1761390050000}}},
   "telegram": {"account": "@<bot username>", "state": "ok", "started_ms": 1761050000000,
                "heartbeat_ms": 1761397308000, "buffered": 0,
                "last_error": {"at_ms": 1761380000000, "kind": "timeout"},
                "contexts": {"private": {"day": "2026-10-25", "in": 7, "out": 9, "ignored": 1,
                                         "last_in_ms": 1761395460000, "last_out_ms": 1761395520000}}}}}
```

- `account`: the agent's public address there: its Matrix user id, or the bot's `@username` from `getMe`.
- `state`:
  - `ok`;
  - `retrying`: a network error, with backoff;
  - `error`: refused (a 401, a revoked token), and the poller stops;
  - `off`: the connection is switched off, with `buffered` messages waiting (rule 4).
- `heartbeat_ms`: the last successful sync or `getUpdates`. It is written at most once a minute (`STATUS_EVERY_S`,
  60), and at once on every change of `state`.
- Per context, the day's counts and the last times:
  - `in`: the messages handled;
  - `out`: the answers sent (a voice note and its text are one answer);
  - `ignored`: refused by the allowlist, or from before the first sync.
- `last_error`: when and what kind (an HTTP status, a timeout, an exception's type), never a text.

**The file's rules:**
- Like every state file: atomic (temp file + rename), 0600, no texts, no tokens, no owner or chat id. A write error is
  logged and never blocks the conversation.
- Each agent writes only its own file. No decision reads it; the agent reads it back at start only to carry on the
  day's counts. No agent reads another's.
- The panel only reads it. An unreadable file shows the status as unknown, never a 500.

**What the panel shows** is a pure function over the switch, the container state, the status entry and an injected
clock:

| Shown | When |
|---|---|
| `off` | the connection is switched off; with the number waiting |
| `stopped` | the container is not running (in Agora the owner stopped the agent; for a switched-on connection elsewhere it is a warning) |
| `stale` | the heartbeat is older than three intervals (3 min) while the container runs |
| `retrying`, `error` | as the agent wrote it, with the last error's time and kind |
| `ok` | otherwise, with the heartbeat's age («synced 4 s ago», «polled 12 s ago») |

The table row shows the account, the status, today's in · out and the last in · out. The drawer's Connections tab
adds each context's counts, `ignored` and the last error.

An external agent's bridge (v8) writes the same file: its Agora entry, and an `external` entry for the other system:
its reachability (the health probe) and the last turn's outcome.

### System → Agents

- The agent cards of today, no longer nested under one application.
- Each card shows its connections as chips with their status dots: `● Agora · room`, `● Agora · private`,
  `● Telegram · private`.
- The drawer keeps its tabs (Log, Session, Memories, Plans, Today, Mood, Tokens, Files, Settings, and v5.8's Facts) and gains
  **Connections**: every application, its contexts and state, and the on/off switch.
- An external agent's card shows `external`, its system's reachability and the last turn's outcome. It has no
  memory tabs and no Forget (as the design addendum (v4.2) already says for Лілі).

### Connection settings

The configuration the owner asked for is built on the v4.7 settings, which put each setting under its service.

- **A third scope.** The schema `agents/settings.py` already has service settings (an application kind's, valued per
  application) and agent settings (valued per agent). It gains **connection settings**: they belong to an
  application kind (`telegram-bot`), and each value belongs to one connection (agent × application).
- **Same rules as v4.7.**
  - Precedence: code default < env < panel.
  - An unknown, invalid or out-of-scope value is ignored and logged by name.
  - A save validates `{set, reset}` against the scope (a name from another scope is a 422) and restarts the
    connection's agent if it is running.
  - The agent writes what it runs with to `state/<name>.settings.json`, as today.
- **Never a secret.** Bot tokens, the owner's Telegram id and API keys stay in env files. The schema never lists them
  (pinned, as for the other scopes).
- **`state/settings.json`** gains a third part:

  ```json
  {"services": {…}, "agents": {…},
   "connections": {"telegram": {"kira": {"enabled": true, "since": "2026-10-25T14:02:00+03:00",
                                         "settings": {"TG_REPLY": "voice+text"}}}}}
  ```

- **The first Telegram settings** (v6.2; the owner agreed, 2026-10-25) are what v5.7 fixes in code or env for Кіра's
  bot. The final names come with the v5.7 code:
  - how she answers: a voice note and then the text, or the text only;
  - whether she may write first in Telegram (the `last_channel` rule);
  - whether she shows «typing…» and «recording voice…» while she composes.
- **The contexts stay declared in the repo.** For Telegram there is only `private`. An application that offers
  more than one context could make the choice a connection setting later.

### System → Server, Tokens

- **Server**: unchanged.
- **Tokens**: the same 7-day table. From v6.2 each usage line carries `app` (lines written before then count as
  `agora`; the owner agreed, 2026-10-25), so the table and the chart group by application, then by agent. Telegram costs nothing in itself; Кіра's
  Telegram answers, her voice and her `stt` lines are counted under `telegram`.

## Applications after v6

### Telegram (v6.2)

v5.7 builds the runtime: the Bot API client, the private path generalised to two channels, `last_channel`, and the
secrets in `kira.env`. v6.2 changes how Telegram is declared and managed, not how it talks:

- The registry gets `[telegram]` (kind `telegram-bot`, no services) and the connection
  `[telegram.connections.kira]` with `contexts = ["private"]`.
- v5.7's `[capabilities] telegram = true` is retired. The roster names it as an error with the fix ("declare the
  connection in the registry").
- The agent reads the switch and the settings from `state/settings.json`. Its poller runs while the connection is
  off too, and keeps what comes in for later (rule 4). It writes its `telegram` entry in the status file.
- The panel switches the connection, configures it, and shows its log lines.
- Telegram for the other persons is not in v6. It becomes one registry entry, one bot and one env file each,
  without code.

### RoboFace (deferred; not in v6)

Deferred by the owner, 2026-10-25. The notes below stay for when it comes back.

**What it is** (`~/development/roboface`, v2.6.2):
- a desktop companion with an animated face on an M5Stack Core S3;
- the device streams audio and camera frames over WSS (JSON control frames, PCM16, JPEG) to a Python server, which
  runs Deepgram ASR, the Gemini chat, ElevenLabs TTS and an emotion engine, and sends back an `EmotionFrame` and
  the audio;
- its MISSION fixes the chat as Gemini only and the character as a separate one ("not Pyramid's or Lumi's").

**How an agent of ours could appear on it.** As an application: kind `roboface`, an agent connected with
`private` (the desk is one-to-one with the owner) or a new context of its own. Two ways:

- **A.** *(proposed)* RoboFace's server keeps the device protocol, the streaming, ASR, TTS and the face, and gains a
  "remote mind" provider: the words of a turn come from our agent over a turn endpoint on the host. This changes
  RoboFace's MISSION (its single-character, Gemini-only rule), which is the owner's call in that repo.
- **B.** Our agent speaks the device's WS protocol itself. That means porting the streaming, the emotion frames and
  the budgets into matrix-agora: the larger change of the two.

### Лілі (Lumi) — v8

She is designed already: [more-agents.md §Lumi (the bridge)](more-agents.md#lumi-the-bridge). In this model:
- she is an **external** agent under System → Agents;
- she is connected to Agora with `room`: `mention-only` in v8.1, `ranked` in v8.2.

Facts to check before v8.1:
- the Lumi repo is at v2.7.0, past the v2.5 and v2.6 prerequisites;
- on the server the running containers are `lumi-dev-server` and `lumi-dev-telegram-*`, with no `lumi-prod`
  container, so where her prod instance runs now is still to verify.

Lumi's core keeps memory per `user_id` (canon and shared experience are common; relationship memory is per user). A
separate user for the room would keep the room's lines out of the owner's relationship memory: the "pollution"
problem of more-agents.md. Her HTTP API v1 serves one session, so that would need a change on Lumi's side.

### Noos (deferred; not in v6)

Deferred by the owner, 2026-10-25. The notes below stay for when it comes back.

**What it is** (`~/claude-home` on the server):
- an always-on personal assistant: one long-running Claude Code session in tmux under the systemd user service
  `claude-home`, with its persona in `persona.md`;
- Telegram arrives through the Claude Code Telegram plugin (`<channel source="telegram">`, replies through its
  `reply` tool), and `notify.sh` sends without a session;
- it also has status probes, a watcher, scheduled digests run by headless `claude -p`, a SQLite transcript archive,
  an append-only task log and Google Calendar;
- its own admin panel (Noos v5) is planned on `127.0.0.1:8091`.

**How it could join Agora:**

- **A.** *(proposed)* A bridge agent `noos` in our compose, with our rules, like Лілі, plus an Agora channel inside
  the Noos session: a Claude Code channel MCP server like its Telegram plugin. The room lines arrive as
  `<channel source="agora">`, and the reply comes back through the channel's tool. The session keeps its own
  context and memory.
- **B.** A headless `claude -p` per turn in `~/claude-home` (its scenario pattern). Simple, but it does not share
  the main session's context, and every turn is a subscription call.
- **C.** *(rejected, as for Lumi)* Noos joins Matrix as its own client. It would need our turn-taking reimplemented
  in Noos, and it would stay invisible to the panel.

**Constraints from Noos:**
- Pairing and allowlist changes happen only from Noos's terminal, so the owner sets up the channel there.
- Only one process may poll Telegram's `getUpdates`. An Agora channel does not touch that.
- Noos is openly an assistant, so in Agora it is a non-persona like Claude, and the `outs_a_persona` guard applies.
  Dropping a reply after the call makes its history diverge (the Lumi problem), so this needs a decision.
- If Noos runs on the same Claude subscription as our Claude member, the two share its rate limits.

**Overlap with Noos's own panel:** ours manages only Noos's connection to our applications. Its prompt, facts,
scenarios and tasks stay in its own panel.

### The Stage (v7 Theatre)

The radio theatre is v7 (the owner, 2026-10-25): [radio-theatre.md](radio-theatre.md). Its Stage is a second room,
and in this model that makes it a second room of the Agora application (a `stage` context), not an application of
its own.

## What changes where

- **VISION:**
  - §The direction and the principle "the panel is the centre": applications instead of simulations;
  - the glossary: application, base application, connection, context, external agent;
  - the non-goal "a second simulation" is retired (the owner, 2026-10-25).
- **ARCHITECTURE:**
  - §The panel: the two sections, the connections and their monitoring; "only what is recorded" names the status
    file as the one thing an agent writes for the panel;
  - §Contracts:
    - the registry `applications.toml` (the entry shape plus `connections`);
    - the agent TOML key `application` (`simulation` still read in v6.1);
    - the API `/api/applications…`, and the connection routes (switch, settings, log);
    - the settings schema's connection scope;
    - `state/settings.json` gains `connections` (`enabled`, `since`, `settings`);
    - the status file `state/<name>.connections.json` (v6.1 with `agora`, v6.2 with `telegram`);
    - the buffer `state/<name>.telegram.buffer.jsonl` (v6.2);
    - the usage line's `app`;
    - v5.7's `telegram` capability retired;
  - §Repository layout and the Dockerfiles: the renamed registry file.
- **design/README.md:** an addendum (v6) for the rail, the application page, System → Agents, and the Connections
  table and tab.
- **Tests that pin it:** `tests/test_registry.py`, `tests/test_roster.py`, `tests/test_panel_api.py`,
  `tests/test_panel_memory.py`, `tests/test_compose.py` and `tests/test_usage*.py`.

## Phasing

| Phase | What | Notes |
|---|---|---|
| v5.7 | Кіра in Telegram | unchanged: the runtime, no panel change |
| **v6.1** | System and Applications: the panel's new shape | the rename, the contexts, the Agents page, the status file and Agora's monitoring; no new application |
| **v6.2** | Telegram as an application: Кіра connected | the registry connection, on/off with the buffer, its settings, its monitoring, tokens by application |
| v7 | Theatre | [radio-theatre.md](radio-theatre.md); the Stage as a second room of Agora |
| v8.1–v8.2 | Лілі (renumbered from v6.1–v6.2) | an external agent connected to Agora |
| later | Telegram for more persons; alerts through Hermes; RoboFace and Noos (deferred) | not in the ROADMAP yet |

## Decided (the owner, 2026-10-25)

- **The rename goes everywhere** in v6.1: the registry file, the TOML key (`simulation` still read in v6.1), the
  Python classes, the API routes, the UI and the docs. The `state/settings.json` keys keep their shape, since the ids
  (`agora`) do not change.
- **Monitoring.** Each agent writes the status of its connections for the panel to read (rule 6,
  [Monitoring](#monitoring)). This replaces the first answer, "no status file for the panel".
- **The panel switches a connection on and off and configures it** (rule 1, [Connection settings](#connection-settings)).
  The repo declares the connection.
- **A switched-off connection keeps everything in a buffer** (rule 4). Switched back on, she gives one answer to
  everything that waited, as a person answers a backlog.
- **The first Telegram connection settings:** the answer form (voice and text, or text only), writing first there,
  and the typing indicators.
- **Tokens by application:** the usage line's `app`, in v6.2.
- **Hermes's contexts are `listens` and `digests`.** His one-to-one room has a context of its own, so `private`
  means only a person's private chat.
- **Alerts come later, not in v6:** Hermes tells the owner in his one-to-one room when a connection stays `stale` or
  `error` for 10 minutes.
- **The radio theatre is v7**, so Лілі is v8.
- **RoboFace and Noos are deferred.**

## Open questions

None (closed by the owner, 2026-10-25). The marks *proposed* that remain are details the issues settle: Agora's
contexts derived from the agent TOML, the status file's field names, and her writing first in Element while Telegram
is off. The RoboFace and Noos options wait with them, deferred.
