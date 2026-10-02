---
name: ship-solution
description: Ship the solution end-to-end from already-generated issues files, offline (no GitHub). Takes one selector or a comma-separated LIST of phases/ranges (default - every phase with an issues file); missing earlier phases are added automatically, the set is sorted into phase order, and released phases are skipped. Per phase - reconcile-issues, execute-issues-file, review-and-fix-issues, release-version 0.N.0, each phase timed. HARDEN once at the end by default (--no-harden to skip). Ends with a detailed execution report with per-phase and total statistics and timings.
---

# Skill: Ship Solution

Build the solution **from the already-generated issues files**, with no issue generation and no GitHub.
Walk the phases in order. For each phase:

1. Reconcile the pre-written issues against reality.
2. Execute them from the file.
3. Review and fix.
4. Release, **timing the whole phase**.

Then harden once at the end, and **write a detailed execution report** with statistics and timings **by
phase and in total**.

This is the offline sibling of `/ship-phase`. The differences, step by step:

| ship-phase step | here |
|---|---|
| 0. reconcile (inside generate) | **`reconcile-issues`**: correct the *pre-generated* issues file in place, with a `⟳ Reconciled` mark |
| 1. generate-issues | **skipped**: the `pN-issues.md` files must already exist. A required phase without one is a hard stop (Step 0.4) |
| 2. upload-issues | **skipped**: no GitHub |
| 3. execute-issues | **`execute-issues-file`**: implement straight from the file |
| 4. review-and-fix-issues | **kept** |
| 5. release-version | **kept** |
| end-of-run HARDEN | **same**: by default, `--no-harden` to skip |
| per-phase chat report | **replaced** by one report file at the end |

It works with or without a git remote. Without one, everything is committed and tagged locally, and the
report says nothing was pushed.

> **This pipeline releases.** Invoking `/ship-solution` opts into the automated per-phase releases (real
> tags, plus pushes when a remote exists) **and** the HARDEN sweep. To build without releasing, use the
> individual skills.

## Usage

```
/ship-solution [<selector>[,<selector>…]] [--no-harden]
```

A **selector** is a phase (`p3` or `3`) or a range (`p3-p5`). Omit it to ship every phase that has an
issues file.

- `/ship-solution`: ship every phase with a `specification/implementation/pN-issues.md`.
- `/ship-solution p4`: phase 4 and any unreleased earlier phases.
- `/ship-solution p3-p5 --no-harden`: phases 3–5, with no HARDEN sweep.

## Instructions

### Step 0: Scope, baseline, plan, and start the clock

1. **Parse the selector list.** Split on commas and trim. With no argument, take every phase that has an
   issues file. Record whether `--no-harden` was passed. If an element doesn't resolve to a phase in 0–9,
   **name it and ask**; never drop it.
2. **Expand and de-duplicate** the elements into a set of phases.
3. **Fill the dependencies.** Add every earlier phase below the highest selected one. Report what was added,
   but don't ask permission; those phases are requirements.
4. **Resolve each phase**, in this order:
   - **Released** (tag `v0.N.0` exists): **skip** it; the dependency is satisfied.
   - **Not released, has `pN-issues.md`:** **include** it.
   - **Not released, no issues file:** **STOP.** This skill cannot generate one. Name every such phase and
     offer the two options: run `/generate-issues pN` for each (or write the files), or use `/ship-phase`,
     which generates them. **Never silently drop the phase and continue.**

   A partly done phase (issues or report exist, but no tag) resumes from its remaining steps. The
   sub-skills are idempotent.
5. **Sort into phase order.** If the order differs from what was typed, say so.
6. **Clean tree and baseline.** Check the tree is clean. Run the automated gates, which must be green (or
   `n/a` before p3), and **record the baseline test count** as the "before" for the statistics.
7. **Start the run clock:** `RUN_START=$(date +%s)`. Append each phase's row to `.ship-solution-progress.md`
   in the repo root as it finishes. The file is gitignored, so a long run never loses a measurement.
8. **Size the work.** Count the issues per phase from each file's summary table, with their sizes
   (S=1, M=3, L=5 points). Note how many are `ops` issues that will need the owner.
9. **Confirm the plan once.** Show:
   - the ordered phases;
   - the filled-in phases, any reordering and the skips;
   - the sizing;
   - the expected owner pauses (p0–p2 are mostly owner steps, and every phase's DoD has manual checks);
   - whether HARDEN runs.

   Then run. Don't re-confirm each sub-step.

### Step 1: For each phase, timed and gated

Run the phases **strictly in sequence**: phase N+1 starts only after phase N is **released**. Invoke each
sub-skill through the **Skill tool**.

Stamp `P_START=$(date +%s)` before the phase starts. Then:

1. **`reconcile-issues pN`** corrects the pre-generated issues in place with dated `⟳ Reconciled` marks,
   and commits the file.
2. **`execute-issues-file pN`** implements each issue in dependency order. Each issue gets the gates, the
   owner's manual checks, one commit and a push when a remote exists. It ends by writing
   `pN-execution-report.md`.
3. **`review-and-fix-issues pN`** writes the ranked review doc and the fix-now fixes, recorded in that doc.
4. **`release-version 0.N.0`** bumps the version and tags `v0.N.0`, pushing when a remote exists.

Stamp `P_END=$(date +%s)` after the release, and record the phase's row:

- **duration:** `P_END − P_START`, as mm:ss;
- **reconcile:** issues corrected / moot / untouched;
- **execute:** issues implemented, commit range, **tests before → after**, owner checks confirmed;
- **review:** findings fixed now / deferred, by severity;
- **release tag.**

**Gate the hand-offs:** reconcile → execute → review → release.

- Release only after the fix-now items are committed, the gates are green, and the owner has confirmed the
  manual DoD.
- Start the next phase only after this one is released.
- Don't report to chat between phases.

**Every phase boundary ends clean** (and pushed, when a remote exists). This skill stops on failure, and a
stop must never strand a phase's work.

### Step 2: END OF RUN — HARDEN (default; `--no-harden` skips it)

After the last phase is released, invoke **`harden-findings <first>-<last> --release`**.

- **What it does:** fixes every still-unfixed 🔴 HIGH / 🟠 MEDIUM finding from the run's review docs (with
  regression tests), updates them in place, and ships a patch release on the latest phase. LOW stays
  deferred, and the escape hatch still applies.
- **Timing:** time the sweep as its own row.
- **With `--no-harden`:** record the sweep as skipped, with the outstanding HIGH/MEDIUM findings and their
  homes.

### Step 3: Write the final execution report

After the whole scope, **or when the run stops**, stamp `RUN_END=$(date +%s)` and write
`specification/implementation/ship-solution-report.md`. Commit it (push if a remote exists) and print its
summary to chat.

```markdown
# Ship-Solution Execution Report — <date>

## Total
- Wall-clock: <Hh Mm Ss>  (RUN_END − RUN_START)
- Phases: <n> · Issues executed: <k> · Commits: <c> · Owner checks confirmed: <m>
- Releases: <all v0.N.P tags>
- Findings: fix-now fixed <a> · hardened HIGH/MEDIUM <b> · LOW deferred <c> · held <d>
- Reconcile: issues corrected <x> · moot <y> · untouched <z>
- Tests: <baseline> → <final> passing · lint clean · zero network or paid calls in the gates
- Pushed: yes / no (no remote)

## By phase
| Phase | Duration | Issues | Commits | Tests (before→after) | Reconcile (corr/moot/kept) | Review (fixed/deferred) | Owner checks | Release tag |
|-------|----------|--------|---------|----------------------|----------------------------|-------------------------|--------------|-------------|
| p3    | mm:ss    | …      | …       | … → …                | …                          | …                       | …            | v0.3.0      |

## HARDEN
- Duration, findings fixed (with commits), held (with reasons), patch tag — or "skipped (--no-harden)" with the outstanding findings.

## Timings
- Fastest / slowest phase; average per phase; time spent waiting on the owner, where it can be told apart.

## Notes
- Anything held by an escape hatch, anything that stopped early (and what remains), reconcile highlights.
```

Work out durations from the epoch stamps. Every number must trace back to the run: the execution reports,
review docs and release tags.

## Important Rules

- **File-driven, no GitHub.** Issues come from `specification/implementation/pN-issues.md`. A required
  phase with **no issues file** is a hard stop, never a silent skip.
- **Reconcile, don't regenerate.** Correct the pre-generated issues in place, with `⟳ Reconciled` marks.
- **Time every phase**, and persist the rows as you go.
- **Release per phase** (`0.N.0`), after fix-now fixes and owner verification. Next phase only after the
  previous one is released. Never batch phases.
- **The plan is phase-ordered and dependency-complete.** De-duplicate, fill the earlier phases, sort, drop
  the released ones. Report the fill, the reordering and the skips.
- **HARDEN once at the end, by default.** `--no-harden` opts out, and the outstanding findings are then
  recorded as outstanding.
- **One report, at the end**, plus its chat summary. It is written even when the run stops early, covering
  what shipped.
- **Sequential and gated; stop on failure.** Never release a phase with a red gate or unconfirmed owner
  checks.
- **Pause for the owner and for real decisions:** a missing issues file, an unresolvable selector, a tag
  collision, a held finding, an ambiguous reconcile, any failure.
- **Delegate, never duplicate.** This skill sequences the sub-skills, gates, times and reports. Each
  sub-skill keeps its own discipline.
