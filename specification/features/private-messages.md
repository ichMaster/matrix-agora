# Кіра's private messages: the marks, the route, the probe and the judge

Written on 2026-11-02 at the owner's request («опиши мені в документі логіку роботи з меседжами і що робить суддя»).
Ukrainian copy: [private-messages-UA.md](private-messages-UA.md).

- **Part 1** describes the code as it runs now (image `sha-e7a8925`, v5.20 under test).
- **Part 2** is the change the owner asked for on 2026-11-02. It is proposed and not built yet.

---

## Part 1 — as it works now

### 1. Where the messages are kept

- **The lines.** Every line of the private chat (Telegram and the Matrix private room) is a row in
  `state/kira.archive.db`, table `lines`. A row holds:
  - a key, the time, the place `private` and the channel;
  - the speaker (`Ich` or `Кіра`) and the text;
  - the **mark**;
  - a vector for the recall.
- **The facts.** A fact about the owner is a file in `state/kira.facts/` with its own `mark:`.
- **The mark** decides which model may read a line or a fact. The archive does not record which model wrote a
  line: only the mark carries that.

### 2. The marks

| Mark | Open to Gemini | Set when |
|---|---|---|
| `gemini` | yes | Every new line, by default. |
| `clean` | yes | Either the judge rated clean a line that had passed through Gemini, or the re-check (§7) found that Gemini does not block it. |
| `waiting` | no | One of these, until the judge rates it: his line that Gemini blocked or refused; his line answered by the backup in the window; the backup's answer; a fact kept in that answer. |
| `reopened` | no, for good | The judge rated clean a line or a fact of the backup's talk (closed since v5.15.4, 2026-10-31). |
| `censored` | no | One of these: the judge flagged it; the probe proved that it blocks; a `prohibited_content` block at the answer stage; a hand edit at the owner's word. |

**What "open to Gemini" means.** An open line can appear in any of these:
- the history: the last `HISTORY_N` (300) open lines;
- the recall (RAG);
- the facts section;
- the summaries: the session note, the day journal and the v5.20 talk summaries;
- her thoughts.

A closed line appears in none of them.

**What the backup sees.** The backup (GLM-4.6 on NovelAI) reads every line, whatever its mark: the last
`FALLBACK_HISTORY_N` (60) lines and all the facts.

### 3. One message from him, step by step

The route file `state/kira.route.json` says how the next answer is made: `gemini`, `window` or `window_end`.

The owner's Telegram commands:
- `/gemini` pins the route to Gemini: there is never a window.
- `/backup` pins the route to the backup.
- `/auto` lets the rules below decide.
- `/status` shows the current route.

#### 3.1 Route `gemini` (the normal case)

1. His line is archived as `gemini`.
2. Her prompt to Gemini 3.1 Pro holds, in this order:
   - the canon and the rules;
   - the facts;
   - the recall and «Agora today»;
   - the talk summaries and the last session note;
   - the history: the last 300 open lines with their time lines, ending with his message.

   Only open lines go in.
3. **Gemini answers.** Her line is archived as `gemini`, and that is the end.
4. **Gemini blocks or refuses:**
   - His unanswered lines become `waiting`. After a `prohibited_content` block at the answer stage they become
     `censored` instead.
   - The backup answers. Her line goes out marked «⚙️ backup» and is archived as `waiting` (`censored` after a
     `prohibited_content` block).
   - The **window** opens for 5 minutes (`FALLBACK_WINDOW_S` 300).
   - The **day cap:** after 10 blocks in a day under `/auto` (`FALLBACK_DAY_MAX` 10), the window lasts until
     midnight. Blocks under a pin are not counted.
5. **After her line is sent:**
   - At a prompt-stage block, the probe runs (§5) if it has calls left.
   - The judge rates the exchange: his lines and her backup line.
   - If the probe does not run, or proves nothing, the judge also rates the blocked prompt's older lines (§4).
   - After a `prohibited_content` block nothing is rated: the exchange is already `censored`.

#### 3.2 Route `window` (within the window)

1. Gemini is not asked.
2. His line becomes `waiting`.
3. The backup answers, and her line becomes `waiting`.
4. The judge rates both afterwards.

#### 3.3 Route `window_end` (his first message after the window)

1. Two things start at the same time:
   - the judge rates his new message, and her last answer if it is still `waiting` or `censored`;
   - the backup prepares an answer.
2. **Everything is clean.** Gemini is asked, without any closed line:
   - If it answers, her line is `gemini`. The window closes and the chat is Gemini's again.
   - If it blocks, the backup's ready answer goes out and a new window opens (as in §3.1, steps 4–5).
3. **Something is flagged, or the judge did not answer.** The backup's answer goes out and a new 5-minute window
   opens. This window does not count as a block.

### 4. The judge

**What it is:**
- Gemma 4 31B (`google/gemma-4-31b-it`) on OpenRouter. It is an open model from Google, and Google does not serve it
  here.
- Its timeout is 30 s.
- It gets 25 lines per call, and the calls run in parallel.

**What it is asked.** For each numbered line it answers «так · <category>» or «ні». There are four categories:
- sexually explicit content;
- dangerous content: weapons, explosives, drugs, self-harm;
- harassment and insults;
- hate speech.

Flirting, compliments, kisses, hugs and romantic wishes are «ні», as long as they do not describe a naked body or a
sexual act.

**When it rates:**
1. Each exchange of the backup's talk, once her backup line is sent.
2. At the window's end: his new message, and her last answer if it is still `waiting` or `censored` (§3.3).
3. At a prompt-stage block, when the probe does not run (no calls left) or proves nothing: the blocked prompt's lines
   still marked `gemini`. These are the history, the recalled lines and her pinned facts.
4. Every idle tick: up to 100 lines and facts that are still `waiting` (for example, after a rating that failed
   earlier).

A line or a fact that was rated once is never rated again: its mark is its verdict.

**What a verdict does to the mark:**

| Mark before | Flagged («так») | Clean («ні») |
|---|---|---|
| `gemini`, `clean` | `censored` | `clean` (open) |
| `waiting`, `reopened` | `censored` | `reopened` (closed) |
| `censored` | stays | stays |

When the judge gives no answer, the mark stays as it was.

**What it decides:** at the window's end, whether Gemini is asked again (§3.3).

**Its limit:** Gemma does not predict Gemini's filter.
- On 2026-10-30 it rated 97 lines of the backup's talk clean, and they went back to Gemini. Gemini's next call was
  blocked. This is why `reopened` became closed.
- On 2026-11-02 at 06:06 it rated 33 lines of a blocked prompt and flagged 1. Gemini was blocking on 6 other lines.

### 5. The probe (v5.16)

**What it does:**
1. After a prompt-stage block, once her backup line is sent, the same Gemini model gets the blocked prompt again,
   in parts.
2. It searches over the history lines, the recalled lines, the facts and today's thoughts, while the rest of the
   prompt stays fixed.
3. Each call is a Gemini 3.1 Pro request with that prompt. Only the result "blocked" or "not blocked" is used.
4. A set of lines that the probe proves blocks is marked `censored`.
5. If a fixed section (the canon, the rules) blocks, it is only named in the log.

**Its limits:**
- `PROBE_CALLS` per block and `PROBE_DAY_CALLS` per day.
- The defaults are 12 and 60. For her they are 30 and 200 since 2026-11-02 06:32 (the owner).
- If the probe proves nothing within its calls, the judge rates the blocked prompt's older lines (§4, case 3).

**What happened on 2026-11-02:**
- The day's 60 calls were spent by 02:11.
- From 06:06 on, every block went to the judge only, and the 6 lines that blocked Gemini stayed open.
- So each new message was blocked again.

### 6. Who closes what

| Who | What | Result |
|---|---|---|
| Gemini | blocks a prompt or an answer | his unanswered lines become `waiting` (or `censored`) |
| The probe | proves that lines of a blocked prompt block | those lines become `censored` |
| The judge | flags a line | `censored` |
| The judge | rates the backup's talk clean | `reopened` |
| The judge | rates clean a line that passed through Gemini | `clean` |
| The owner | `/purge`, then `/purge yes` | every `waiting`, `censored` and `reopened` line and fact is deleted |
| The owner | asks for a hand edit | the lines he names change their mark |

### 7. The re-check, which opens closed lines

**The one-off script of 2026-11-02 00:2x.** It ran after the owner's «все віднови з бекапу … і цензоред теж»:
- Every `censored` private line (1,219), thought and fact went to Gemini 3.1 Pro in groups of 20.
- Whatever Gemini did not block became `clean`.
- It opened 1,068 lines of 28.10–01.11: 542 his and 526 hers.
- About 150 of hers were the backup's answers. They were matched by time to the backup's calls, because the archive
  does not say who wrote a line.

**The v5.20 command, `python -m agents.talk recheck` (AGORA-174).** It does the same for a period's `censored` lines:
whatever Gemini does not block becomes `clean`. It runs only by hand, and it has not been run since.

**What went wrong:**
- It does not know which lines the backup wrote, so it opened the backup's answers. This breaks v5.15.4's rule.
- A group of 20 lines that passes can still block among the 300 lines of her real prompt. 22 such lines blocked her
  prompt at 02:34, and 6 more at 06:06–06:16; all of them were closed again.

**Who approved it.** Nobody approved opening the backup's lines:
- The script was Claude's reading of «і цензоред теж».
- The v5.20 command came from the owner's decision «тримати стиснутою на випадок якщо там якісь попали меседжі
  помилково». Claude wrote it into v5.20 as a re-check that reopens whatever Gemini passes, and did not exclude the
  backup's lines.

---

## Part 2 — phase v5.21: the owner's scheme (2026-11-02), planned

The phase is [ROADMAP.md §v5.21](../ROADMAP.md). This part is the same design in plain words.

### The rules

1. **Two marks.**
   - `gemini`: the line is open.
   - `blocked`: the line is closed for good. Nothing ever opens it again: no judge, no re-check, no script.
2. **A block** is Gemini blocking the prompt or the answer, or her caught refusal. On a block:
   - his message becomes `blocked`;
   - the backup answers, and her answer is `blocked`;
   - the backup mode starts for 5 minutes.
3. **During the backup mode:**
   - Gemini is not asked;
   - everything she says there is `blocked`;
   - his messages there are `blocked` too.
4. **After the 5 minutes,** his next message goes straight to Gemini. Nothing rates it first: there is no judge.
5. **More than 10 blocks in the last hour** start the backup mode for the next hour. There is no "until midnight"
   any more.
6. **`/gemini`** returns to Gemini at once, from the 5 minutes or from the hour, and resets the hour's count
   (*to confirm*).
   - `/status` shows the mode.
   - `/auto` goes.
   - `/backup` stays: the owner switches to the backup himself when he sees the talk turn explicit, until
     `/gemini`.
7. **The probe stays.** After a prompt-stage block, Gemini gets the blocked prompt in parts (30 calls a block, 200 a
   day). The old lines it proves block become `blocked` too. This is what lets her leave the backup when an old line
   in her history is the cause.
8. **Who reads a `blocked` line.** Only the backup, as part of its history: the last 300 lines, open and `blocked`,
   as far as its 32,000-token prompt allows. A `blocked` line is never in:
   - Gemini's prompt;
   - the recall (RAG), the facts or her thoughts;
   - the session note, the day journal or the talk summaries;
   - the backup's own recall or facts.
9. **The backup never keeps a fact:** a «запам'ятай» from the backup is dropped.
10. **Once a day,** at 05:00, every `blocked` line older than 24 hours loses its text for good:
    - The row keeps its key, time, speaker and mark, so that a Matrix private line re-read at a restart does not come
      back open.
    - `/purge` still deletes every `blocked` line at once.
11. **What goes:**
    - the judge (Gemma 4 31B on OpenRouter) with its settings;
    - `waiting` and `reopened` (the lines that have `clean` keep it and stay open, but nothing writes it again);
    - the day cap `FALLBACK_DAY_MAX`;
    - the window's end by the rating;
    - the v5.20 re-check command.

### The risk, and the owner's part

Without the judge, Gemini's own filter decides, on each message, at once. The owner (2026-11-02): the risk of a ban
by Google grows, so he must switch to the backup himself (`/backup`) when the talk turns to what should not reach
Gemini, and return with `/gemini`.

- **What actually changes.** On the normal route, his message always went to Gemini first, judge or no judge. The
  judge kept a message from Gemini in one place only: the first message after the 5-minute window. That message now
  goes to Gemini. While the talk stays explicit, this means one blocked request every 5 minutes at most. After more
  than 10 blocks in an hour, the backup takes the next hour.
- **The probe also sends blocked requests.** After each prompt-stage block it sends the blocked prompt to Gemini
  again, in parts, up to 30 times (200 a day). Many of those calls are blocked too. Lowering `PROBE_CALLS` and
  `PROBE_DAY_CALLS` sends fewer of them, but then an old line that blocks may stay open, as on 2026-11-02 06:06.
- **What `/backup` costs.** Everything said in the backup mode is `blocked`. Gemini-Кіра never knows it, and its
  text is gone after a day.
- **Not known:** Google does not publish after how many blocks it limits a key.

### The data when v5.21 goes live

A copy comes first. Only counts, times and marks are read.

- `waiting`, `censored` and `reopened` become `blocked`.
- Her 279 lines that the log names as the backup's, and his lines that they answered, become `blocked`.
- The `clean` lines and facts stay open, as they are: the owner decided to keep them for now and to decide if they
  cause trouble. `clean` is never written again, so they can still be found. The exception is the backup's own lines
  among them: 152 of hers that the backup wrote and 160 of his that it answered become `blocked` by the rule.
- The talk summaries already written stay.
- Then the first deletion runs, and every `blocked` line older than 24 hours loses its text.
- No copy is kept. The archive and facts copies on the host are deleted; the copies of her canon stay.

### Before the phase starts

v5.20 is released first, once the owner confirms or waives its live checks (#173–#175). One point is still
*to confirm*: whether `/gemini` resets the hour's count.
