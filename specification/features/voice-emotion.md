# Feature: emotion in Кіра's voice — ElevenLabs audio tags

> **Status: draft, 2026-10-25.** A proposal, not a contract. Adapted for matrix-agora from the findings of the Noos
> session of 2026-10-21 (the measurements are kept in [Findings](#findings-2026-10-21) below). Scoped to **Кіра**
> for now: one voice is calibrated, and the other eight members are untested. The other speakers stay as they are.
> It designs ROADMAP phase **v5.9** (the owner, 2026-10-25), after v5.8 and before v6. Its open questions are
> closed (see [Decided](#decided-the-owner-2026-10-25)).
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

That is a second step. For now her settings stay fixed, and the tags carry the emotion of the line. *Proposed home:*
a later phase, together with a mood for the persons (the cat's horoscope mood, v4.2, is the nearest precedent).

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
- **The emotion state is later** (proposed, not contradicted): her settings stay fixed in v5.9.
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
