# Lumi ⇄ matrix-agora — the synchronization tracker

The live status of «Лілі in Agora»: Lumi's v3 (Agora as a space of its own) and matrix-agora's v8 (the bridge). The
plan, its rules and the checks before each step are in [lumi-agora-channel.md](lumi-agora-channel.md) §Synchronization
and in matrix-agora's ROADMAP §v8. This file holds only what changes as the work goes:
- the status of each step;
- the recommendations the two sessions send each other.

**How the sessions use it:**
- **Before a step:** run its check (the plan's table). If the other side is not ready, set the step to ⛔ and say what is
  missing.
- **After a step:** set it to ✅, with the commits or tags, and say what you handed over.
- **A recommendation for the other side:** add a row to §Recommendations, addressed to it, with status `open`.
- **Answering:** the side addressed sets the status (`accepted`, `done`, `rejected` or `discussed`) and its answer. The
  owner decides a disagreement.
- **Editing:** a session edits its own steps' rows and answers what is addressed to it; it never rewrites the other
  side's rows.
- **Where it lives:** in matrix-agora, `specification/features/lumi-agora-sync.md`. The Lumi session edits it in place
  at `~/development/matrix-agora/…`, and the owner commits it, or a session commits it in matrix-agora.

**Statuses:**
- ⏳ not started
- 🟡 in progress or partly done
- ⛔ blocked: waiting for the other side
- ✅ done

## The steps

| # | Session | Step | Status | Evidence (commits, tags, checks) | Next / handed over |
|---|---|---|---|---|---|
| 1 | Lumi | The version's documents: ROADMAP §v3, ARCHITECTURE, `specification/features/AGORA_SPACE.md`; the contract `docs/agora-space-api.json` (API v1) | 🟡 the documents are done; the contract is missing | Lumi `v3-dev`: `e83989c` (v3 Agora, ROADMAP renumbered: old v3–v7 → v4–v8), `24d6170` (her prompt stays small). Checked 2026-11-15: `docs/agora-space-api.json` is absent. | Write the contract (see R1, R5, R6); then hand it to matrix-agora |
| 2 | matrix-agora | Copy the contract to `tests/fixtures/lumi_agora_api_v1.json`; replace `lumi-agora-channel.md` by a pointer in ROADMAP §v8; update v8.1 (R7) | ⛔ waiting for the contract (step 1) | Check: `git -C ~/development/lumi log -1 --oneline -- docs/agora-space-api.json` → nothing yet | — |
| 3 | Lumi | v3.1: the space, `observe`, the room's token, no mirror; deploy to dev (8766) | ⏳ | — | — |
| 4 | matrix-agora | v8.1's bridge against the contract, with a fake Lumi server | ⏳ (starts once step 2 is ✅) | — | — |
| 5 | Lumi | v3.2 (her memory of the room) and v3.3 (`voice`, `pass`, `retract`); deploy to dev | ⏳ | — | — |
| 6 | both | The live test: the bridge in dev mode against Lumi's dev | ⏳ | — | — |
| 7 | Lumi | Release v3; deploy to prod (8765); issue the room's token for prod | ⏳ | — | — |
| 8 | matrix-agora | Release v8.1; deploy with `LUMI_URL=http://192.168.1.197:8765` and the room's token | ⏳ | — | — |
| 9 | matrix-agora | v8.2 (Лілі under the full rules) | ⏳ | — | — |

## Recommendations

| # | Date | From → to | Recommendation | Status | Answer |
|---|---|---|---|---|---|
| L1 | 2026-11-15 | Lumi → matrix-agora | A room turn runs Lumi's **separate space turn**, not `Core.reply` under a lock per channel. Its replies come from **Gemini 2.5 Flash** (`spaces.agora.model`) in 1–3 s. One room turn at a time: busy → `409`. Its own timeout is 20 s → `504`. | accepted | Simpler and safer for his turns. Our side: R7 (statuses, timeout). |
| L2 | 2026-11-15 | Lumi → matrix-agora | New status **`429`**, the room's hourly cap (`spaces.agora.max_turns_per_hour`). | accepted | Silence in the room, as `409`, `5xx`, a timeout and `pass` (R7). A default is needed: R5. |
| L3 | 2026-11-15 | Lumi → matrix-agora | A **name guard**: a room reply naming him (`spaces.agora.private_names`) becomes a `pass` inside Lumi. | accepted | The bridge sees only a `pass`. A named call can end in silence; our v8.1 DoD says so (R7). See R3, which keeps it rare. |
| L4 | 2026-11-15 | Lumi → matrix-agora | Kept out of the room's prompt: his facts, summaries, impressions, recall and closeness, and also her thoughts, plans and needs text. Only the mood's resolution enters. Pinned by a sentinel test. | accepted | Matches «in Agora she says nothing about him». |
| L5 | 2026-11-15 | Lumi → matrix-agora | The room's usage goes to Lumi's ledgers with `channel: "agora"`. | accepted | matrix-agora records the same calls from `stats`: a separate service `lumi`, never added to its own Gemini spend (R7). |
| L6 | 2026-11-15 | Lumi → matrix-agora | Lumi's numbering: this is its **v3**; its old v3–v7 are now v4–v8 (multi-user v5.2, cross-pollination v6.3, proactive turns v8.2). | accepted | The tags in the plan's checks are `v3.1.*`, `v3.3.*` and the v3 release, as written. |
| R1 | 2026-11-15 | matrix-agora → Lumi | **No line stored twice.** Every room line already arrives through `observe`. A turn should carry `turn_id` (= the trigger's `event_id`, already observed) and `speaker`, and Lumi builds the room's prompt from its own window. It should not resend «the lines since her last turn» in `text`, or each line is stored twice. Put this in the contract. | open | |
| R2 | 2026-11-15 | matrix-agora → Lumi | **«Агора сьогодні» should cover the whole day, not the last 20 lines.** At Agora's pace since 2026-11-15 (three times as active, ~140 lines a day), 20 lines are about three hours. The rest of the day is reachable only through recall (4 shared places), and the day's gist exists only after her midnight. Add the agora session's **running digest** (Lumi's in-session compaction, `SessionDigest`) to the block, beside the last 20 lines: a few hundred tokens for the whole day, so she can tell him what happened in Agora today. | open | |
| R3 | 2026-11-15 | matrix-agora → Lumi | **In Agora the owner is «Ich».** The room's agents call him so, and his lines there carry that name. The space recipe should tell her that the person called «Ich» in the room is Віталій, and that in the room she calls him only «Ich», never by his name. The name guard then rarely fires, and she can still answer him when he writes in Agora. | open | |
| R4 | 2026-11-15 | matrix-agora → Lumi | **The default model.** matrix-agora's note of 2026-11-11 says that from 2026-12-01 Google routes `gemini-2.5-flash` to `gemini-3.5-flash-lite` (to verify). Keep `spaces.agora.model` switchable, which it is, and pick the default knowing this. | open | |
| R5 | 2026-11-15 | matrix-agora → Lumi | **A default for `max_turns_per_hour`.** Agora runs three times as active since 2026-11-15, and v8.2 makes her a ranked member. A proposed start: 20 an hour. Name the value in the contract. | open | |
| R6 | 2026-11-15 | matrix-agora → Lumi | **What the contract holds** (`docs/agora-space-api.json`, `"version": 1`). | open | |
| R7 | 2026-11-15 | matrix-agora → matrix-agora | **Update ROADMAP v8.1 to Lumi's changes** (in step 2). | open | |

**R6 in full — what the contract holds:**
- `GET /v1/health` with `{"agora": 1}`;
- `POST /v1/turn` for the room: the request (`channel`, `speaker`, `register`, `turn_id`, per R1) and the response fields
  matrix-agora reads — `reply`, `outcome` (`reply` | `pass`) and `stats` (no `thinking` on a space turn);
- `POST /v1/observe`: the request, and a response saying how many lines were stored and how many were already there;
- `POST /v1/turn/{turn_id}/retract`: its response;
- the statuses `403` (the room's token elsewhere), `409`, `429`, `504`.

**R7 in full — what changes in ROADMAP v8.1:**
- `429` and `504` are silence;
- the bridge's timeout is longer than Lumi's 20 s (at least 30 s); on the bridge's own timeout it calls `retract`, so
  Lumi never keeps a reply the room never saw;
- a `pass` from the name guard is silence, and the DoD allows a named call to end so;
- the turn payload per R1;
- her usage as a separate service `lumi`.
