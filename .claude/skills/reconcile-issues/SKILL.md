---
name: reconcile-issues
description: Review one phase's already-generated specification/implementation/vA.B-issues.md against the REAL current implementation (and the live setup, read-only) and correct any issue that has drifted - stale file names, changed signatures, evolved contracts, or work already done. Edits the file in place with a visible "Reconciled" mark. Corrects issues only; never implements code or changes the version.
---

# Skill: Reconcile Issues

`/generate-issues` grounds new issues in the real implementation (its Step 0.5). This skill does the same
for a **pre-generated** issues file. It reads `specification/implementation/vA.B-issues.md`, compares each
issue's assumptions with the **actual current code**, and **corrects the issues that drifted, in the file,
with a visible change-mark**, so the record shows the original issue was modified.

It only **corrects the issues**: it never implements code, never touches the version and never uses GitHub.
Run it right before `/execute-issues-file`.

## Usage

```
/reconcile-issues <vA.B | path-to-issues-file>
```

- `/reconcile-issues v1.1` → reconciles `specification/implementation/v1.1-issues.md`

## Instructions

### Step 0: Read the issues and the real implementation

1. **The issues file:** resolve the target to `specification/implementation/vA.B-issues.md` and read all of it:
   the summary table, the dependency tree and every `### AGORA-###` section.
2. **The code:** read the **real current code** the issues touch: `agents/`, `panel/`, `tests/`, `server/`,
   `pyproject.toml`, `.env.example` and the agent TOML files. Note the actual module and function names,
   signatures, config keys, env var names and dependencies.
3. **Earlier records:** read the earlier phases' `specification/implementation/*-execution-report.md` and
   `*code-review*.md`, especially **"Fixes applied"** and **"Architecture impact"**.
4. **The spec:** read [specification/ROADMAP.md](../../../specification/ROADMAP.md) §vA.B (the DoD),
   [specification/ARCHITECTURE.md](../../../specification/ARCHITECTURE.md) (contracts) and `CLAUDE.md`.
5. **Owner-run work:** check the live state read-only where possible (e.g.
   `curl -s http://192.168.1.197:8008/_matrix/client/versions`). If an owner step may already be done, ask
   the owner.

### Step 1: Find the drift

Compare each issue's **assumptions** with reality:

- **Paths:** wrong or renamed files and modules (e.g. an issue naming `agents/bot.py` when the code has
  `agents/agent.py`).
- **Names and signatures** that changed: functions, config keys (e.g. `HISTORY_N` read from TOML vs `.env`),
  the session file fields, nio callback names, the `google-genai` call shape.
- **Contracts** that a landed fix moved past the spec: the filter, the transcript format, `bot_streak`
  semantics, the compose environment.
- **Work already done:** the deliverable was already shipped by an earlier fix or phase, or an owner step
  was already performed on the host or in Element.
- **The code is ground truth** where it disagrees with the issue text or a stale spec.

### Step 2: Correct the issues in place, with a visible mark

For each issue that drifted, edit its section in `vA.B-issues.md`:

1. **Fix the details** (Description, What needs to be done, Acceptance criteria) so they match the real
   implementation. Keep the **AGORA id and the intent**; correct only what drifted.
2. **Add a change-mark** as a blockquote directly under the issue heading:
   > **⟳ Reconciled (<today>):** originally referenced `agents/bot.py` and a `history` TOML key; corrected
   > to the shipped `agents/agent.py` reading `HISTORY_N` from `.env`. Reason: matches the real
   > implementation.
3. **Moot issues** (already delivered) stay in the file with a clear mark:
   > **⟳ Reconciled (<today>):** already satisfied by `<commit / release / owner step>`; execution is
   > verification-only (add or confirm the test, or re-run the DoD check; no new production code).
4. Use today's date. Never rewrite silently; every change is stamped.

### Step 3: If nothing drifted

Leave issues that match reality untouched. If **no** issue needed a correction, add one note under the
file's intro and stop:
`> **⟳ Reconciled (<today>): no drift found — issues match the current implementation.**`

### Step 4: Record

Commit the corrected file (`docs: reconcile vA.B issues against the implementation`, with the running model's
`Co-Authored-By` trailer) and push if a remote exists. Report which issues were corrected and why, which
were marked moot, and which were untouched.

## Important Rules

- **Correct issues only.** Never implement code, change the version or use GitHub. That is
  `/execute-issues-file` and `/release-version`.
- **The real code is ground truth** where it disagrees with the issue or a stale spec.
- **Every change is marked.** Keep the AGORA id and intent, and add a dated `⟳ Reconciled` blockquote.
- **No churn.** Don't touch issues that already match reality.
- **Ask on genuine ambiguity.** If it's unclear whether the issue or the code is right, raise it with the
  user rather than guessing.
