# Feature: emotion in Кіра's voice — ElevenLabs audio tags

> **Status: draft, 2026-10-25.** A proposal, not a contract. Adapted for matrix-agora from the findings of the Noos
> session of 2026-10-21 (the measurements are kept in [Findings](#findings-2026-10-21) below). Scoped to **Кіра**
> for now: one voice is calibrated, and the other eight members are untested. The other speakers stay as they are.
> It designs ROADMAP phase **v5.9** (the owner, 2026-10-25), after v5.8 and before v6. Its open questions are
> closed (see [Decided](#decided-the-owner-2026-10-25)). **v5.9 shipped** (v5.9.0, 2026-10-25). On 2026-10-26 the
> owner widened the deferred emotion state into [Her emotional life](#her-emotional-life-v510-proposed): a mood of
> the day, events of her life and a longer-lived emotional state, as phases **v5.10+** (proposed, with open questions).
>
> **Checked on 2026-10-25 in this repository** (the owner asked that the findings be re-measured before anything
> changes): see [Verified on Кіра's voice](#verified-on-кіраs-voice-2026-10-25). The tags and the ladder held, v4 takes `uk`, the cost
> claim did not hold, and the spelling fix proved nothing; the proposal below follows the re-measurement.
>
> Sources:
> - the measurements and the recipe the owner picked by ear (2026-10-21);
> - the matrix-agora code at v5.8: `agents/voice.py`, `agents/speech.py`, `agents/agent.py`, `agents/telegram.py`,
>   `agents/recording.py`;
> - Кіра's canon (`agents/canon/kira.md`).

## Summary

ElevenLabs' newer models perform square-bracket directions inside the text: `[laughs]`, `[sighs]`, `[whispers]`.
Кіра's voice was calibrated by ear, and a laughter ladder on `eleven_v4_turbo` won.

The proposal:
- She writes one or two tags herself, inline, from a palette verified on her voice.
- Code splits that one reply in two:
  - **the voice** gets the tags as written;
  - **the text**, in Agora, the Element private chat and Telegram, gets the reply with the tags removed and nothing
    in their place: no emote, no emoji (the owner, 2026-10-25).
- Her voice settings are fixed per voice for now.
- The reader never sees a bracket, and the listener never hears one.

## Today in matrix-agora (v5.8)

The original note says no ElevenLabs model is set in this repository. That is not so:
- **One model for every speaker and for Hermes.** `agents/voice.py` sets `TTS_MODEL = "eleven_turbo_v2_5"`; its
  comment says 0.5 credit a character, which the account no longer shows (see Costs).
- **One set of voice settings.** `VOICE_SETTINGS` is `stability 0.5, similarity_boost 0.75, style 0.4`, with
  `language_code: "uk"`, output `pcm_24000`, then Opus through ffmpeg.
- **Tags on this model are read aloud** (verified on her voice): `[смішок] … [laughs] …` came back as «Смішок. Ага,
  звісно, лавс.».

Where one of her lines goes today:

| Path | Voice | Text |
|---|---|---|
| Agora (`send_line`) | an `m.audio` voice message, when `voice_due` and `voiceable` hold and the monthly budget allows | always the same words as `m.text` |
| Element private chat (`private_reply` → `send_line`) | as Agora | as Agora |
| Telegram (`send_telegram`) | always a voice note (`sendVoice`), within the budget | then `sendMessage`, plain text, no parse mode |
| Hermes's recording (v5.4) | her voice message as it is; a line with no voice is **re-synthesised from its text** in her voice | — |

What she sends is also what is kept: her history, the session, the summary, the archive (v5.8), and the other
members' transcripts all hold the sent text.

## The design

### One pass

She writes the tags herself, in the same reply, with no second model call to add emotion. Whoever places a tag must
know the intent behind the sentence, and a second pass would add a second and a few hundred tokens to every reply.

### Her palette, in her prompt

A small block of three rules, carried only by an agent with the new capability `emotion` (Кіра):
1. **The palette verified on her voice:** `[starts laughing]`, `[laughs]`, `[laughs harder]`, `[wheezing]`,
   `[chuckles]`, `[surprised]`, `[thoughtful]`, `[hesitant]`, `[whispers]`, `[sighs]`.
2. **The budget and placement:**
   - one or two tags a reply, most replies none;
   - a tag goes before the clause it governs;
   - laughter climbs the ladder over short clauses (`[starts laughing] …` → `[laughs] …` → `[laughs harder] …`);
   - laughter is never spelled out («ха-ха») next to a ladder;
   - a quiet ending is `[thoughtful]` → `[sighs]` → `[whispers]`.
3. **Nothing in the brackets but the palette:** no stage directions in words, no emoji.

Her canon already reads as a voice specification: a laugh heard two rooms away, warmth, hesitancy. The palette
follows from it.

*Proposed:* keep the palette in a file next to her canon, `agents/canon/kira.voice.md`, named by her TOML
(`voice_spec`), so that a later voice gets its own palette without a code change.

### The split (`agents/emotion.py`, pure)

`split_tags(reply) -> (text, speech)`:

- **`speech`** keeps the reply as written, tags and all, for the synthesiser.
- **`text`** is the reply with every tag removed and nothing in its place (the owner, 2026-10-25: no emote, no emoji),
  the spaces tidied:
  - a known tag, or an invented one (a bracket that opens with a letter of any case, 2–40 characters, no digit, not a
    link's text — v5.9 review #3), is removed;
  - a bracket that is not a tag (`[1]`, `arr[i]`, `[ОСТРІВ 3]`) stays.
- **Where the text goes:** where it goes today. It stays a plain `m.text` in Matrix and plain text in Telegram, with no
  formatting and no parse mode.
- **A line that goes out as text only** (her share of voice, the monthly cap, no voice id) sends the clean text, never
  the raw reply.
- **Every other component sees only the text:** her history, the session, the summary, the archive, the facts'
  extraction, and the other members. Her past lines never show a bracket, so neither she nor the members learn to
  write tags into the text.

### Spelling for the voice (not needed)

The original note proposed rewriting her Latin inserts in Cyrillic for the voice. The re-measurement does not support
it:
- On today's model the inserts came out recognisable, and on `eleven_v4_turbo` only «literally» was mangled.
- The Cyrillic spelling did no better: «літерально» was heard as «ліберальна», and «фер енаф» as «Farnoff».
- `Ich` is pronounced «Іх» on v4.

The recogniser itself is unsure of English words inside Ukrainian, so the owner's ear settled it: her inserts sound
right on v4 (the owner, 2026-10-25). They stay as she writes them.

### Her model and settings

- **Per-agent model.** A new agent setting, `ELEVENLABS_MODEL`, defaults to `eleven_turbo_v2_5`, so every other
  speaker and Hermes stay as they are. Кіра's `server/kira.env` sets `eleven_v4_turbo`.
- **Per-agent settings.** Her voice settings take the recipe the owner picked by ear: `stability 0.3`,
  `similarity_boost 0.75`, `speed 1.0` (`VOICE_STABILITY`, `VOICE_SPEED`; the others keep v5.3's).
- **The safety rule.** An agent whose model does not render tags (`TAG_MODELS` = `eleven_v3`,
  `eleven_v3_conversational`, `eleven_v4`, `eleven_v4_turbo`) never sends a bracket to the synthesiser. The speech
  text is stripped like the room text, so a tag is never read aloud.

### Hermes's recording

Nothing changes. Her voiced lines come to the recording as audio, with the tags performed. Her text has no tags and
no marks, so a text-only line he re-synthesises in her voice reads cleanly.

### The emotion state (later)

The original note's deeper proposal:
- a small state of valence, arousal and fatigue that persists between turns and decays to a baseline;
- voice settings derived from it, never chosen by the model.

That is a second step. For now her settings stay fixed, and the tags carry the emotion of the line. Its design, widened
by the owner on 2026-10-26, is [Her emotional life](#her-emotional-life-v510-proposed) below.

## Her emotional life (v5.10+, proposed)

> **Status: proposal, 2026-10-26.** The owner asked for three things:
> - a mood of the day like the cat's: the horoscope with the biorhythms laid over it;
> - more than valence, arousal and fatigue, so that what happened in earlier talks and in her life holds longer;
> - real events of her life, not only plans and memories.
>
> The owner answered the main questions the same day (see [Decided](#decided-the-owner-2026-10-26)); the phases are
> in the ROADMAP as **v5.10–v5.15**. For Кіра only, for now (the owner, 2026-10-26). The same day the owner added
> her reading of the news and her own thoughts, as v5.12.

### Today, for comparison

- **The cat has a mood** (v4.2, `agents/mood.py`, `agents/sky.py`):
  - once a local day, one call reads his natal chart, the day's biorhythms (the 23-, 28- and 33-day sines) and the
    day's real sky (a grounded search, kept in `state/kit.sky.json`);
  - the reading is appended to `state/kit.mood.log`;
  - only its «РЕЗОЛЮЦІЯ» enters his prompt as «Настрій дня».
- **Кіра keeps no emotional state.** Each reply re-derives her mood from the prompt:
  - her canon;
  - her memories (7 days, 4 weeks, 6 months);
  - the hourly «Сьогодні» block;
  - the last summary;
  - the recent lines.

  Between conversations a feeling survives only as words in the summary (≤ 200 words) and in the day's memory. How
  long she stays hurt or glad depends on what the model happened to write there.
- **Her days have no events of their own:**
  - her plans are intentions;
  - their mutations (v2.2) make some of them fail;
  - the day's memory, written after midnight, invents the concrete details of the day inside the life story's frame.

  Nothing happens *to* her that she did not plan: no news, no surprise, no setback. The current chapter of her life
  story is a frame (her work, her week, her people, open threads) with no dated events in the present, so its threads
  never move by themselves.

### The layers

Each layer has its own time scale, so a feeling lasts as long as its kind would in a person. Every number lives in
code and in `state/`. She only ever reads words (see How it reaches her).

| Layer | What it holds | Lives | Comes from |
|---|---|---|---|
| **1. The moment** | valence (pleasant ↔ unpleasant), arousal (calm ↔ excited), fatigue | hours: decays to the day's baseline (half-life ~2 h) | the tags she writes, what was said to her, the hour and her week |
| **2. The day** | the mood of the day: the baseline the moment returns to | one local day | the horoscope (her natal chart + the day's sky) with the biorhythms laid over it, as the cat's; *optionally* the real weather |
| **3. The background** | how she has been lately | weeks: a slow average of the days (half-life ~10 days) | the days, the season, her load (a deadline, a premiere) |
| **4. Feelings toward people** | per person: closeness, trust, hurt, longing, jealousy | weeks to months, each at its own pace | what happened in the talks (the session's end) and in her life (events) |
| **5. Open threads** | a charged thing that is not settled: an unanswered question, a sharp word, a promise not kept, news she is waiting on | until settled; fades slowly if never touched | the session's end and her events |
| **6. Anticipation** | a dated thing ahead: a birthday, a deadline, a premiere, a date, an anniversary | grows as the day nears, peaks on it, becomes a memory after | her known events and her plans |
| **7. The weight of memories** | how strongly a day is remembered | as long as it is strong: past the 7-day window | the day memory's charge |

Notes on each:

1. **The moment, with no extra call per reply.** The tags she writes are already a signal: a laughter ladder raises
   valence and arousal, `[sighs]` lowers valence, `[whispers]` lowers arousal. Code maps them in a pure table. The
   hour and her usual week give the fatigue: after a night under the dome she is tired the next morning.
2. **The day is the cat's mood, for a person.**
   - Her natal chart becomes a private canon file, `agents/canon/kira.natal.md`.
   - The day's sky is her own `state/kira.sky.json`; no state is shared with the cat.
   - The resolution sets the baseline numbers (a small call answers them with the reading) and the words of
     «Настрій дня».
   - *Optional:* the real Lviv weather (Open-Meteo, no key). A clear night on an observation night lifts an astronomer;
     rain on a climbing Sunday weighs.
3. **The background** is what makes a bad week feel like a bad week. It nudges the day's baseline, so one good day
   does not erase a hard fortnight.
4. **Feelings toward people.**
   - One call at a session's end reads the session and answers JSON deltas, each with the line that caused it. It
     could be the summary's call or the facts' call, extended. Code clamps the deltas and applies them.
   - Each feeling decays at the pace her temperament gives it. Her canon says she remembers a hurt longer than she
     shows, so hurt fades slowly and a passing joy faster. The half-lives are per person, in her TOML.
   - **Longing** needs no call: it grows with silence (`last_private_ms`, pure) and drops at contact. It colours the
     lines she writes first.
5. **Open threads** are where a talk's emotion outlives the talk.
   - Each thread is a sentence of what happened (from the session or an event, never invented), a feeling, an
     intensity and a date.
   - Raising it again reinforces it. The session-end call says when the journal shows it settled, and then it
     closes.
   - At most the three strongest reach the prompt.
   - Every thread, open or closed, is kept in a log forever.
6. **Anticipation** is a pure curve over the days left to a known date, so the same date weighs more each day. The
   dates come from her known events (below) and her plans; the anniversaries come from her life story.
7. **The weight of memories** is what holds a life event longest.
   - The day-memory call also answers the day's charge (0–3).
   - Beyond the 7-day window, up to a few strong days of the last months stay in her prompt by their date, the way
     people remember vivid days.
   - Recall (v5.8) ranks a charged line higher.

### Events of her life (the owner's question, 2026-10-26)

**What happens today:** the life story gives the frame and the past, and plans give intentions. Nothing *happens*
to her. The day memory invents the day's details only after midnight, so during the day she never meets news or a
surprise, and her open threads stay where the story left them.

**Proposed:** an events layer, `state/kira.events/` (one file per day, written once, never rewritten), from two
sources:
- **Known events, written by the owner** in her life story's current chapter, as a dated list: a deadline, a
  premiere, a birthday, a trip, a decision that falls due.
  - Each is *known ahead* (she expects it, so it feeds anticipation and her plans) or a *surprise* (it reaches her
    only on its date).
  - This is the "more events in the story": the owner writes the turning points; the frame stays as it is.
- **Generated events**, rolled like the plans' mutations.
  - Each day, with a probability per kind, code rolls an event:
    - work, a success or a setback;
    - news from one of her people;
    - a suitor's move;
    - health, the city, the weather;
    - chance.
  - One call writes it inside the frame. It moves one of her open threads by one step and leans toward the next
    chapter as a silent direction, as the plans do.
  - A rolled event is a fact of her life for the day it falls on.

**Where events go:**
- **«Сьогодні вже…»:** once it has happened.
- **The day memory:** the memory tells it, with the details.
- **The next plans:** a setback leads to a plan to fix it.
- **The emotion layers:** threads, feelings and anticipation.

**The rules hold:**
- An event involves only her, her people outside the room and the city; never Ich's or a member's words or deeds.
- A surprise never reaches a prompt before its date. Like the future chapters, it is visible only to the code that
  delivers it.
- An event, once fallen, is never rewritten.

### Reading and thoughts (v5.12; the owner, 2026-10-26)

**What the owner asked:** Кіра reads the news and has thoughts of her own: a thought on each item she reads, and
her own reflection on her talks, with the owner and in Agora. The thoughts come on a schedule, even while she is
talking, and go into a memory she can recall as she recalls the chat, marked as her own: «я думала…».

**Two sources:**
- **Zaxid.net**, Lviv's outlet, for the local news with the full text. Its RSS (`zaxid.net/rss/all.xml`) lists
  about 50 newest items with a title and a short description. The article page carries the full text in its JSON-LD
  `articleBody`, so no HTML is scraped. Checked on 2026-10-26: the feed answers, and a sample page held 2,661
  characters of body text.
- **The Guardian**, so she may pick what Claude did not. `agents/guardian.py` already builds the search and read
  URLs and parses the answers. Here code calls it directly over the sections of her interests, with no SDK and no
  tools. She reads it in English and thinks in Ukrainian. She keeps no shared state with Claude and never reads his,
  so the two pick independently, and the same article picked by both is fine.

Other sources checked on the same day:
- **Українська правда:** its RSS carries the full text, but it is national, not local.
- **Суспільне, Укрінформ, Твоє місто, 1256, Портал:** their feeds carry only a description. The Портал's article
  pages answer 403.

**A reading**, every `READING_EVERY_S` (3 hours) within her waking hours:
1. One call gets the fresh titles from both sources, with her canon, the mood of the day and her recent thoughts. It
   picks at most `READING_PICKS` (2) items that would touch her, or none.
2. Code fetches the full text of each pick.
3. One call per pick writes her thought: first person, 1–3 sentences, built only on the article's facts. Recall
   brings her earlier thoughts on the topic, so she stays herself.
4. She may change her mind. That is a new thought, and the old one stays.

**A reflection**, every `REFLECT_EVERY_S` (1 hour), for each place with new lines since her last reflection there
(the private chat in Element and Telegram, and Agora):
- One call reads those lines and writes one or two thoughts of hers: what stayed with her, what she thinks of what
  was said, what she would say next time.
- It runs mid-conversation too, on the lines so far. It sends nothing and never holds up a reply.

**Where thoughts go:**
- **The archive.** Each thought is a line of `state/kira.archive.db`, embedded like the rest. A news thought and a
  reflection on Agora get the place `thought`; a reflection on the private chat gets `thought_private`. The private
  recall searches both. Agora's recall searches `thought` only, as it already searches only `agora` today. A recalled
  thought reads «26 жовтня — я думала: …», never as something said.
- **A day file.** `state/kira.thoughts/YYYY-MM-DD.md` keeps every thought with its time, its kind (`news` or
  `reflection`) and its place, and for news the source, the title and the link. It is appended, never rewritten.
- **Her prompts.** A block «Що ти сьогодні думала» holds the last three thoughts of today. A reflection on the
  private chat appears only in her private prompt.
- **Writing first.** In the private chat and Telegram she may share an item with her thought and its link, or come
  back to a reflection.
- **Agora.** A persona move `thought` lets her bring up something she read or thought when it fits. She never
  starts a talk with it: Agora's news initiative stays Claude's.
- **The day memory:** what she read and what she thought.

**The rules hold:**
- She reads her phone like anyone and never «searched».
- The facts come only from the article: no invented number, quote or name. The opinion is hers.
- A reflection never invents Ich's or a member's words or deeds.
- People in the news stay public figures she does not know.

### How it reaches her

- **In words, never numbers.** Code maps the state to short phrases through a pure table, for example «ти сьогодні
  легка й швидка», «тобі бракує його — він давно не писав», «у тобі ще сидить образа». They form one block, «Як ти
  зараз», after «Сьогодні»:
  - **in the private chat:** the whole block, including her feelings toward the owner and the threads about him;
  - **in Agora:** the day, the background and the threads that are not about him, under the discretion rule.
- **In her voice.** Code, never the model, derives stability and speed from arousal and fatigue, within the panel's
  ranges (stability 0.2–0.5, speed 0.9–1.1). An excited Кіра is less stable and quicker; a tired one is slower. The
  tags still carry the line.
- **In her behaviour (open question 4).** The state could also change *what* she does: shorter replies when hurt,
  writing first sooner when longing, not at all for a while after a quarrel.
- **In the panel.** The Voice tab (v5.9) shows the state read-only:
  - the mood of the day;
  - the baseline;
  - the feelings as bars;
  - the open threads;
  - the events of the last days.

### Rules that hold

- **She believes she is human.** No word of state, score, generator or horoscope engine reaches her prompt; she
  reads a feeling. Her canon may let her believe in her transits; the reading itself stays in the log.
- **Truth.** Feelings about people and the threads come only from what was said (the journal and the session) or
  from her events, never invented about Ich or a member.
- **Nothing lived is deleted.** The state's history and every event and thread are appended to logs. Only the
  current state is a small file rewritten atomically, like the «Сьогодні» block.
- **Pure decisions with an injected clock:** the decay, longing from silence, the anticipation curve, the event
  rolls, the mapping to words and the voice settings.
- **Costs:**
  - one grounded search and one call a day for the mood, as the cat;
  - one call a day for a generated event;
  - one call at a session's end (or none, merged into the summary call);
  - reading and thoughts (v5.12) on `GEMINI_MODEL`, never Pro:
    - up to about 18 calls a day for the readings (a pick and up to two thoughts, six times);
    - one call an hour for each place she talked in;
    - the thoughts' embeddings;
  - no call per reply.

### Phases (proposed: v5.10+)

| Phase | What it delivers |
|---|---|
| **v5.10** — Кіра's mood of the day | The cat's horoscope and biorhythms, for a person: her natal file in the private canon, her own day's sky, the reading log, «Настрій дня» in both prompts, the panel shows it; the real Lviv weather in the reading (decided). |
| **v5.11** — Events of her life | Known events, dated in the current chapter (written with the owner); generated events rolled every hour (everyday, joyful, inspiring, heavy); Lviv's news woven in selectively. They reach «Сьогодні», the day memory and the next plans; `state/kira.events/`; the panel lists them. |
| **v5.12** — Reading and thoughts | Zaxid.net (the full text) and The Guardian, read every 3 hours; a thought on each item she picks; a reflection every hour on her talks, with the owner and in Agora, even mid-talk; thoughts in her archive, recalled as «я думала…»; the move `thought`; the panel's Thoughts tab. |
| **v5.13** — The moment and the day | Valence, arousal and fatigue decaying to the day's baseline, and the background; signals from her tags, the hour and her week; her voice's stability and speed derived from them. |
| **v5.14** — Feelings, open threads and behaviour | The session-end call (deltas with their cause), decay by temperament, longing from silence, the threads' life cycle, «Як ти зараз» in her prompts; the bounded effects on her reply length, writing first and a silence after a quarrel (decided); the panel. |
| **v5.15** — Anticipation and strong memories | The curve to known dates and anniversaries; the day memory's charge; strong days kept past the window; recall ranks charged lines higher. |

### Decided (the owner, 2026-10-26)

1. **The weather: yes.**
   - The real Lviv weather goes into the mood of the day (v5.10). It comes from Open-Meteo, with no key: the day's
     temperature, rain and wind, the cloud cover through the night, sunrise and sunset.
   - It is kept once a day in `state/kira.weather.json`.
   - A failed fetch means no weather, never a blocked mood.
2. **Lviv's news, woven into her life selectively.**
   - Once a day, the day's items from Zaxid.net's feed are kept in `state/kira.citynews.json`. It is the same local
     source as her reading (v5.12), with real items and real links. It replaces the grounded search first proposed
     here (2026-10-26).
   - Each item is rolled like a plan's mutation. With a probability, at most two a day, it becomes part of her life
     in one of these ways:
     - she was there;
     - she heard of it from one of her people;
     - it touched her work;
     - it touched one of her people;
     - it changed her plans.
   - Most news passes her by.
   - **A real person stays real:** a real news item never makes a real person one of her people, and a real
     tragedy never gets a victim from her life. She may be affected by it (a night of alerts, a closed street, a
     concert she went to), but she never owns someone else's loss.
3. **Generated events may be heavy, inspiring or joyful, and they are rolled every hour.**
   - At each local hour change in her waking hours (the hook that refreshes «Сьогодні»), code rolls once:
     - `EVENT_P`, e.g. 0.12, gives about two events a day;
     - the kind is weighted: everyday most often, then joyful and inspiring, heavy (an illness, a loss, a real
       setback) rarely.
   - A hit means one call writes the event. Inputs:
     - the current chapter;
     - the open threads;
     - today's plan;
     - the mood of the day;
     - the last events;
     - the next chapter, as a silent direction.
   - The block «Сьогодні вже…» for that hour carries it.
   - Plans and day memories stay daily; only the «Сьогодні» block, and now the events, are hourly.
4. **The state may change what she does, not only how she sounds.** Every effect is bounded in code:
   - **Reply length:** her reply cap scales between 0.6× and 1.2× (short when hurt or tired, longer when excited).
   - **Writing first:** her idle interval shortens with longing and lengthens with hurt, within `PRIVATE_HOURS` and
     the daily cap.
   - **A silence after a quarrel:** after a strong hurt she may answer the owner later (a bounded delay, at most
     20 minutes) and shorter. His message is never dropped.
   - **Agora's turn rules stay shared.** The state never changes *whether* she takes a turn, since that is derived
     from shared inputs (the ranking, R1–R4). It changes only how she answers and its length; she may still `PASS`.
5. **Кіра only, for now.** Every part of v5.10–v5.15 is switched on for her alone, in her TOML. The other persons
   get none of it until the owner decides otherwise.
6. **She reads the news and thinks (v5.12).**
   - Two sources: a local one with the full text (Zaxid.net) and The Guardian.
   - A thought on each item she reads, and her own reflection on her talks with the owner and in Agora.
   - On a schedule, even while she talks.
   - Into her archive like the chat, marked «я думала…».
   - See [Reading and thoughts](#reading-and-thoughts-v512-the-owner-2026-10-26).

**Not answered yet; these defaults hold unless the owner says otherwise:**
- **Known events:** Claude drafts the dated list in her current chapter, and the owner edits it.
- **A session's end:** a separate call (kind `feelings`) reads the session for the feelings and threads, kept apart
  from the summary's call so each stays simple.
- **What she reads:** her work, Lviv, Ukraine and what she cares about. Claude drafts a paragraph on it in her
  canon, and the owner edits it.
- **Politics and war:** she reacts to events and holds views, as a person in Lviv does. She does not argue party
  politics unless asked.
- **Links:** when she shares an item in the private chat or Telegram, its link goes with it. In Agora she tells it
  in her own words.

## Costs

- **No difference between the two models on this account** (verified): the same 57-character line was billed
  `character-cost: 14` on both `eleven_turbo_v2_5` and `eleven_v4_turbo`, and the API lists `token_cost_factor 1.0`
  for every model. The code comment «0.5 credit a character» on `TTS_MODEL` is not what the account shows today.
- **The tags themselves** add roughly 10–30 characters to a reply that has them. They are sent, so they are counted:
  the `tts` usage line keeps counting the characters sent, and *proposed* it also names the model.

## What changes where

- `agents/emotion.py` (new): the palette, `split_tags`, `TAG_MODELS`.
- `agents/voice.py`:
  - the model and the settings per agent;
  - the safety strip for a model that does not render tags;
  - the `TTS_MODEL` comment corrected (the cost).
- `agents/agent.py`:
  - `send_line` and `send_telegram` send `speech` to the synthesiser and `text` as the message;
  - history, the session, the archive and the facts get `text`;
  - the palette block goes into her prompts.
- `agents/roster.py`: the capability `emotion` (a person's only), on in `kira.toml`; `voice_spec` in the TOML.
- `agents/settings.py`: `ELEVENLABS_MODEL`, `VOICE_STABILITY`, `VOICE_SPEED` (agent settings).
- ARCHITECTURE: §Voice (the tags, the split, the model per agent), §Contracts (the capability, the TOML key, the
  settings, the env names in `kira.env.example`).
- **Tests**, pure first:
  - `split_tags` on the edge cases (an unknown tag, `[1]`, `arr[i]`, a ladder);
  - the safety strip for a tag-less model;
  - the synthesiser gets the tags and the message does not, in Agora, the Element chat and Telegram;
  - no bracket in the history, the archive or another member's transcript.

## Decided (the owner, 2026-10-25)

- **The findings are re-measured first** on her real voice, in this repository ([Verified](#verified-on-кіраs-voice-2026-10-25)).
- **No mark of the tags in the text:** no emote, no emoji. The text is her words alone.
- **Her English and Scottish inserts sound right** on `eleven_v4_turbo`; no spelling map.
- **It is phase v5.9**, after v5.8.
- **The emotion state is later** (proposed, not contradicted): her settings stay fixed in v5.9. On 2026-10-26 the
  owner placed it in v5.10+, with a mood of the day like the cat's and events of her life
  ([Her emotional life](#her-emotional-life-v510-proposed)).
- **`language_code: "uk"`** works on `eleven_v4_turbo` (measured).

---

## Verified on Кіра's voice (2026-10-25)

Re-measured in this repository, on her real voice id (`KIRA_VOICE_ID`), through the same request body as
`agents/voice.py` (`language_code: "uk"`, `pcm_24000`), heard back with Deepgram `nova-2`, `uk`. A throwaway script,
not part of the code; about 1,000 characters were spent.

| Check | `eleven_turbo_v2_5` (today) | `eleven_v4_turbo` | Holds? |
|---|---|---|---|
| `[смішок] Ага, звісно. [laughs] Я так і думав.` | 2.6 s → «Смішок. Ага, звісно, лавс. Я так і думав.» — **tags read aloud** | 4.5 s → «Ага, звісно, я так і думав.» — **tags performed** | yes |
| the same without `language_code` | — | 4.4 s, the same | v4 accepts `uk` either way |
| plain story vs laughter ladder, her recipe (stability 0.3, speed 1.0) | — | 8.0 s vs 11.2 s per 100 characters (+40%) | yes (the original: +44%) |
| `literally`, `Anyway`, `Ich`, `Fair enough` | «Литерали», «Енівей», «их», «Ференаф» | «личилий», «Еніей», «Іх», «Фернаф» | partly: only «literally» breaks, on v4 |
| the same in Cyrillic, on v4 | — | «ліберальна», «Aniway», «Farnoff» | no improvement |
| `character-cost` for one 57-character line | 14 | 14 | the cost claim does **not** hold |

## Findings (2026-10-21)

These come from the Noos session, measured with the real account; where the docs and the measurement disagreed,
the measurement stands.

**Tags by model.** Method: synthesise, then recognise with Deepgram `nova-3`. A tag that survives into the
transcript was spoken; a tag that disappears was performed.

| model | tags | evidence |
|---|---|---|
| `eleven_multilingual_v2` | **read aloud as words** | `[смішок] Ага, звісно. [laughs] Я так і думав` → «Смішок. Ага, звісно, лавс. Я так і думав» |
| `eleven_v3` | rendered | → «Ха-ха, ага, звісно» |
| `eleven_v3_conversational` | rendered | «Ха-ха-ха, а, звісно» |
| `eleven_v4` | rendered | «Ха-ха-ха, звісно» |
| `eleven_v4_turbo` | rendered | «Ха-ха-ха, звісно» |

- **Ukrainian tags work like English ones.** `[смішок]`, `[зітхає]`, `[шепоче]` and `[радісно]` all disappeared from
  the transcript and changed the delivery.
- **Undocumented tags are swallowed, not spoken.** `[deep belly laugh]` and `[hesitant]` were not read aloud, and
  both altered the pacing.
- **The documentation contradicts itself** about which models render tags. All four above rendered them.

**Tags change the delivery.**
- **Duration per 100 characters, in Кіра's voice:**
  - plain speech: ~11 s;
  - a laughter ladder: 15.8 s;
  - `[deep belly laugh]`: 15.4 s.
- **Loudness (RMS over 5-second windows):**
  - 0.16 through surprise and laughter;
  - 0.05 through `[thoughtful]` → `[sighs]`;
  - 0.008 in the final `[whispers]`. The recogniser dropped the whispered tail entirely.

**The recipe the owner picked by ear (Кіра's voice, seven laughter variants):**
- `eleven_v4_turbo`, `stability 0.3`, `similarity_boost 0.75`, `speed 1.0`;
- a ladder over three or four short clauses, not a single tag, since a lone `[laughs]` only puts a smile in the
  voice;
- the tag before its clause, so long sentences are chopped;
- the same tag repeated for a sustained emotion;
- no spelled-out laughter next to a ladder;
- quiet endings work.

**The rendering sketch** (the original's §6.4; not used — the owner chose a clean text, 2026-10-25) was run on
these inputs:

| in | out (room text) |
|---|---|
| `Дивись [1] і [deep belly laugh] ось так. [laughs] Ха.` | `Дивись [1] і ось так. *сміється* Ха. 😂` |
| `Код: arr[i] = 3 і [ОСТРІВ 3]` | `Код: arr[i] = 3 і [ОСТРІВ 3]` |
| `[excited] Є! [applause] Вітаю. [sighs] Хоча...` | `Є! Вітаю. *зітхає* Хоча... 😔` |
| `[whispers] тихо. [laughs] [laughs harder] ха!` | `*шепоче* тихо. *сміється* ха! 😂` |

The text channel shows what a reader would otherwise lose, not everything the listener gets: `[excited]` and
`[applause]` are performed but leave no mark.

**Noos's own decisions, for the record:**
- Noos keeps `eleven_multilingual_v2` (the owner, 2026-10-21), so tags stay unavailable there.
- `voice/el_say.sh` there gained an environment override for the model.
