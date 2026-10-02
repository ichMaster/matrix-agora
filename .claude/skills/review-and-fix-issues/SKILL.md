---
name: review-and-fix-issues
description: Code-review a phase, a component or the current branch, write a criticality-ranked recommendations doc in specification/implementation/, implement the fix-now items with regression tests, then record what was done in the SAME doc. Never releases.
---

# Skill: Review & Fix Issues

One loop over the codebase: **review → recommend → fix → record.**

1. Run a critical code review.
2. Write a single recommendations document that ranks findings by criticality and marks each **FIX NOW**
   or **DEFER →**.
3. Implement the fix-now items with regression tests.
4. **Update that same document in place**, marking what was fixed and adding a "Fixes applied" section.

The recommendations and the results live in **one document**.

This skill fixes only small, in-scope, high-value findings. It **never** bumps the version or cuts a
release (that stays with `/release-version`), and it never pulls deferred or larger work forward without
flagging it.

## Usage

```
/review-and-fix-issues [target]
```

- `/review-and-fix-issues v0.5`: review what the phase delivered (through its tag `v0.5.0` if released).
- `/review-and-fix-issues agents`: scope the review to one component (`agents` / `panel` / `server` / `tests`).
- `/review-and-fix-issues`: review the **current branch**, i.e. everything built so far.

## Instructions

### Step 0: Scope and a green baseline

1. **Resolve the target:**
   - a phase (`vA.B`) / a version (`vA`) or its tag: the commits whose subjects carry that phase's `AGORA-###` ids, plus
     the files they touched;
   - a component;
   - no argument: the whole working tree.
2. **Clean tree:** check `git status` is clean and note the branch.
3. **Green baseline:** run the automated gates (`uv run ruff check .`, `uv run pytest`, and the compose
   check if `server/` exists). If the suite is **red or flaky**, say so. Fix a clear flake first (small,
   its own commit) or raise it and ask. **Never review or fix on top of a red suite.**

### Step 1: Critical code review

Read the in-scope code and take the highest-risk areas first. Be **adversarial**: hunt for *real*
defects, not restatements of what works.

- **Allowlist and authority:**
  - Is the room and sender check applied on **every** reply path, including replies triggered by the
    other agent and delayed replies?
  - Are DMs and other rooms ignored, are invites accepted only from `OWNER` into `ROOM_ID`, and does the
    bot never answer itself?
- **Restart behavior:**
  - Are events from the first sync processed, so history gets replayed?
  - Is a new device created on every start?
  - Does a missing or corrupt `state/<name>.json` crash the bot instead of falling back to a password login?
- **Loop protection (v1.2):**
  - Is `bot_streak` derived from the shared timeline, so both agents agree, and reset only by `OWNER`?
  - Can a delayed reply race a newer owner message and answer from stale history?
  - Can both agents answer a mention meant for one?
  - Does mention detection handle Ukrainian case forms? The ROADMAP's DoD uses the vocative «Адо» for Ада.
  - Is `PASS` handled with surrounding whitespace or punctuation?
  - Is the randomness (`BOT_REPLY_P`, the delay) injectable for tests?
- **Canon and memory (v2.1):**
  - Does a missing or empty canon stop the bot at startup?
  - Does any prompt or reply rule say the agent is a model or a bot?
  - Are memory writes atomic?
  - Does shutdown summarization hang past its timeout?
  - Is the session timeline capped by `SESSION_MAX_MESSAGES`?
  - Are summaries ever logged?
- **World and day memories (v2.2):**
  - Is the time computed in `TIMEZONE`, including across DST switches?
  - Are weekday and month names independent of the system locale?
  - Is the clock injectable?
  - Is a past day's memory ever rewritten?
  - Is the catch-up bounded by `MEMORY_DAYS`?
  - Does the memory prompt forbid invented words or actions by the owner or the other agent?
  - Is a past day's or week's plan ever rewritten after its period ends?
  - Is the today block refreshed at most once per hour (lazy, cached per hour) and reset at midnight?
  - Can a plan commit the owner or the other agent to something?
  - Are the prompt sections in the specified order?
- **Token accounting (v3.1):**
  - Does a usage line ever carry message or prompt text?
  - Does a missing `usage_metadata` crash the bot?
  - Are prices hardcoded?
  - Does the report break on a corrupt line, or on its sums?
- **The panel (v3.3):**
  - Is the Bearer token required on every API route (401 without it), and absent from logs and responses?
  - Do simulation, service and agent names resolve only through the registry and fixed lists — can any
    request data reach a filesystem path, an argv or the docker API?
  - Could a stale lock PID make Stop signal an unrelated process?
  - Are secrets masked in the settings view? Is "Forget" blocked while the agent runs?
  - Are huge logs tailed without reading the whole file? Do zombie processes pile up?
  - Does the UI degrade by card when docker or `state/` is unreachable? Are stop/restart/forget confirmed?
- **Robustness:**
  - Can an exception in a nio callback or the Gemini call kill `sync_forever`?
  - Is typing left on after a failure (no `finally`)?
  - Is a `None` `resp.text` handled?
  - What happens when the homeserver connection drops?
  - Are empty or huge messages handled, and is the history bounded by `HISTORY_N`?
- **Message semantics:**
  - Are replies sent as `m.text`?
  - Are only `RoomMessageText` events handled? Edits, notices and other event types must not trigger a
    reply.
  - Is the transcript format `Name: text` as specified?
- **Secrets and logging:**
  - Do tokens, passwords, the API key or message texts appear in logs, exception messages or `repr`?
  - Are the `state/` files readable by other users?
  - Is anything secret committed or echoed?
- **Server config:**
  - Are federation and encryption off?
  - Is registration closed after v0.4?
  - Does the registration token live only in `server/.env`?
  - Is the port published as intended (LAN plus ufw)?
- **Spec drift:** does the code diverge from the ARCHITECTURE.md contracts or the ROADMAP, or add what no phase asks for?

For each finding, capture:

- a **concrete failure scenario** (inputs → wrong result or crash);
- a `file:line` anchor;
- a **severity**: 🔴 HIGH / 🟠 MEDIUM / 🟡 LOW;
- a **proposed fix**.

Cross-check against ROADMAP.md and ARCHITECTURE.md. If a gap is already scheduled for a later phase, note that instead of
treating it as new.

### Step 2: Write the recommendations document (the plan)

Write **one** doc at `specification/implementation/<scope>-code-review.md`, e.g. `v0.4-code-review.md`,
`agents-code-review.md`, or `branch-code-review.md` for the whole tree. Include:

- a header: date, reviewer, **scope**, method;
- a **criticality-ranked summary table**: `# | Severity | Finding | Recommendation | Status`.
  Recommendation is `FIX NOW` or `DEFER → <home>`; Status starts as `⏳ pending`;
- for each finding, its failure scenario and proposed fix;
- a short **"What's solid"** section, to keep the review balanced;
- **suggested next actions**.

Decide **FIX NOW vs DEFER** honestly:

- **FIX NOW** means real, small, self-contained, high-value and in scope now: an allowlist hole, a replay on
  restart, a crash that kills sync, a secret in a log.
- **DEFER →** means larger work, or work a later phase already owns. Give the home: a later phase (`v1.1`…`v3.3`),
  `backlog` (no phase owns it) or `cleanup (/simplify)`. Do **not** pull it forward.

Commit the doc as the plan (`docs: vA.B code review`) **and push it** if a remote exists. The review is worth
keeping even if the fix pass is interrupted.

### Step 3: Implement the FIX NOW items, with tests

For each **FIX NOW** finding, in criticality order:

1. Implement the fix following `CLAUDE.md` and ARCHITECTURE.md. Keep it minimal.
2. **Add a regression test that would have caught the bug**, with nio and Gemini mocked. For a race,
   drive the interleaving explicitly.
3. **Validate:** lint and tests green, and compose if `server/` changed. Commit only passing code.
4. **Commit** one focused change per finding: `fix(<area>): … (code review #N)`, with the running model's
   `Co-Authored-By` trailer. **Then push.** Never leave a landed fix unpushed.
5. **A contract change** updates ARCHITECTURE.md and the pinning test in the **same** commit.

If a fix turns out bigger than "fix now" (it touches a contract broadly or needs a design decision),
**stop and re-classify it as DEFER** in the doc, with the reason, and move on. Don't half-land it.

### Step 4: Update the SAME document (the result)

Edit the doc **in place**:

- **Status column:** flip it to `✅ FIXED — <commit>` for each applied fix; keep `⏳ deferred` for the rest.
- **"Fixes applied" section:** for each fix, give the change, the regression test and the verification
  (final gate status).
- **"Architecture impact" note:** add one for any fix that **changed a documented contract or
  design-relevant behavior**, and make sure ARCHITECTURE.md reflects it. The next
  `/generate-issues` or `/reconcile-issues` reads these notes.
- **"Suggested next actions":** update them. Fixes on an already-released phase suggest a patch release
  (`/release-version A.B.1`); deferred items are carried into their phase.

Commit the update (`docs: vA.B code review — fixes applied`) **and push**.

### Step 5: Report

Summarize:

- findings by severity;
- which were **fixed** (with commits) and which **deferred** (with homes);
- the final gate status.

If fixes landed on an already-released phase, suggest `/release-version A.B.<next>`, but do **not** run
it. Offer a deeper pass with `/code-review high` for confirmation.

## Important Rules

- **One document, updated in place.** Recommendations and results share a single doc.
- **Fix only the FIX NOW items.** Never pull deferred work forward without re-classifying it in the doc.
- **Every fix ships a regression test**, with nio and Gemini mocked. No test calls the network or a paid
  API.
- **Green before, green after.** Commit only code that passes the gates.
- **Record architecture deltas.** A contract change updates ARCHITECTURE.md and its test in
  the same commit, and gets an "Architecture impact" note.
- **Never release.** No version bump, no tag.
- **Never leave work unpushed** (when a remote exists). This skill can stop mid-way, so "the next step will
  push it" is not a safe assumption.
- **Ask on genuine ambiguity**: an unclear scope, or a borderline fix-now-vs-defer call.
