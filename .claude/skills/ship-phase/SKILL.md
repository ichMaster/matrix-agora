---
name: ship-phase
description: Full GitHub-backed delivery pipeline over SPEC.md phases. Takes one selector or a comma-separated LIST of phases/ranges (e.g. p3, p3-p5, p0,p4). The list names TARGETS - missing earlier phases are added automatically, the set is de-duplicated, sorted into phase order, and already-released phases are skipped. Per phase - generate-issues (with reconcile), upload-issues, execute-issues, review-and-fix-issues, release-version 0.N.0. At the END of the run a HARDEN sweep runs BY DEFAULT (opt out with --no-harden). Gated; stops on failure; pauses for owner-run steps.
---

# Skill: Ship Phase — the full delivery pipeline

Drive the whole loop over SPEC.md's phases. **Each phase is released before the next one is generated**,
so the next phase's issues are reconciled against the real, post-fix implementation. The hardening sweep of
deferred findings runs **by default once at the end of the run**; pass `--no-harden` to skip it.

**The loop:**

```
PLAN = selectors → phases → de-duplicated → + missing earlier phases → sorted p0..p5
       → minus already-released (tag v0.N.0 exists)

for each PHASE pN in PLAN (in order):
    0. RECONCILE  — ground pN in the real implementation + all prior fixes (inside generate-issues)
    1. generate-issues pN
    2. upload-issues @specification/implementation/pN-issues.md
    3. execute-issues pN::phase     (implement → gates → owner checks → commit → push → close)
    4. review-and-fix-issues pN     (review → ranked doc → fix-now fixes → same doc)
    5. release-version 0.N.0        ← RELEASE PER PHASE (tag v0.N.0)
    → REPORT the phase to chat
→ END OF RUN: HARDEN (harden-findings <plan scope> --release) — BY DEFAULT, skipped with --no-harden
→ overall summary to chat
```

This skill is a **thin orchestrator**. It sequences the sub-skills, adds the gating and the end-of-run
hardening, and releases per phase; each sub-skill keeps its own discipline.

> **This pipeline releases.** Invoking `/ship-phase` is the explicit opt-in to the automated per-phase
> releases (real tags and pushes) **and** to the HARDEN sweep. `/release-version`'s own rules still hold:
> it never downgrades and it confirms the changelog. To build without releasing, use the individual skills.

## Usage

```
/ship-phase <selector>[,<selector>…] [--no-harden]
```

A **selector** is a phase (`p3`, or a bare `3`) or a range (`p3-p5`). Pass one, or a comma-separated list
of any mix; whitespace around commas is ignored.

- `/ship-phase p3`: ship phase 3, plus any earlier phases that aren't released yet.
- `/ship-phase p3-p5`: ship phases 3, 4 and 5 in order, then HARDEN, then an overall summary.
- `/ship-phase p5,p3 --no-harden`: ships p3 → p4 → p5 (reordered, gap filled), with no HARDEN sweep.

> **The list is a target, not the whole plan.** The phases are cumulative: the echo bot (p3) needs the
> homeserver, the accounts and the room (p0–p2). So missing earlier phases are **added automatically**, and
> anything already released is skipped. On a repo released through `v0.4.0`, `/ship-phase p5` does exactly
> one phase's work.

## Instructions

### Step 0: Scope, baseline and the plan

1. **Parse the selector list.** Split on commas and trim. Each element is a phase or a range. Record whether
   `--no-harden` was passed.
2. **Reject nothing silently.** If an element doesn't resolve to a phase in 0–5 (a typo, `p7`, a reversed
   range `p5-p3`), name it and ask. Never drop it and ship the rest.
3. **Expand and fill.** Resolve the elements to a set of phases and de-duplicate. Then add **every earlier
   phase** below the highest one that isn't already in the set. These are requirements, not scope creep:
   report them at confirmation but don't ask permission.
4. **Sort into phase order.** The set is never a running order: `/ship-phase p5,p3` ships p3 first. If the
   order differs from what was typed, say so.
5. **Skip released phases** (tag `v0.N.0` exists). A phase that is partly done (issues file or GitHub
   issues exist, but no tag) resumes from its remaining steps. The sub-skills are idempotent: generate asks
   before overwriting, upload skips existing issues, execute skips closed ones, release refuses a downgrade.
6. **Preconditions:**
   - `gh` is authenticated and the repo has a GitHub remote. If either is missing, stop and offer
     `gh repo create` (run by the user) or the offline `/ship-solution`.
   - The tree is clean.
   - The automated gates are green, or `n/a` before p3. Never start on a red suite.
7. **Flag the owner's work up front.** Phases p0–p2 are mostly steps the owner performs on the Ubuntu host
   and in Element, and from p0 onwards each phase's DoD has manual checks. Tell the user at confirmation
   that the run **will pause** for them.
8. **Confirm the plan once.** Show:
   - the ordered phase list;
   - the filled-in phases, any reordering and the skips;
   - whether HARDEN runs;
   - the expected owner pauses.

   Then run. Don't re-confirm before each sub-step; pause only for the blockers in the rules below.

**Worked example:** `/ship-phase p5,p3` on a repo where `v0.0.0`–`v0.2.0` are tagged.

```
selectors : p5 · p3
filled    : + p4                ← needed by p5, not named
skipped   : p0 p1 p2            ← already released
ordered   : p3 → p4 → p5        (p5 was listed first; phase order is required)

PLAN: p3, p4, p5 → HARDEN p3-p5 → summary
Owner pauses: the DoD checks of each phase (Element, live Gemini from p4)
```

### Step 1: For each phase, the five steps, gated

Run the phases **strictly in sequence**: phase N+1 starts only after phase N is **released**. Invoke each
sub-skill through the **Skill tool** and follow its instructions fully.

0. **RECONCILE.** This happens inside `generate-issues` (its Step 0.5). It reads the real code, the
   earlier execution reports and the earlier code-review docs ("Fixes applied", "Architecture impact").
   Where fixes moved the code away from SPEC.md, the code is ground truth.
1. **`generate-issues pN`** writes `specification/implementation/pN-issues.md`.
2. **`upload-issues @specification/implementation/pN-issues.md`** creates the GitHub issues, labels and
   dependency comments, and `pN-github-report.md`, and commits them.
3. **`execute-issues pN::phase`** implements the issues one per commit, runs the gates, gets the owner's
   manual checks, pushes, closes the issues, and writes `pN-execution-report.md`.
4. **`review-and-fix-issues pN`** writes the ranked review doc, fixes only the FIX NOW items (with
   regression tests) and records them in that same doc.
5. **`release-version 0.N.0`** bumps the version, tags `v0.N.0` and pushes.

**Gate the hand-offs:**

- upload only after generate wrote the file;
- execute only after the issues exist;
- review only after execute finished with every issue closed (none failed or `awaiting owner`);
- release only after the review's fix-now items are committed, the gates are green, and the phase's manual
  DoD is confirmed by the owner;
- start the next phase only after this one is released.

**Every phase boundary ends pushed and clean.** Before phase N+1, check that `git status` is clean and
there are no unpushed commits, and `git push` if there are. This skill **stops on failure by design**, so a
stop must never leave a phase's work on one machine only.

### Step 2: REPORT each phase to chat

After each release, report:

- the `AGORA-###` range → GitHub numbers;
- the execution commit range and the gate status;
- the manual checks the owner confirmed;
- the review findings (fixed now / deferred, with homes);
- any "Architecture impact" notes;
- the release tag.

Then continue with the next phase.

### Step 3: END OF RUN — HARDEN (default; `--no-harden` skips it)

Once the last phase in the plan is released, invoke **`harden-findings <first>-<last> --release`** through
the Skill tool, with the run's phase range.

- **What it does:** fixes every still-unfixed 🔴 HIGH / 🟠 MEDIUM finding from the run's review docs, each
  with a regression test, updates the docs in place, and ships a patch release on the latest phase (e.g.
  `v0.5.1`).
- **Held findings:** its escape hatch applies, so a fix that can't land cleanly is held with a reason, not
  forced.
- **With `--no-harden`:** skip it, and list the outstanding HIGH/MEDIUM findings and their homes in the
  summary.

Then give a short **overall summary**: phases shipped, phases skipped as already released, the HARDEN
outcome, anything that stopped early and what remains, and what's next.

## Important Rules

- **Release per phase (`0.N.0`)**, after it is built, reviewed, fix-now-fixed and owner-verified. Never
  batch phases into one release; never release mid-phase.
- **Next phase only after the previous one is released.** This strict order is what makes reconciliation
  meaningful.
- **HARDEN runs once at the end of the run, by default.** Invoking the skill is the consent; `--no-harden`
  is the opt-out.
- **Every phase boundary ends pushed and clean.**
- **Stop on failure; don't paper over it.** A failed sub-skill or a red gate halts the run. Report what
  completed and what remains. Never release a phase whose gates aren't green.
- **Pause for the owner.** Owner-run steps and manual DoD checks are confirmed by the owner, never assumed.
  Don't act on the Ubuntu host or in Element unless asked.
- **Pause for real decisions:** an id or tag collision, an overwrite-or-append prompt, a held HARDEN
  finding, a failure. Routine confirmations run straight through.
- **Delegate, never duplicate.** This skill sequences `generate-issues`, `upload-issues`, `execute-issues`,
  `review-and-fix-issues`, `release-version` and `harden-findings`, and adds gating; it has no logic of its
  own.
- **The plan is phase-ordered and dependency-complete, always.** De-duplicate, fill the earlier phases,
  sort, then drop the released ones. Report the fill, the reordering and the skips.
