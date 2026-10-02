---
name: upload-issues
description: Upload a phase issues file (specification/implementation/pN-issues.md) to GitHub one issue at a time, with pN:: labels and dependency comments, then write and commit pN-github-report.md.
---

# Skill: Upload Phase Issues to GitHub

Upload the issues from one phase issues file to GitHub one at a time, with labels prefixed by the phase and
with dependency links. Then record the `AGORA-###` → GitHub number mapping.

## Usage

```
/upload-issues <phase-issues-file>
```

Example: `/upload-issues @specification/implementation/p3-issues.md`

If the file doesn't exist yet, run `/generate-issues pN` first.

## Instructions

### Step 0: Preconditions

1. `gh auth status`. If it isn't authenticated, tell the user to run `gh auth login` and stop.
2. `git remote -v`. If the repo has no GitHub remote, stop. Tell the user to create one (`gh repo create`)
   or to use the offline flow (`/execute-issues-file pN`). Never create the remote yourself.

### Step 1: Read the issues file

Determine the phase `pN` from the filename or heading. The label prefix is `pN::`.

From the **Issues Summary Table**, parse each issue's ID, Title, Size, Area, Phase and Dependencies. Then
parse each `### AGORA-###` section: Description, What needs to be done, Dependencies, Expected result,
Acceptance criteria.

### Step 2: Confirm with the user

Show the target repository, the number of issues, and the full list of labels. Ask for confirmation.

### Step 3: Create labels (if missing)

Labels have the form `pN::{category}` or `pN::{category}:{value}`. The phase title for the `pN::phase`
description comes from the phase table in `CLAUDE.md`.

```bash
gh label create "p3::phase"  --color "0E8A16" --description "Phase 3 — Echo bot" 2>/dev/null || true
gh label create "p3::size:S" --color "28A745" --description "Small — one function or file" 2>/dev/null || true
gh label create "p3::size:M" --color "FFC107" --description "Medium — a feature across a few files" 2>/dev/null || true
gh label create "p3::size:L" --color "DC3545" --description "Large — a new component or a contract change" 2>/dev/null || true
# one per area used in this phase: agents, server, config, tests, docs, ops
gh label create "p3::area:agents" --color "1D76DB" 2>/dev/null || true
gh label create "p3::area:ops"    --color "D93F0B" --description "Owner performs on the host or in Element" 2>/dev/null || true
```

### Step 4: Create issues one by one

Create the issues **sequentially, one `gh issue create` per issue, never batched**, in summary-table order.
After each one, show the result and move straight on; don't wait for confirmation between issues.

1. **Skip duplicates.** If an issue whose title starts with `AGORA-###:` already exists, skip it and record
   its existing number:
   `gh issue list --state all --search "AGORA-### in:title" --json number,title`.
2. Build the body:

   ```markdown
   ## Description
   {description}

   ## What needs to be done
   {full content}

   ## Dependencies
   {dependency list, with #numbers of already-created issues}

   ## Expected result
   {expected result}

   ## Acceptance criteria
   {checklist, including any **Manual (owner):** items}

   ---
   **ID:** {AGORA-###}
   **Size:** {S/M/L}
   **Phase:** {pN}
   **Area:** {agents/server/config/tests/docs/ops}
   ```

3. Create it:

   ```bash
   gh issue create \
     --title "AGORA-###: {title}" \
     --label "pN::phase,pN::size:{S/M/L},pN::area:{area}" \
     --body "$(cat <<'BODY'
   {issue body}
   BODY
   )"
   ```

4. Record the mapping `AGORA-###` → `#number` and report `Created AGORA-### -> #{number}: {title}`.
5. For each dependency that is already created, comment:
   `gh issue comment {number} --body "Blocked by #{dep-number} (AGORA-###)"`.

### Step 5: Write and commit the report

Write `specification/implementation/pN-github-report.md`:

```markdown
# Phase pN — GitHub Issues Report

**Uploaded:** {date}
**Repository:** {repo URL}
**Total issues:** {count} ({created} created, {skipped} already existed)

## Issue Mapping

| AGORA ID | GitHub # | Title | Phase | Labels | URL |
|----------|----------|-------|-------|--------|-----|
| AGORA-001 | #5 | ... | p3 | p3::phase, p3::size:S, p3::area:agents | {url} |

## Labels Created

- pN::phase
- pN::size:S, pN::size:M, pN::size:L
- pN::area:{list}
```

Commit the issues file (if it isn't committed yet) together with the report as
`docs: upload pN issues to GitHub`, with the running model's `Co-Authored-By` trailer, and push.
`/execute-issues` needs a clean tree and reads this mapping.

### Step 6: Report to the user

Report the number of issues created and skipped, a link to the repository's issues page, and the report
path. Suggest `/execute-issues pN::phase`.

## Error Handling

- **`gh` unauthenticated:** tell the user to run `gh auth login`.
- **No remote:** tell the user to run `gh repo create`, or to use `/execute-issues-file`.
- **Issue with the same `AGORA-###` already exists:** skip it and note it in the report.
- **Label creation fails:** continue; the labels may already exist.
- **Any other failure:** report what was created so far and what remains, and still write the report for
  the created issues.
