---
name: execute-issues
description: Execute one phase's GitHub issues (label pN::phase) sequentially in dependency order - implement, run the acceptance gates, get owner confirmation for manual DoD checks, commit, push, close - then write pN-execution-report.md.
---

# Skill: Execute GitHub Issues

Execute one phase's GitHub issues sequentially. For each one: implement, validate, commit, push and close.
Then write an execution report.

## Usage

```
/execute-issues <label|phase> [--issue AGORA-###] [--dry-run]
```

The label is the phase label exactly as it appears on GitHub (`p3::phase`). A bare `p3` also works.

- `/execute-issues p3::phase`: execute every open issue of phase 3.
- `/execute-issues p3::phase --issue AGORA-007`: one issue (its dependencies must already be closed).
- `/execute-issues p3::phase --dry-run`: show the execution plan without changing anything.

## Instructions

### Step 0: Verify prerequisites

1. **Branch:** note the current branch.
2. **Clean tree:** run `git status`. If the only uncommitted files are this phase's issues file or GitHub
   report under `specification/implementation/`, commit them first (`docs: add pN issues`). Any other
   uncommitted change: stop and ask.
3. **GitHub:** `gh` is authenticated and the repo has a remote.
4. **Fetch the open issues:** `gh issue list --label "pN::phase" --state open --limit 100`.
5. **Read the phase files:** the issues file `specification/implementation/pN-issues.md`, and
   `pN-github-report.md` for the `AGORA-###` → `#number` mapping.
6. **Read the spec:** [specification/SPEC.md](../../../specification/SPEC.md) §{N+2} (the phase's tasks and
   DoD), §11 (security) and §12 (out of scope), plus `CLAUDE.md`: invariants, contracts and gates.
7. **Green baseline:** run the automated gates that apply (see `CLAUDE.md` **Acceptance gates**), so a
   later failure can be attributed. Never start on a red suite.

### Step 1: Build the execution queue

- **Order:** parse `AGORA-###` ids from the issue titles (`AGORA-###: {title}`) and order them by the issues
  file's Dependency Tree. Issues with no unmet dependency go first.
- **Resuming:** closed issues are already excluded (`--state open`), so a re-run resumes where the last one
  stopped.
- **`--issue`:** execute only that issue, after checking that its dependencies are closed.

Show the plan and ask for confirmation. With `--dry-run`, stop here.

### Step 2: Execute each issue (loop)

#### 2a. Announce

Print `--- Starting AGORA-###: {title} ---`.

#### 2b. Read the issue

Read its detailed section in the issues file: what needs to be done and the acceptance criteria.

#### 2c. Implement

Follow `CLAUDE.md` and SPEC.md. Route by component:

- **`agents/agent.py`:** one codebase for both agents; the TOML picks the account and persona. Its
  pieces are:
  - config loading (TOML + `.env` via python-dotenv);
  - the session: password login once → `state/<name>.json`, restored after that;
  - invite handling (`OWNER` into `ROOM_ID` only);
  - startup: the first sync only for `next_batch`, then `sync_forever`;
  - the message filter and allowlist;
  - the `HISTORY_N` history buffer;
  - the Gemini call, typing, and sending as `m.text`;
  - turn-taking (p5);
  - canon loading and session memory (p6), place / calendar / time and day memories (p7), usage accounting
    (p8). See CLAUDE.md **Canon, memory, world and tokens**.
- **Pure decisions:** keep the filter, mention detection, `bot_streak`, who-replies, transcript and prompt
  assembly, the session-end decision, calendar formatting, the missing-days calculation and usage aggregation
  as functions over plain data, with the clock injected. That way tests need no nio objects, and the nio callbacks stay thin
  adapters.
- **Gemini** (`google-genai`, from p4): `client.aio.models.generate_content` with `gemini-2.5-flash`, the
  persona (canon from p6) as `system_instruction`, `max_output_tokens=400` and `thinking_budget=0`. On failure or empty
  text: log, send nothing, keep running.
- **`server/docker-compose.yml`:** its environment is a contract. `CONTINUWUITY_SERVER_NAME` never changes.
  Registration closes in p2 and stays closed.
- **Owner-run work (`ops` issues):**
  - Write any repo artifact the issue names.
  - Print the owner's steps as a numbered checklist, using the exact commands from SPEC.md.
  - Don't act on the Ubuntu host, in Element, or on accounts and rooms unless the owner asks in this session.
- **Contract changes** (the CLAUDE.md **Contracts** list) update SPEC.md, SPEC-UA.md, CLAUDE.md and the
  test that pins the contract, in the same commit.
- **Scope:** stay inside the phase and outside SPEC.md §12. Follow the existing style.

#### 2d. Validate

1. **Lint:** `uv run ruff check .` must be clean.
2. **Tests:** `uv run pytest` must exit 0. Every code issue adds or extends tests. Mock `matrix-nio` and
   `google-genai`; no test touches the network.
3. **Compose:** when `server/` changed, run
   `REGISTRATION_TOKEN=dummy docker compose -f server/docker-compose.yml config -q`. Keep `-q`.
4. **Manual (owner) criteria:**
   - **Your share:** run the read-only `curl` checks yourself if the homeserver is reachable.
   - **The owner's share:** for the rest, print a numbered checklist and ask the owner to perform and
     confirm it.
   - **Live Gemini runs** happen only when the owner asks.
   - **Recording:** record each item as `confirmed by owner` or `pending owner`, never as `pass` on your own.
5. **Acceptance criteria:** walk each criterion against the phase DoD in SPEC.md.

Gates that don't apply yet (there is no `pyproject.toml` before p3) are recorded as `n/a`. Never commit on
a red gate.

#### 2e. Commit

```bash
git add {specific files created or modified}
git commit -m "$(cat <<'EOF'
AGORA-###: {title}

{1-2 sentence summary of what was implemented}

Closes #{github-issue-number}

Co-Authored-By: <the running model's trailer> <noreply@anthropic.com>
EOF
)"
```

- **Manual checks still pending:** write `Refs #N` instead of `Closes #N`, so that pushing doesn't close an
  issue the owner hasn't verified.
- **`ops` issue with no repo artifact:** it has no commit; go straight to 2g once the owner confirms.

#### 2f. Push

`git push`.

#### 2g. Close or hold the issue

- **All criteria met:** close the issue with a summary.

  ```bash
  gh issue close {number} --comment "$(cat <<'EOF'
  ## Implementation Summary

  **Commit:** {hash or "none (owner steps only)"}
  **Files changed:** {count}

  ### What was done
  {bullets}

  ### Validation
  {lint / tests / compose: pass, fail or n/a; manual: confirmed by owner}

  ### Acceptance criteria
  {checklist}
  EOF
  )"
  ```

- **Owner checks still pending:** leave the issue open. Comment with the pending checklist, mark it
  `awaiting owner` in the log, and continue with issues that don't depend on it.

#### 2h. Log progress

Add to the execution log: the issue id and title, commit, files, gate results, manual checks, and status
(`completed` / `awaiting owner` / `failed` / `skipped`).

### Step 3: Handle failures

If implementation or validation fails:

1. Do not commit broken code.
2. Revert: `git checkout -- .` for tracked files, and delete **by name** the new files this issue created.
   Never `git clean`.
3. Comment on the GitHub issue explaining what failed.
4. Log the failure.
5. Ask the user whether to continue with the next issue (if nothing depends on the failed one) or stop.

### Step 3b: No automatic version bump

Never change `VERSION`, `RELEASE.txt`, `pyproject.toml`'s version or tags here. That is `/release-version`,
on explicit confirmation. A phase with failed, skipped or `awaiting owner` issues is **not** releasable;
say so in the report.

### Step 4: Write the execution report

Write `specification/implementation/pN-execution-report.md`:

```markdown
# Phase pN — Execution Report

**Date:** {date}
**Branch:** {branch}
**Label:** pN::phase
**Target release:** v0.N.0
**Executed by:** Claude Code

## Summary

| Status | Count |
|--------|-------|
| Completed | {n} |
| Awaiting owner | {n} |
| Failed | {n} |
| Skipped | {n} |
| Remaining | {n} |

## Issues

| # | AGORA ID | Title | Status | Commit | Files | Gates | Manual |
|---|----------|-------|--------|--------|-------|-------|--------|
| 1 | AGORA-001 | ... | completed | a1b2c3d | 4 | lint ✓ tests ✓ compose n/a | confirmed |

## Detailed Results

### AGORA-001: ...
**Status:** completed · **Commit:** a1b2c3d · **GitHub:** #5
**Gates:** [x] lint · [x] tests · [ ] compose (n/a)
**Manual (owner):** {each check: confirmed by owner / pending owner}

## Next Steps
{remaining or awaiting-owner issues, their dependencies, and whether the phase is releasable}
```

Commit the report (`docs: pN execution report`, with the trailer) and push.

## Important Rules

- **One issue at a time**, in dependency order. Never start an issue whose dependencies aren't closed.
- **One issue = one commit.** Never mix work across ids.
- **No broken code.** Commit only when the gates that apply are green.
- **Tests ship with the feature.** nio and Gemini are mocked, and no test or gate calls the network or a
  paid API. Live Gemini runs are opt-in, by the owner.
- **Manual checks need the owner.** Never report a manual DoD check as passed without the owner's
  confirmation, and never `Closes #N` an issue with pending owner checks.
- **Contracts stay stable.** A contract change updates SPEC.md, SPEC-UA.md, CLAUDE.md and its pinning test
  in the same commit.
- **Security invariants:**
  - The allowlist (`ROOM_ID` + `{OWNER, other agent}`) guards every reply path.
  - Registration stays closed after p2.
  - Port 8008 is never exposed beyond the LAN.
- **Secrets stay out:**
  - Never print `.env`, `server/.env`, `server_con.yaml` or anything under `state/` (tokens, summaries, day
    memories). To check that a value is set,
    test it without echoing it (`grep -q '^GEMINI_API_KEY=.' .env`).
  - Passwords, tokens and the API key never go into argv, logs, commits or issue comments.
  - Message, summary and memory texts are never logged.
  - The agents believe they are human: no code path or prompt says an agent is a model or a bot.
- **Ask on ambiguity.** If an issue is unclear, ask rather than guess.
- **Progress updates.** Print a short status line after each issue.
