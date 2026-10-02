---
name: execute-issues-file
description: Execute one phase's issues straight from its local specification/implementation/pN-issues.md (no GitHub). Implement -> gates -> owner confirmation for manual checks -> commit -> push (if a remote exists) for each issue in dependency order, then write pN-execution-report.md. The offline counterpart of execute-issues.
---

# Skill: Execute Issues From File

Execute one phase's issues **straight from its issues file**, `specification/implementation/pN-issues.md`,
with **no GitHub involvement**: no issue lookup and no closing. Each issue is implemented, validated,
committed and pushed in dependency order, and the run ends with an execution report.

This is the offline counterpart of `/execute-issues`. The discipline is the same; only the issue list comes
from the markdown file instead of `gh issue list`.

## Usage

```
/execute-issues-file <pN | path-to-issues-file> [--issue AGORA-###] [--dry-run]
```

- `/execute-issues-file p3` → executes `specification/implementation/p3-issues.md`.
- `/execute-issues-file @specification/implementation/p4-issues.md`.
- `--issue AGORA-###`: only that issue. Its file-listed dependencies must already be committed.
- `--dry-run`: print the execution plan without changing anything.

## Instructions

### Step 0: Verify prerequisites and read the file

1. **Branch and tree:** note the current branch and check `git status`.
   - If the only uncommitted file is this phase's issues file, commit it first (`docs: add pN issues`).
   - Any other uncommitted change: stop and ask.
2. **Remote:** check `git remote -v`. Without a remote, the run commits but doesn't push; say so up front.
3. **Read the issues file:** resolve the target to `specification/implementation/pN-issues.md` and read the
   summary table, the Dependency Tree and every `### AGORA-###` section. **No `gh` is used.**
4. **Read the spec:** [specification/SPEC.md](../../../specification/SPEC.md) §{N+2} (tasks and DoD), §8 and
   §9, plus `CLAUDE.md` (invariants, contracts, acceptance gates).
5. **Green baseline:** run the automated gates that apply, so a later failure can be attributed.

### Step 1: Build the execution queue from the file

- **Order:** parse the ids and titles from the summary table and order them by the Dependency Tree.
- **Skip what's done:** an issue whose id already appears in a commit subject (`git log --grep "^AGORA-###:"`)
  is done; skip it. This is what makes the run resumable.
- **`--issue`:** execute only that issue, after checking that its dependencies are committed.

Show the ordered plan and proceed. With `--dry-run`, stop here.

### Step 2: Execute each issue, in dependency order

1. **Announce:** `--- Starting AGORA-###: {title} ---`.
2. **Read** its section: what needs to be done and the acceptance criteria.
3. **Implement** per `CLAUDE.md` and SPEC.md, routed by component. The routing is the same as
   `/execute-issues` Step 2c:
   - `agents/agent.py` holds session, invites, first-sync, filter, history, Gemini and turn-taking, with the
     decisions kept as pure functions.
   - `server/docker-compose.yml`'s environment is a contract.
   - `ops` issues produce their repo artifacts plus a numbered checklist for the owner. Don't act on the
     host or in Element unless the owner asks.
   - A **contract change** updates SPEC.md, SPEC-UA.md, CLAUDE.md and its pinning test in the same commit.
4. **Validate:**
   - `uv run ruff check .` clean and `uv run pytest` green, with nio and Gemini mocked.
   - The compose gate when `server/` changed.
   - For **Manual (owner)** criteria, run the read-only `curl` checks yourself and ask the owner to perform
     and confirm the rest.
   - Record each result as pass / fail / n/a, and each manual check as `confirmed by owner` /
     `pending owner`.
5. **Commit** (one issue = one commit, only when the gates are green):

   ```bash
   git commit -m "$(cat <<'EOF'
   AGORA-###: {title}

   {1-2 sentence summary of what was implemented}

   Co-Authored-By: <the running model's trailer> <noreply@anthropic.com>
   EOF
   )"
   ```

   There is no `Closes #…` line, since there is no GitHub issue. An `ops` issue with no repo artifact has no
   commit; it is done once the owner confirms.
6. **Push:** `git push` if a remote exists.
7. **Log** the id and title, commit, files, gate results, manual checks and status (`completed` /
   `awaiting owner` / `failed` / `skipped`).

An issue whose code is committed but whose owner checks are pending is `awaiting owner`. Continue with
issues that don't depend on it.

### Step 3: Handle failures

On a failed implementation or a red gate:

1. Don't commit.
2. Revert tracked changes with `git checkout -- .` and delete **by name** the new files this issue created.
   Never `git clean`.
3. Log the failure.
4. Ask whether to continue with the next independent issue or stop.

### Step 3b: No automatic version bump

Never touch `VERSION`, `RELEASE.txt`, `pyproject.toml`'s version or tags here; that is `/release-version`.
A phase with failed, skipped or `awaiting owner` issues is not releasable.

### Step 4: Write the execution report

Write `specification/implementation/pN-execution-report.md` with the same structure as `/execute-issues`
Step 4:

- a status summary table;
- a per-issue table (AGORA id · title · status · commit · files · gates · manual);
- detailed results;
- next steps.

There is no GitHub column. Commit it (`docs: pN execution report`, with the trailer) and push if a remote
exists.

## Important Rules

- **File-driven, no GitHub.** The issue list, details and order come from `pN-issues.md`. Never run
  `gh issue list`/`create`/`close`, and never write `pN-github-report.md`.
- **One issue = one commit**, one issue at a time, in dependency order.
- **No broken code.** Commit only when lint and tests are green, and compose too when `server/` changed.
- **Tests ship with the feature**, with nio and Gemini mocked. No test or gate calls the network or a paid
  API.
- **Manual checks need the owner.** Never report one as passed on your own.
- **Contracts stay stable**: SPEC.md, SPEC-UA.md, CLAUDE.md and the pinning test change together.
- **Secrets stay out.** Never print `.env`, `server/.env`, `state/*.json` or `server_con.yaml`; no secrets
  in argv, logs or commits; no message texts in logs.
- **Ask on ambiguity.** If an issue's scope is unclear, ask rather than guess.
- **Progress updates.** Print a short status line after each issue.
