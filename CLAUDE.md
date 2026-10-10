# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Specification

Read these before planning work; they are the project's contract with itself.

- **[specification/VISION.md](specification/VISION.md)** — what matrix-agora is, for whom, the principles (incl. "the agents believe they are human"), the non-goals, and the glossary. A request that violates a non-goal is a conversation, not a task.
- **[specification/ARCHITECTURE.md](specification/ARCHITECTURE.md)** — components, the message flow and allowlist, turn-taking, canon, memory, world awareness, token accounting, the panel, the **contracts**, configuration, security, and the acceptance gates.
- **[specification/ROADMAP.md](specification/ROADMAP.md)** — four versions (v0 Platform, v1 Conversation, v2 Persona & memory, v3 Operations), each phase `vA.B` with Goal, Tasks, DoD and Tests. Build phases strictly in order and check each against its DoD before moving on.

- **[specification/design/](specification/design/README.md)** — the panel's UI: the brief and the Claude Design handoff (screens, tokens, copy, status logic) that v3.3–v3.4 build to; English UI.

**`specification/history/` (SPEC.md, SPEC-UA.md) is frozen.** Those are the superseded originals, kept for history only: never update them, never treat them as a source of truth, and never require changes to stay in sync with them.

## Project status

Proof of concept: a private Matrix room where the owner and two LLM agents ("Ada" and "Bruno", Gemini 2.5 Flash) talk together. So far the repo holds only the specification. The panel is the point of the project: it will grow into an admin panel for simulations and agents like Lili; the chat is the first simulation (VISION §The direction).

Latest release: v4.1.0 (phase v4.1 — roster, agent types and N-agent turn-taking). Versions v0–v3 are complete. Version v4 (Ensemble) has begun: phases v4.1–v4.7 in ROADMAP, designed in the draft [specification/features/more-agents.md](specification/features/more-agents.md) (Ukrainian copy: `more-agents-UA.md`).

| Version | Phases | What it delivers |
|---|---|---|
| `v0` Platform | v0.1 homeserver · v0.2 server deploy · v0.3 client · v0.4 accounts+room · v0.5 echo bot | owner steps + the deploy script; first real code in v0.5 |
| `v1` Conversation | v1.1 Gemini replies · v1.2 turn-taking | code |
| `v2` Persona & memory | v2.1 canons + session memory · v2.2 a life story, world awareness, plans (with mutations) + day memories + the hourly today block | code + canon files |
| `v3` Operations | v3.1 token accounting · v3.2 agent images + CI/CD + server deployment · v3.3 the panel: viewing (read-only) · v3.4 the panel: control | code |
| `v4` Ensemble (planned) | v4.1 roster, agent types, N-agent turn-taking · v4.2 the cat in the room · v4.3 the cat's past life and initiative · v4.4 Claude on the subscription, when asked · v4.5 Claude the philosopher · v4.6 the Lumi bridge, when named · v4.7 Лілі under the full rules | code + canon files |

## Layout and commands

See ARCHITECTURE.md §Repository layout for the full tree. The essentials:

- Dev mode on the Mac (one terminal per agent): `scripts/run-agent.sh ada` / `scripts/run-agent.sh bruno`; Ctrl+C stops. Since v3.2 the live agents run on the server — stop the server's container first (`docker compose stop ada` on the host), since the lock is per host; the Mac `state/` is an older copy
- Production (from v3.2): everything runs on the Ubuntu server; deploy the stack with `server/deploy.sh` (`--dry-run` first; it syncs `server/docker-compose.yml` + the local, gitignored `server/.env`, pulls, `up -d`); never hand-edit files on the host. Each agent is its own container (`ada`, `bruno`, image `ghcr.io/ichmaster/matrix-agora-agent:${AGENT_IMAGE_TAG}`) — stop with `docker compose stop -t 30 <name>` so the session summary runs; logs in `~/matrix-agora/state/logs/<name>.log`
- Panel (from v3.3, actions from v3.4): `http://192.168.1.197:8090`, Bearer `PANEL_TOKEN`
- Token report (from v3.1): `uv run agents/usage_report.py --days 7`
- Daily token report: since v3.2 the compose service `usage-report` writes `~/matrix-agora/reports/usage/latest.md` on the server every day at 07:00 (v3.1.1's Mac launchd job, `scripts/install-usage-daily.sh`, is uninstalled); by hand on the Mac: `scripts/usage-daily.sh`
- Server (on the Ubuntu host, from `server/`): `docker compose up -d`, then `docker compose logs -f homeserver`
- Homeserver smoke test from the Mac: `curl http://192.168.1.197:8008/_matrix/client/versions`
- `server_con.yaml` (gitignored) holds the SSH host, user and password for the Ubuntu host; `server/deploy.sh` (v0.2) is its only consumer. Never print it, commit it, or put the password on a command line. Deploy or act on the host only when the owner asks.

## Acceptance gates

Automated gates need no network: tests mock `matrix-nio` and `google-genai` and inject the clock, so nothing reaches the homeserver or Gemini.

| Gate | Command | When |
|---|---|---|
| Lint | `uv run ruff check .` | any Python change |
| Tests | `uv run pytest` (one test: `uv run pytest tests/test_x.py::test_name`) | any Python change |
| Compose | `REGISTRATION_TOKEN=dummy docker compose -f server/docker-compose.yml config -q` | `server/` changed |

- **Compose gate:** keep `-q`. Without it, the command prints the resolved config.
- **Before v0.5:** there is no `pyproject.toml`, so the Python gates are `n/a`, not passed. ruff and pytest are dev dependencies, added by the issue that creates `pyproject.toml`.
- **Manual gates:** the ROADMAP DoD items marked **Manual (owner)** need the live homeserver, Element or (from v1.1) a real Gemini key.
  - Claude may run the read-only `curl` checks from the Mac.
  - Anything on the Ubuntu host, in Element, or that makes a live Gemini call is done or confirmed by the owner.
  - A manual check counts as passed only once the owner confirms it.

## Rules that are easy to break

The full mechanisms live in ARCHITECTURE.md; these are the invariants most often broken by accident:

- **Login once, reuse the token** (`state/<name>.json`), or every start creates a new device.
- **Never process the first sync's events** — a restarted bot would reply to the whole history.
- **The allowlist guards every reply path**: only `ROOM_ID`, only `{OWNER, other agent}`, only `RoomMessageText`; everything else logged as `ignored`.
- **Turn-taking is derived from shared inputs** — the `event_id`, the shared room timeline and the roster (`rank`, `wave_count`, R1–R4) — never add shared state or coordination between the agents.
- **Send `m.text`, never `m.notice`**; typing reset in `finally`; on a failed/empty Gemini reply log and stay silent, never crash.
- **The agents never know their future.** Future life-story chapters, the death date and the hidden plan-mutation tags never reach a conversational prompt; only the plan generator sees the next chapter.
- **The persona agents believe they are human** (from v4.2 scoped to `persona` agents). No code path or prompt — reply rules, summary prompts, memory prompts — may say a persona is a model or a bot, and a non-persona agent's reply that would call one so is dropped (`outs_a_persona`).
- **Nothing lived is deleted, and nothing past is rewritten**: day memories, digests (week/month/year) and plans stay forever, and room facts in memories, plans and the today block come only from the conversation journal.
- **Keep decisions pure**: the filter, mentions, the ranking and `wave_count`, who-replies, prompt assembly, session-end, day and plan-period selection, the hourly today-refresh decision and usage aggregation are functions over plain data with an injected clock.
- **Secrets stay out**: never print `.env`, `server/.env`, `server_con.yaml` or anything under `state/`; no tokens, passwords, keys or message/summary/memory texts in logs, argv, commits or issue comments. To check a value is set, test it without echoing it (`grep -q '^GEMINI_API_KEY=.' .env`).

## Contracts

The list of contracts lives in **ARCHITECTURE.md §Contracts** (env var names, the TOML schema and canon layout, the `state/` files, the filter rule, the transcript format + `PASS` + prompt order, turn-taking semantics, the compose environment). Changing one updates ARCHITECTURE.md and the test that pins it, in the same commit.

## Delivery workflow (skills)

`.claude/skills/` holds a spec-driven pipeline adapted from the H11 project.

- **Issues:** each ROADMAP phase `vA.B` becomes `specification/implementation/vA.B-issues.md`. Issue ids are `AGORA-###`, numbered globally and never reset.
- **Implementation:** each issue is one commit. Each phase is then reviewed, and the fix-now findings are fixed.
- **Releases:** phase `vA.B` ships as `A.B.0` (tag `vA.B.0`); post-release fixes bump the last digit (`A.B.1`, …).
- **GitHub flow:** `/ship-phase <selector>` (a phase `vA.B`, a version `vA`, or a range) runs `/generate-issues` → `/upload-issues` → `/execute-issues` → `/review-and-fix-issues` → `/release-version` for each phase, then `/harden-findings` at the end of the run.
- **Offline flow:** `/ship-solution` runs `/reconcile-issues` → `/execute-issues-file` → `/review-and-fix-issues` → `/release-version` over issues files that already exist.
- **Sessions:** `/spawn <alias> [--tab] [role]` starts a new Claude session with a role — in the background (tmux `cc-<alias>`, survives closing tabs; `tmux attach -t cc-<alias>` to chat) or, with `--tab`, as a VS Code tab; `/join <alias>` names the current tab, `/send <alias> <message>` messages another tab. `/sessions` lists them with their type (bg / tab) and status; `prune` drops stale ones, `stop <alias>` ends a background one. The same in a UI: the **Claude Sessions** sidebar panel (`tools/sessions-panel/`, a local VS Code extension — see its README to rebuild). Aliases live in `.claude/session-aliases/` (`registry.json` is gitignored, `roles/` holds the role briefs).
- **Who releases:** versions are bumped and tagged only by `/release-version`, `/ship-phase`, `/ship-solution` or `/harden-findings --release`.

## Constraints

- `CONTINUWUITY_SERVER_NAME` cannot change without wiping the database.
- Registration is open with a token only until the bot accounts exist (v0.4). After that it is turned off (`CONTINUWUITY_ALLOW_REGISTRATION: "false"`).
- Running without TLS is a deliberate PoC trade-off. Never expose ports 8008 or 8090 through the router; the panel is LAN-only behind the owner token. Any outside access must go through Tailscale later.
