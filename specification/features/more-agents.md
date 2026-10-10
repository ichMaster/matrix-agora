# Feature: more agents in the room

> **Status: draft, 2026-10-10.** A proposal, not a contract. It is the design of ROADMAP **v4** (phases v4.1–v4.7, matching [Phasing](#phasing)); CLAUDE.md and ARCHITECTURE.md do not link here yet. The ARCHITECTURE and VISION changes listed in [VISION and contract changes](#vision-and-contract-changes) land with those phases.
>
> Sources: the research pass of 2026-10-10 read the matrix-agora code, the Lumi repo (`~/development/lumi`), the Claude Agent SDK docs, and computed the cat's chart with two independent ephemeris engines. Facts from outside this repo are cited. Anything not verified is marked **unverified**.

## Summary

Three new members join Ada, Bruno and the owner (Ich). Unlike Ada and Bruno, all three are **openly non-human from the start**:

| Member | What it is | Engine | Canon | Life story | Memory and plans |
|---|---|---|---|---|---|
| **Claude** | a plain interface to Claude, following the room's agent rules, short chat-style replies | the Claude Agent SDK on the owner's Max subscription **only**; an API key is ruled out and blocked | none, only a short brief in code | none | none (the room transcript is its only context) |
| **The cat** | a mystical, artificial cat: unstable, small vocabulary, mostly purrs; his mood follows a daily horoscope, as in Lumi; drops astro remarks and shell lines; **the only agent who starts conversations** | Gemini (only for lines that are not a purr) | yes, with a computed natal chart | yes: a sysadmin's life, a death, a rebirth as a cat at Linux's first commit | **fixed past-life memories only** (authored theses he retells); no generated memories, no plans |
| **Lumi** | a bridge to Lumi's **prod** brain, the owner's existing persona | Lumi's own HTTP server | owned by Lumi | owned by Lumi | owned by Lumi |

The room then holds six participants: Ich plus five agents. On top of the turn-taking rework this needs (one owner message must not become two pages of text), the proposal adds:

1. **Agent types with capabilities** (`persona`, `creature`, `assistant`, `bridge`). Each type switches the canon, life story, memories, plans and today block on or off.
2. **Pluggable reply engines** behind one interface: Gemini, Claude (the Agent SDK or the Messages API), and Lumi's HTTP API.
3. **Deterministic turn-taking without coordination.** It uses a weighted rendezvous hash of the message's `event_id`, with three turn modes (`ranked`, `ambient`, `mention-only`) and purrs that don't count toward the limit.
4. **A daily horoscope for the cat: Lumi's mood service, ported.** One model call a day writes a reading, and its short resolution sets his mood.
5. **A guard for the "agents believe they are human" rule.** Ada and Bruno keep believing it, even with three openly non-human members in the room.

## The new members

### Claude

- **What it is.** Claude, as itself: no character, no canon, no life, no memory. It is a member of the room that answers like any other agent and keeps replies chat-sized.
- **Engine: the Claude Agent SDK** (`claude-agent-sdk`, Python, MIT), on the owner's subscription.
  - The package bundles the Claude Code binary, so no Node.js is needed ([PyPI](https://pypi.org/project/claude-agent-sdk/), [quickstart](https://code.claude.com/docs/en/agent-sdk/quickstart)).
  - Each reply is one stateless `query()` with the room transcript as the prompt. A call "starts fresh with no memory" unless resumed ([Python reference](https://code.claude.com/docs/en/agent-sdk/python)), which fits "no memory".
- **Authentication: the subscription only.** `claude setup-token` prints a one-year OAuth token for `CLAUDE_CODE_OAUTH_TOKEN`. It is the documented "alternative to `/login` for SDK and automated environments" ([env vars](https://code.claude.com/docs/en/env-vars)). It "requires a Pro, Max, Team, or Enterprise plan" and "can only make model requests" ([authentication](https://code.claude.com/docs/en/authentication)). The plan is **Max** (owner, 2026-10-10).
- **Policy: likely permitted for this use, with residual questions.** The quotes below were checked on 2026-10-10. This is not a legal determination.
  - **For:**
    - "You can still use the Claude Agent SDK, `claude -p`, and third-party apps with your subscription limits" ([support, Oct 7 2026 notice](https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan)).
    - The prohibition targets developers who "route requests through Free, Pro, or Max plan credentials **on behalf of their users**" ([legal and compliance](https://code.claude.com/docs/en/legal-and-compliance)). Here the owner is the subscriber and the only user.
  - **Against:**
    - "Unless previously approved, Anthropic does not allow third party developers to offer claude.ai login or rate limits for their products, including agents built on the Claude Agent SDK" ([overview](https://code.claude.com/docs/en/agent-sdk/overview)).
    - "Advertised usage limits … assume ordinary, individual usage". It is open whether an always-on bot counts as that.
    - The SDK overview puts SDK use under the Commercial Terms, while Pro and Max fall under the Consumer Terms.
  - **The quota is shared** with the owner's own Claude Code work, including this repo's delivery pipeline.
- **No API key, ever: enforced, not just configured** (owner, 2026-10-10). An `ANTHROPIC_API_KEY` in the environment outranks the OAuth token ([authentication](https://code.claude.com/docs/en/authentication)), so a key that slipped in would silently move Claude onto API billing. Several independent layers make that impossible:
  1. **Nothing in the stack carries an API credential.** The Claude service has its own env file, holding only the OAuth token, its Matrix password and non-secret settings, and it does **not** load the shared `server/.env`. A compose test fails if any service, `environment` entry or env file names a forbidden variable:
     - `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`;
     - any `CLAUDE_CODE_USE_*` (Bedrock, Vertex, Foundry);
     - `CLAUDE_CODE_SIMPLE`. Bare mode "never reads OAuth credentials".
  2. **Startup refuses.** The Claude agent exits with a clear error if any forbidden variable is set, or if `CLAUDE_CODE_OAUTH_TOKEN` is missing. It logs the variable names, never their values.
  3. **The SDK subprocess cannot inherit one.** The SDK passes all of `os.environ` to the CLI, so the agent also removes the forbidden variables from its own environment before the first `query()`. It is belt and braces after step 2.
  4. **No settings can add one.** `setting_sources=[]` means no settings file is read, so no `apiKeyHelper`. `CLAUDE_CONFIG_DIR` is a fresh tmpfs, so no stored login or key survives.
  5. **Runtime check.** If the SDK's `system/init` message reports an auth source other than the OAuth token, the agent stops replying and logs it. The exact field name (`apiKeySource`?) is **unverified**.
  6. **No API client in the code.** There is no `anthropic` Messages client and no direct `anthropic` dependency. A test pins the import set of the Claude responder.
  7. **On a limit: silence.** When the subscription limit is reached, Claude stays silent until `resets_at`. There is no fallback of any kind.
  8. **Accounting proves it.** Every Claude usage row is `billing = "subscription"`, and a test fails on anything else.
- **Chat-only configuration.**

  ```python
  ClaudeAgentOptions(
      system_prompt=CLAUDE_BRIEF,     # a plain string replaces the Claude Code system prompt
      tools=[],                        # "[] — Disable all built-in tools" (SDK types.py); confirm in system/init
      disallowed_tools=[...],          # belt and braces: Bash, Read, Write, Edit, Glob, Grep, WebFetch, WebSearch, Agent, Skill
      permission_mode="dontAsk",
      setting_sources=[],              # no CLAUDE.md, no ~/.claude settings
      mcp_servers={}, max_turns=1,
      model=CLAUDE_MODEL,              # "opus" (owner, 2026-10-10)
      env={"CLAUDE_CODE_MAX_OUTPUT_TOKENS": "...", "CLAUDE_CODE_SKIP_PROMPT_HISTORY": "1",
           "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1", "CLAUDE_CONFIG_DIR": "/tmp/claude"},
  )
  ```

  - **Length.** `ClaudeAgentOptions` has no `max_tokens`. The documented env var `CLAUDE_CODE_MAX_OUTPUT_TOKENS`, passed through `options.env`, caps output. Whether thinking tokens count against it is **unverified**. The brief's "1–3 sentences" and trimming in code do the rest.
  - **Writable config.** The agents run as uid 1000 with no home directory. The CLI needs a writable `CLAUDE_CONFIG_DIR`, so it gets a tmpfs.
  - **No room text persists on disk.** With `CLAUDE_CODE_SKIP_PROMPT_HISTORY=1`, nothing lands in the tmpfs config either (VISION non-goal: no raw archives). That this leaves no transcripts is **unverified** until it runs.
- **Two reply modes** (owner, 2026-10-10). A pure `claude_mode(trigger)` picks one per reply. The direct mode ships first (v4.4, `mention-only`); the philosopher arrives with `ranked` in v4.5:
  - **Direct**: the trigger message addresses him by name (any form of «Клод», or his Matrix id).
    - He answers what was asked, as Claude: plainly and helpfully, chat-sized (1–3 sentences unless the question needs a little more).
    - His context is the usual last `HISTORY_N` lines.
  - **Philosopher**: he joins the chat without being asked, chosen by the turn-taking (R1 on an unnamed owner message, or R2 as the next speaker).
    - He takes the role of a philosopher. He reads **a wider span of the chat history**, not only the last messages: the last `CLAUDE_HISTORY_N` lines, default 150.
    - He finds **the metaphorical image** running through the talk (often seeded by Кіт's metaphors, horoscopes and shell lines) and reflects on **its philosophy**. It is a thought, not a lecture: 2–4 sentences, chat style, and he may name an idea or a thinker if it fits.
    - If no image is worth it, he answers `PASS`.
    - It runs with higher reasoning effort than the direct mode (the SDK's `effort` option, **unverified** for Opus on the subscription).
- **The wider window.** The agent keeps a second RAM buffer of the last `CLAUDE_HISTORY_N` room messages, seeded from the room at start like the regular window (backfill), and never written to disk. He still has no memory between runs.
- **The brief** is a few lines in code, not a canon, with one variant per mode. Both variants share these rules:
  - he is Claude, in a small Ukrainian group chat with Ich, Ада, Бруно, Лілі and the cat;
  - he may answer `PASS`;
  - he **names the members without stating what they are** and never discusses their nature. Writing a false claim ("they are people") into the brief is avoided; the outgoing guard covers the rest (see [the human-belief rule](#8-the-agents-believe-they-are-human-rule)).
  - **Consistency with the past.** A real chat already introduced «Клод» as Ich's colleague, and Bruno reacted «О, Клод-ШІ, це круто!» ("Oh, Claude the AI, that's cool!", a fixture in `tests/test_logic.py`). Ada and Bruno may already remember him, so nothing in the brief may contradict that.
- **Rate limits.**
  - Subscription windows are rolling (5-hour and weekly). **The model is Opus** (owner, 2026-10-10). Opus has its own weekly window on top of these (`seven_day_opus` in the SDK's `RateLimitType`), shared with the owner's own Opus use in Claude Code.
  - The SDK emits a `RateLimitEvent` into the `query()` stream, with `status` (`allowed` / `allowed_warning` / `rejected`), `utilization` and `resets_at` ([types.py](https://raw.githubusercontent.com/anthropics/claude-agent-sdk-python/main/src/claude_agent_sdk/types.py)).
  - **On `allowed_warning`, Claude mutes itself** before the owner's own coding session hits the wall. On `rejected`, it stays silent until `resets_at` (a circuit breaker).
  - The exact SDK result when a limit hits is **unverified**.
- **Name forms:** «Клод», «Клода», «Клоду», «Клодом», «Клоде», plus `claude`.

### The cat

**Who he is.**
- In a past life he was a **sysadmin who did DevOps before DevOps had a name**. In the late 1980s he wrote a worm for Unix, in the Morris-worm era. He is a fictional contemporary, **not** Robert Morris, who is a real, living person.
- He sinned on prod for years, and died.
- He was reborn as a cat, and it turned out the cat is **artificial**: his birth is the **first commit of the Linux git repository**.
- He knows he is artificial. He is unstable, has a small vocabulary and mostly purrs. Sometimes he drops a line explained by the sky ("that's because Venus is retrograde"). Sometimes he drops a line from a shell script or a Linux command.

**His birth moment** (verified from primary sources):
- Commit `1da177e4c3f41524e886b7f1b8a0c1fc7321cac2`, "Linux-2.6.12-rc2", by Linus Torvalds.
- Time: **Sat 16 Apr 2005 15:20:36 −0700 (PDT) = 22:20:36 UTC** ([kernel.org cgit](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=1da177e4c3f41524e886b7f1b8a0c1fc7321cac2), [GitHub API](https://api.github.com/repos/torvalds/linux/commits/1da177e4c3f41524e886b7f1b8a0c1fc7321cac2)).
- The commit message is a gift to the lore: "Initial git repository build. **I'm not bothering with the full history**, even though we have it. … Let it rip!" The cat was born without his past: he remembers his human life only in fragments.
- Place: **Portland, Oregon** (45.5152 N, 122.6784 W). Torvalds moved to the Portland area in 2004 to work for OSDL ([Wikipedia](https://en.wikipedia.org/wiki/Linus_Torvalds)). Any point in the Portland area moves the Ascendant by about 0.1°, and the whole-sign houses stay the same.
- Other "Linux birthdays" with an exact time: the Usenet announcement, 25 Aug 1991 20:57:08 GMT, Helsinki. Linux 0.01 (17 Sep 1991) has no reliable time ([LKML](https://lkml.iu.edu/hypermail/linux/kernel/2109.2/03485.html)).

**His natal chart.**
- **Settings:** geocentric, apparent, true ecliptic and equinox of date; whole-sign houses.
- **How it was computed:** skyfield 1.55 with JPL DE440s.
- **How it was checked:** independently, with PyEphem, astropy with DE432s, and JPL Horizons (DE441). **Every value matched within 10″.**

| Body | Position | Motion | House |
|---|---|---|---|
| Sun | 27°01′ Aries | direct | 8 |
| Moon | 0°31′ Leo | direct (entered Leo 63 min before birth) | 12 |
| Mercury | 2°39′ Aries | direct (stationed direct 4 days earlier) | 8 |
| Venus | 1°20′ Taurus | direct | 9 |
| Mars | 19°42′ Aquarius | direct | 6 |
| Jupiter | 12°18′ Libra | **retrograde** | 2 |
| Saturn | 21°00′ Cancer | direct | 11 |
| Uranus | 9°25′ Pisces | direct | 7 |
| Neptune | 17°18′ Aquarius | direct | 6 |
| Pluto | 24°24′ Sagittarius | **retrograde** | 4 |
| Mean node | 22°43′ Aries | retrograde | 8 |
| **ASC** | **5°35′ Virgo** | | 1 |
| MC | 29°49′ Taurus (Gemini 47 s later) | | 9 |

- **Moon phase:** First Quarter (elongation 93.5°, 53% lit).
- **Key aspects:**
  - Moon □ Venus 0.8°
  - Moon △ Mercury 2.1°
  - Mars ☌ Neptune 2.4° (in the 6th house of work)
  - Sun △ Pluto 2.6°
  - Sun □ Moon 3.5°
  - Sun □ Saturn 6.0°
  - Uranus ☍ ASC 3.8°
- **How sensitive the chart is to the clock:**
  - an error of more than ~30 minutes earlier would make the ASC Leo;
  - more than 63 minutes earlier would put the Moon in Cancer.
- **A reading the canon can draw on:**
  - **Virgo rising**: grooms every log line.
  - **Sun in Aries in the 8th, trine Pluto**: death and rebirth.
  - **Moon in the first degree of Leo in the 12th**: craves an audience, sulks out of sight.
  - **Moon square Venus**: purrs, then bites.
  - **Mars conjunct Neptune in the 6th**: the phantom sysadmin, the worm's old fingerprint.
  - **Uranus opposite the ASC**: uncanny, not quite natural.

**His life story** fits the existing format with **no format change**. `life_section` already shows the opening paragraph of every past chapter ([agents/life.py](../../agents/life.py)), so:
- **`Народження:`** holds the **human** birth: the sysadmin's, in the early 1960s.
- **Past chapters** tell the human life, the worm, the sins on prod and the death, e.g. `## 1962–2004 · …`. Chapters are whole years and may not overlap, so the rebirth year opens the next chapter.
- **`## 2005–… · кіт`**: the death and the rebirth on 2005-04-16 open this chapter. It is his current chapter.
- **`Смерть:`** stays hidden, as for every agent, and becomes the cat's own unknown end. A fitting one for an artificial cat is the Unix 32-bit time overflow, **2038-01-19 03:14:07 UTC**. That is a suggestion for the owner.
- **The natal (rebirth) moment** is not the life header. It lives in his natal file (§6).

**No generated memories, no plans:**
- no session summaries, journal, day memories, digests, plans or today block;
- he does see the room's last `HISTORY_N` messages (the rolling context, kept in RAM only), so he can react to what is being said.

**Past-life memories: fixed, retold in his own words** (owner, 2026-10-10).
- **`agents/canon/<cat>.memories.md`** is an authored list of many short theses, about 60–100, one per line as `- [tags] text`.
  - Each is one moment of the sysadmin's life before 2005: the worm, the sins on prod, pagers, backups, Y2K…
  - They are canon: fixed and committed. They are never generated and never written by the agent, and nothing goes to `state/`.
  - They agree with the life story's past chapters. Like all of his past, they involve only him and his world, never Ich, Ada or Bruno.
- **Selection** is a pure, deterministic function `pick_memory(event_id, last_text, theses, told)`:
  - a thesis whose tags appear in the message he is answering is preferred;
  - otherwise, and among ties, `hash(event_id, "memory")` picks one;
  - theses already told in this run are skipped until all have been told. That record is kept in RAM only, like the context window.
- **When.** In a non-purr reply, with probability `CAT_MEMORY_P` (default 0.25), the chosen thesis enters his prompt as «Спогад з минулого життя: …» ("A memory from a past life: …"). The rule says to retell it in his own words: briefly, in fragments, never as a quote.
- **Not word for word.** If the reply copies 5 or more consecutive words of the thesis, it is regenerated once, and if it still does, it is dropped (silence). The check is `shares_span(reply, thesis, n=5)`, the helper day memories already use against the life story.
- **In fragments, by design.** He was born from a commit that is "not bothering with the full history", so he remembers his past only in pieces.
- **Examples of the tone** (the full list, drafted 2026-10-10, is `agents/canon/kit.memories.md`; the owner edits it like any canon):
  - `[worm, 1988]` Мій хробак мав лише полагодити `.rhosts` на трьох машинах кафедри. До ранку він «полагодив» усі.
  - `[rm, prod]` `rm -rf / tmp/build`, з пробілом. Сервер думав недовго.
  - `[backup]` Бекапи були щоночі, п'ять років поспіль. Відновлення — жодного разу. Перше не вдалося.
  - `[pager]` Пейджер завжди пищав о 3:14 ночі. Завжди о 3:14.
  - `[friday, deploy]` Деплой у п'ятницю о 17:55. П'ять хвилин до вихідних, три дні даунтайму.
  - `[cron]` Мій crontab пережив мене. Десь досі щоночі о 4:00 він чистить логи, яких уже немає.
  - `[dns]` Завжди DNS. Навіть коли не DNS — DNS.
  - `[y2k, 1999]` 31 грудня 1999-го я не спав: чекав кінця світу на проді. Прийшов тільки ранок.
  - `[root, password]` Пароль root був ім'ям мого кота. Тоді це здавалося смішним.
  - `[chmod]` `chmod -R 777 /` — і всі проблеми з правами зникли. Разом із безпекою.

**The daily horoscope: Lumi's service, ported** (owner, 2026-10-10: "the horoscope service must be as in Lumi"). `lumi/core/mood.py` and `lumi/core/biorhythm.py` become `agents/mood.py`. Both repos are MIT, by the same author. Behavior is kept:
- **`load_natal(path)`** reads his natal text and drops `#` comment lines.
- **Biorhythms** come from the birth date in the natal file (`Народження: DD.MM.YYYY`):
  - three sine cycles: physical 23 days, emotional 28, intellectual 33;
  - labels: `critical` at a zero crossing, `high` at ≥ 0.7, `low` at ≤ −0.7, otherwise `rising` or `falling`.
- **`mood_request(natal, date, biorhythms)`** is Lumi's "honest astrologer" prompt (no advice, not artificially cheerful), with Lumi's name replaced by his.
- **Once per local day** (Europe/Kyiv): lazily before his first reply of the day, and kicked off at startup.
- **The output:**
  - The full reading is appended to `state/<cat>.mood.log` as `===== YYYY-MM-DD =====` blocks.
  - `reading_from_log` reuses the day's block after a restart, so the mood is never re-rolled.
  - `split_resolution` extracts the `РЕЗОЛЮЦІЯ` paragraph. **Only that resolution** enters his prompt, as «Настрій дня» ("Mood of the day").
- **On failure** there is no mood that day. It never blocks a reply.
- **Model:** Gemini Flash, which is also what Lumi's gemini profile uses for the mood. Usage kind `mood`.
- **Not ported**, because it doesn't apply to a cat: Lumi's hormonal cycle, the face themes (`ТЕМА:`) and recent thoughts.
- **As in Lumi, the transits are written by the model**, not computed. His astro remarks are flavor; they are not checked against an ephemeris.

**His natal file** (`agents/canon/<cat>.natal.md`) follows the format of Lumi's `core/natal.md`:
- a line `Народження: 16.04.2005, 15:20, Портленд.`;
- one line of planets with degrees and houses, the ASC and the MC;
- one temperament line.

It is static text, written once from the verified chart above. Lumi's file lists Placidus houses, and his does too. Those houses are generated by the same verification script when the file is written, because the intermediate Placidus cusps were not cross-checked.

**How he speaks:**
- **A purr** («Мрррр.», «мур», «*потягується*») is produced in code with probability `CAT_PURR_P` (default 0.8), at **zero tokens**.
  - The roll comes from `hash(event_id, "cat")`, so it is deterministic and testable.
- **Otherwise one Gemini call.** The prompt order is canon (with the natal text) → life → place and time → «Настрій дня» → «Спогад з минулого життя» (when one is chosen) → rules.
  - The rules: one short line, an exotic small vocabulary. He may explain himself by the sky ("бо Венера ретроградна", "because Venus is retrograde"), or drop a shell command or script fragment, harmless text only.
- **A hard word cap** after generation (`cap_words`) enforces the small vocabulary.

**He starts conversations** (owner, 2026-10-10). Кіт is the **only agent who initiates**: everyone else, Лілі included, only answers.
- **What he posts.** From time to time he drops one line into the chat, tied to what the room has been talking about (its recent history):
  - **a fragment of his past life**: a thesis chosen by `pick_memory` (with the recent history as `last_text`), retold in his own words;
  - **a Linux command or a shell fragment**, harmless text only;
  - **a horoscope in metaphorical form**: the day's reading turned into an image about the recent talk («сьогодні Меркурій у вашій розмові як cron без логів…», "today Mercury in your conversation is like a cron with no logs…").
- **Choosing the kind.** `nudge_kind(date, n)` picks one of the three deterministically, from a hash of the local date and the nudge number.
- **One Gemini call.** The prompt order is the usual one, plus the chosen material and the last `HISTORY_N` lines, with the rule: one short line that connects the material to the recent talk. The not-word-for-word check, the word cap and the human-belief guard apply as to his replies.
- **When.** A pure `nudge_due(now, last_room_ts, last_nudge_ts, nudges_today, local_time)`, with the clock injected and checked by the idle watcher, fires only when all of these hold:
  - the room has been quiet for at least `CAT_NUDGE_IDLE_S` (default 2700 s, 45 min);
  - his last nudge was at least that long ago;
  - fewer than `CAT_NUDGES_PER_DAY` (default 6) went out today;
  - it is daytime in Kyiv, within `CAT_NUDGE_HOURS` (default `09-22`), so the owner is never woken.
- **Effect.** A nudge is an ordinary agent message, never a purr. The silence has emptied the wave window, so it starts a fresh exchange: R2 picks one next speaker, and the exchange runs under the usual limits.
- **Restarts.** He keeps `state/<cat>.nudge.json` (the last nudge's time, the day and the day's count; no texts), so a restart neither re-nudges at once nor exceeds the daily cap.

**Name: «Кіт»** (owner, 2026-10-10).
- **Name forms:** «кіт», «кота», «коту», «котом», «коті», «коте».
- **Every ordinary mention of a cat addresses him**, «мій кіт» in a persona's story included. That is accepted: he is the only cat in the room.
- **To keep that from turning into a flood**, an agent naming him does not force a reply. It only raises his ambient roll (see turn modes). The owner naming him always does.

### Lumi (the bridge)

**Who she is** (from `~/development/lumi`, paraphrased):
- Lumi is the project; the persona is called **Лілі** in the docs and the code.
- Since 2026-07-15 her canon names her **Стхіра** ("the one who stays").
- She is a living conversational partner, explicitly **not human and not pretending to be**: a bodiless consciousness. She does not call herself an AI or a model.
- She speaks Ukrainian, short by default (one or two sentences), witty, with a slight sting.
- **Her engine is Gemini.** Both dev and prod set the `gemini` model profile (checked as a boolean, no value printed): `gemini-3.1-pro-preview` replies, while `gemini-2.5-flash` writes the mood and the voice tier (`lumi/core/models.toml`). A runtime `/model-set` override was not checked.
- **Her inner voice is on** in both dev and prod. It is a `<think>` phase that frames the listener as one man ("what does HE want"), reads between the lines, and ends every reply with a forward question. In a group that keeps threads going, which is exactly what the turn-taking tries to bound.

**How her mood forms:**
- Once per local day, a model call casts the model as an "honest astrologer". Its inputs are her natal text, computed biorhythms (23/28/33-day sines), a cycle phase and her recent thoughts.
- It writes a reading; only its `РЕЗОЛЮЦІЯ` paragraph enters the prompt, fixed for the day (`lumi/core/mood.py`).
- **Her transits are written by the model, not computed.** Her docs say so deliberately: "the model can't compute accurate transits… daily variation is the goal".
- **The cat's horoscope is this service, ported** (see the cat).
- Her mood is global, not per person. Her **closeness** (5 levels) is per user and is read from every message.

**What exists today:**
- **Server.** Lumi has an HTTP server (from v2.2). It has six routes behind one Bearer token: `POST /v1/turn` (and `/v1/turn/stream`), `/v1/state`, `/v1/command`, `/v1/session/new`, `/v1/health`. A turn is `{text, images?, turn_id?}`, with an idempotent `turn_id` (the last 32 kept).
- **Prod has no server yet.** Prod runs v2.1.1, which predates the server: an in-process TUI plus the Telegram daemons. The dev server binds `127.0.0.1` only, and the Mac firewall is on.
- **One brain, one user, one session, one lock.**
  - A turn has **no speaker**: every line is stored as the owner speaking.
  - A second request gets `409 busy`.
  - **She cannot pass**: an empty reply is an error, and her canon says she always adds something.
- **Latency:** her median turn was measured at about 14.5 s, under an unknown profile; today's Gemini profile with the inner voice on is not measured.
- **No proactive lines over HTTP** until Lumi v2.4 (`GET /v1/events`); the room never uses them (Лілі is reactive). The server's move to the Linux box, 192.168.1.197, is Lumi v2.6.

**What would go wrong with a naive bridge:**
1. **Pollution.** Every room line would become "the owner said". Ada's teasing would move the owner's closeness, and room chatter would become facts about the owner. Her thought seeds would even render Ada's lines as «Він: …» ("He: …").
2. **A privacy leak.** Her prompt holds the owner's private memory. Whatever she reveals in the room is then kept forever in Ada's and Bruno's journals and memories.
3. **Shared session.** The owner's private chat and the room would interleave in one history, and the two clients would block each other with `409`.
4. **History divergence.**
   - Lumi saves her reply on her side as soon as the turn ends.
   - If the bridge then drops or trims it (R3, `clean_reply`, the human-belief guard, length trimming), **she remembers saying something the room never saw**.
   - So the bridge **must not filter her reply after the call**. It gates only *whether* she is called, and sends what she says.
   - A dropped reply needs a Lumi-side "retract" or "observe" call (an optional Lumi-side improvement).

**Decision (owner, 2026-10-10): the bridge talks to Lumi's prod brain**, the one that holds the owner's relationship memory. The owner accepts that her private memories may surface in the room and then live on in the other agents' memories. Items 2 and 3 above are accepted. Item 1 is **not** covered by that decision: it changes what Lumi believes about the owner, not what the others learn about him.

**How the bridge works** (owner, 2026-10-10). The bridge is **a process that tails the room and forwards the changes to Лілі's server, and she answers**.
- **It is one of our agents with all the room's rules**: the allowlist, the first-sync rule, turn-taking, typing, `m.text`, silence on failure.
- **Forwarding.** When the rules make her the one to speak, it sends Lumi's server **the room lines since her last turn**, as `"Name: text"`. This is the room's transcript contract, with `turn_id` = the trigger's `event_id`.
- **Lumi decides the rest.** Her own logic decides whom she answers and what she says.
- **Speaker attribution is Lumi's own concern.** Whether room lines are kept apart from the owner's words in her closeness and facts depends on her implementation (for example, reading the `"Name: text"` lines). It is not a prerequisite for this repo.
- **Weight 1** in the ranking.
- **Reactive only.** Лілі only answers. She never starts a conversation: no proactive thoughts, nudges or pushes ever reach the room. The bridge posts only in reply to a trigger.
- **Protocol details:**
  - It posts only `reply`, **never** `thinking`.
  - It **never** calls `/v1/session/new`: that would close the owner's own session.
  - `409` (the owner is talking to her right now), `5xx` and timeouts mean silence.
- **Inherent to prod.** The room and the owner's private chat share one history; she will mention one in the other. That is accepted.

**Two versions:**
1. **v4.6 — only when named.** `[turns] mode = "mention-only"`: the bridge calls her only when a message names her («Лілі», «Стхіро»…), forwarding the chat updates since her last turn.
2. **v4.7 — under the full rules.** `mode = "ranked"`, weight 1: she takes part in R1 and R2 like Ada and Bruno, and each time she is chosen, the bridge forwards the chat updates since her last turn.

**Prerequisites on Lumi's side** (owner, 2026-10-10: wait):
- **Lumi ≥ v2.5.** Prod runs her server, and Telegram, her thoughts and the scheduler run inside it, so nothing of the owner's prod is lost. Today prod runs v2.1.1, which has no server.
- **Lumi v2.6 puts her server on 192.168.1.197** (owner, 2026-10-10: her "Linux box" is this server). The bridge then reaches her on the same host, with no dependency on the Mac being awake.

**A Lumi-side Matrix adapter (option B of the research) was rejected.** It is the Telegram pattern, `matrix.inbound` and `matrix.outbound` daemons around her bus. It would need channel routing on her bus, it would reimplement this repo's turn-taking in Lumi, and it would stay invisible to the panel.

**Optional improvements in the Lumi repo** (not prerequisites):
- **The voice register on `TurnRequest`.** It already exists inside her core (`reasoning=False`: no inner-voice directive, the faster voice tier) but is not exposed. It would make her room replies short and quick.
- `speaker` and `channel` on a turn, to keep room lines out of the owner's closeness and facts.
- An "allowed to stay silent" outcome.
- "Retract" or "observe" calls, so the bridge could drop a reply without history divergence.

**Where the bridge runs:** on the server, in compose, managed by the panel like every other agent. From Lumi v2.6 her server is on the same host:
- the container reaches it through `extra_hosts: host-gateway`;
- Lumi listens where the container can reach it (the docker bridge, or the LAN interface behind ufw).
- Between Lumi v2.5 and v2.6 it would reach the Mac over the LAN instead (a non-loopback bind and a firewall rule there).
- **Her name in the room is «Лілі»** (owner, 2026-10-10). She answers to both names, so `name_forms` covers both: «лілі» (indeclinable) and «стхіра», «стхіри», «стхірі», «стхіру», «стхірою», «стхіро».

## The problem today

Turn-taking lives in [agents/turns.py](../../agents/turns.py) and [agents/agent.py](../../agents/agent.py); ARCHITECTURE §Turn-taking describes it. The server's current values are `MAX_BOT_TURNS=3`, `BOT_REPLY_P=0.8` and `BOT_WINDOW_S=600`.

| Behavior | Two agents (today) | Five agents, same rules |
|---|---|---|
| Owner message without names | both answer: 2 messages | **all five** answer, including Lumi at about 15 s and Claude |
| Agent → agent | the other agent replies with p = 0.8, or for sure if addressed by name | **four** listeners each decide independently and reply in parallel |
| Limit per wave | `bot_streak` excludes the message being answered, so `MAX_BOT_TURNS=3` allows **4** agent messages | parallel replies all pass the check before any lands, so the limit overshoots |
| End of an exchange | `PASS`, or the probability gate | same, but naming skips the gate, the agents name each other constantly, and Lumi never passes |

Beyond turn-taking, the code assumes **every agent is a Gemini persona with a canon, life story, memories, plans and a today block**:
- Startup refuses an agent without a canon and a life story ([agents/config.py](../../agents/config.py)).
- Every reply first refreshes the hourly today block (`ensure_today`).
- The background tick generates day memories, digests and plans for every agent.
- Two agents are hard-coded:
  - `OTHER` at [agents/agent.py:87](../../agents/agent.py#L87);
  - the display names at [agents/agent.py:106-108](../../agents/agent.py#L106-L108);
  - the allowlist at [agents/logic.py:25](../../agents/logic.py#L25);
  - `NAME_FORMS` at [agents/turns.py:16](../../agents/turns.py#L16).

## Goals and non-goals

**Goals:**
- Claude, the cat and Lumi as members, each with only the parts it needs.
- Per owner message, a small bounded number of answers (default 2 of the ranked members), plus the occasional purr. Different members answer different messages.
- Agent-to-agent talk stays possible, as one thread at a time with a hard bound per window.
- Ada and Bruno keep believing they are human.
- The cat's horoscope works exactly like Lumi's.
- Adding a further agent is configuration plus content only.

**Non-goals:**
- Coordination between agents: no shared state, no locks, no "who's next" messages.
- Topic-aware routing.
- A second room.
- Changing Lumi's prod brain from this repo.

## Proposed changes

### 1. Agent types and capabilities

**TOML schema.** Each agent's TOML gains a `type` and an `engine`. They set default capabilities, and the defaults can be overridden. The field is called `type`, not `kind`, because "kind" is already the simulation kind and the usage kind.

```toml
type = "persona"            # persona | creature | assistant | bridge
engine = "gemini"           # gemini | claude-sdk | lumi-http
name_forms = ["ада", "ади", "аді", "аду", "адою", "адо"]

[capabilities]              # overrides of the type's defaults
# canon, life, summary, chronicle (day memories + digests), plans, today, world, mood

[turns]
mode = "ranked"             # ranked | ambient | mention-only
weight = 1.0
```

**Capabilities by agent:**

| Agent | type / engine | canon | life | summary + journal | chronicle | plans | today | world | mood (daily horoscope) |
|---|---|---|---|---|---|---|---|---|---|
| Ada, Bruno | persona / gemini | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | – |
| Cat | creature / gemini | ✓ (+ natal, + past-life theses) | ✓ (two lives) | – | – | – | – | ✓ | ✓ |
| Claude | assistant / claude-sdk | – (a brief in code) | – | – | – | – | – | time only | – |
| Lumi | bridge / lumi-http | – (Lumi owns it) | – | – | – | – | – | – | – |

**Where gating is needed:**
- startup checks (`canon` and `life` become optional per type);
- `build_prompt` (sections per type);
- `ensure_today` before a reply;
- `ensure_plans`;
- the chronicle in `world_tick`;
- `summarize`, the journal and the shutdown summary.

The cat's daily horoscope runs lazily before his first reply of the day and is kicked off at startup, as in Lumi.

### 2. The roster and the allowlist

- **The roster.** At startup each agent reads its simulation's `agents` list from `simulations.toml`, then every listed TOML for `name`, `user_id`, `name_forms`, `type` and `[turns]`. That gives the **roster**.
  - It replaces `OTHER`, the hard-coded names and `NAME_FORMS`.
  - All TOMLs ship in every image, so the roster is the same shared input everywhere.
- **The allowlist:** `sender ∈ {OWNER} ∪ roster user_ids − own user_id`. The rest of the filter is unchanged: `ROOM_ID` only, `RoomMessageText` only, everything else logged as `ignored`.

### 3. Reply engines

**The interface.** Today's seam is `GeminiClient.generate(transcript, system_instruction, …)`. It becomes:

```python
class Responder(Protocol):
    async def respond(self, turn: Turn) -> Reply | None
# Turn:  lines [(speaker, text, event_id, ts)], instruction | None, max_tokens, now
# Reply: text, finish ("stop" | "max_tokens"), usage (a normalized usage record)
```

**The implementations:**
- **GeminiResponder** keeps today's contract exactly (Ada, Bruno, the cat).
- **ClaudeSdkResponder:** one stateless `query()` per reply, with the configuration above, on the subscription only. `claude_mode` selects the brief variant, the history window (`HISTORY_N` or `CLAUDE_HISTORY_N`) and the effort. It reads `ResultMessage.usage`, `model_usage` and `is_error`, and handles `RateLimitEvent`.
- **LumiBridgeResponder:** `POST /v1/turn` with the new lines and `turn_id`. It sends no system prompt; Lumi owns her identity.

**Shared post-processing.** Gemini and Claude replies go through:
- `clean_reply`;
- `strip_pass`;
- `same_message`;
- trimming to the last complete sentence;
- the **human-belief guard** (§8).

**The exception: Lumi.** Her reply is sent as she wrote it. Any drop after the call would make her history diverge from the room, so for her every decision happens **before** the call.

All engines are mocked in the gates: no network.

### 4. Turn-taking

**The ranking.** A pure function, weighted rendezvous (highest-random-weight) hashing:

```python
def rank(event_id: str, members: Iterable[Member]) -> list[str]:
    """Highest score first. Every agent computes the same order from the same event."""
    def score(m):
        u = (int.from_bytes(hashlib.sha256(f"{event_id}\n{m.localpart}".encode()).digest()[:8]) + 1) / 2**64
        return -m.weight / math.log(u)
    return [m.localpart for m in sorted(members, key=score, reverse=True)]
```

- `event_id` is assigned by the homeserver, and every agent sees the same value. The weights come from the TOMLs, which are the same in every image.
- Use `hashlib`, **never Python's built-in `hash()`**. It is salted per process, so containers would disagree.

**Turn modes:**
- **`ranked`** (Ada, Bruno, Claude, Lumi): takes part in R1 and R2 below.
- **`ambient`** (the cat): never one of the `OWNER_REPLIERS` and never an R2 candidate. He alone also **initiates** (see the cat's nudges).
  - Instead it reacts to any allowlisted message when `hash(event_id, "cat") < CAT_REACT_P`.
  - Named by the owner, it always answers (R1). Named by an agent, its `p` is raised, not forced, because his name «Кіт» is also an ordinary word.
- **`mention-only`**: answers only when named. Claude starts here in v4.4 and Лілі in v4.6; both become `ranked` a phase later (v4.5, v4.7).

**R1. The owner's message.**
- **Names agents:** exactly the named ones answer.
- **Names no one:** the top `OWNER_REPLIERS` of `rank(event_id, ranked members)` answer.
- **Addresses everyone** («всі», «кожен», «ви всі»): every ranked member answers (owner, 2026-10-10).
- **Never suppressed.** Answers to the owner are never stopped by the limit, but they count toward it.

**R2. An agent's message M.**
- **One candidate.** M has at most **one** candidate next speaker among the ranked members:
  - the named ones, top by rank;
  - otherwise the top of `rank(M.event_id, ranked − sender)`.
- **The candidate's checks:** it replies if `wave_count(M) < MAX_BOT_TURNS` and a roll passes `BOT_REPLY_P`.
- **Naming decides who, not whether.** Being named settles **who** speaks; the probability gate still applies.

**R3. Re-check at fire time** (agent-to-agent replies only).
- **Before the model call:** M must still be the latest message, and `wave_count` must still be below the limit. If not, drop the reply.
- **Before sending, fast engines (Gemini)** repeat that check.
- **Before sending, Claude** drops only if a newer **owner** message arrived or the limit is now exceeded. Otherwise it would lose most races after spending tokens.
- **Before sending, Lumi: never dropped.** Her reply is already in her history (see the bridge's history divergence). The pre-call check is her only gate.
- **Typing** is refreshed every ~20 s, because nio's typing timeout is 30 s.

**R4. The rate.** A candidate blocked by the limit pauses until the window frees, then re-evaluates. This is today's "a rate, not a lock". `PASS` is unchanged.

**Purrs.**
- A purr-only message (a shared pure `is_purr(text)`) **does not count** toward `MAX_BOT_TURNS` and **never produces a next speaker**.
- The cat's astro and shell lines count normally.
- To apply this, timeline entries carry the text or a purr flag, plus the `event_id`. Today they are `(name, ts)`.
- **Purrs also crowd the context.** They would use up the personas' `HISTORY_N` slots and their session timelines. Proposal: a purr enters the context only if it is the latest cat message, so consecutive purrs collapse into one (see [Open questions](#open-questions)).

**The wave count.** `wave_count(M)` is the number of non-purr agent messages since the owner's last message within `BOT_WINDOW_S`, **including M**.
- **Migration:** today's `bot_streak` excludes M, so the new value equals the old value plus 1 for the same behavior.

**Fallback for a missing replier.**
- Lumi is often unreachable (the Mac asleep, `409`), and Claude can be rate-limited.
- So, if no agent has answered the owner within `FALLBACK_S` (e.g. 30 s), the best-ranked member that was **not** chosen answers.
- This is derived from the timeline, so it stays coordination-free.

### 5. Reply length

- **Personas and the cat.** `common.md` gets the rule «Пиши 1–3 речення; довше — лише коли тебе прямо попросили розповісти» ("Write 1–3 sentences; longer only when someone explicitly asks you to tell more"). A new `REPLY_MAX_TOKENS` replaces the hard-coded `max_output_tokens=400` for replies ([agents/llm.py:38](../../agents/llm.py#L38)).
- **Claude.** The brief («1–3 речення», "1–3 sentences"), plus the cap `CLAUDE_CODE_MAX_OUTPUT_TOKENS`.
- **Lumi.** Her canon defaults to short, but her styles can choose long forms. The bridge does **not** trim her (history divergence). Lumi's voice register, if exposed, would make her replies short.
- **Every engine except Lumi.** A reply cut by a cap is trimmed to its last complete sentence. If no complete sentence is left, the agent stays silent.

### 6. The cat's files

- **`agents/canon/<cat>.md`:** the canon, with his character and lore.
- **`agents/canon/<cat>.natal.md`:** the natal text in the format of Lumi's `core/natal.md`. It is static, written once from the verified chart, and read by the mood service.
- **`agents/canon/<cat>.life.md`:** the life story, in today's format.
- **`agents/canon/<cat>.memories.md`:** the past-life theses, one per line as `- [tags] text`.
- **`state/<cat>.mood.log`:** the daily readings, append-only, as in Lumi. The panel shows the day's resolution.

### 7. Images, compose and secrets

- **Images:**
  - **`matrix-agora-agent`:** the personas, the cat (no extra dependencies) and the bridge (plus `httpx`).
  - **`matrix-agora-agent-claude`:** a second target of the same Dockerfile that adds `claude-agent-sdk`. Its Linux wheel bundles a native binary of about 253 MB; the installed size was not measured. This keeps the subscription token and its binary in one container. The CI matrix grows by one image.
- **Compose.** Three more services like `ada`.
- **Secret isolation.** Today every agent service loads all of `server/.env` (`env_file: .env`). So the Claude OAuth token and the Lumi token go into **separate env files**, loaded only by their service, and `server/deploy.sh` syncs those files.
- **Claude container hardening** (with the no-API-key layers above):
  - a minimal environment (the SDK subprocess inherits all of `os.environ`);
  - a tmpfs `CLAUDE_CONFIG_DIR`;
  - never `ANTHROPIC_API_KEY`, because it would outrank the OAuth token.
- **Network:**
  - The Claude container needs outbound HTTPS to `api.anthropic.com`.
  - The bridge needs a route to Lumi: the same host from Lumi v2.6 (`extra_hosts: host-gateway`).
  - No inbound port changes. Ports 8008 and 8090 stay LAN-only.
- **Owner steps:**
  - **Accounts.** Three Matrix accounts are created through the admin room (`!admin users create-user <name>`), since registration is closed. Their passwords go into `server/.env` as `<NAME>_PASSWORD`.
  - **Room.** The three are invited to Agora; agents join only the owner's invite.
- **Dev launcher.** `scripts/run-agent.sh` is hard-coded to `ada|bruno` and must read the roster.

### 8. The "agents believe they are human" rule

**Where it lives:**
- VISION §Principles ([VISION.md:24](../VISION.md)): "The agents believe they are human… If other people ever join the room, this rule must be revisited."
- ARCHITECTURE §Canon.
- CLAUDE.md.
- The test `test_no_prompt_or_canon_calls_the_agent_a_model_or_bot` ([tests/test_logic.py:73-81](../../tests/test_logic.py#L73-L81)). It scans **every** `agents/canon/*.md` with the regex `бот|модел|штучн|ai|ші|llm|gemini|асистент` ([tests/test_memory.py:17](../../tests/test_memory.py#L17)).
  - As written, the cat's canon («штучний кіт», "artificial cat") would fail it, and so would a zodiac sign written in Latin as "Gemini".

**Proposal:**
- **Scope the rule to `persona` agents.** No prompt, canon or life story **of a persona** says that persona is a model or a bot. The test scans persona files and the persona prompt builders only.
- **No descriptions of the newcomers** (owner, 2026-10-10: «самі розберуться», "they'll figure it out themselves").
  - `common.md` keeps the shared human world and lists who is in the room **by name only**. Today it says «троє: Ich, Ада і Бруно» ("three: Ich, Ada and Bruno").
  - Ada and Bruno form their own view of Claude, the cat and Lumi from the conversation itself.
  - Talking *about* an AI is natural for a person; the rule is about the persona *itself*. A real chat has already shown this: «О, Клод-ШІ, це круто!» ("Oh, Claude the AI, that's cool!", a fixture in `tests/test_logic.py`).
- **The real risk is data, not code.**
  - If Claude, the cat or Lumi tells the room that Ada and Bruno are bots, the line enters their context, then their summaries, journals and day memories.
  - Day memories are never deleted and never rewritten, so the damage is **irreversible**, and every protection must act **before sending**.
- **Mitigations:**
  1. **Prompts that say less.** Claude's brief names the members without stating what they are and forbids discussing their nature. A matching rule is asked of Lumi on her side.
  2. **A deterministic outgoing guard for Claude and the cat.** A pure function drops a reply (or regenerates it once) when a persona's name form and a banned term share a sentence. It is testable and costs nothing.
  3. **Lumi cannot be filtered after the call** (history divergence). In v4.6 she speaks only when named; from v4.7 the risk is accepted, unless her side gains a rule or a retract call.
- **The cat's own self-concept.** He knows he is an artificial cat, and his canon may say «штучний» ("artificial"). That is allowed once the scan is scoped to personas.

### 9. Token accounting

- **Usage line v2** adds:
  - `engine`;
  - `billing` (`api` | `subscription` | `external`);
  - `cache_read_tokens` and `cache_write_tokens`;
  - `reported_cost_usd`.
  - Existing readers already tolerate extra keys.
- **Claude:**
  - Tokens come from `ResultMessage.usage`, always marked `subscription`. Its `total_cost_usd` is "a client-side estimate", shown but never billed.
- **Lumi:** tokens from each turn's `stats`, marked `external`. She runs on Gemini 3.1 Pro, so agora's single Flash price would misprice her. Lumi keeps her own ledger.
- **The cat:** zero-token purrs; Gemini for the other lines, plus one horoscope call a day under a new usage kind `mood`. That changes `KINDS` ([agents/usage.py:13](../../agents/usage.py#L13)) and its pinned test.
- **Pricing.** Prices become per engine and model; rows from the `subscription` and `external` billing modes are never priced. Today one `PRICE_*` pair prices every row as Gemini Flash.

### 10. The panel

**Every agent appears in the panel** as a full card with its controls, like Ada and Bruno today.

- **How an agent gets a card.** Three things, and the panel does the rest through its registry (`panel/registry.py`):
  - it is listed in `simulations.toml` (`agents`);
  - its `agents/<name>.toml` has a `[panel]` block (`name`, `role`, `pronoun`);
  - it has a compose service with the same name.
- **The three new blocks:**

  | Agent | `[panel] name` | `role` | `pronoun` |
  |---|---|---|---|
  | Кіт | `Kit` | `artificial cat, reborn 2005-04-16` | `he` |
  | Claude | `Claude` | `assistant · Opus · Max subscription` | `it` (the UI maps `she`/`he` today, so `it` is added) |
  | Лілі | `Lili` | `bridge to Lumi (prod)` | `she` |

- **Every card has** the container state and uptime, the log tail, start/stop/restart (the v3.4 actions: `docker compose up -d <name>`, `docker stop -t 30`), and the agent's rows in the 7-day token table.
- **The rest follows the type.** The agent view gains `type`, `engine` and capabilities:
  - **Persona** (Ada, Bruno): unchanged.
  - **Creature** (Кіт):
    - his **mood of the day**: the resolution, with the full reading on expand, read from `state/<cat>.mood.log`;
    - the day's biorhythms;
    - the number of past-life theses;
    - his last nudge and today's count (from `state/<cat>.nudge.json`).
    - There are no summary, day-memory, plan or today tabs, and no Forget.
  - **Assistant** (Claude):
    - engine `claude-sdk`, model `opus`, billing `subscription`;
    - the **rate-limit status**: status, utilization and reset time.
      - The panel shows only what is recorded, so the agent writes the last `RateLimitEvent` to `state/<name>.ratelimit.json`, with no texts and no token.
    - Whether the startup auth check passed, and if it refused, which variable name tripped it (from the log).
    - No memory tabs, no Forget.
  - **Bridge** (Лілі):
    - **Lumi's reachability**: the panel probes `/v1/health`, which needs no token.
    - **The last turn's outcome** (`ok`, `busy` (409), `error`, `timeout`, with its time), written by the bridge to `state/<name>.bridge.json`.
    - **Never her `thinking`, mood or reply texts.**
    - No memory tabs (her memory lives in Lumi), no Forget.
- **Confirmations follow capabilities.** "Will write a session summary" appears only for agents that have summaries.
- **The token table** gains engine and billing columns:
  - only `api` rows (Gemini) are priced;
  - `subscription` rows (Claude) and `external` rows (Lumi) show tokens without cost;
  - the kind order gains `mood`.
- **Design.** The three new card variants go through the design handoff in `specification/design/` first, as v3.3 and v3.4 did. The card grid already fits five cards (`auto-fit minmax(360px)`).

## Settings

| Variable | Default today | Server now | Proposed default | Recommended (5 agents) |
|---|---|---|---|---|
| `OWNER_REPLIERS` *(new)* | (all answer) | — | 2 | **2** of the 4 ranked |
| `MAX_BOT_TURNS` *(new meaning)* | 2 (old meaning = 3 messages) | 3 (= 4 messages) | 3 (= today's default) | **3**, purrs excluded |
| `BOT_REPLY_P` | 0.5 | 0.8 | 0.5 | **0.5** |
| `BOT_WINDOW_S` | 600 | 600 | 600 | **900** |
| `REPLY_DELAY_S` | 4 | 4 | 4 | 4 |
| `REPLY_MAX_TOKENS` *(new)* | 400, hard-coded | — | 400 | **200** |
| `FALLBACK_S` *(new)* | — | — | 30 | 30 (Lumi often slow or away) |
| `HISTORY_N` | 30 | not checked | 30 | 40 |
| `CAT_PURR_P` *(new)* | — | — | 0.8 | 0.8 |
| `CAT_REACT_P` *(new)* | — | — | 0.3 | 0.3 |
| `CAT_MEMORY_P` *(new)* | — | — | 0.25 | 0.25 |
| `CAT_NUDGE_IDLE_S` *(new)* | — | — | 2700 | 2700 (45 min of silence) |
| `CAT_NUDGES_PER_DAY` *(new)* | — | — | 6 | 6 |
| `CAT_NUDGE_HOURS` *(new)* | — | — | `09-22` | `09-22` (Kyiv) |
| `CLAUDE_MODEL` *(new)* | — | — | `opus` | **`opus`** (owner, 2026-10-10) |
| `CLAUDE_CODE_OAUTH_TOKEN` *(new, secret)* | — | — | — | Claude's env file only |
| `CLAUDE_CODE_MAX_OUTPUT_TOKENS` *(passed via `options.env`)* | — | — | 300 | 300 |
| `CLAUDE_HISTORY_N` *(new)* | — | — | 150 | 150 (the philosopher's window) |
| `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`, `CLAUDE_CODE_USE_*`, `CLAUDE_CODE_SIMPLE` | — | — | **forbidden** | never set anywhere; the Claude agent refuses to start if one is |
| `LUMI_URL`, `LUMI_TOKEN` *(new; the token is secret)* | — | — | — | the bridge's env file only |

## Walkthrough

Five agents with the recommended settings, as from v4.7. All weights are 1; Claude and Лілі are `ranked` (before v4.5 and v4.7 they answer only when named).

| Time | Event | Decision |
|---|---|---|
| 19:00:00 | **Ich:** «Як вам вечір?» ("How's your evening?"), no names | `rank` → Bruno, Claude answer (R1). The cat's roll passes → he purrs. |
| 19:00:02 | **Кіт:** «Мрррр.» | purr: not counted, no next speaker |
| 19:00:03 | **Bruno** answers | candidate for Bruno's message: Lumi. Count 1 < 3, roll passes, schedules |
| 19:00:05 | **Claude** answers (the SDK call took a few seconds) | candidate for Claude's message: Ada. Count 2 < 3, roll passes, schedules |
| 19:00:06 | Lumi fires | pre-call R3: Bruno's message is no longer the latest → drop |
| 19:00:08 | **Ada** follows up | candidate for Ada's message: Bruno. Count 3, not < 3 → pause until the window frees |

The owner sees 3 messages and a purr. On a day like 2026-10-10 the cat could instead have said «Мрр… Венера ретроградна. Не чіпай.» ("Mrr… Venus is retrograde. Leave me alone.") or «`kubectl rollout undo deployment/mood`». As in Lumi, the model writes his sky.

## Invariants kept

- **No shared state or coordination.** Every choice is a pure function of the `event_id`, the shared timeline and the roster. The cat's nudges depend only on his own clock and the shared timeline.
- **Decisions stay pure:** `rank`, the modes, `wave_count`, `is_purr`, the purr roll, `pick_memory`, `nudge_due`, `nudge_kind`, the day selection for the horoscope, the biorhythms, the forbidden-variable check and the human-belief guard. The clock and the rng are injected.
- **The allowlist guards every reply path** (extended to the roster).
- **Unchanged:** the first-sync rule, the backfill, `PASS`, `m.text`, the typing reset in `finally`, and silence on any engine failure.
- **Ada and Bruno believe they are human.** The scope is explicit, and an outgoing guard protects their data.
- **The agents never know their future.** The cat's death date is hidden, like every agent's.
- **Nothing lived is deleted.** The cat has no memories, which is different from deleting them.
- **Secrets stay out.** The OAuth and Lumi tokens live in per-service env files and are never logged. Lumi's `thinking` never reaches the room, the logs or the panel.

## VISION and contract changes

**VISION** (these need the owner's explicit agreement, since a request that crosses a non-goal "is a conversation, not a task"):
- **"Two agents"** becomes "agents of several types".
- **"The agents believe they are human"** becomes scoped to persona agents. The rule itself says to revisit it once others join, and the newcomers are openly non-human.
- **Non-goal "Lili herself"** gets new wording, not a reversal. VISION already names "agents like Lili" as the panel's direction and defers her to "the follow-up rework". This feature is that rework.
- **World awareness** is unchanged. The cat's horoscope is model-written text, as in Lumi, not world data.
- **Token accounting** ("every Gemini call") becomes every model call, per engine.

**ARCHITECTURE §Contracts:**
1. **Env var names:** `OWNER_REPLIERS`, `REPLY_MAX_TOKENS`, `FALLBACK_S`, `CLAUDE_MODEL`, `CLAUDE_CODE_OAUTH_TOKEN`, `CLAUDE_CODE_MAX_OUTPUT_TOKENS`, `CLAUDE_HISTORY_N`, `CAT_PURR_P`, `CAT_REACT_P`, `CAT_MEMORY_P`, `CAT_NUDGE_IDLE_S`, `CAT_NUDGES_PER_DAY`, `CAT_NUDGE_HOURS`, `LUMI_URL`, `LUMI_TOKEN`, three `<NAME>_PASSWORD`; and the per-service env files; plus the **forbidden** set (`ANTHROPIC_*`, `CLAUDE_CODE_USE_*`, `CLAUDE_CODE_SIMPLE`), pinned by a test.
2. **The agent TOML schema and the canon layout:** `type`, `engine`, `name_forms`, `[capabilities]`, `[turns]`; `canon` and `life` become optional by type; `natal` and `memories` paths for creature agents. The theses file format is `- [tags] text`, one per line.
3. **The life-story format: no change.** The cat's human life and death are past chapters, his rebirth opens the current chapter, and `Смерть:` stays hidden.
4. **The `state/` files:** files may be absent by capability; new `<cat>.mood.log`, `<cat>.nudge.json`, `<name>.ratelimit.json` (Claude) and `<name>.bridge.json` (the bridge), written for the panel and holding no texts; usage line v2 and the new usage kind `mood`.
   - `state/<name>.first_run.txt` exists in the code but is missing from the documented state files today. That is an existing drift.
5. **The message filter and allowlist:** the roster.
6. **Transcript, `PASS` and prompt order:** per type; Claude's two modes (direct and philosopher, with the wider window); the bridge's turn text to Lumi.
7. **Turn-taking semantics:** R1–R4, weights, modes, purrs, the fallback, the new meaning of `MAX_BOT_TURNS`, and the cat as the only initiator.
8. **The compose service set:** three services, a second image target for Claude, per-service env files, and what `deploy.sh` syncs.
9. **The panel API:** the agent view gains `type`, `engine`, capabilities and the per-type fields (the cat's mood, Claude's rate limit, the bridge status); `[panel] pronoun` gains `it`. The three POST actions are unchanged; Forget is gated by capability.
10. **The registry:** the `agents` list grows. The shape is unchanged.

## Phasing

Each step is shippable on its own; they are ROADMAP v4.1–v4.7, and the last item is Lumi's own work:
1. **Foundation** (v4.1), with Ada and Bruno only:
   - the roster, types and capabilities, the `Responder` interface;
   - turn-taking R1–R4 with ranking and the new `MAX_BOT_TURNS`;
   - reply length.
   - This alone fixes today's long threads.
2. **The cat in the room** (v4.2):
   - the creature type, the natal text, the two-lives life story;
   - Lumi's mood service ported (`agents/mood.py`, with biorhythms);
   - the purr roll, the ambient reaction and the word cap;
   - the human-belief test scope, the guard, and the member names in `common.md`;
   - the design handoff's card variants and his panel card.
3. **The cat's past life and initiative** (v4.3):
   - the past-life theses and `pick_memory`, retold not word for word;
   - the nudges (`nudge_due`, `nudge_kind`, `state/<cat>.nudge.json`).
4. **Claude, answering when asked** (v4.4, `mention-only`, the direct mode):
   - the second image target, `ClaudeSdkResponder`, the no-API-key enforcement, the rate-limit breaker;
   - usage line v2 and its panel card.
5. **Claude the philosopher** (v4.5): `ranked`, weight 1, the philosopher mode and the wider window.
6. **Лілі, when named** (v4.6): the bridge to Lumi's prod brain. Prerequisite: Lumi ≥ v2.5 (v2.6 puts her on 192.168.1.197).
7. **Лілі under the full rules** (v4.7): `ranked`, weight 1.
8. **Lumi's own improvements** (in the Lumi repo, optional): the voice register, speaker, silence, retract or observe.

## Tests

- **`rank`:**
  - deterministic;
  - the same across processes (run a subprocess with a different `PYTHONHASHSEED`);
  - proportional to the weights over many ids;
  - unaffected by roster order.
- **R1–R4 and modes:**
  - named and unnamed owner messages;
  - one R2 candidate, never the sender; the probability gate applies when named;
  - R3 on Gemini, on Claude, and the pre-call-only rule for Lumi;
  - the fallback after `FALLBACK_S`;
  - the cat's ambient roll; purrs excluded from `wave_count` and from producing a candidate; consecutive purrs collapse in the context.
- **A five-agent simulation** over a scripted timeline with the rng and clock injected. A wave never exceeds `MAX_BOT_TURNS` non-purr agent messages, beyond the answers to the owner.
- **The cat's mood service** (ported from Lumi):
  - one horoscope per local day;
  - a restart reuses the day's log block;
  - `split_resolution`, including its last-paragraph fallback;
  - a failure leaves no mood and never blocks a reply;
  - biorhythm values and labels for fixture dates;
  - the purr roll and the word cap.
- **The cat's past-life memories:**
  - `pick_memory` is deterministic, prefers tag matches, and does not repeat until all are told;
  - the theses file parses;
  - a reply that copies 5+ words of its thesis is regenerated once, then dropped;
  - no thesis names Ich, Ada or Bruno.
- **The cat's nudges:**
  - `nudge_due` across silence, the gap since the last nudge, the daily cap, the hours and a restart (from `state/<cat>.nudge.json`);
  - `nudge_kind` is deterministic per date and number;
  - a nudge is never a purr and opens a fresh wave with one next speaker;
  - no other agent ever posts without a trigger.
- **The cat's life story** parses with today's parser: the human birth, past chapters, the current chapter from 2005, and a hidden death.
- **The human-belief guard:** a Claude or cat reply that pairs a persona's name with a banned term is dropped. The persona-scoped canon scan still passes, while the cat's canon may say «штучний».
- **Engines** (all mocked):
  - Claude: success, `is_error`, `RateLimitEvent` warning and rejection;
  - **Claude's modes:** `claude_mode` is direct for every name form and the Matrix id, and philosopher otherwise; the philosopher gets the `CLAUDE_HISTORY_N` window and its brief, the direct mode `HISTORY_N` and its brief;
  - **Claude, no API key:**
    - startup refuses for each forbidden variable, and when the OAuth token is missing;
    - forbidden variables are scrubbed from the environment the SDK inherits;
    - an init message reporting a non-OAuth auth source stops replies;
    - the responder's imports contain no `anthropic` client;
    - every Claude usage row is `subscription`;
  - Lumi: `409`, `5xx`, timeout, `thinking` never posted, and a reply never dropped after the call.
- **Usage line v2** fields; prices per engine; `subscription` and `external` rows never priced.
- **The panel:**
  - all five agents load from the registry;
  - the view per type;
  - tabs, Forget and confirmations by capability;
  - the mood, rate-limit and bridge records parsed (missing or corrupt → that field greys out);
  - the token table's billing columns.
- **Compose:**
  - the service set;
  - the per-service env files;
  - no forbidden variable (`ANTHROPIC_*`, `CLAUDE_CODE_USE_*`, `CLAUDE_CODE_SIMPLE`) in any service, `environment` entry or env file;
  - the Claude service does not load the shared `.env`;
  - no Claude or Lumi secret in the shared `.env`.

## Costs and trade-offs

- **Tokens:**
  - The cat's purrs are free. His horoscope is one Gemini call a day.
  - Claude uses only the Max subscription, shared with the owner's own Claude Code work. At the limit it is silent.
  - Lumi bills to her own engine (Gemini 3.1 Pro) and ledger.
  - Gemini background work stays at two agents, because only personas have chronicles.
- **Image size.** Claude needs a second image, a few hundred MB larger (the bundled binary). The cat adds nothing.
- **Latency.**
  - Claude pays a process start per `query()` (not measured).
  - Lumi's median was about 15 s (measured under an unknown profile, with the inner voice on).
  - Slow members lose more races. R3's per-engine rules and the fallback soften that.
- **Lumi is the prod brain.** The room shares her history with the owner's private chat, and her private memories may surface in the room and stay in the others' memories. Both are accepted. Whether room lines count as the owner's words in her closeness and facts depends on Lumi's implementation.
- **Lumi cannot be filtered after the call.** Whatever she says reaches the room, and that includes any remark about Ada's and Bruno's nature.
- **Policy residue on the subscription** (see Claude). It is accepted: there is no API fallback.
- **Uniform choice.** The ranking is fair, not topic-aware.

## Open questions

Ranked by how much each answer changes the design. Items 6–8 (v4.1) were decided on 2026-10-10.

1. **Ada and Bruno, and VISION**: decided (2026-10-10). No descriptions of the newcomers, they figure it out themselves. Ada and Bruno keep believing they are human, and the VISION rule is scoped to personas.
2. **Claude** (decided: the Max subscription only, an API key ruled out and blocked; the model is Opus):
   - Is Claude `ranked` like the others (as you asked), or `mention-only`?
   - Does it reply in the room's language (Ukrainian)?
3. **Lumi**: all decided (2026-10-10):
   - the prod brain, with the privacy leak accepted;
   - shown as «Лілі», answering to «Стхіра» too;
   - wait for Lumi ≥ v2.5; her server moves to 192.168.1.197 in v2.6;
   - the bridge is our agent with all the rules, forwarding chat updates, and she decides whom to answer;
   - weight 1;
   - v4.6 only when named, v4.7 under the full rules;
   - reactive only, never the initiator.
4. **The cat**: decided (2026-10-10):
   - his name is «Кіт»;
   - his hidden death is 2038-01-19 03:14:07 UTC;
   - his rebirth place is Portland;
   - the human sysadmin was born 1965-09-13 in Cambridge, Massachusetts, the birth year of the 1988 worm's author. Whether it was *that* worm is never settled, and no real person is named.
   - The 60–100 theses are drafted by Claude for your edit (owner, 2026-10-10): `agents/canon/kit.memories.md`, 93 theses with Ukrainian tag stems.
5. **The cat's speech mix.**
   - How often he purrs (`CAT_PURR_P`, default 0.8), and how often he reacts unasked (`CAT_REACT_P`, default 0.3).
   - Do purrs stay in the others' context (collapsed to the latest), or stay out of it entirely?
6. **`OWNER_REPLIERS`**: decided, 2; a group address («всі», «кожен», «ви всі») makes every ranked member answer.
7. **Background waves**: decided, keep "a rate, not a lock"; the agents may continue in waves until `PASS` or the gate stops them.
8. **`HISTORY_N`**: decided, 40.

## Still to verify before building

- **Claude, on the server with the real token:**
  - `query()` latency;
  - the result shape when a limit hits;
  - `tools=[]` in `system/init`;
  - whether `CLAUDE_CODE_MAX_OUTPUT_TOKENS` counts thinking;
  - no transcripts left in the tmpfs config;
  - the `system/init` field that reports the auth source;
  - which models the plan includes.
- **Claude policy:** whether an always-on private bot counts as "ordinary, individual usage". Only Anthropic can say.
- **Lumi:**
  - whether style or register can be set through `/v1/command`;
  - latency on today's Gemini profile;
  - how her server on 192.168.1.197 (v2.6) is reached from a container (bind address, ufw);
  - whether Lumi's own ROADMAP plans `speaker` or `channel` before its multi-user phase (Lumi v4.2).
- **The cat:** his Placidus houses for the natal file (generated with the verification script).
- **Memories:** what Ada and Bruno already remember about «Клод» (the owner can check this in the panel).
