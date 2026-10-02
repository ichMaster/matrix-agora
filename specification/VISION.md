# Vision — matrix-agora

## In one sentence

matrix-agora is a private Matrix room on a home LAN where the owner and two small Gemini-backed agents — Ada and Bruno, who believe they are human and live in Lviv — talk together, remember past conversations, and are run from a local web panel.

## What we are building

A deliberately simple proof of concept: a self-hosted Matrix homeserver on the home network, Element Desktop as the owner's client, and two Python agents that share one codebase and differ only in config. The agents see both the owner and each other; nobody from outside can message them. The build order validates the setup itself (server → client → bots → three-way conversation) before any sophistication: first an echo bot, then Gemini replies, then turn-taking rules so the agents don't loop, then identity (canons) and memory (session summaries, day-by-day memories, auto-generated plans for the days ahead, an hourly sense of today, and place and time), and finally operations (token accounting, Docker images with CI behind them, and a local web panel that starts, stops and observes the agents).

## For whom

A private project for the owner alone. One human account (`@me`), two agent accounts, one invite-only room. Registration on the homeserver is closed after setup, federation is off, and nothing is reachable from outside the LAN. This is not a product and has no other users.

## The longer-term direction

After the PoC the project will be reworked into an **admin panel for running agents like Lili** — the owner's existing text persona. The web panel (v3.2) is the seed of that admin panel; the simple Gemini agents are stand-ins so the scheme (homeserver, accounts, room discipline, supervision) is proven before a real agent is connected. That rework is a follow-up project, not part of this roadmap.

## Principles

- **Simplicity first.** Complexity is added only by version, never all at once. A PoC that works end to end beats a complete design.
- **Closed by default.** An invite-only room, an allowlist in code, registration closed after setup, federation off, no port forwarded on the router, the panel bound to `127.0.0.1`. Nothing is ever opened to the public.
- **The agents believe they are human.** Their canons describe people, not bots, and no prompt or code path tells them otherwise. This is the owner's game in a closed room — the owner is the only person they talk to and knows the truth, so there is no outsider to mislead. If other people ever join the room, this rule must be revisited.
- **Rules live in code, identity lives in the canon.** The reply-format rules (speak only as yourself, no name prefix, `PASS` allowed) are code, so editing a canon cannot break them. Who the agent *is* — character, voice, attitudes — is an authored markdown file.
- **Memory is compressed, not archived.** An agent keeps a rolling summary of the last session, short auto-generated memories of recent days, auto-generated plans (per day and per week) and an hourly today note — never full logs, vector stores or RAG. Old topics fade by compression.
- **Invention is bounded by the record.** Day memories, plans and the today block may invent what the agent does alone in Lviv, but anything involving the owner or the other agent comes only from the conversation journal — otherwise the two agents' memories would contradict each other — and a plan never commits the owner or the other agent to anything.
- **Every model call is counted.** Each Gemini call appends a usage line (tokens, kind, ok) so the owner can always see what conversations cost. Counting and reporting only — no limits, budgets or billing.
- **The repo deploys itself.** Configuration lives in the repo and reaches machines by script: `server/deploy.sh` pushes `server/` to the Ubuntu host, and the agents run on the Mac from one Docker image via compose. Nothing is hand-edited on a host. CI runs the gates and builds the image, but it never reaches the LAN — deploys always run from the Mac.
- **The agents run without the panel.** The panel is a convenience for supervision; starting agents from a terminal always works, and closing the panel never stops them.
- **The agents' world is Ukrainian; the project's code is English.** Conversation, prompts, calendar strings and the panel UI are Ukrainian. Code, comments, tests and specification are English.
- **No secrets in the public repo.** Canons are committed and therefore hold no secrets and no private data about the owner. Keys, passwords, tokens, logs and everything the agents remember stay in gitignored files.

## Non-goals

- E2EE, voice/video calls, media (images, voice messages) — text only.
- Long-term memory beyond the last-session summary and the last `MEMORY_DAYS` day memories: no full conversation logs, no vector DB, no RAG.
- Live world data (weather, news, city events, external APIs). World awareness is only place, calendar and clock.
- Token limits, budgets or billing — accounting only counts and reports.
- Public or multi-user access of any kind: no open registration, no internet exposure, no panel access from other devices.
- Cloud-to-LAN CD, container orchestration beyond docker compose, registries beyond GHCR.
- Lili herself. This PoC runs simple stand-in agents; connecting real agents is the follow-up rework, not a phase here.

## Glossary

- **Owner** — the one human (`OWNER`, `@me:agora.lan`): the admin of the homeserver and the only person in the room.
- **Agent** — one of two Python processes (`Ada`, `Bruno`) sharing `agents/agent.py`, each with its own Matrix account, TOML config and canon.
- **Homeserver** — [Continuwuity](https://continuwuity.org), a Rust Matrix server in one Docker container on the Ubuntu box (`agora.lan`, LAN-only, HTTP).
- **The room** — the single private, invite-only, unencrypted room ("Агора", `ROOM_ID`) where all conversation happens.
- **Allowlist** — the in-code rule that an agent reacts only to messages in `ROOM_ID` from `{OWNER, the other agent}`.
- **Canon** — the committed markdown description of who an agent is: `agents/canon/common.md` (shared world) + `agents/canon/<name>.md` (personal character). Replaces the early `persona` field.
- **Session** — a stretch of conversation; it ends after `SESSION_IDLE_S` of silence or when the agent is stopped.
- **Session summary** — the rolling first-person summary of the last session, `state/<name>.memory.md`, injected into the prompt after a restart.
- **Day memory** — a short auto-generated first-person text about one past day, `state/<name>.days/YYYY-MM-DD.md`; never rewritten once made.
- **Plan** — a short auto-generated first-person intention file: per week (`state/<name>.plans/week-YYYY-MM-DD.md`) and per day (`state/<name>.plans/YYYY-MM-DD.md`); frozen once its period ends.
- **Today block** — `state/<name>.today.md`: what the agent has already done today and what is still ahead, regenerated automatically every hour and reset at midnight.
- **Conversation journal** — the per-day record of session summaries, `state/<name>.days/YYYY-MM-DD.talk.md`; the only source of room facts for day memories.
- **`bot_streak`** — the count of consecutive agent messages since the owner's last message; both agents derive it from the shared room timeline, which is what keeps them from looping.
- **`PASS`** — the literal reply with which a model declines to answer; the agent then sends nothing.
- **Usage line** — one JSON line per Gemini call in `state/<name>.usage.jsonl`: timestamp, kind, token counts, ok — never any text.
- **Server deploy** — `server/deploy.sh`: the one scripted path by which the repo's `server/` config reaches the Ubuntu host (sync + `docker compose up -d` + verify).
- **Agent image** — the single Docker image both agents run from on the Mac (`compose.yml`, services `ada`/`bruno`), with `state/` bind-mounted from the host.
- **Panel** — the local web panel (`uv run panel/app.py`, `127.0.0.1:8090`) that starts/stops agents and shows logs, memory, tokens and server status.
