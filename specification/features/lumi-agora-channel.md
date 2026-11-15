# Lumi — proposed version: Agora, the room as a channel

*For Lumi's ROADMAP. Prepared on 2026-11-15 in matrix-agora (its v8, «Лілі in Agora»), after a review of Lumi 2.12.3.
It is written in Lumi's ROADMAP format, a version with phases `vA.B`, each with a Goal, Tasks, DoD and Tests. It is
proposed as the **next version, before Personality**: number it where you place it, and renumber the later versions.
The file references are as of 2.12.3; check them before building.*

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
- **The record:** a stored message carries `channel` and `speaker` (a repository migration; old rows are `owner` / his
  name).
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
