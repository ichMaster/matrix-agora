---
name: release-version
description: Bump the project version (ROADMAP phase vA.B -> A.B.0, post-release fix -> A.B.C), update VERSION / pyproject.toml / uv.lock / RELEASE.txt / the CLAUDE.md status line, commit, create an annotated tag, and push.
---

# Skill: Release Version

Bump the project version, update every version reference, write release notes, commit, tag and push.

## Usage

```
/release-version <version> [changelog line 1; changelog line 2; ...]
```

- `/release-version 0.4.0`: release phase v0.4 and generate the changelog from the commits.
- `/release-version 1.2.1 Fix replay on restart; typing reset in finally`: a patch with given notes.

**Version scheme (`A.B.C`):** `A` = roadmap version (v0→0 … v3→3), `B` = phase within it, `C` = a
post-release fix on that phase. ROADMAP phase `vA.B` → release `A.B.0`, tag `vA.B.0`; a later fix on it
bumps `C` (`A.B.1`, …). Releases are cut per phase. A version beyond the roadmap (e.g. `1.0.0`-style
semantics) is a decision the owner makes explicitly.

**Never change the version without explicit user confirmation**; running this skill, or an orchestrator
that calls it, is that confirmation.

## Instructions

### Step 0: Parse arguments

1. The first argument is the target version. Accept `0.4.0` or `v0.4.0` and normalize to `0.4.0`.
2. The remaining arguments, split on `;`, become the changelog bullets.
3. Validate that the version matches `A.B.C` (digits only) and that `vA.B` is a real ROADMAP phase.

### Step 1: Verify prerequisites

1. **Branch:** note the current branch.
2. **Clean tree:** check `git status`. If it is dirty, ask whether to include the uncommitted changes.
3. **Current version:** read it from `VERSION`, else the latest `v*` tag (`git describe --tags --abbrev=0`),
   else treat it as none.
4. **No downgrade:** refuse if the target is less than or equal to the current version (compare as the
   `A.B.C` tuple; phases release in roadmap order).
5. **Phase releases** (`A.B.0`): check the phase's execution report
   (`specification/implementation/vA.B-execution-report.md`) has no failed, skipped or `awaiting owner`
   issues. Its manual DoD checks must be confirmed by the owner. If they aren't, stop and say what is
   missing; the owner can waive it explicitly, and the waiver goes into the release notes.

### Step 2: Generate the changelog (if not provided)

1. Collect the commits since the last tag (`git log --oneline <tag>..HEAD`), or all commits if there is no
   tag.
2. Summarize them as concise bullets: group related commits and reference the phase and `AGORA-###` ids.
3. Show the changelog to the user and ask for confirmation.

### Step 3: Update the version files

Touch only files that exist, except `VERSION` and `RELEASE.txt`, which are created if missing.

1. **`VERSION`:** the bare version string, e.g. `0.4.0`.
2. **`pyproject.toml`:** the `[project]` `version` field. Then run `uv lock` so `uv.lock` records the new
   project version; otherwise the next `uv run` rewrites the lock and dirties the tree.
3. **`README.md`:** update it only if it already carries a version string. Never add one.
4. **`CLAUDE.md`:** update the `Latest release:` line under **Project status**, e.g.
   `Latest release: v0.4.0 (phase v0.4 — echo bot).`
5. **`RELEASE.txt`:** prepend a block at the top (after any header) and keep the older entries unchanged:

   ```
   Version <version> (YYYY-MM-DD)
   ---------------------------
   - <changelog item 1>
   - <changelog item 2>
   ```

### Step 4: Commit

Stage only the version files that **exist**. `git add` is fatal on a pathspec that matches nothing:

```bash
for f in VERSION RELEASE.txt README.md CLAUDE.md pyproject.toml uv.lock; do
  if [ -e "$f" ]; then git add "$f"; fi
done
```

Use the `if` form, not `[ -e "$f" ] && git add "$f"`. The latter leaves the loop's exit status at 1 when the
last file is absent.

```bash
git commit -m "$(cat <<'EOF'
Release v<version>

<1-2 sentence summary of what this release includes>

Co-Authored-By: <the running model's trailer> <noreply@anthropic.com>
EOF
)"
```

### Step 5: Tag

```bash
git tag -a v<version> -m "<one-line summary of the release>"
```

### Step 6: Push

If a remote exists, push the branch and then **only the tag just created**, never `--tags` or
`--follow-tags`:

```bash
git push
git push origin "v<version>"
```

Without a remote, say that the release is local only.

### Step 7: Report

```
Released v<version>
  Branch: <branch>
  Commit: <short hash>
  Tag:    v<version>
  Pushed: yes / no (no remote)
  Files updated:
    - VERSION
    - pyproject.toml, uv.lock
    - RELEASE.txt
    - CLAUDE.md
```

## Important Rules

- **Never downgrade.** Refuse a target less than or equal to the current version.
- **Clean tree first.** If there are uncommitted changes, ask before proceeding.
- **Phase releases need a complete phase.** No failed, skipped or `awaiting owner` issues, and the manual
  DoD confirmed by the owner (or explicitly waived, and noted).
- **Annotated tags only** (`git tag -a`).
- **Version metadata only.** This skill touches `VERSION`, `pyproject.toml`, `uv.lock`, `RELEASE.txt`,
  `README.md` and CLAUDE.md's status line, never agent, panel or server code.
- **Confirm the changelog** when it is auto-generated.
- **Plain-text release notes** in `RELEASE.txt`.
