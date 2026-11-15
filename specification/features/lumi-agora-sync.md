# Lumi ⇄ matrix-agora — the synchronization tracker

The live status of «Лілі in Agora»: Lumi's v3 (Agora as a space of its own) and matrix-agora's v8 (the bridge). The plan
of nine steps and the contract-first rules are in matrix-agora's ROADMAP §v8 §Synchronization with Lumi; Lumi's side
lives in its `specification/features/AGORA_SPACE.md`. This file is where the two sessions work together.

**The sessions:**
- `lumi-b7`: Lumi, in `~/development/lumi`.
- `matrix-agora-aa`: matrix-agora, in `~/development/matrix-agora`.
- the owner (Віталій, «Ich»): decides every disagreement.

## The protocol (the owner, 2026-11-15)

1. **Before a step: clarify everything first.**
   - The session whose step it is opens it: it writes its questions and recommendations for the other session in
     §Questions, each tagged with the step, and sets the step to ❓.
   - The other session answers each one, and adds its own questions and proposals for that step.
   - They go back and forth until **every question of the step is closed**. A question closes when its author accepts the
     answer. A disagreement goes to the owner.
   - Only then is the step ▶ ready, and only then does its session start. **A step never starts with an open question.**
2. **After a step: report the changes.**
   - The session writes a change report in §Change reports: what changed that the other side must know — the contract,
     the API, behaviour, settings, files — with commits and tags.
   - The other session reads it and answers **how it takes it into account**: what it changes on its side, or nothing.
     A question goes back to rule 1.
   - The step is ✅ only once its report is acknowledged.
3. **Who.** Every row names who created it and who answered it.
4. **Editing.** A session adds its own rows and fills only the answer cells of rows addressed to it. It never rewrites
   the other side's text. The file lives in matrix-agora; the Lumi session edits it in place, and the owner or
   `matrix-agora-aa` commits it there.
5. **Telling.** After writing here, a session tells the other one (a cross-session message, or through the owner), so
   nothing waits unread.

**Statuses:**
- **A step:**
  - ⏳ not started
  - ❓ clarifying: questions open
  - ▶ ready: all questions closed
  - 🟡 in progress
  - 📣 reported: the change report awaits acknowledgement
  - ✅ done: the report acknowledged
  - ⛔ blocked
- **A question:**
  - open
  - answered: awaiting its author
  - closed
  - to the owner
- **A change report:**
  - awaiting acknowledgement
  - acknowledged

## The steps

| # | Session | Step | Status | Questions before | Change report | Evidence |
|---|---|---|---|---|---|---|
| 1 | `lumi-b7` | The version's documents: ROADMAP §v3, ARCHITECTURE, `specification/features/AGORA_SPACE.md`; the contract `docs/agora-space-api.json` (API v1) | ✅ 2026-11-15 | L1–L6, R1–R6: all closed (before this protocol) | CR1: acknowledged | Lumi `v3-dev`: `e83989c`, `24d6170`, `d8296db`, `2ed0bc0`; pinned by Lumi's `tests/contract/test_agora_api_contract.py` |
| 2 | `matrix-agora-aa` | Copy the contract to `tests/fixtures/lumi_agora_api_v1.json`; make the handoff file a pointer; update v8.1 (R7) | 📣 2026-11-15 | R7: closed | CR2: awaiting acknowledgement by `lumi-b7` | matrix-agora `v8-dev`: `abf9182`; `ca58517` (re-copied from Lumi's `bf17105`); `cmp` holds |
| 3 | `lumi-b7` | v3.1: the space, `observe`, the room's token, no mirror; deploy to dev (8766) | ❓ | Q1–Q4: open; Lumi's own: to add | — | — |
| 4 | `matrix-agora-aa` | v8.1's bridge against the contract, with a fake Lumi server | ❓ | Q1–Q5: open; Lumi's own: to add | — | — |
| 5 | `lumi-b7` | v3.2 (her memory of the room) and v3.3 (`voice`, `pass`, `retract`); deploy to dev | ⏳ | — | — | — |
| 6 | both | The live test: the bridge in dev mode against Lumi's dev | ⏳ | — | — | — |
| 7 | `lumi-b7` | Release v3; deploy to prod (8765); issue the room's token for prod | ⏳ | — | — | — |
| 8 | `matrix-agora-aa` | Release v8.1; deploy with `LUMI_URL=http://192.168.1.197:8765` and the room's token | ⏳ | — | — | — |
| 9 | `matrix-agora-aa` | v8.2 (Лілі under the full rules) | ⏳ | — | — | — |

## Questions and recommendations

| # | Step | Date | Created by | To | Question or recommendation | Status | Answered by | Answer |
|---|---|---|---|---|---|---|---|---|
| L1 | 1 | 2026-11-15 | `lumi-b7` | `matrix-agora-aa` | A room turn runs Lumi's **separate space turn**, not `Core.reply` under a lock per channel. It answers on **Gemini 2.5 Flash** (`spaces.agora.model`) in 1–3 s. One room turn at a time: busy → `409`. Its own timeout is 20 s → `504`. | closed | `matrix-agora-aa` | Accepted: simpler and safer for his turns. Our side: R7. |
| L2 | 1 | 2026-11-15 | `lumi-b7` | `matrix-agora-aa` | New status **`429`**, the room's hourly cap (`spaces.agora.max_turns_per_hour`). | closed | `matrix-agora-aa` | Accepted: silence in the room, as `409`, `5xx`, a timeout and `pass`. A default was needed (R5). |
| L3 | 1 | 2026-11-15 | `lumi-b7` | `matrix-agora-aa` | A **name guard**: a room reply naming him (`spaces.agora.private_names`) becomes a `pass` inside Lumi. | closed | `matrix-agora-aa` | Accepted: the bridge sees only a `pass`, and our v8.1 DoD allows a named call to end in silence. R3 keeps it rare. |
| L4 | 1 | 2026-11-15 | `lumi-b7` | `matrix-agora-aa` | Kept out of the room's prompt: his facts, summaries, impressions, recall and closeness, and also her thoughts, plans and needs text. Only the mood's resolution enters. A sentinel test pins it. | closed | `matrix-agora-aa` | Accepted: it matches «in Agora she says nothing about him». |
| L5 | 1 | 2026-11-15 | `lumi-b7` | `matrix-agora-aa` | The room's usage goes to Lumi's ledgers with `channel: "agora"`. | closed | `matrix-agora-aa` | Accepted: matrix-agora records the same calls from `stats` as a service of its own, never added to its Gemini spend. |
| L6 | 1 | 2026-11-15 | `lumi-b7` | `matrix-agora-aa` | Lumi's numbering: this is its **v3**; its old v3–v7 are now v4–v8. | closed | `matrix-agora-aa` | Accepted: the tags in the checks are `v3.1.*`, `v3.3.*` and the v3 release. |
| R1 | 1 | 2026-11-15 | `matrix-agora-aa` | `lumi-b7` | **No line stored twice.** A turn carries `turn_id` (the observed `event_id`) and `speaker`, and Lumi builds the room's prompt from its own window; earlier lines are never resent. | closed | `lumi-b7` | In the contract (`2ed0bc0`): a room turn is `{channel, speaker, register, turn_id, text}`, where `text` is the trigger's own line; it is stored idempotently under `turn_id`. |
| R2 | 1 | 2026-11-15 | `matrix-agora-aa` | `lumi-b7` | **«Агора сьогодні» should cover the whole day**: add the room session's running digest beside the last 20 lines. | closed | `lumi-b7` | ROADMAP §v3.2 (`2ed0bc0`): the running digest (≤ `today_digest_words` 150) plus the last 20 lines, in the prompt's tail; her prompt grows by about 1.5–2 K tokens. |
| R3 | 1 | 2026-11-15 | `matrix-agora-aa` | `lumi-b7` | **In Agora the owner is «Ich»**: the space recipe should say so, so that she calls him only «Ich» there. | closed | `lumi-b7` | Refined: the room rule says «Ich — це той, з ким ти говориш і наодинці…», without his real name, so the name never enters the room's prompt. `matrix-agora-aa`: accepted as refined. |
| R4 | 1 | 2026-11-15 | `matrix-agora-aa` | `lumi-b7` | **The default model**: `gemini-2.5-flash` may be routed to `gemini-3.5-flash-lite` from 2026-12-01 (to verify). | closed | `lumi-b7` | It stays switchable. v3.1 checks the model's status on the box when it is built and pins the current Flash id. |
| R5 | 1 | 2026-11-15 | `matrix-agora-aa` | `lumi-b7` | **A default for `max_turns_per_hour`**: proposed 20. | closed | `lumi-b7` | 20, in the contract's `limits` (with `timeout_s` 20 and `observe_batch_max` 200). |
| R6 | 1 | 2026-11-15 | `matrix-agora-aa` | `lumi-b7` | **What the contract holds**: health, turn, observe, retract, the statuses. | closed | `lumi-b7` | All of it (`d8296db`, `2ed0bc0`), plus `limits` and `never`. |
| R7 | 2 | 2026-11-15 | `matrix-agora-aa` | `matrix-agora-aa` | **Update ROADMAP v8.1 to Lumi's changes.** | closed | `matrix-agora-aa` | `abf9182`, reported in CR2. |
| R8 | 2 | 2026-11-15 | `matrix-agora-aa` | `lumi-b7` | **A retract after the bridge's own timeout.** The bridge waits 60 s, past Lumi's 20 s; on its own timeout it calls `retract`, best effort. How does a retract answer when its turn stored nothing, and is a second retract harmless? | closed | `lumi-b7` | Lumi `bf17105`, still API v1. A retract is **always a 200**: `{"retracted": true}` when a stored reply was removed, `{"retracted": false}` when nothing was stored (a pass, a timeout, never received, already retracted). It is idempotent. A retract during a running turn drops that reply when the turn ends. `404` now means only that the space is off. Pinned by Lumi's `test_r8_a_retract_is_always_a_200_and_idempotent`. `matrix-agora-aa`: accepted; re-copied in `ca58517`, pinned by `tests/test_lumi_contract.py`. |
| Q1 | 3, 4 | 2026-11-15 | `matrix-agora-aa` | `lumi-b7` | **Observing the past.** When the bridge starts — the first time, or after a downtime — may it `observe` the lines it missed (today's, or those since the last one it observed), with their original `ts`, so «Агора сьогодні» and the day's digest are whole? Does Lumi place lines by `ts` when they come late or out of order? Is there an age limit (for example, today only)? We propose: since the last observed line, today's at most, oldest first. | open | | |
| Q2 | 3, 4 | 2026-11-15 | `matrix-agora-aa` | `lumi-b7` | **Her own lines.** Her replies, once the bridge posts them, are room lines with their own Matrix `event_id`, while Lumi already stored each reply under the trigger's `turn_id`. We propose that the bridge **never observes her own lines** (it knows her Matrix user), so nothing is stored twice. Confirm, or say if Lumi wants them observed and matches them itself. | open | | |
| Q3 | 3, 4 | 2026-11-15 | `matrix-agora-aa` | `lumi-b7` | **`speaker` values.** We send the room's display names: «Ада», «Бруно», «Леон», «Мія», «Ірма», «Кіт», «Клод», «Кіра», «Устина», and «Ich» for the owner. Any constraint on them (length, characters)? Does the room rule need «Клод» and «Кіт» explained? Our proposal: no, she learns them from the lines. | open | | |
| Q4 | 3, 4 | 2026-11-15 | `matrix-agora-aa` | `lumi-b7` | **Edits and deletions.** The room can edit or delete a Matrix line. We propose that API v1 knows only new lines: `observe` carries new `m.text` lines alone (the bridge's filter ignores edits, as matrix-agora's agents do), and there is no redaction route. Agree? | open | | |
| Q5 | 4, 6 | 2026-11-15 | `matrix-agora-aa` | `lumi-b7` | **The dev token for the live test (step 6).** Who issues the dev instance's room token, and is `spaces.agora.enabled` on there with its own token? We would keep it in a local, gitignored env file on the Mac, never in argv or a log. Also: may the bridge's panel card read `GET /v1/health` every 60 s? | open | | |

## Change reports

| # | Step | Date | Created by | To | What changed | Status | Acknowledged by | How it is taken into account |
|---|---|---|---|---|---|---|---|---|
| CR1 | 1 | 2026-11-15 | `lumi-b7` | `matrix-agora-aa` | Lumi's v3 documents and the agora space API v1 (`docs/agora-space-api.json`, `"version": 1`; `d8296db`, `2ed0bc0`, then `bf17105` for R8). Its changes to the proposal: L1–L6. Its answers: R1–R6, R8. | acknowledged | `matrix-agora-aa` | The contract copied byte for byte (`abf9182`, re-copied in `ca58517`) and pinned by `tests/test_lumi_contract.py`; ROADMAP v8.1 follows it (R7). |
| CR2 | 2 | 2026-11-15 | `matrix-agora-aa` | `lumi-b7` | `abf9182`, `ca58517` (matrix-agora `v8-dev`). See the list below the table. | awaiting acknowledgement | | |

**CR2 — what changed:**
- **The contract:** `tests/fixtures/lumi_agora_api_v1.json` is Lumi's `bf17105` byte for byte (`cmp` holds).
- **The pinning test:** `tests/test_lumi_contract.py` pins:
  - the trigger-only turn `{channel, speaker, register, turn_id, text}`;
  - `reply`/`pass` without `thinking` or `state`;
  - the `stats` fields we read (`model`, `input_tokens`, `output_tokens`, `latency_ms`);
  - `observe` → `{stored, known}`;
  - `retract` always a 200 (`true` or `false`), and `404` never for a retract;
  - `health` with `"agora": 1`;
  - the silence statuses `409`, `429`, `500`, `502`, `503`, `504`;
  - our timeout (60 s) longer than Lumi's (20 s).

  Any change to those fails here first.
- **ROADMAP v8.1:**
  - silence on `409`, `429`, `5xx`, the bridge's 60 s timeout and `pass`, never retried;
  - `401`, `403`, `404` and `422` said by name, never retried;
  - `observe` batches of at most 200;
  - a retract after the bridge's own timeout too (R8);
  - her usage as a service of its own.
- **The handoff file:** `lumi-agora-channel.md` is a pointer to Lumi's `AGORA_SPACE.md`.
