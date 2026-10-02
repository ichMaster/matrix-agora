# Vision — matrix-agora

## In one sentence

matrix-agora is a private Matrix room on a home LAN where the owner and two small Gemini-backed agents — Ada and Bruno, who believe they are human and live in Lviv — talk together and remember past conversations, all of it running on a home server and managed from one web panel: the seed of an admin panel for agent simulations.

## What we are building

A deliberately simple proof of concept: a self-hosted Matrix homeserver on the home network, Element Desktop as the owner's client, and two Python agents that share one codebase and differ only in config. The agents see both the owner and each other; nobody from outside can message them. The build order validates the setup itself (server → client → bots → three-way conversation) before any sophistication: first an echo bot, then Gemini replies, then turn-taking rules so the agents don't loop, then identity (canons) and memory (session summaries, day-by-day memories, auto-generated plans for the days ahead, an hourly sense of today, and place and time), and finally operations: token accounting, one Docker image with CI behind it, each agent deployed to the Ubuntu server as its own container, and the panel — served from that server — that manages the first simulation and its agents.

## For whom

A private project for the owner alone. One human account (`@ich`), two agent accounts, one invite-only room. Registration on the homeserver is closed after setup, federation is off, and nothing is reachable from outside the LAN. This is not a product and has no other users.

## The direction: the panel is the product

The panel is what this project is really building. Today it manages the first **simulation** — the Matrix chat (the homeserver and the "Agora" room) — and the two agents connected to it. Later it will manage other simulations that agents join, and agents like Lili — the owner's existing text persona. That is why its model is generic from day one: a **registry of simulations** (deployment, health, logs and maintenance are written against a registry entry, never against "the chat") and agents connected to simulations. This roadmap implements exactly one simulation kind and no more; the simple Gemini agents are stand-ins that prove the scheme before a real agent is connected.

## Principles

- **Simplicity first.** Complexity is added only by version, never all at once. A PoC that works end to end beats a complete design.
- **Closed by default.** An invite-only room, an allowlist in code, registration closed after setup, federation off, no port forwarded on the router, and the panel LAN-only behind a single owner token. Nothing is ever opened to the public.
- **The panel is the centre.** One panel manages simulations and the agents connected to them. Today the only simulation is the chat; deploy, health, logs and maintenance are written against a simulation-registry entry, so a new simulation kind is a registry entry plus its compose services — not a panel rewrite.
- **The agents believe they are human.** Their canons describe people, not bots, and no prompt or code path tells them otherwise. This is the owner's game in a closed room — the owner is the only person they talk to and knows the truth, so there is no outsider to mislead. If other people ever join the room, this rule must be revisited.
- **Rules live in code, identity lives in the canon.** The reply-format rules (speak only as yourself, no name prefix, `PASS` allowed) are code, so editing a canon cannot break them. Who the agent *is* — character, voice, attitudes — is an authored markdown file.
- **A whole life, not a loop.** Each agent has a written life story from birth to death, anchored to real dates. The past and the present chapter are what the agent remembers and lives; future chapters silently steer its plans as real time catches up with them. The agent never knows its future, its death included.
- **Memories follow the life; plans drift from it.** Day memories are generated *from* the life story — new concrete details of each day, never copied text. Plans — for the year, the month, the week and the day — are intentions with mutations: people plan things that don't happen, and the memories tell what really did. The agent never knows which of its plans will fail.
- **Everything is kept; what is old is compressed.** Nothing the agents lived is ever deleted: every day memory, day journal and plan stays in `state/`. Older time is summarized in layers — weeks from days, months from days, years from months — so the prompt carries yesterday in detail and last year in a paragraph. No full conversation logs, vector stores or RAG.
- **Invention is bounded by the record.** Day memories, plans and the today block may invent what the agent does alone in Lviv, but anything involving the owner or the other agent comes only from the conversation journal — otherwise the two agents' memories would contradict each other — and a plan never commits the owner or the other agent to anything.
- **Every model call is counted.** Each Gemini call appends a usage line (tokens, kind, ok) so the owner can always see what conversations cost. Counting and reporting only — no limits, budgets or billing.
- **The repo deploys itself.** Configuration lives in the repo and reaches the server by script: `server/deploy.sh` pushes the whole stack — homeserver, panel, one container per agent — to the Ubuntu host, which pulls the images from GHCR. Nothing is hand-edited on a host. CI runs the gates and builds the images, but never reaches the LAN; `uv run` on the Mac stays as the dev mode.
- **The agents run without the panel.** The panel is a management surface, not a dependency: `docker compose` and the terminal dev mode always work, and stopping the panel never stops the agents.
- **The agents' world is Ukrainian; the project's code is English.** Conversation, prompts, calendar strings and the panel UI are Ukrainian. Code, comments, tests and specification are English.
- **No secrets in the public repo.** Canons are committed and therefore hold no secrets and no private data about the owner. Keys, passwords, tokens, logs and everything the agents remember stay in gitignored files.

## Non-goals

- E2EE, voice/video calls, media (images, voice messages) — text only.
- Raw archives of conversations (full message logs), vector DBs and RAG — long-term memory is the layered digests, not search.
- Live world data (weather, news, city events, external APIs). World awareness is only place, calendar and clock.
- Token limits, budgets or billing — accounting only counts and reports.
- Public or multi-user access of any kind: no open registration, no internet exposure, no accounts — the panel takes a single owner token.
- Cloud-to-LAN CD, container orchestration beyond docker compose, registries beyond GHCR.
- A general remote shell: the panel offers only fixed actions (deploy state, start/stop/restart, logs, health, forget) — never command input.
- A second simulation. The registry and the model are ready for more, but this roadmap builds only the chat.
- Lili herself. This PoC runs simple stand-in agents; connecting real agents is the follow-up rework, not a phase here.

## Glossary

- **Owner** — the one human (`OWNER`, `@ich:agora.lan`): the admin of the homeserver and the only person in the room.
- **Agent** — one of two instances of `agents/agent.py` (`Ada`, `Bruno`), each with its own Matrix account, TOML config and canon. From v3.2 each runs as its own Docker container on the server; `uv run` on the Mac is the dev mode.
- **Homeserver** — [Continuwuity](https://continuwuity.org), a Rust Matrix server in one Docker container on the Ubuntu box (`agora.lan`, LAN-only, HTTP).
- **The room** — the single private, invite-only, unencrypted room ("Agora", `ROOM_ID`) where all conversation happens.
- **Allowlist** — the in-code rule that an agent reacts only to messages in `ROOM_ID` from `{OWNER, the other agent}`.
- **Canon** — the committed markdown description of who an agent is: `agents/canon/common.md` (shared world) + `agents/canon/<name>.md` (personal character). Replaces the early `persona` field.
- **Session** — a stretch of conversation; it ends after `SESSION_IDLE_S` of silence or when the agent is stopped.
- **Session summary** — the rolling first-person summary of the last session, `state/<name>.memory.md`, injected into the prompt after a restart.
- **Life story** — `agents/canon/<name>.life.md`: dated chapters from birth to death; the current chapter frames everyday life; future chapters and the death date are never shown to the agent.
- **Plans** — year intentions, month, week and day plans (`state/<name>.plans/`): sincere intentions generated from the life story with mutations; frozen once their period ends.
- **Plan mutation** — a deliberate, random deviation of a plan item from the life story (probability `PLAN_MUTATION_RATE`).
- **Memory digest** — a first-person summary of a finished week (`weeks/`), month (`months/`) or year (`years/`), generated from the finer layer and never rewritten.
- **Day memory** — a short auto-generated first-person text about one past day, `state/<name>.days/YYYY-MM-DD.md`; never rewritten once made.
- **Plan** — a short auto-generated first-person intention file: per week (`state/<name>.plans/week-YYYY-MM-DD.md`) and per day (`state/<name>.plans/YYYY-MM-DD.md`); frozen once its period ends.
- **Today block** — `state/<name>.today.md`: what the agent has already done today and what is still ahead, regenerated automatically every hour and reset at midnight.
- **Conversation journal** — the per-day record of session summaries, `state/<name>.days/YYYY-MM-DD.talk.md`; the only source of room facts for day memories.
- **`bot_streak`** — the count of consecutive agent messages since the owner's last message; both agents derive it from the shared room timeline, which is what keeps them from looping.
- **`PASS`** — the literal reply with which a model declines to answer; the agent then sends nothing.
- **Usage line** — one JSON line per Gemini call in `state/<name>.usage.jsonl`: timestamp, kind, token counts, ok — never any text.
- **Simulation** — an environment agents join, managed by the panel as one unit: compose services + a health probe + log sources. The chat (the homeserver with the "Agora" room) is the first and only one here.
- **Simulation registry** — the declarative list of simulations; every panel mechanism is written against its entries.
- **Server deploy** — `server/deploy.sh`: the one scripted path by which the repo's config reaches the Ubuntu host (sync + `docker compose pull && up -d` + verify).
- **Agent image** — the single Docker image both agents run from, one container per agent (the `ada`/`bruno` services in `server/docker-compose.yml`), with `state/` bind-mounted from the server.
- **Panel** — the web panel served from the Ubuntu box (`http://192.168.1.197:8090`, Bearer `PANEL_TOKEN`): the product of the project. It manages the simulations (today — the chat) and the agents: launching and stopping their containers, health, logs, memory, tokens, host metrics.
