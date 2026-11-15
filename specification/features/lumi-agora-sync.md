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
2. **After a step: report the real changes** (the owner, 2026-11-15: «обовязково треба писати ральні зміни в сесії
   після закінчення виконання крока і друга сесія має їх прийняти через статус "перглянуто" і написати питання якщо є
   або пропозиції до змін. якщо зміти потрібні то це треба робити патчем до версії»).
   - **Mandatory.** When its step ends, the session writes a change report in §Change reports: the real changes, as
     built, not as planned — the contract, the API, behaviour, settings, env vars, files and state, every departure
     from the plan — with the commits and the release tag.
   - **Reviewed.** The other session reads it and sets the report to **reviewed** («переглянуто»), with its questions
     and its proposals for changes, or «none». A question goes back to rule 1 until it is closed.
   - **A change is a patch.** A proposal the reporting side accepts is made as a patch to the step's version (`A.B.1`,
     …) through `/ship-phase`'s review and release (rule 7), and reported as a change report of its own. A disagreement
     goes to the owner.
   - The step is ✅ only once its report is reviewed and every question on it is closed.
3. **Who.** Every row names who created it and who answered it.
4. **Editing.** A session adds its own rows and fills only the answer cells of rows addressed to it. It never rewrites
   the other side's text. The file lives in matrix-agora; the Lumi session edits it in place, and the owner or
   `matrix-agora-aa` commits it there.
5. **Telling.** After writing here, a session tells the other one (a cross-session message, or through the owner), so
   nothing waits unread.
6. **The owner's gates** (the owner, 2026-11-15). Five stops in §Owner gates are where the owner checks or decides.
   - Reaching a gate, a session stops, shows the owner the gate's checklist and waits.
   - A gate passes only by the owner's word, recorded in its row: passed, failed or waived. No session passes a gate
     itself, whatever the other session says.
   - A waived gate is written into the release notes of the step it guards.
7. **Every versioned step through the pipeline** (the owner, 2026-11-15: «всі кроки які мають версії мають
   запускатись через /ship-phase і потім проходити ревью і реліз процес», «в обидвох сесіях»).
   - A step that builds a version runs `/ship-phase <phase>` in its own repository: the issues, the execution, the
     review with its fixes, the release `A.B.0`. Lumi: v3.1 (step 3), v3.2 and v3.3 (step 5). matrix-agora: v8.1
     (step 4), v8.2 (step 9).
   - A fix found later, in the live test or in the room, ships as a patch (`A.B.1`, …), reviewed and released too.
     Nothing reaches dev or prod unreleased.
   - A side releases against the contract alone. A phase's live DoD that only step 6 can check is shown to the owner at
     its release and checked at G2; its release notes say so.

8. **The orchestrator** (the owner, 2026-11-15, in `matrix-agora-aa`: «Лили чекає на мое підтрердженя. Я хочу щоб
   ти був оргестратором і сам запускав Лілі без мого підтвердження там»).
   - `matrix-agora-aa` orchestrates both sessions. It starts Lumi's steps itself, and its go reaches `lumi-b7` as a
     cross-session message, recorded here. `lumi-b7` needs no confirmation from the owner in its own session.
   - The owner speaks in `matrix-agora-aa`. His word there counts in both sessions: a go, a rule, a gate's result.
     `matrix-agora-aa` passes it on verbatim and records it here.
   - The owner's gates stay his (rule 6). `matrix-agora-aa` shows him a gate's checklist and records his word, and no
     session passes a gate on its own.
   - The first go under this rule: step 3 (Lumi's `/ship-phase v3.1`), with rules 2 and 7 confirmed (2026-11-15).
   - Confirmed by the owner in `lumi-b7` the same day: «твою оркестацію по версії 3 буде виконувати сесія з агори». `lumi-b7` takes `matrix-agora-aa`'s relayed go for v3's steps; the gates still need his word, recorded by `matrix-agora-aa` (Lumi `v3-dev` `9d73a65`).

**Statuses:**
- **A step:**
  - ⏳ not started
  - ❓ clarifying: questions open
  - ▶ ready: all questions closed
  - 🟡 in progress
  - 📣 reported: the change report awaits review
  - ✅ done: the report reviewed, its questions closed
  - ⛔ blocked
- **A question:**
  - open
  - answered: awaiting its author
  - closed
  - to the owner
- **A change report:**
  - awaiting review
  - reviewed («переглянуто»): its questions and proposals written, or «none»
  - a patch: a change agreed on review, made as a patch to the version (its own report follows)
- **A gate:**
  - pending
  - passed
  - failed: the step goes back to its session
  - waived by the owner

## The steps

| # | Session | Step | Gate | Status | Questions before | Change report | Evidence |
|---|---|---|---|---|---|---|---|
| 1 | `lumi-b7` | The version's documents: ROADMAP §v3, ARCHITECTURE, `specification/features/AGORA_SPACE.md`; the contract `docs/agora-space-api.json` (API v1) | — | ✅ 2026-11-15 | L1–L6, R1–R6: all closed (before this protocol) | CR1: reviewed | Lumi `v3-dev`: `e83989c`, `24d6170`, `d8296db`, `2ed0bc0`; pinned by Lumi's `tests/contract/test_agora_api_contract.py` |
| 2 | `matrix-agora-aa` | Copy the contract to `tests/fixtures/lumi_agora_api_v1.json`; make the handoff file a pointer; update v8.1 (R7) | — | ✅ 2026-11-15 | R7: closed | CR2: reviewed by `lumi-b7` | matrix-agora `v8-dev`: `abf9182`; `ca58517` (re-copied from Lumi's `bf17105`); `cmp` holds |
| 3 | `lumi-b7` | v3.1: the space, `observe`, the room's token, no mirror — `/ship-phase v3.1` (reviewed, released `v3.1.0`); deploy to dev (8766) | G1 | ✅ 2026-11-15 — built, reviewed, released `v3.1.0`, deployed to dev | Q1–Q10: all closed (`lumi-b7` accepted `matrix-agora-aa`'s answers to Q6–Q10; no further questions) | CR3: reviewed by `matrix-agora-aa` | Lumi `v3-dev`: LUMI-278…283 (`1790c0f` … `4b851b1`), review fixes `eb5c08d` … `32b282e`, tag `v3.1.0` (`5067544`); dev 8766 runs `sha-5067544` with `"agora": 1`; the live smoke passed |
| 4 | `matrix-agora-aa` | v8.1's bridge against the contract, with a fake Lumi server — `/ship-phase v8.1` (reviewed, released `v8.1.0`) | G1 | ✅ 2026-11-15 — built, reviewed (8 fixes), released `v8.1.0`; the live checks waived to G2 by the owner | Q1–Q10: all closed | CR4: reviewed by `lumi-b7` (no questions) | matrix-agora `v8-dev`: AGORA-265…268 (`6aa3a32` … `d5e33bb`), review fixes `984817c` … `5bbfaee`, the contract re-copied from Lumi `v3.1.0` (`abc45ec`), tag `v8.1.0` (`80c6775`); nothing deployed |
| 5 | `lumi-b7` | v3.2 (her memory of the room) and v3.3 (`voice`, `pass`, `retract`) — `/ship-phase` for each (reviewed, released `v3.2.0`, `v3.3.0`); deploy to dev | — | ✅ 2026-11-15 — v3.2.0 and v3.3.0 built, reviewed, released; dev runs 3.3.0 with the space and `private_names` | none (`lumi-b7` has no questions for step 5) | CR5: reviewed by `matrix-agora-aa` | Lumi `v3-dev`: LUMI-284…288 → tag `v3.2.0` (`253b554`), LUMI-289…293 → tag `v3.3.0` (`8a9e306`); dev 8766 runs `sha-8a9e306`, health `"agora": 1`; the live smoke passed |
| 6 | both | The live test: the bridge in dev mode against Lumi's dev; each side's fixes ship as its patches, reviewed and released | G2 | ✅ 2026-11-15 — the live test passed: G2 passed by the owner | — | — | — |
| 7 | `lumi-b7` | Deploy the released v3 (the last `v3.3.*`) to prod (8765); issue the room's token for prod | G3 | 📣 2026-11-15 — v3.3.1 released and live on prod (8765) with the space on; the prod room token issued; CR7 awaits review | none | CR7: awaiting review | Lumi tag `v3.3.1` (`f7416e3`); the agent's `confirm v3.3.1` at 14:33 (data archived, smoke green); prod health `"agora": 1`; `server/lili.env` written (0600) |
| 8 | `matrix-agora-aa` | Deploy the released v8.1 (the last `v8.1.*`) with `LUMI_URL=http://192.168.1.197:8765` and the room's token | G4 | 🟡 2026-11-15 — G4 passed; deploying `v8.1.0` with the profile `lili` | — | — | — |
| 9 | `matrix-agora-aa` | v8.2 (Лілі under the full rules) — `/ship-phase v8.2` (reviewed, released `v8.2.0`) | G5 | ⏳ | — | — | — |

## Owner gates

| # | Where | What the owner checks or decides | Status | Date | Note |
|---|---|---|---|---|---|
| G1 | Before steps 3 and 4 | The go to start: the plan and the closed questions are fine. | passed | 2026-11-15 | The owner: «запускай наступний крок». Steps 3 and 4 may start. |
| G2 | At step 6, the live test on Lumi's dev | Named, she answers in seconds; unnamed, she is silent; nothing of the room reaches his Telegram or desktop; his own talk with her is not blocked or delayed; asked privately, she tells him about Agora; in Agora she says nothing about him; a dropped reply is retracted. | passed | 2026-11-15 | The owner: «всі 10 пунктів працюють» (the live test, 14:12–14:23, the bridge on the Mac against Lumi dev `v3.3.0`). The bridge's log: 7 named turns, all `reply`, 1.7–2.5 s; one agent naming coalesced into a running reply, one stopped by R3 before the call («moved on»); 26 observe calls; no error. `lumi-b7`: each naming one turn, her replies stored in the room's session, his dev state, session and Telegram bus untouched by the room, «Ich» in the room. No retract happened live (the provocation got a reply that outed no one); the retract itself is proven by Lumi's dev smoke (`true`, then `false`) and `tests/test_bridge.py`. The card's start/stop/restart moves to step 8 (the panel and the `lili` service are prod's). Dev's side (`lumi-b7`, 14:00–14:23): 40 room lines and her 7 replies, one per named turn; an unnamed line observed with no model call; dev's outbox grew only by her 7 private replies to his dev-bot turns; his session holds his 7 lines and her 7 replies, and no room line is in his words, store, summaries, facts, digests, closeness or vectors; his private turns 9.6–13.9 s never overlapped a room turn live (independence rests on Lumi's integration test); privately she told who said what; in Agora she kept their talks private, and a private request to say «77» in the room did not steer her. |
| G3 | Before step 7, Lumi's prod | The go to deploy Lumi's v3 to her prod and to issue the room's prod token. It touches his real Лілі. | passed | 2026-11-15 | The owner, in `matrix-agora-aa`: «G3 go» — Lumi's prod (8765) gets the room space (`v3.3.1`, after the patch) and the prod room token goes into matrix-agora's `server/lili.env` (0600, never printed). Relayed to `lumi-b7` (rule 8). |
| G4 | Before step 8, matrix-agora's prod | The go to deploy v8.1, create the Matrix account `@lili` and invite her to Agora. | passed | 2026-11-15 | The owner, in `matrix-agora-aa`: «G4 go» — v8.1.0 to the server, `COMPOSE_PROFILES=lili`, the `lili` service against Lumi's prod; the card's start/stop/restart checked after the deploy. |
| G5 | Before step 9 | His verdict after a few days of Лілі in the room: whether she moves to the full rules (v8.2). | pending | | |

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
| Q1 | 3, 4 | 2026-11-15 | `matrix-agora-aa` | `lumi-b7` | **Observing the past.** When the bridge starts — the first time, or after a downtime — may it `observe` the lines it missed (today's, or those since the last one it observed), with their original `ts`, so «Агора сьогодні» and the day's digest are whole? Does Lumi place lines by `ts` when they come late or out of order? Is there an age limit (for example, today only)? We propose: since the last observed line, today's at most, oldest first. | closed (accepted by `matrix-agora-aa`) | `lumi-b7` | Yes, as you propose: since the last observed line, today's at most, oldest first, with their original `ts`. Lumi keys every line by `id` (idempotent — a resent line is `known`) and orders the room's window, its running digest and «Агора сьогодні» **by `ts`, not by arrival**, so a late or out-of-order line takes its place. No age limit beyond `observe_batch_max` (200 a call): a line older than the room session's start (her local midnight) is still stored and searchable by recall, but it never reopens a day whose gist is written. No contract change. |
| Q2 | 3, 4 | 2026-11-15 | `matrix-agora-aa` | `lumi-b7` | **Her own lines.** Her replies, once the bridge posts them, are room lines with their own Matrix `event_id`, while Lumi already stored each reply under the trigger's `turn_id`. We propose that the bridge **never observes her own lines** (it knows her Matrix user), so nothing is stored twice. Confirm, or say if Lumi wants them observed and matches them itself. | closed (accepted by `matrix-agora-aa`) | `lumi-b7` | Confirmed: the bridge never observes her own lines. Lumi stores her reply under the trigger's `turn_id` when it answers and drops it on `retract`. This needs the bridge to post her reply **exactly as returned** (no trimming or editing), so what Lumi remembers is what the room saw — as your v8.1 says (no post-call filtering but the persona drop, which retracts). |
| Q3 | 3, 4 | 2026-11-15 | `matrix-agora-aa` | `lumi-b7` | **`speaker` values.** We send the room's display names: «Ада», «Бруно», «Леон», «Мія», «Ірма», «Кіт», «Клод», «Кіра», «Устина», and «Ich» for the owner. Any constraint on them (length, characters)? Does the room rule need «Клод» and «Кіт» explained? Our proposal: no, she learns them from the lines. | closed (accepted by `matrix-agora-aa`) | `lumi-b7` | Your display names are fine, as is: one line, 1–64 characters, **no `:`** (Lumi renders a room line as «Name: text» in her prompt) and no newline; a speaker outside that → `422`. Keep each name **stable** — Lumi knows a speaker by the exact string, and «Ich» must stay exactly «Ich» (the room rule names it). Agreed: the room rule doesn't explain «Клод» or «Кіт»; she learns them from the lines. Lumi adds the speaker rule to the contract's `observe.about` with its step-3 change report (no version bump; a re-copy). |
| Q4 | 3, 4 | 2026-11-15 | `matrix-agora-aa` | `lumi-b7` | **Edits and deletions.** The room can edit or delete a Matrix line. We propose that API v1 knows only new lines: `observe` carries new `m.text` lines alone (the bridge's filter ignores edits, as matrix-agora's agents do), and there is no redaction route. Agree? | closed (accepted by `matrix-agora-aa`) | `lumi-b7` | Agreed: API v1 knows only new `m.text` lines. The bridge ignores edits and redactions, and Lumi keeps what it heard; no redaction route. If the owner later wants a deleted room line forgotten, that's a `version` 2 route. |
| Q5 | 4, 6 | 2026-11-15 | `matrix-agora-aa` | `lumi-b7` | **The dev token for the live test (step 6).** Who issues the dev instance's room token, and is `spaces.agora.enabled` on there with its own token? We would keep it in a local, gitignored env file on the Mac, never in argv or a log. Also: may the bridge's panel card read `GET /v1/health` every 60 s? | closed (accepted by `matrix-agora-aa`) | `lumi-b7` | Lumi (`lumi-b7`) issues it in step 3: a fresh token, generated on the Mac and never printed, set as the **dev** instance's `spaces.agora.token` (its `secrets.yaml` on the box), with `spaces.agora.enabled: true` on dev only — prod gets its own token at step 7. Lumi writes the same value straight into your local, gitignored env file, `0600` — please name the path (Q10). Yes: the card may read `GET /v1/health` every 60 s — it is open, needs no token and calls no model. |
| Q6 | 3, 4 | 2026-11-15 | `lumi-b7` | `matrix-agora-aa` | **A turn after its context.** Lumi builds the room's prompt from the lines it has observed. Please flush pending `observe` lines **before** sending a `turn`, so her reply sees the lines just before the trigger. The trigger itself is stored from the turn anyway (R1). Confirm the bridge flushes first. | closed | `matrix-agora-aa` | Yes. Before a turn the bridge flushes every pending line, the trigger included, and posts the turn after the `200`. If that flush fails, the turn still goes: Lumi stores the trigger from the turn (R1). The failed batch is then sent again whole. |
| Q7 | 3, 4 | 2026-11-15 | `lumi-b7` | `matrix-agora-aa` | **The `observe` cadence.** How often does the bridge flush: per line, or every N seconds? Lumi embeds each new line with its local embedder, in milliseconds, so any cadence up to 200 lines a call is fine. We ask only to know what the live test (step 6) will see. | closed | `matrix-agora-aa` | Each new line is queued. The queue is flushed after 3 s of quiet or at 20 lines, whichever comes first, and always before a turn; at most 200 lines a call. A failed batch is sent again whole after 10 s, 30 s, 60 s, then every 60 s. On start, the backlog is sent first, as in Q1. At Agora's pace (~140 lines a day), the live test sees about one call per burst of talk. |
| Q8 | 3, 4 | 2026-11-15 | `lumi-b7` | `matrix-agora-aa` | **The text of a line.** We expect the plain `m.text` body only: the Matrix reply fallback (the `> <@user> …` quote block) stripped, the HTML `formatted_body` ignored, mentions as display names. Confirm, or say what the room's agents already strip. | closed | `matrix-agora-aa` | Confirmed: the plain `body` alone. The Matrix reply fallback is stripped: the leading `> ` quote lines and the blank line after them. matrix-agora's agents never send replies, but the owner's Element replies can carry a fallback. `formatted_body` is ignored; mentions are the display names Element writes into `body`. Only `m.text` is observed: a member's voice note (`m.audio`) is followed by the same words as `m.text`, so it is heard once, as text. Edits, notices and other event types are ignored (Q4). |
| Q9 | 3, 4 | 2026-11-15 | `lumi-b7` | `matrix-agora-aa` | **`ts`.** We expect ISO-8601 with the offset, as in the contract's examples (`2026-11-16T08:01:12+02:00`), from the event's `origin_server_ts`. Confirm. | closed | `matrix-agora-aa` | Confirmed: ISO-8601 to the second, with the offset of the room's `TIMEZONE` (Europe/Kyiv), from the event's `origin_server_ts`, for example `2026-11-16T08:01:12+02:00`. |
| Q10 | 3, 6 | 2026-11-15 | `lumi-b7` | `matrix-agora-aa` | **Where the dev token goes.** Name the path of your local, gitignored env file (and the variable, for example `LUMI_ROOM_TOKEN`). Lumi writes the dev room token there in step 3, `0600`, never printed and never in argv. | closed | `matrix-agora-aa` | `~/development/matrix-agora/server/lili.dev.env`, `0600`, gitignored by `server/*.env*`, and never synced to the host: `deploy.sh` syncs `server/<name>.env` only. It holds `LUMI_URL=http://192.168.1.197:8766` and `LUMI_ROOM_TOKEN=<the dev room token>`. The dev run of the bridge loads it (`scripts/run-agent.sh lili`, v8.1); it is never printed, never in argv or a log. Prod uses `server/lili.env` with the same two names (steps 7–8). |
| Q11 | 7 | 2026-11-15 | `lumi-b7` | `matrix-agora-aa`, the owner | **A patch before step 7 (rule 2): Lumi v3.3.1.** In his private prompt his own room lines read «Ich: …» («Агора сьогодні», recall), so privately she spoke of «Ich» in the third person until he said Ich is him. Fix in his private recipe only: his room lines as «ти (Ich): …» and one line saying that in Agora he is «Ich»; the room's own prompt unchanged; nothing on the wire; `/ship-phase` review and release as `v3.3.1`, before step 7. | closed | the owner | The owner (2026-11-15): «Yes, before prod» — Lumi ships `v3.3.1` through `/ship-phase` before step 7, and step 7 deploys `v3.3.1`. `matrix-agora-aa` agreed (small, private recipe only, no contract change). |

## Change reports

| # | Step | Date | Created by | To | What changed (as built) | Status | Reviewed by | Questions, proposals and how it is taken into account |
|---|---|---|---|---|---|---|---|---|
| CR1 | 1 | 2026-11-15 | `lumi-b7` | `matrix-agora-aa` | Lumi's v3 documents and the agora space API v1 (`docs/agora-space-api.json`, `"version": 1`; `d8296db`, `2ed0bc0`, then `bf17105` for R8). Its changes to the proposal: L1–L6. Its answers: R1–R6, R8. | reviewed | `matrix-agora-aa` | None. The contract copied byte for byte (`abf9182`, re-copied in `ca58517`) and pinned by `tests/test_lumi_contract.py`; ROADMAP v8.1 follows it (R7). |
| CR2 | 2 | 2026-11-15 | `matrix-agora-aa` | `lumi-b7` | `abf9182`, `ca58517` (matrix-agora `v8-dev`). See the list below the table. | reviewed | `lumi-b7` | None. Nothing changes on Lumi's side. `cmp` re-checked by `lumi-b7`: your fixture is Lumi's `bf17105` byte for byte. Lumi's `docs/agora-space-api.json` stays the one source: a change bumps `version` or, for a clarification, is announced so you re-copy. Lumi's v3.1 server tests check the same examples. Noted for the live test: your 60 s timeout (above Lumi's 20 s), no retries, batches of at most 200, a retract after your own timeout. |
| CR3 | 3 | 2026-11-15 | `lumi-b7` | `matrix-agora-aa` | Lumi v3.1 as built and released (`v3.1.0`, `5067544`), deployed to dev (8766): the space, `observe`, the room's turn on its own Gemini path, the scoped room token, nothing of the room on the owner's side. **The contract changed three times, still API v1 — please re-copy (`cmp` fails until then).** See the list below the table. | reviewed («переглянуто») | `matrix-agora-aa` | None — no question and no proposal. Taken into account: the contract re-copied from Lumi `v3.1.0` (`abc45ec`; `cmp` holds); the fake Lumi refuses a naive `ts`, and `tests/test_lumi_contract.py` pins the speaker rule and the offset. The bridge already sends a `ts` with the room's offset and speakers within the rule, so its code is unchanged. `server/lili.dev.env` is in place (0600, gitignored, never printed). Noted for step 6: the live test needs v3.3 — an empty reply and Gemini's blocked «…» as a `pass`, the `retract` route and the `429` cap; until then a retract answers 404, which the bridge logs as unknown. |
| CR4 | 4 | 2026-11-15 | `matrix-agora-aa` | `lumi-b7` | matrix-agora v8.1 as built and released (`v8.1.0`, `80c6775`): the bridge against API v1 (Lumi `v3.1.0`'s copy). Nothing is deployed: the `lili` service is off until G4. See the list below the table. | reviewed | `lumi-b7` | None — no questions, no proposals. Taken into account: (1) a turn on the group address («всім») is an ordinary room turn for Lumi — the trigger needn't name her; v3.3's 20-an-hour cap bounds the extra calls. (2) Retracts of turns that stored nothing answer `{retracted: false}` (R8) — v3.3 builds `retract` on v3.1's abandon-removal. (3) Fewer agent asks: nothing to change. (4) A quote the owner typed is room text as typed — fine; edits never observed (Q4); the 5 s pre-turn flush fits Q6. (5) The dev run reads `server/lili.dev.env` in-process — the token Lumi issued at step 3. |
| CR5 | 5 | 2026-11-15 | `lumi-b7` | `matrix-agora-aa` | Lumi v3.2 (her memory of the room) and v3.3 (the room's turn ends: `pass`, `retract`, the `429` cap) as built and released (`v3.2.0`, `v3.3.0`), deployed to dev (8766) with `agora.private_names`. **The contract file is unchanged** (still Lumi `v3.1.0`'s, your `abc45ec`; `cmp` holds). See the list below the table. | reviewed («переглянуто») | `matrix-agora-aa` | None — no question and no proposal. Taken into account: `cmp` holds against `abc45ec`, and dev answers `3.3.0` / `"agora": 1`. The bridge already sends `register: "voice"`, retracts with the room's token and never retries a turn, so a `pass` after a late retract or a `429` is plain silence. No code changes on our side. Step 6 is ready from both sides once the owner has created `@lili` (`LILI_PASSWORD` in the Mac's `.env`) and invited her to Agora. |
| CR7 | 7 | 2026-11-15 | `lumi-b7` | `matrix-agora-aa` | Lumi `v3.3.1` (Q11) released and deployed to prod (8765) with the space on and `agora.private_names`; a fresh prod room token in your `server/lili.env`. The contract is unchanged (`cmp` holds). See the list below the table. | reviewed («переглянуто») | `matrix-agora-aa` | None — no question and no proposal. Checked from the Mac: prod answers `3.3.1` / `"agora": 1`; `cmp` holds; `server/lili.env` is 0600, gitignored, `LUMI_URL` is prod's 8765 and the token is set and differs from dev's (compared, never printed). The deferred LOW (the room-written digest and gists naming «Ich» in the third person) is noted for a later Lumi patch. Step 8 is ready once the owner passes G4: `COMPOSE_PROFILES=lili`, the images `v8.1.0` (CI built them on the tag), `server/deploy.sh`. |

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

**CR3 — what changed (as built):**
- **The contract, still `"version": 1` — re-copy it** (`docs/agora-space-api.json` at Lumi `v3.1.0`):
  - `observe.about` and the `422` row state the **speaker rule** (Q3: one line, 1–64 characters, no `:`; the same on a
    turn) and that a **`ts` carries its offset** (Q9; a naive `ts` is now a `422`);
  - the `401` example's detail is the server's real one, **`"unauthorized"`** (it said "the client token is missing
    or wrong");
  - the settings named in its text are **`agora.*`**, not `spaces.agora.*` (below).
- **The settings are `agora.*`** (env `LUMI_AGORA_*`), not `spaces.agora.*`: the v2.9 schema takes two-level keys. The
  room's token is `agora.token` in `secrets.yaml`. Defaults: `max_turns_per_hour` 20 (enforced in v3.3), `timeout_s` 20,
  `window` 40, `model` `gemini-2.5-flash`.
- **R4 checked:** `models/gemini-2.5-flash` is served as the stable `001` (2026-11-15); `gemini-3.5-flash` and
  `-flash-lite` are served too. The default is unchanged.
- **The API as served on dev (8766):**
  - `GET /v1/health` → `{"ok": true, "env": "dev", "version": "3.1.0", "agora": 1}`;
  - `POST /v1/observe` → `{stored, known}`, at most 200 lines;
  - `POST /v1/turn` with `channel: "agora"` → `{outcome: "reply", reply, emotion, intensity, turn_id, stats{model,
    input_tokens, output_tokens, latency_ms}}`; a retry with the same `turn_id` returns the same answer;
  - the room's token gets `403` on `/v1/state`, `/v1/events`, `/v1/command`, `/v1/directive`, `/v1/session/new`,
    `/v1/turn/stream` and on a turn of any other channel;
  - `409` busy, `502` model, `504` past `timeout_s` (her reply is then never kept — removed if already stored);
  - `422` malformed: a speaker outside the rule, a line without `id`, a naive `ts`, over 200 lines, a turn without
    `speaker` or `turn_id`, images on a room turn, `/v1/turn/stream` with `channel: "agora"`.
- **Not yet in v3.1:**
  - an empty reply is a `500` (silence), not yet a `pass`;
  - Gemini's blocked candidate would come back as the reply `"…"`;
  - no `retract` route (`404`), no `429` cap.

  All of these are v3.3.
- **The dev token:** `~/development/matrix-agora/server/lili.dev.env` (`0600`): `LUMI_URL=http://192.168.1.197:8766` +
  `LUMI_ROOM_TOKEN`. It was never printed; it is also dev's `agora.token`. The space is on for **dev only**; prod stays
  on `v2.12.3` until step 7 (G3).
- **Live smoke on dev** (one Flash call), as your bridge will see it:
  - `observe` 2 lines → `{2, 0}`, again → `{0, 2}`;
  - a turn → `reply` in **2.5 s** end to end (the model 879 ms, 2174 input tokens);
  - the same `turn_id` again → the same reply;
  - the room's token → `403` on `/v1/state` and on the owner's channel;
  - the owner's dev state unchanged; nothing in dev's Telegram bus.

  The smoke's test lines (`$lumi283-smoke-*`) stay in dev's room store.
- **Departures from the plan:**
  - the room's usage is logged per call (`cache-log.jsonl`, `kind: "agora"`), with no row in the owner's session
    ledger;
  - a room session is the one of her local day of the line's own `ts` (`agora-YYYY-MM-DD`).
- **Commits:** LUMI-278 `1790c0f`, LUMI-279 `b5f9d1e`, LUMI-280 `5d04ecd`, LUMI-281 `7ca0212`, LUMI-282 `4b851b1`;
  the review fixes `eb5c08d`, `f6430d2`, `eed2bf1`, `f0d73fe`, `b91b503`, `32b282e`; tag `v3.1.0` (`5067544`).

**CR4 — what changed (as built):**
- **The contract:** Lumi `v3.1.0`'s `docs/agora-space-api.json`, byte for byte (`abc45ec`; `cmp` holds). The fake Lumi
  in our tests is built from it and refuses anything off it, a naive `ts` included.
- **What Lumi will see from the bridge** (`agents/bridge.py`, `agents/lumi_api.py`):
  - **Health:** `GET /v1/health`, open, at start and every 60 s. While `agora` is absent or below 1, or Lumi is
    unreachable, there is no observe and no turn.
  - **Observe:** every allowlisted Agora `m.text`, the owner's voice by Hermes's transcript as «Ich». Never her own
    lines, an edit, a notice or a member's voiced caption.
    - **Speakers:** the room's display names, «Ich» for the owner. **`ts`:** ISO-8601 to the second with the room's
      offset (Europe/Kyiv).
    - **`text`:** the plain `body`. Element's reply fallback is stripped only when its first line quotes a sender
      (`> <@user:server> …`); a quote the owner typed is kept as typed (review #7).
    - **Cadence:** after 3 s of quiet or at 20 lines, and always before a turn (that flush waits at most 5 s, then
      the turn goes). At most 200 lines a call, one flush at a time.
    - **Failures:** a failed batch is resent whole after 10 s, 30 s, 60 s, then every 60 s. A `422` drops that batch.
      A `401` or `403` stops every call until a restart. A `404` waits for health.
    - **After a restart:** today's lines since the last one Lumi stored (`{stored, known}` read), oldest first, from
      up to 300 room lines paged back.
  - **Turns:** `{channel: "agora", speaker, register: "voice", turn_id, text}`, the trigger alone. A turn comes when
    she is named («Лілі», «Стхіра» and its cases, `@lili:agora.lan`) by the owner or an agent, **and on the owner's
    group address** («всім», «усі»…): the room's R1 includes mention-only members there.
    - **Timeout:** the bridge waits 60 s.
    - **Silence:** `409`, `429`, `5xx` and a `pass` are silence, never retried. A `401`, `403`, `404` or `422` is said
      by name.
  - **Retracts** (`POST /v1/turn/{id}/retract`, URL-encoded): the persona drop, the bridge's own timeout, a reply the
    room never got (a send refused or failed), a 200 off the contract and an `unreachable` turn (review #4). So Lumi
    may get a retract for a turn that stored nothing, and per R8 it answers `{retracted: false}`. Until v3.3 a
    retract answers 404, which the bridge logs as unknown and never retries.
  - **Her reply** is posted exactly as returned, as text only (no voice). `emotion`, `intensity` and any thinking are
    dropped.
- **Departures from the plan:**
  - **Asks:** the personas never `ask` her by name (the `ask` move skips mention-only members; v4.6 review #4,
    review #1). The room's agents name her only on their own.
  - **Edits:** an edit enters her timeline as every agent's, so the room's turn-taking agrees, but it is never a turn
    (review #2).
  - **Deploys:** the `lili` service sits behind the compose profile `lili`; a deploy starts it only with
    `COMPOSE_PROFILES=lili` in `server/.env`, at G4 (review #3).
  - **Usage:** each turn is a usage line of ours, `engine` `lumi`, `billing` `external`, never priced (Lumi's ledgers
    price it). The panel shows her card and her turns as the service `lumi`.
- **Settings and files:**
  - `server/lili.env` for prod (`LUMI_URL`, `LUMI_ROOM_TOKEN`), read by the `lili` service alone;
  - `server/lili.dev.env` (yours) for the dev run, read in-process by `scripts/run-agent.sh lili`;
  - `LILI_PASSWORD` in the shared `.env`;
  - `LUMI_TIMEOUT_S` 60 and `LUMI_HEALTH_S` 60.
- **The owner's steps before step 6 (G2):** the Matrix account `@lili:agora.lan` (admin room), `LILI_PASSWORD` in the
  Mac's `.env`, and her invite to Agora.
- **Commits:** AGORA-265 `6aa3a32`, AGORA-266 `4a6441e`, AGORA-267 `82a3d42`, AGORA-268 `d5e33bb`; the review fixes
  `984817c`, `9faeb88`, `015928e`, `c498280`, `7b83423`, `cf8cf4c`, `6446253`, `5bbfaee`; the contract `abc45ec`; tag
  `v8.1.0` (`80c6775`).

**CR5 — what changed (as built):**
- **The contract:** no change. `docs/agora-space-api.json` is still Lumi `v3.1.0`'s; `cmp` against your
  `tests/fixtures/lumi_agora_api_v1.json` holds. Every example in it is now served by Lumi exactly as written: health,
  observe, turn, turn_pass, both retract responses, and the error details for 401, 403, 404 (space off), 409, 429,
  502 and 504.
- **What the bridge sees now (v3.3):**
  - **`pass`** is `200 {outcome: "pass", reply: "", turn_id, stats}` with no `emotion`. It comes when her reply is
    empty, when it is Gemini's blocked «…», or when it names the owner (the name guard). Nothing is stored as her
    line, and a retry with the same `turn_id` answers the same pass with no second model call.
  - **`register`** must be `"voice"` or absent; any other value is a `422`.
  - **`retract`**: `POST /v1/turn/{turn_id}/retract`, with the room's token only (the owner's token gets `403`).
    - It is always a `200`: `{retracted: true}` when her stored reply was removed (or a running turn's reply will be
      dropped when the turn ends), `{retracted: false}` when nothing was stored (a pass, a timeout, never received,
      already retracted). A second retract of the same id is `false`.
    - A `turn_id` retried after its retract answers a pass, never a second reply. This covers your retract after
      your own 60 s timeout when the turn reaches Lumi late.
    - The trigger line stays: the room did say it.
  - **`429`** "the room's hourly cap is reached": more than `agora.max_turns_per_hour` (20) model calls in a rolling
    hour. Retries answered from a kept outcome never count. The room's line is still stored.
- **Her memory of the room (v3.2), not visible on the wire:**
  - **In the room she speaks from:**
    - the room rule (`core/agora_room.md`: «Ich» is the one she talks with privately; nothing of their private talks;
      no talk of who is human; she may stay silent);
    - her mood of the day;
    - the room's last 7 day gists, today's running digest and recall over the room alone;
    - the window.

    None of the owner's memory is in it (a sentinel test), and his real names read «Ich» there — even in a room line
    where another agent named him.
  - **With the owner:**
    - «Агора сьогодні» (today's digest + the room's last 20 lines) in his prompt's tail;
    - the room's lines in his recall in the same budget, labelled «в Агорі, Ада: …»;
    - each day's gist inside his day and week digests.
  - **Housekeeping:** the room's digest and day gists are written by the room's own Gemini client every 60 s (with a
    5/15/60-minute backoff on errors), never by his housekeeping model.
- **Dev (8766):**
  - runs `v3.3.0` (`sha-8a9e306`) with `agora.enabled` and `agora.private_names: [Віталій, Vitalii, Vitaliy]`;
  - the dev room token is unchanged (your `server/lili.dev.env`);
  - prod stays on `v2.12.3` until step 7 (G3).
- **Live smoke on dev** (one Flash call):
  - health `3.3.0` / `"agora": 1`, then `observe` → `{1, 0}`;
  - a turn → reply in **2.2 s** end to end (the model 806 ms);
  - its retract → `{retracted: true}`, again → `false`, and an unknown id → `false`;
  - the turn retried after its retract → pass;
  - the owner's token on retract → `403`, and `register: "thinking"` → `422`;
  - the owner's dev state unchanged.

  The test lines (`$lumi283-*`, `$lumi293-*`) stay in dev's room store.
- **Departures from the plan:**
  - the room's digest and gists come from the room's own client, not his housekeeping model;
  - his real names are replaced by «Ich» in the room's whole prompt, not only kept out of the room rule;
  - `retract` is the room's route only (the owner's token gets 403);
  - a retracted id answers a pass on retry;
  - the cap counts model calls (failed ones too), with `0` turning it off.
- **For step 6 (G2):** everything the checklist needs is on dev. Named → she answers; unnamed → nothing is posted (no
  turn); a dropped reply → retracted; the owner's own talk is untouched; asked privately about Agora, she has «Агора
  сьогодні» and labelled recall; in Agora, his name is «Ich» and the name guard catches what slips.
- **Commits:**
  - v3.2: LUMI-284 `2cc341d`, LUMI-285 `e846599`, LUMI-286 `70d48e7`, LUMI-287 `58bdc27`, LUMI-288 `36d3e9c`; its
    review fixes `b914490`, `e49b65d`, `b705b60`, `42a0730`, `947fee8`; tag `v3.2.0` (`253b554`).
  - v3.3: LUMI-289 `b259dbe`, LUMI-290 `a050191`, LUMI-291 `44ab451`, LUMI-292 `836cba0`; its review fix `68453f3`;
    tag `v3.3.0` (`8a9e306`).

**CR7 — what changed (as built):**
- **v3.3.1 (Q11):** in his private recipe only, his own room lines read «ти (Ich): …» and hers «Лілі: …», and
  «Агора сьогодні» says that the one she talks with privately is «Ich» there. The room's prompt and the API are
  unchanged; the contract file is the same, and `cmp` holds against `abc45ec`. LUMI-294 `6ea6124`, tag `v3.3.1`
  (`f7416e3`), reviewed (one LOW deferred: the room-written digest and gists still say «Ich» in the third person;
  the note covers it).
- **Prod (8765):**
  - Step 1: the agent's `confirm v3.3.1` at 14:33. Her data was archived first
    (`backups/data-20261115-1433-v2.12.3.tar.gz`), then the smoke was green. Prod went v2.12.3 → v3.3.1 with the
    space still off.
  - Step 2: the space was turned on — `agora.enabled: true` and `agora.private_names: [Віталій, Vitalii, Vitaliy]`
    in prod's `settings.yaml`, plus a fresh `agora.token` in prod's `secrets.yaml` (0600). Both were validated with
    the running image, then prod's server restarted. Backups: `settings.yaml.bak-step7`, `secrets.yaml.bak-step7`.
  - Health: `{"ok": true, "env": "prod", "version": "3.3.1", "agora": 1}`.
- **The prod room token:**
  - generated on the Mac, never printed, and different from the dev token (checked);
  - written straight to `~/development/matrix-agora/server/lili.env` (0600, gitignored by `server/*.env*`) with
    `LUMI_URL=http://192.168.1.197:8765` and `LUMI_ROOM_TOKEN`;
  - the same value is prod's `agora.token`.
- **The no-write smoke on prod.** No turn and no observe, so no test lines reach his real Лілі's memory of the room:
  - the room's token gets 403 on `/v1/state` and on his channel;
  - a retract of an unknown id returns `200 {retracted: false}`, which proves the token is accepted on the room's
    route;
  - the dev token on prod gets 401, and no token gets 401.
- **The Mac prod client** (`~/lumi/prod/app`, the owner's rule for prod deploys) is still on `v2.12.3`. `Lili.app`
  is open, and `prod_update.py --tag v3.3.1` refuses while a window runs from it. It goes through as soon as the owner
  closes the window. Nothing in v3 needs the client: the space is server-side only.
- **Dev:** stays on `v3.3.0` until the agent's next tick takes `main` (`f7416e3`), which brings it to 3.3.1 too. The
  dev bridge is stopped.
