---
name: ship-phase
description: Full GitHub-backed delivery pipeline over ROADMAP phases. Takes one selector or a comma-separated LIST of phases/versions/ranges (e.g. v0.4, v1, v0-v2). The list names TARGETS - missing earlier phases are added automatically, the set is de-duplicated, sorted into roadmap order, and already-released phases are skipped. Per phase - generate-issues (with reconcile), upload-issues, execute-issues, DEPLOY the build (automatic, never asked), the OWNER TESTS it live, review-and-fix-issues, then release-version A.B.0 which DEPLOYS the release. At the END of the run a HARDEN sweep runs BY DEFAULT (opt out with --no-harden). Gated; stops on failure; pauses only for the owner's live test and owner-run steps.
---

# Skill: Ship Phase — the full delivery pipeline

Drive the whole loop over the ROADMAP's phases. **Each phase is released before the next one is
generated**, so the next phase's issues are reconciled against the real, post-fix implementation. The
hardening sweep of deferred findings runs **by default once at the end of the run**; pass `--no-harden` to
skip it.

**The loop:**

```
PLAN = selectors → phases → de-duplicated → + missing earlier phases → sorted into roadmap order
       → minus already-released (tag vA.B.0 exists)

for each PHASE vA.B in PLAN (in order):
    0. RECONCILE  — ground vA.B in the real implementation + all prior fixes (inside generate-issues)
    1. generate-issues vA.B
    2. upload-issues @specification/implementation/vA.B-issues.md
    3. execute-issues vA.B::phase   (implement → gates → commit → push → close the code issues)
    4. DEPLOY the phase build        ← AUTOMATIC, never asked (main → :sha-<short>; release-version §Deploy)
    5. OWNER TESTS it live           ← the only pause: the phase's Manual (owner) DoD, confirmed or waived
    6. review-and-fix-issues vA.B   (review → ranked doc → fix-now fixes → same doc)
    7. release-version A.B.0        ← RELEASE PER PHASE (tag vA.B.0) and DEPLOY it (:vA.B.0), automatic
    → REPORT the phase to chat
→ END OF RUN: HARDEN (harden-findings <plan scope> --release) — BY DEFAULT, skipped with --no-harden
→ overall summary to chat
```

This skill is a **thin orchestrator**. It sequences the sub-skills, adds the gating and the end-of-run
hardening, and releases per phase; each sub-skill keeps its own discipline.

> **This pipeline releases and deploys.** Invoking `/ship-phase` is the explicit opt-in to the automated
> per-phase releases (real tags and pushes), **to every deploy** and to the HARDEN sweep. `/release-version`'s
> own rules still hold: it never downgrades and it confirms the changelog. To build without releasing, use the
> individual skills.

> **The owner's order** (2026-11-18: «порядок такий - спочатку деплой мое тестування, потім код ревью і фікси і
> потім деплой і реліз»; «і не питай мене про деплой, це має бити автоматично»):
> 1. the phase's code is built (its code issues closed, gates green);
> 2. **deploy** that build — automatically, never asking;
> 3. **the owner tests it** live (the phase's Manual (owner) DoD);
> 4. **code review and fixes** (`review-and-fix-issues`);
> 5. **deploy and release** — the release tag, then its images deployed, automatically.
>
> A fix found later — in the owner's test, in the room, or by HARDEN — ships as a patch `A.B.C` through the
> same order where it applies: fix → review → release → deploy (the owner, 2026-11-15: every versioned step
> runs through this pipeline, reviewed and released).

## Usage

```
/ship-phase <selector>[,<selector>…] [--no-harden]
```

A **selector** is a phase (`v0.4`, or a bare `0.4`), a version (`v1` = all its phases), or a range
(`v0-v2`, `v0.4-v1.2`). Pass one, or a comma-separated list of any mix; whitespace around commas is
ignored.

- `/ship-phase v0.4`: ship phase v0.4, plus any earlier phases that aren't released yet.
- `/ship-phase v1`: ship v1.1 and v1.2 (and any unreleased earlier phases), then HARDEN, then a summary.
- `/ship-phase v2,v1 --no-harden`: ships v1.1 → v1.2 → v2.1 → v2.2 (reordered), with no HARDEN sweep.

> **The list is a target, not the whole plan.** The roadmap is cumulative: the echo bot (v0.5) needs the
> homeserver, the deploy, the client and the room (v0.1–v0.4), and v2 cannot be built without v1. So missing earlier
> phases are **added automatically**, and anything already released is skipped. On a repo released through
> `v2.2.0`, `/ship-phase v3.1` does exactly one phase's work.

## Instructions

### Step 0: Scope, baseline and the plan

1. **Parse the selector list.** Split on commas and trim. Each element is a phase (`vA.B`), a version
   (`vA`), or a range. Record whether `--no-harden` was passed.
2. **Resolve against the ROADMAP.** The phase universe is the `### vA.B` headings of
   [specification/ROADMAP.md](../../../specification/ROADMAP.md), grouped under their `## vA` version
   headings, **in file order**. A version selector expands to all its phases; a range to every phase it
   spans.
3. **Reject nothing silently.** If an element doesn't resolve to a real ROADMAP phase or version (a typo,
   `v9`, a reversed range `v2-v0`), name it and ask. Never drop it and ship the rest.
4. **Expand, de-duplicate and fill.** Resolve the elements to a set of phases. Then add **every earlier
   roadmap phase** before the latest one that isn't already in the set. These are requirements, not scope
   creep: report them at confirmation but don't ask permission.
5. **Sort into roadmap order.** The set is never a running order: `/ship-phase v2,v1` ships v1 first. If
   the order differs from what was typed, say so.
6. **Skip released phases** (tag `vA.B.0` exists). A phase that is partly done (issues file or GitHub
   issues exist, but no tag) resumes from its remaining steps. The sub-skills are idempotent: generate asks
   before overwriting, upload skips existing issues, execute skips closed ones, release refuses a downgrade.
7. **Preconditions:**
   - `gh` is authenticated and the repo has a GitHub remote. If either is missing, stop and offer
     `gh repo create` (run by the user) or the offline `/ship-solution`.
   - The tree is clean.
   - The automated gates are green, or `n/a` before v0.5. Never start on a red suite.
8. **Flag the owner's work up front.** Most of v0 (v0.1, v0.3, v0.4) is steps the owner performs on the Ubuntu host
   and in Element, and every phase's DoD has **Manual (owner)** checks. Tell the user at confirmation
   that the run **will pause** for them — for the live test after the deploy, never for the deploy itself.
9. **Confirm the plan once.** Show:
   - the ordered phase list, grouped by version;
   - the filled-in phases, any reordering and the skips;
   - whether HARDEN runs;
   - the expected owner pauses.

   Then run. Don't re-confirm before each sub-step; pause only for the blockers in the rules below.

**Worked example:** `/ship-phase v2.1,v1` on a repo where v0 is fully released (`v0.1.0`–`v0.5.0` tagged).

```
selectors : v2.1 · v1
expanded  : v2.1 | v1.1 v1.2
filled    : (nothing missing below v2.1 beyond the set)
skipped   : v0.1–v0.5                ← already released
ordered   : v1.1 → v1.2 → v2.1      (v2.1 was listed first; roadmap order is required)

PLAN: v1.1, v1.2, v2.1 → HARDEN v1-v2 → summary
Owner pauses: each phase's Manual (owner) DoD (Element, live Gemini from v1.1)
```

### Step 1: For each phase, the five steps, gated

Run the phases **strictly in sequence**: phase N+1 starts only after phase N is **released**. Invoke each
sub-skill through the **Skill tool** and follow its instructions fully.

0. **RECONCILE.** This happens inside `generate-issues` (its Step 0.5). It reads the real code, the
   earlier execution reports and the earlier code-review docs ("Fixes applied", "Architecture impact").
   Where fixes moved the code away from ARCHITECTURE.md, the code is ground truth.
1. **`generate-issues vA.B`** writes `specification/implementation/vA.B-issues.md`.
2. **`upload-issues @specification/implementation/vA.B-issues.md`** creates the GitHub issues, labels and
   dependency comments, and `vA.B-github-report.md`, and commits them.
3. **`execute-issues vA.B::phase`** implements the code issues one per commit, runs the gates, pushes and
   closes them. The phase's `ops` issue (deploy and live checks) stays open for steps 4–5.
4. **DEPLOY the phase build — automatically, never asked.** Fast-forward `main` to the working branch, wait
   for CI's `:sha-<short>` images, set them in `server/.env` and run `server/deploy.sh` (the procedure:
   `release-version` §Deploy). A red CI or a failed deploy stops the run and is reported.
5. **The OWNER TESTS it.** Give the owner the phase's Manual (owner) DoD as a short checklist and wait for his
   word: each check confirmed, or waived. Fix what his test finds first (one commit each, gates green,
   deployed again the same way) before the review. Then close the `ops` issue and write
   `vA.B-execution-report.md`.
6. **`review-and-fix-issues vA.B`** writes the ranked review doc, fixes only the FIX NOW items (with
   regression tests) and records them in that same doc.
7. **`release-version A.B.0`** bumps the version, tags `vA.B.0`, pushes, and **deploys the release**
   (`:vA.B.0`) automatically.

**Gate the hand-offs:**

- upload only after generate wrote the file;
- execute only after the issues exist;
- deploy only after every code issue is closed and the gates are green;
- review only after the owner has tested the deployed build (confirmed or waived) and every issue is closed;
- release only after the review's fix-now items are committed and the gates are green;
- start the next phase only after this one is released **and deployed**.

**Every phase boundary ends pushed and clean.** Before the next phase, check that `git status` is clean and
there are no unpushed commits, and `git push` if there are. This skill **stops on failure by design**, so a
stop must never leave a phase's work on one machine only.

### Step 2: REPORT each phase to chat

After each release, report:

- the `AGORA-###` range → GitHub numbers;
- the execution commit range and the gate status;
- the deploys (the test build's `:sha-…` and the release's `:vA.B.0`, with their times);
- the manual checks the owner confirmed or waived;
- the review findings (fixed now / deferred, with homes);
- any "Architecture impact" notes;
- the release tag.

Then continue with the next phase.

### Step 3: END OF RUN — HARDEN (default; `--no-harden` skips it)

Once the last phase in the plan is released, invoke **`harden-findings <first>-<last> --release`** through
the Skill tool, with the run's phase range.

- **What it does:** fixes every still-unfixed 🔴 HIGH / 🟠 MEDIUM finding from the run's review docs, each
  with a regression test, updates the docs in place, and ships a patch release on the latest phase (e.g.
  `v1.2.1`).
- **Held findings:** its escape hatch applies, so a fix that can't land cleanly is held with a reason, not
  forced.
- **With `--no-harden`:** skip it, and list the outstanding HIGH/MEDIUM findings and their homes in the
  summary.

Then give a short **overall summary**: phases shipped, phases skipped as already released, the HARDEN
outcome, anything that stopped early and what remains, and what's next.

## Important Rules

- **The order is fixed:** build → deploy → the owner tests → review and fixes → release and deploy.
- **Deploys are automatic — never ask.** Every phase build and every release is deployed by Claude
  (`release-version` §Deploy). Only a red CI or a failed deploy pauses, as a failure.
- **Release per phase (`A.B.0`)**, after it is built, deployed, owner-tested, reviewed and fix-now-fixed.
  Never batch phases into one release; never release mid-phase.
- **Later fixes are patches** (`A.B.1`, …) — reviewed, released and deployed the same way; nothing is
  hand-built outside the pipeline.
- **Next phase only after the previous one is released.** This strict order is what makes reconciliation
  meaningful.
- **HARDEN runs once at the end of the run, by default.** Invoking the skill is the consent; `--no-harden`
  is the opt-out.
- **Every phase boundary ends pushed and clean.**
- **Stop on failure; don't paper over it.** A failed sub-skill or a red gate halts the run. Report what
  completed and what remains. Never release a phase whose gates aren't green.
- **Pause for the owner** only for his live test and owner-run steps: manual DoD checks are confirmed (or
  waived) by the owner, never assumed. Deploys are not owner steps. Anything else on the host or in Element
  waits for his word.
- **Pause for real decisions:** an id or tag collision, an overwrite-or-append prompt, a held HARDEN
  finding, a failure. Routine confirmations run straight through.
- **Delegate, never duplicate.** This skill sequences `generate-issues`, `upload-issues`, `execute-issues`,
  `review-and-fix-issues`, `release-version` and `harden-findings`, and adds gating; it has no logic of its
  own.
- **The plan is roadmap-ordered and dependency-complete, always.** De-duplicate, fill the earlier phases,
  sort into ROADMAP file order, then drop the released ones. Report the fill, the reordering and the skips.
