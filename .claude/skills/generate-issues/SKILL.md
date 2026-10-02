---
name: generate-issues
description: Decompose one SPEC.md phase (p0–p9) into a dependency-ordered issues file at specification/implementation/pN-issues.md, grounded in the real current code. The output feeds /upload-issues (GitHub flow) or /execute-issues-file (offline flow).
---

# Skill: Generate Phase Issues

Decompose one SPEC.md **phase** (`p0`–`p9`) into a small, dependency-ordered **issues file** at
`specification/implementation/pN-issues.md`. The file is the input to `/upload-issues` → `/execute-issues`
(GitHub flow), or straight to `/execute-issues-file` (offline flow).

## Usage

```
/generate-issues <phase>
```

- `/generate-issues 3` or `/generate-issues p3`: SPEC.md phase 3 (echo bot) → `specification/implementation/p3-issues.md`

One file per phase. Issue ids (`AGORA-###`) are **globally sequential** across phase files **and across
regeneration runs**. Never reset them.

## Instructions

### Step 0: Read inputs

1. Normalize the argument to `pN`, with N in 0–9. For anything else, name it and ask.
2. Read the phase's section of [specification/SPEC.md](../../../specification/SPEC.md). The section number is
   **N + 2**: phase 3 is §5 (see the phase table in `CLAUDE.md`). Take its **Tasks**, **Behavior** and **Project
   structure** where present, and its **DoD**. `specification/SPEC-UA.md` is the Ukrainian original of the
   same file; read it only to check a translation.
3. Read SPEC.md §1 (architecture) and §12 (security). The scope fence is the phase itself: never pull a
   later phase's work in early, and never add what no phase asks for.
4. Read `CLAUDE.md`: the agent invariants, the turn-taking rules, the **Contracts** list and the
   **Acceptance gates**.
5. **Find the next free `AGORA-###` id. Never restart the numbering.** Check both sources and continue
   from the higher:

   ```bash
   # (a) GitHub: survives a wiped working tree (skip if the repo has no remote)
   gh issue list --state all --limit 1000 --json title \
     --jq '.[].title | capture("AGORA-(?<n>[0-9]+)").n' 2>/dev/null | sort -n | tail -1

   # (b) local issues files: covers ids drafted but not uploaded
   grep -rhoE 'AGORA-[0-9]+' --include='*-issues.md' specification/implementation/ 2>/dev/null \
     | grep -oE '[0-9]+' | sed 's/^0*//' | sort -n | tail -1
   ```

   Pass the directory with `--include`, not a `*-issues.md` glob. Under zsh an unmatched glob aborts the
   command before `2>/dev/null` applies, and `specification/implementation/` may not exist yet.

   The next id is `max(a, b) + 1`, zero-padded to three digits. Start at `AGORA-001` only if both sources
   come back empty. Say in the report which sources were checked: with no remote, or with `gh`
   unauthenticated, (b) alone governs.
6. If `specification/implementation/pN-issues.md` already exists, ask whether to overwrite or append.

### Step 0.5: Reconcile with the real implementation

Ground the phase in what was actually built and fixed, not only in what SPEC.md describes. Review fixes and
hardening in earlier phases may have moved the code away from the spec.

1. Read the **real current code** this phase builds on: `agents/`, `tests/`, `server/`, `pyproject.toml`,
   `.env.example` and the agent TOML files. Note the actual module and function names, signatures, config
   keys and env var names.
2. Read the earlier phases' `specification/implementation/p*-execution-report.md` and `*code-review*.md`,
   especially their **"Fixes applied"** and **"Architecture impact"** notes.
3. Where SPEC.md is stale relative to a landed fix, the **code is ground truth** for this phase's issues.
   Note the drift, and put the SPEC.md / SPEC-UA.md / CLAUDE.md correction into the issue that touches that
   contract.
4. For owner-run tasks (the Ubuntu host, Element, accounts, the room), check what can be checked read-only,
   e.g. `curl -s http://192.168.1.197:8008/_matrix/client/versions`, and ask the owner about the rest. A
   task that is already done becomes a verification-only issue, not new work.

### Step 1: Decompose the phase

Turn the phase's tasks into a small set of issues, typically **2–5**. An owner-only phase such as p1 may be
a single issue. Don't pad. Each issue is a coherent, independently verifiable slice:

- **Size** by complexity:
  - **S:** one function or file.
  - **M:** a feature across a few files.
  - **L:** a new component or a contract change.
- **Area**, one of:
  - `agents`: `agents/`.
  - `server`: `server/`.
  - `config`: `pyproject.toml`, `.env.example`, `.gitignore`.
  - `tests`.
  - `docs`: SPEC.md, README.md, CLAUDE.md.
  - `ops`: steps the owner performs on the Ubuntu host or in Element.
- **Order by dependency.** The first issue is usually the gate that everything builds on. In p3 that is the
  project skeleton plus config loading and the session login; in p5 it is the pure turn-taking module.
- **Tests in every code issue.** Keep decision logic pure so it can be unit-tested with plain data: the
  message filter, mention detection, `bot_streak`, who replies, building the transcript. `matrix-nio` and
  `google-genai` are mocked, and no test touches the network.
- **Manual DoD checks** from SPEC.md go into the acceptance criteria as **Manual (owner):** items. The
  executor cannot pass them on its own.
- **Contract changes:** a change to anything in the CLAUDE.md **Contracts** list carries the SPEC.md,
  SPEC-UA.md and CLAUDE.md updates and the test that pins it, in the **same** issue.
- **Owner-run (`ops`) issues:**
  - List the exact commands from SPEC.md.
  - Mark which checks Claude can run read-only from the Mac.
  - Name any repo artifact the issue produces (e.g. `server/.env.example`).
- **Stay within the phase.** No Gemini in p3, no turn-taking rules in p4 beyond what §6 asks for, nothing
  that no phase asks for.

### Step 2: Write the issues file

Write `specification/implementation/pN-issues.md` in English. Use **exactly** this format:

````markdown
# pN — Issues

Issues for phase **pN — {title}**, derived from [SPEC.md](../SPEC.md) §{N+2} and the contracts in
[CLAUDE.md](../../CLAUDE.md). This file covers one phase; ids continue from the previous phase
(AGORA-{prev} → **AGORA-{first}…{last}**).

{1–3 sentences: what the phase delivers, what it builds on, what it leaves for later phases.}

## Issues Summary Table

| # | ID | Title | Size | Area | Phase | Dependencies |
|---|----|-------|------|------|-------|--------------|
| 1 | AGORA-{first} | {title} | M | agents | pN | -- |
| 2 | AGORA-{…} | {title} | S | tests | pN | AGORA-{first} |

**Size legend:** S = one function or file · M = a feature across a few files · L = a new component or a contract change

---

## Dependency Tree

```
AGORA-{first} ({gate})
  |
  +-- AGORA-{…} (…)
  |
  +-- AGORA-{…} (…)  => {phase DoD}
```

**Parallelization hints:** {what must go first; what is independent}.

---

## pN — {title}

### AGORA-{id} — {Title}

**Description:**
{1–3 sentences; name the files it touches.}

**What needs to be done:**
- {bullet}

**Dependencies:** {AGORA ids, or None}

**Expected result:**
{one sentence}

**Acceptance criteria:**
- [ ] {functional criterion}
- [ ] **Tests:** {the unit tests added, with nio/Gemini mocked}
- [ ] **Contract:** {contract + the test that pins it + the SPEC.md/SPEC-UA.md/CLAUDE.md updates} — *(only if a contract changes)*
- [ ] **Gates:** {which of lint / tests / compose apply}
- [ ] **Manual (owner):** {DoD check from SPEC.md §{N+2}} — *(only where the DoD needs the live system)*

---

{repeat the `### AGORA-{id} …` block per issue}

## pN scope notes

**Critical path:** AGORA-{…} → … → AGORA-{…}.
**Phase DoD (SPEC.md §{N+2}):** {restate the DoD}.
**Contracts touched:** {contracts + their tests, or "none"}.
**Owner steps:** {what the owner must do on the host or in Element, or "none"}.
**Not in this phase:** {nearby work that belongs to a later phase or to no phase}.
**Generated later:** `pN-github-report.md` (on upload), `pN-execution-report.md` (on execution).
````

### Step 3: Report

Show the user the file path, the issue count, the `AGORA-###` range, the critical path, and which id
sources were checked. Suggest the next step:

```
/upload-issues @specification/implementation/pN-issues.md     # GitHub flow
/execute-issues-file pN                                       # offline flow
```

Do **not** create GitHub issues or commit here. This skill only writes the local file, so the user can
read and edit it first.

## Important Rules

- **One file per phase**, at `specification/implementation/pN-issues.md`.
- **Ids are globally sequential** (`AGORA-###`) across phase files and regeneration runs. Resolve the next id
  as `max(GitHub, local issues files) + 1`.
- **Tests in every code issue**, with nio and Gemini mocked. Manual DoD checks are labeled
  **Manual (owner):**.
- **Contract change = SPEC.md + SPEC-UA.md + CLAUDE.md + the pinning test**, all in the same issue.
- **Stay within the phase**; don't add what no phase asks for. PoC simplicity beats completeness.
- **Honor the DoD.** Together, the issues must satisfy the phase DoD in SPEC.md §{N+2}.
- **Ask on ambiguity.** If a task is under-specified, ask before inventing scope.
- **Don't touch GitHub.** `/upload-issues` does that.
