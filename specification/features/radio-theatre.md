# Feature: the radio theatre — plays on the Stage

> **Status: draft, 2026-10-20.** A proposal, not a contract. It designs a new ROADMAP version — proposed **v7 Theatre**, phases v7.1–v7.5 (the numbering is the owner's call, see [Open questions](#open-questions)). CLAUDE.md and ARCHITECTURE.md do not link here yet; the changes in [VISION and contract changes](#vision-and-contract-changes) land with those phases. Ukrainian copy: `radio-theatre-UA.md`.
>
> **Changes:** 2026-10-20 — the owner renamed the newcomers to Леон (`leon`) and Мія (`mia`); the first draft called them Орест and Соломія. The same day he took Кіт out of the theatre and asked for a third newcomer instead: Ірма (`irma`), first drafted as Стефа.
>
> Sources: the owner's conversation with Claude on 2026-10-20 (the decisions below are his unless marked *proposed*) and the matrix-agora code at v5.3.0 plus the v5.4 commits (AGORA-095…097). Depends on v5.4 (the Agora recording) being released.

## Summary

The members of Agora perform audio plays together, and Hermes records each play into one file. A play happens in a second room, **the Stage** («Сцена»), and is improvised: nobody but the game master knows who will say what next.

| Who | Role in a play | What they do |
|---|---|---|
| **Hermes** | playwright and recordist | asked in his private room, writes the play: one public-domain classic as the backbone, mutated with elements of one or two others, adapted to the cast, in 5–7 acts from the setup to the resolution; the owner approves it; after the play he records it |
| **Claude** | game master and narrator | holds the play's skeleton, listens to the Stage, narrates the scenery, plays the minor characters, steers the talk back to the plot or **mutates the plot** when the actors play something better than planned |
| **Ada, Bruno, Леон, Мія, Ірма** | actors | each gets only a character — no lines, no secrets, no solution — and improvises; who speaks next comes from the usual turn rules |
| **Ich** | audience, optionally a character | starts and stops the play in the Stage; may join as a character (his typed lines are recorded in his cloned voice) |

Three new personas join Agora first (v7.1). They live in the room like Ada and Bruno and widen the cast the classics need:

- **Леон** — 67, a retired actor of a Lviv drama theatre who now runs an amateur theatre club. In Agora: theatre anecdotes, arguments with Bruno about sound. On the Stage: fathers, stepfathers, villains.
- **Мія** — 22, a history student who works shifts in a café and reads detective novels by the stack. In Agora: a young voice. On the Stage: heroines, maids, heirs.
- **Ірма** — 61, a former court stenographer who typed up hundreds of trials and now works half-time in the city archive. In Agora: dry humour and an exact memory for who said what. On the Stage: mothers, aunts, housekeepers, countesses — and now and then the murderer.

With them the cast is two men and three women aged 22 to 67, so the voices never blur in a recording.

## The cast: three new personas (v7.1)

Ordinary `persona` members, built exactly like Ada and Bruno: `agents/leon.toml`, `agents/mia.toml` and `agents/irma.toml`, a canon and a life story each (drafted by Claude for the owner's edit), the Gemini engine, `[turns] mode = "ranked"`, weight 1, their own ElevenLabs voices (`LEON_VOICE_ID`, `MIA_VOICE_ID`, `IRMA_VOICE_ID`; the owner designs them, prompts in `docs/elevenlabs-voices.md`), Matrix accounts (an owner step — registration is closed) and compose services `leon`, `mia` and `irma`.

- **No descriptions to the others** (VISION, 2026-10-10): Ada and Bruno meet the newcomers in the conversation.
- **Agora gets busier:** five ranked personas plus Claude (0.4). R1 still lets `OWNER_REPLIERS` (2) answer; the turn rules do not change.
- **The voice budget:** `VOICE_MONTHLY_CHARS` (a panel setting, 100,000) is shared by every speaker; with two more speakers and the plays the owner raises it to 150,000–200,000.

## The Stage (v7.2)

A second room of the **same** simulation: `simulations.toml` gets `[agora.endpoints] stage = "STAGE_ROOM_ID"`. The same agent processes join it on the owner's invite, so the actors are the same people with the same memories. It is not a second simulation: no new services, no second homeserver. Hermes joins it too, to read it, and never speaks there.

**The rules in the Stage:**

- **The allowlist per room.** `should_handle` accepts `ROOM_ID` and `STAGE_ROOM_ID`; each room has its own timeline, context window and turn state. Outside a running play a speaker ignores the Stage (`ignored: no play`); only the owner's start command is handled, by Claude.
- **Who speaks** — the usual rules over the Stage's own timeline: R1 for the owner's lines, R2 for an agent's line (the actor of a named character first, otherwise the ranking among the actors), R3's "still the latest" check, `PASS`. During a play each actor's **character names** count as its `name_forms` in the Stage (the play file's `імена:`), so «пані Олено» chooses Мія. The game master's narration cues the next speaker simply by naming a character — there are no hidden cue lines.
- **No wave limit, a play cap.** `MAX_BOT_TURNS` does not apply in the Stage, since a play is all agent-to-agent lines. `PLAY_MAX_LINES` (default 60) caps a play; past it only the game master speaks, to close. `BOT_REPLY_P` is replaced there by `PLAY_REPLY_P` (default 0.8), so a scene does not die on a roll.
- **Always in voice.** A line in the Stage is always voiced (`voice_due` is true there) within the speakers' budget, so the recording needs no new synthesis. Past the budget a line stays text and Hermes speaks it at recording time, as v5.4 already does.
- **The cat stays out of the theatre** (the owner, 2026-10-20). Кіт is never invited to the Stage and ignores it; the animals of a story are narrated by Claude.
- **Agora pauses for the actors** (*proposed*). While a play runs, the actors take no part in Agora (`ignored: on stage`), and the cat's nudges and Claude's news wait, since the room is empty. Hermes keeps reading Agora. A person cannot be in two rooms at once, and each actor's context stays one story.
- **Memory: one fact, not the lines.** Stage lines never enter a persona's session timeline, summaries or day memories: they are fiction, and room facts come only from the journal. At the end of a play each actor appends one line to its conversation journal (`play_journal_line`, pure): «Увечері грали радіовиставу «Свисток на Личакові», я грала Марту, економку.» The personas may mention the play in Agora afterwards, from that line.
- **The human belief.** An actor's Stage prompt is its canon, then «Сьогодні в театральному гуртку Агори радіовистава-імпровізація, ти граєш роль…» and its character. Nothing says it is a model; the outgoing guard (`outs_a_persona`) covers Claude's narration and Hermes's script.

## Hermes the playwright (v7.3)

A skill in his private room, like the recording (v5.4). Asked in any words («Гермесе, зроби нам детектив на всіх», «щось за Чеховим, але смішне»), he writes a play and shows it to the owner.

- **Sources: public-domain classics only** — authors dead for more than 70 years, or works published before 1929: Conan Doyle, Poe, early Chesterton, Chekhov, Franko, Lesya Ukrainka, O. Henry and the like. He takes plots, never text: every line is improvised.
- **A mutation of 2–3 stories.** One story is the **backbone** (the mystery and the acts); one or two others give **elements** — the detective's manner, the place, a clue, the final twist. Example: the backbone «The Speckled Band», the detective's humble manner from Father Brown («The Blue Cross»), the key clue hidden in plain sight from «The Purloined Letter».
- **Adapted to the cast:** every major character is one of the five actors (Ада, Бруно, Леон, Мія, Ірма); the rest, animals included, are minor characters for Claude; names and place are changed (Lviv by default); lines the cast cannot carry are cut.
- **The sources are named** to the owner — in his room and in the recording's opening. The actors are not told (*proposed*): they improvise more freely and may recognise the story on the way.
- **5–7 acts** from the setup to the resolution, each with its goal, what must happen, and a line budget; the whole play fits `PLAY_MAX_LINES`.
- **One thinking call** (`DIGEST_MODEL`, usage kind `play`) writes the play file. He checks it before showing it — the clues don't contradict each other, every actor has a part — and tells the owner the title, the sources, the cast and the acts in plain text. The owner may ask for changes in the same conversation (a new version of the file); his approval in any words sets the status to `approved`.
- **The play file** — `state/plays/<id>.md`, written only by Hermes (format below); the id is `YYYY-MM-DD-<slug>`. Nothing of the room is in it.

## Claude the game master (v7.4)

In the Stage Claude has his own turn mode, `gm` (*proposed name*): never chosen by R1 or R2, but he reads every line.

- **When he is called.** The owner's start in the Stage («Завіса!», «починаймо») opens the latest `approved` play. Then the code calls him (`gm_due`, pure) after `PLAY_GM_SILENCE_S` (15 s) of silence, after `PLAY_GM_EVERY_N` (4) actor lines without him, when a line names a minor character he plays (the names in `## Епізодичні`), when the current act's line budget is spent, and when the owner names him.
- **What he reads:** all the Stage's lines of this play (`CLAUDE_HISTORY_N`, 150, covers a play), the play file, his run state (the act and the mutations so far) and `GM_BRIEF`, a new brief in `agents/logic.py`.
- **One move per call:** `PASS`; narrate (scenery, sound, the characters' actions — one to three sentences); steer back to the plot with an event (a bell, a letter, a scream); voice a minor character; move to the next act; or **mutate** the plot.
- **Mutations.** When the actors improvise something better than the plan — an invented neighbour, a sincerely innocent suspect — he may change the culprit, add a character, move a clue or add a twist. Two limits: the act structure stays (setup → climax → resolution), and nothing contradicts what was already said. It is the idea of the plan mutations of v2.2, chosen by him rather than rolled.
- **Hidden lines.** He ends a message with lines the code reads and never sends (`stage_marks`, pure, like `recording_mark`): «АКТ N» (the next act begins), «МУТАЦІЯ: …» (what he changed and why), «КІНЕЦЬ» (the play is over). They go to `state/plays/<id>.run.json`, which only his process writes.
- **The ending.** The resolution, then «КІНЕЦЬ»; also when the cap is reached, or when the owner says «Стоп» in the Stage (status `stopped`).
- **The subscription.** A play costs ~15–30 calls of `CLAUDE_MODEL` (Opus) on the Max subscription. The rate-limit breaker of v4.4 applies: when it trips, the play ends with a short line from code («Вистава переривається.») and `stopped`.

## The recording of a play (v7.5)

Hermes watches `run.json`; at `done` (or `stopped`, with a note) he records the play — the v5.4 pipeline over the Stage's events of the play's period:

- the opening in his voice: «Радіотеатр Агори. Гермес представляє: „<назва>“, за мотивами <джерела>.»; the closing names the cast: «Грали: Бруно — отець Тарас, … Від автора і за всіх інших — Клод. Написав і записав Гермес, ваш вісник.»;
- 0.5 s between lines, 1.5 s at the start of each act (the «АКТ» times from `run.json`);
- one `m.audio` file «Сцена — <назва>.ogg» to his private room, then one line of text: the length, lines, acts and number of mutations.

No hidden line is in the recording: none was ever sent.

## The play file

Hermes writes it; a pure parser reads it (`agents/plays.py`: `parse_play`, `actor_card`, `stage_names`). Only Claude's prompt ever holds `## Ядро` and `## Акти`; an actor's prompt holds only its own line of `## Персонажі` (pinned by a test, like "the agents never know their future").

```markdown
# Свисток на Личакові
Джерела: А. Конан Дойл, «Пістрява стрічка» (1892) — хребет; Г. К. Честертон, «Блакитний хрест» (1910) — манера детектива; Е. А. По, «Викрадений лист» (1844) — доказ на видноті
Місце: Львів, Личаків, жовтень, дощ
Статус: approved

## Ядро
Два роки тому в старому будинку на Личакові вночі померла сестра Олени; перед смертю вона чула свист. Розгадка за замовчуванням: вітчим, щоб не віддати спадок, пускав отруйну змію через вентиляційний отвір. Докази: фальшивий шнур дзвоника, отвір у сусідню кімнату, прикручене до підлоги ліжко, блюдце з молоком на сейфі — усе на видноті.

## Персонажі
- bruno → Отець Тарас, тихий парафіяльний священник, що розплутує справи; імена: отець тарас, отче, отче тарасе
- mia → Олена, 22, налякана падчерка; імена: олена, олено, пані олено
- leon → Гриміт Ройлот, 67, вітчим, вибуховий лікар; імена: ройлот, пане ройлоте, вітчим
- ada → Ганна, вдова лікаря, що допомагає отцю Тарасу і все записує; імена: ганна, ганно, пані ганно
- irma → Марта, економка будинку, знає більше, ніж каже; імена: марта, марто, пані марто

## Епізодичні
Клод: сестра Юлія (у спогадах), листоноша, сусід-візник

## Акти
### 1. Зав'язка · 6–8
Мета: Олена приходить до отця Тараса. Має статися: страх, свист уночі, смерть сестри.
### 2. Історія · 6–10
Мета: підозра. Має статися: вітчим, спадок, ремонт, через який Олену переселили в кімнату сестри.
### 3. Погроза · 4–6
Мета: лиходій на сцені. Має статися: вітчим вривається і погрожує.
### 4. Огляд · 8–10
Мета: докази. Має статися: шнур, отвір, ліжко, блюдце на сейфі.
### 5. Ніч · 6–8
Мета: кульмінація. Має статися: темрява, свист, шипіння.
### 6. Розв'язка · 4–6
Мета: правда і вибір. Має статися: зізнання або кара, фінальна картина.
```

`state/plays/<id>.run.json` (Claude's process only): `{"play", "status": "running" | "done" | "stopped", "act", "acts": [{"n", "ts"}], "mutations": [{"ts", "text"}], "started_ms", "ended_ms", "lines"}` — no line of the room.

## Settings

| Name | Default | Read by | Meaning |
|---|---|---|---|
| `PLAY_MAX_LINES` | 60 | every speaker | the cap of a play |
| `PLAY_REPLY_P` | 0.8 | every speaker | an actor's roll on an unnamed agent line in the Stage |
| `PLAY_GM_SILENCE_S` | 15 | Claude | silence before the game master is called |
| `PLAY_GM_EVERY_N` | 4 | Claude | actor lines in a row before he is called |
| `PLAY_ACTS` | `5-7` | Hermes | the range of acts he writes |

New env names: `STAGE_ROOM_ID` (both shared examples), `LEON_VOICE_ID`, `MIA_VOICE_ID`, `IRMA_VOICE_ID`, `LEON_PASSWORD`, `MIA_PASSWORD`, `IRMA_PASSWORD`.

## Walkthrough

1. Ich in Hermes's room: «Гермесе, зроби нам детектив на всіх, щось за Конан Дойлом». Hermes answers with the title, the sources, the cast and the acts. Ich: «Нехай Леон буде лиходієм. Затверджую.»
2. Ich in the Stage: «Завіса!». Claude narrates the opening scene and ends with a hidden «АКТ 1».
3. The actors improvise; the narration names characters and R2 picks the next speaker; Claude speaks on his triggers. Мія invents a cousin with a key, and Claude mutates the plot: «МУТАЦІЯ: …».
4. After about 45 lines Claude closes with the resolution and «КІНЕЦЬ». Agora resumes, and each actor journals one line.
5. Hermes sends «Сцена — Свисток на Личакові.ogg» (about 6 minutes) to his room.

## Invariants kept

- **Turn-taking from shared inputs only** — the room timeline, the roster and now the play file; no coordination between agents. The play file and the run state each have a single writer.
- **The persona agents believe they are human**; to them a play is an amateur radio play.
- **The agents never know their future**, and the actors never know the play's core.
- **Hermes never says a word in Agora or in the Stage**; his play goes to his own room and the file.
- **Nothing lived is deleted**: play files and run states are kept; the Stage's lines live only on the homeserver.
- **Secrets and texts stay out of logs**: logs name events only (`play: written <id>`, `play: approved`, `play: started`, `play: act 3`, `play: mutation`, `play: done (N lines)`).

## VISION and contract changes

- **VISION:** the non-goal "A second simulation" stays; "a second room" (the non-goal of `more-agents.md`) is lifted — the Stage is the simulation's second room. Glossary: **Stage**, **play**, **playwright**, **game master**, **mutation (of a play)**. Hermes's principle gains "and never in the Stage".
- **ARCHITECTURE:** §Message flow (the allowlist per room), §Turn-taking (the Stage's rules, the `gm` mode), §The herald (the playwright skill, the play's recording), §Memory (Stage lines out, the journal line), §Data and state files (`state/plays/`), §Contracts.
- **Contracts:** `simulations.toml` endpoints gain `stage` (an agent still belongs to one simulation); the env names above; `voice.env` read by `leon`, `mia` and `irma` too; the turn mode `gm`; the play file format and `run.json`; the hidden lines; the compose service set (`leon`, `mia`, `irma`).

## Phasing

1. **v7.1 Three new personas** — independent of the theatre; can ship first.
2. **v7.2 The Stage** — the second room, the per-room allowlist and timeline, the Stage rules, the Agora pause, the journal line; a hand-written play file to test with.
3. **v7.3 Hermes the playwright** — the skill, the sources, the mutation of stories, the approval.
4. **v7.4 Claude the game master** — `gm`, `gm_due`, `GM_BRIEF`, the hidden lines, `run.json`, the start and the end.
5. **v7.5 The recording of a play** — the v5.4 pipeline reused (needs v5.4 released).

## Tests

- `parse_play`: the sections; a malformed file is refused with a reason; `actor_card` returns only that actor's line; the core and the acts never reach an actor's prompt.
- `stage_names`: character names choose the actor in the Stage only, never in Agora.
- Turns in the Stage: R1 and R2 with character names, no wave limit, `PLAY_MAX_LINES`, `PLAY_REPLY_P`; Agora's rules unchanged.
- `gm_due`: each trigger, and none while his reply is on its way.
- `stage_marks`: «АКТ N», «МУТАЦІЯ: …», «КІНЕЦЬ» parsed and stripped, never sent; a message of marks only sends nothing.
- The Agora pause: an actor ignores Agora while `run.json` is `running`.
- Memory: Stage lines never reach the session; `play_journal_line`.
- The recording: the opening and closing from the play file, the act pauses, the file name.
- Logs: no line text, no play text.

## Costs and trade-offs

- **Voice:** a play of about 50 lines is 4,000–5,000 characters, 6–7 minutes; Hermes's opening and closing come from his own budget.
- **Claude:** 15–30 Opus calls per play on the subscription — the most expensive part, and rate limits apply.
- **Gemini:** one thinking call per play for Hermes (plus revisions) and about 50 Flash calls for the actors.
- **Quality:** Flash actors improvise unevenly; the game master's events and mutations carry the plot. Expect the first plays to sprawl.

## Open questions

1. **Numbering:** v7 after Лілі (v6), or before it? v7.1 can ship on its own at any time.
2. **Do the actors know the sources?** Proposed: no.
3. **The Agora pause** during a play: proposed yes.
4. **The owner in a play:** only the audience, or a character too (typed lines in his cloned voice)?
5. **Where the recording goes:** Hermes's room (proposed), or also the Stage.
6. **Claude's voice for minor characters:** his own voice for now (proposed), a second voice later?
7. **The cap and the acts:** `PLAY_MAX_LINES` 60 and 5–7 acts?
8. **The newcomers:** names, ages, the details of their canons and life stories; their voices.
9. **The `gm` mode:** its name, and whether Claude may answer in the Stage outside a play.
