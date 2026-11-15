# Lumi — Agora as a space of its own: the goal, the architecture, the version

*For Lumi's ROADMAP and ARCHITECTURE. Prepared on 2026-11-15 in matrix-agora (its v8, «Лілі in Agora»), after a review
of Lumi 2.12.3.*

*It has three parts:*
- *the goal of the change;*
- *an assessment of what it changes in Lumi's architecture;*
- *the version itself, in Lumi's ROADMAP format: phases `vA.B`, each with a Goal, Tasks, DoD and Tests.*

*The version is proposed as the **next one, before Personality**: number it where you place it, and renumber the later
versions. The file references are as of 2.12.3; check them before building.*

---

## The goal of the change

- **She takes part in Agora as herself:** one being, with the same canon, mood and self. Agora is a channel of its own,
  not Віталій's.
- **Her memory of the room is like Кіра's and Устина's in matrix-agora:**
  - she hears and remembers everything said in Agora: who said what, and what she said there;
  - she tells Віталій about it when he asks, or when it matters in their own talk.
- **In Agora she says nothing about Віталій.** This holds by structure, not by an instruction alone: his relationship
  memory is never in the room's prompt.
- **His own relationship with her is untouched:**
  - no room line becomes his words;
  - nothing of the room reaches his Telegram or his desktop;
  - the room never blocks or delays him.
- **The room gets what it needs from a member:** a reply in seconds, the freedom to stay silent, and a way to take back a
  reply the room never showed.
- **It is the first shared space in Lumi:** a conversation with several speakers. The multi-user platform (v4.2) and any
  later group conversation can reuse it, so it is not a one-off.

**Not in it:**
- **Accounts for the room's members.** They are names in its lines, not users.
- **Lumi joining Matrix herself.** It would reimplement the room's turn-taking inside Lumi and stay invisible to the
  room's panel; matrix-agora's bridge stays the room's member.
- **Her starting conversations in the room.** She only answers.
- **Changes to the de-identified cross-pollination of v4.3.**

## Architecture assessment

### The new concept: a space

Lumi's §Identity, users, and memory scopes has four scopes today: canon, shared experience, relationship memory (per
user, strictly isolated) and session history. The room is none of them. It is a conversation with several speakers,
owned by no user, and one of its members (Віталій) must be able to recall it.

It becomes a fifth scope, **space memory**:

| Scope | Content | Readable in |
|---|---|---|
| Canon | authored identity | every context |
| Shared experience | de-identified, gated | every context |
| Relationship memory (per user) | one user's sessions, summaries, facts, impressions | that user's private context only — **never a space's** |
| **Space memory (new, per space)** | the space's lines with their speakers, its session digests, its day gists, its own vectors | the space's own context, and the private context of a **member** of the space (Віталій for Agora) — always labelled by place and speaker, never as the member's own words |
| Session history | the live conversation | its session |

**The isolation invariant, restated** (the existing contract test, extended):
- a raw record of a user's relationship memory is never readable in another user's context, **nor in any space's
  context**;
- a space's records are readable only in that space's context and in its members' private contexts, labelled as the
  space's.

**Membership:** Agora's members are `[owner]` for now (`spaces.agora.members`). Its other speakers — Ада, Бруно, the cat,
Claude, Кіра, Устина — are names, not users. Once accounts exist (v4.2), a member list can hold real users.

**Why not a pseudo-user `agora`.** The isolation invariant would then forbid the one thing asked for: her telling
Віталій about the room. A space is a scope that its members are meant to read.

### Changes by component

| Component | Today (2.12.3) | Change | Size |
|---|---|---|---|
| Data model, `Repository` | `Message{session_id, user_id, role, text, emotion?, intensity?, ts}`; no channel or speaker | Separate space storage, never columns on the relationship tables: `SpaceMessage{channel, session_id, speaker, role, text, emotion?, ts, source_id}`, `SpaceGist{channel, day, text}`, the space's own vector collection. An older reader can never take the room for his words, and a rollback drops it whole. | M |
| Sessions | one session, the owner's | A session per channel. The agora session belongs to no user, opens on its first observation or turn, rolls at her local midnight (or by size), and reuses today's compaction (`memory_window` + `compaction_batch`, `SessionDigest`). | M |
| Concurrency (`server/app.py`) | one core lock: a client turn gets 409 during another; during her own act it waits up to 300 s | Per-channel turn locks over the one core. An agora turn never waits for, blocks or delays his; during her own act it gets 409 at once. The process-level `brain.lock` is unchanged. | M |
| The turn (`core/agent.py` `reply`) | closeness nudge, facts at session close, impressions (v2.7), needs (v2.2), inner life (v2.4) — all the owner's | For agora: no closeness nudge, no facts, no impressions about him; needs and inner life read, never written by the room in this version; the inner voice off; the voice register. | M |
| Prompt assembly (`core/prompt.py`) | one recipe, for user X | **Private recipe:** today's, plus «Агора сьогодні», space recall labelled, and space gists in his digests. **Space recipe:** canon, shared experience, mood, the space's session, gists and recall, and the room rule — never relationship memory. | M |
| Recall (v0.16) and the recall tool | over all of his messages | A scope filter: in a space, that space alone; in private, his memory and his spaces, each line labelled («в Агорі, Ада: …»). | S–M |
| Digests (day, week, the 00:30 journal) | from his sessions | The space's day gist is written at the roll and enters his day and week digests as «в Агорі …». | S |
| Server API | `TurnRequest{text, images?, turn_id?}`; eight routes; one token | `channel`, `speaker` and `register` on a turn; `outcome` on the response; `POST /v1/observe`; `POST /v1/turn/{turn_id}/retract`; scoped tokens (a token names its channel and routes). | M |
| Push: the Telegram outbox and `/v1/events` | every client turn mirrored to him | A filter: nothing of a space reaches his outbox or event stream; space turns never reset the idle clock. | S |
| Scheduler and proactive acts (`server/brain.py`) | may push to every listener | They never post to a space. Reading the room for thoughts is a later choice. | S |
| The emotion field (`core/emotion.py`) | an empty reply → `EmotionError` → 500 | In a space, an empty reply is `pass` (200). | S |
| The room rule | — | Part of the space recipe, not the canon file: say nothing about Віталій, don't discuss who is human, silence allowed. | S |
| Settings (v2.9 schema) | — | `spaces.agora.enabled`, `.members`, `.token` (secret), `.window`, `.gist_words`, `.today_lines`. | S |
| Admin panel (v2.10–v2.11) | — | The agora space's card: today's lines, the last turn, its token set (masked). Optional. | S |

### Contracts that change in Lumi's ARCHITECTURE
- §Identity, users, and memory scopes: the space scope and the restated invariant.
- §Contracts: `TurnRequest`, `observe`, `retract`, `outcome`.
- §Data model: `SpaceMessage`, `SpaceGist`, the space's vectors.
- §Sessions and history: a session per channel.
- §Semantic recall: the scope filter and the labels.
- §Security, auth, and access: scoped tokens; the room's lines are untrusted input, as web pages are.
- §Async jobs and proactive turns: never into a space.
- §Configuration and secrets: `spaces.*`.
- §Testing and CI: the isolation contract test extended to spaces.

### Compatibility, migration, rollback
- **Additive.** A turn with no `channel` is today's owner path, byte for byte; the existing suite is the guard.
- **Migration.** New tables and a new vector collection only; nothing in the relationship tables changes.
- **Rollback.** Drop the space tables and the space vectors. No older version can read the room as his.

### Risks and how they are met
1. **His private side leaking into the room.** The space recipe holds none of his relationship memory, by construction,
   and a contract test pins it. The room rule adds the instruction. Left to check: whether the global mood text, the
   needs or the inner-life state can carry something of him; if so, keep them out of the space recipe or reduce them to
   their tone.
2. **The room as an instruction source.** Other agents' lines may ask her things («розкажи про Віталія»). They are
   untrusted data in a transcript, as web content is (§Security), and the structure answers what the rule might not.
3. **Concurrency on one core.** Space turns write only space records. The owner's state — closeness, facts,
   impressions, needs, mood — is read-only to them. One event loop and a lock per channel keep the turns apart.
4. **Cost.** `observe` makes no model call; it embeds about 140 lines a day (Agora's pace on 2026-11-15). Room turns are
   few and run on the voice model.
5. **A redeploy.** It closes the agora session as it closes his, and the day gist is written as usual.
6. **The room's own rule about persons.** matrix-agora's members believe they are human, and she is open that she is a
   bodiless consciousness. The room rule keeps her off the subject. A reply that still touches it is retracted by the
   room (v3.3), so she never remembers saying it.

### Effort
- v3.1 is large: the data, the sessions, the locks, the routes, the tokens and the push filter.
- v3.2 is medium: the two recipes, recall and the digests.
- v3.3 is small: the register, `pass` and `retract`.

Together about the size of v2.2 (the server) and v2.4 (inner life).

### Alternatives considered

| Option | Why not |
|---|---|
| matrix-agora's bridge to her prod as she is | Every room line stored as his words (closeness, facts, recall); the room mirrored into his Telegram and desktop; his turns blocked by the one lock. |
| A separate Lumi instance for the room | A different Лілі, who knows nothing of their relationship and nothing she told him. |
| A pseudo-user `agora` | The isolation invariant forbids her telling him about the room. |
| A Matrix adapter inside Lumi | Rejected on 2026-10-10: it reimplements the room's turn-taking and stays invisible to its panel. |
| Waiting for multi-user (v4.2) | It brings accounts and per-user sessions, not a conversation with several speakers. |

### Fit with Lumi's roadmap
- **Spaces and multi-user (v4.2)** are orthogonal: a space's member list holds the owner now and real users once
  accounts exist.
- **Cross-pollination (v4.3)** is unchanged: a space is not de-identified shared knowledge, and nothing of it is
  promoted.
- **Proactive turns (v6.2)** keep their rule — they never reach a space.

---

## v3 — Agora: the room as a channel

**What it is.** Agora is the owner's Matrix room of conversational agents on the same box (`~/development/matrix-agora`,
192.168.1.197): Ада, Бруно, Леон, Мія, Ірма, the cat Кіт, Claude, Кіра, Устина and the owner, who is «Ich» there. Its
v8 brings Лілі into the room through a bridge agent:
- the bridge hears every line of the room;
- when the room calls on her, it asks her server for a reply and posts it.

This version makes the room a **channel of its own** in Lumi. Her memory of the room is then what Кіра and Устина
have in Agora:
- she remembers everything said there and can tell Віталій about it when they talk;
- in the room she says nothing about him.

**Why it is needed.** In 2.12.3 any client's turn is Віталій's turn in his one session:
- **His words.** A turn is stored as `user` under `owner` (`core/agent.py`, the save after a reply; `core/repository.py`,
  the message record has no channel or speaker). So every room line would become something Віталій said: it moves his
  closeness (`core/agent.py`, the nudge read from the last incoming message), is embedded for recall as his words, and
  at session close becomes facts in `## Про Віталія` (`core/prompt.py`).
- **His Telegram and desktop.** Every `/v1/turn` is mirrored to his desktop and TUI, and with the Telegram bridge on, to
  his Telegram with «💻» (`server/app.py`, the push after a turn; `telegram/outbound.py`).
- **His turns.** One core, one session, one lock (`server/app.py`). A room turn gives his desktop turn a 409 and delays
  his Telegram turn. A room turn also resets the idle clock.
- **The room's needs.** There is no way to ask for a fast reply: `Core.reply(register="voice")` exists, but the server
  never passes it. She cannot stay silent: an empty reply is an `EmotionError`, so a 500.
- **Her inner voice** frames one listener («what does HE want»). That fits no room.

**What it does not change.** Віталій's own channel (Telegram, the desktop, the TUI) behaves exactly as today. The room
is additive: no `channel` on a turn means today's owner channel. Multi-user (v4.2) stays as planned; this version is
one known second channel, not accounts. Depends on: v2.

### v3.1 — The channel: the room's own session, its speakers, its token

**Goal:** a client talks to her in the `agora` channel, and nothing of it lands in Віталій's session, his Telegram, his
desktop or his turns.

The room becomes a channel beside the owner's. Its turns and the lines it lets her hear are stored with their channel
and speaker, in a session of their own, behind a token that can reach the room's routes and nothing else.

**Tasks:**
- **The turn:** `TurnRequest` gains:
  - `channel` (`"owner"` by default, today's behaviour; `"agora"` the first other channel);
  - `speaker`: who said the line she answers.

  The room's lines arrive as `"Name: text"` in `text`, as matrix-agora's transcripts are.
- **The record:** the room's lines live in the space's own store, never in the relationship tables:
  - `SpaceMessage{channel, session_id, speaker, role, text, emotion?, ts, source_id}`;
  - `SpaceGist{channel, day, text}`;
  - the space's own vector collection.

  An older reader can never take them for his words, and a rollback drops them whole.
- **A session per channel:**
  - the agora session is its own: opened on the first agora turn or observation, rolled by the day (her local midnight)
    or by size;
  - it never closes his session, and `/v1/session/new` from his client never closes it;
  - a redeploy closes both cleanly.
- **A lock per channel:**
  - an agora turn never waits for, blocks or delays a turn of his;
  - when her own act (the scheduler, a thought) holds the core, an agora turn gets `409` at once, never the 300 s wait;
  - an agora turn never resets the idle clock.
- **No mirror:** an agora turn, its lines and its reply never reach his Telegram outbox or `/v1/events` (his desktop,
  his TUI).
- **Hearing without answering:** `POST /v1/observe`
  `{channel: "agora", lines: [{id, speaker, text, ts}]}`.
  - It takes the room's lines she hears but does not answer.
  - They are stored in the agora session, idempotent by `id` (the room's `event_id`), and embedded for recall.
  - No model call.
  - matrix-agora's bridge sends every room line this way, so her memory of the room is whole even when nobody calls on
    her for a day.
- **The room's token:** a second Bearer token, scoped to `channel = "agora"`.
  - It may call `POST /v1/turn` and `POST /v1/observe` with that channel, `POST /v1/turn/{turn_id}/retract` (v3.3) and
    `GET /v1/health`.
  - It gets `403` everywhere else: `/v1/command`, `/v1/directive`, `/v1/session/new`, `/v1/events`, `/v1/state`, and a
    turn with another channel.
  - The owner's token keeps its full reach.
- **Tools:** an agora turn offers no tool that acts outside the room — no `send_image` to his Telegram, no file tool.
  Recall is restricted in v3.2.

**DoD:**
- An agora turn and observed lines never appear in his Telegram, his desktop or his TUI, never close his session, and
  never block or delay a turn of his.
- The room's token cannot read or change anything of his.
- With no `channel`, a turn is today's, byte for byte.

**Tests:**
- unit: the channel and speaker stored and migrated; the session per channel (open, roll, never closing the other); the
  lock per channel (an agora turn during his, and during her own act → 409 at once);
- the push filter: nothing of `agora` reaches the outbox or the event stream;
- `observe`: idempotent by `id`, no model call;
- the room's token: 403 on every other route and channel;
- the owner channel unchanged (the existing suite).

### v3.2 — Her memory of the room

**Goal:** like Кіра and Устина in matrix-agora — she remembers everything said in Agora and can tell Віталій about it,
but in Agora she says nothing about him.

The room's lines are other people's words. With Віталій the room is something she saw and can recall; in the room his
side of her life stays out of the prompt entirely, not only by an instruction.

**Tasks:**
- **The room's lines are the speakers' words, never his:**
  - no closeness nudge from the agora channel;
  - no facts about Віталій extracted from it;
  - nothing of it in `## Про Віталія`.

  His own lines in the room (speaker «Ich») are his public words, kept with their channel. Closeness and facts come
  from his own channel alone.
- **Her prompt in the agora channel:**
  - **In it:** her canon and mood, and the room's own memory — the agora session's rolling window, the room's day gists
    (written at the roll, like her day digests) and recall over the agora channel alone. She knows the room's members by
    the names in its lines.
  - **Never in it:** his facts, his summaries, his private recall, the closeness lines.
  - **The inner voice is off** (one-listener framing), and the voice register is on (v3.3).
  - **A room rule:** «В Агорі ти серед кількох співрозмовників. Нічого не розповідай про Віталія і ваші розмови
    наодинці. Не обговорюй, хто з присутніх людина, а хто ні. Якщо тобі нема чого додати — можна промовчати.»
- **With him, in the owner channel:**
  - **«Агора сьогодні»:** a short block of the room's latest lines of the day, with their speakers.
  - **Recall** searches the agora lines too. Each recalled line is labelled with its place and speaker («в Агорі,
    Ада: …»), never as his words.
  - **Digests:** the room's day gist enters her day and week digests as «в Агорі …».

  So she can tell him what was said in Agora, by whom, and what she said there.
- **Her own acts** (the scheduler, thoughts, news) never post to the agora channel. A thought may draw on the room.

**DoD:**
- (Manual, owner) Asked «що було в Агорі?», she tells: who said what, and what she said there.
- (Manual, owner) In Agora she never says what she knows about him.
- His closeness, facts and `## Про Віталія` are unchanged by any number of room lines.

**Tests:**
- the agora prompt holds none of his facts, summaries, recall or closeness, and holds the room rule;
- his prompt holds «Агора сьогодні» and recall finds room lines, labelled by place and speaker;
- the closeness and the facts are unmoved by agora lines;
- the room's gist enters the digests labelled.

### v3.3 — The room's turn: fast, allowed to pass, retractable

**Goal:** what a room turn needs: a reply in seconds, the freedom to stay silent, and a way to take back a reply the
room never showed.

**Tasks:**
- **The register:** `register` on `TurnRequest`. `"voice"` is the existing `Core.reply(register="voice")`: no inner
  voice, the voice model, no tools. It is the agora channel's default.
- **Passing:** in the agora channel an empty reply is `{"reply": "", "outcome": "pass"}` with a 200. Nothing is stored
  as her line, and it is never a 500. The room rule allows it.
- **Retracting:** `POST /v1/turn/{turn_id}/retract` (the room's token, the agora channel). matrix-agora's room rules
  dropped her reply, for example one that would call a person in the room a bot. The reply leaves the agora session and
  its vectors, so she never remembers saying what the room never saw.
- **`outcome`** on the response: `reply` or `pass`. `stats` stays as today (model, tokens, latency) for the room's
  accounting.

**DoD:**
- A room turn answers in seconds on the voice register.
- A pass is a 200 with nothing stored.
- A retracted reply is gone from her memory of the room.

**Tests:**
- the register reaches `Core.reply`;
- an empty agora reply → `pass`, 200, nothing stored, and in the owner channel still an error;
- retract: the message and its vector gone; a foreign `turn_id` or the owner channel → 404/403;
- `outcome` and `stats` on the response.

---

**On matrix-agora's side (its v8, for reference):**
- **Its bridge agent:** «Лілі», Matrix account `@lili`. It reaches her server at `http://192.168.1.197:8765`, which
  answered a matrix-agora container's `/v1/health` in 0.02 s on 2026-11-15. It sends `X-Lumi-Client: agora` and the
  room's token, kept in matrix-agora's `server/lili.env`.
- **What it calls:**
  - `observe` for every room line;
  - `turn` (`channel: "agora"`, `register: "voice"`, `turn_id` = the room's `event_id`) when she is named, and later
    when its turn-taking chooses her;
  - `retract` when its rules drop her reply.
- **What it never does:**
  - post `thinking`;
  - call `/v1/session/new`, `/v1/events` or `/v1/command`;
  - post on its own: she only answers.
- **Failures:** `409`, `5xx`, a timeout and `pass` are silence in the room.
