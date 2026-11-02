# Gemini 3.1 Pro: what Кіра's private answer costs, and how to cut it

**Written:** 2026-11-02, from her usage lines, her prompt's measured parts and a few test calls inside her container.
**Question (the owner):** a strategy to lower the cost of 3.1 Pro while she stays on it.
**Companion:** [gemini-speed.md](gemini-speed.md) holds the speed tests these numbers build on.

## Where the money goes

**Prices.** 3.1 Pro costs $2 per 1M input tokens and $12 per 1M output tokens, thinking included. `PRICE_MODELS` uses
the same pair: her `private` cost of the last 7 days, $58.24, is exactly 23.08M input × $2 plus 1.007M output × $12.
Third-party price tables also list a cache read at $0.50 per 1M (75% off) and cache storage at $4.50 per 1M tokens
per hour. These cache prices are not yet checked against Google's own page.

**One answer** sends about 41,000 input tokens and gets about 800–1,200 output tokens back, most of them thinking:

| | Tokens | Cost |
|---|---|---|
| Input | ~41,000 | $0.082 |
| Output and thinking | ~900 | $0.011 |
| **One answer** | | **≈ $0.093** |

So **88% of an answer's cost is its input.** Thinking cannot be lowered: 3.1 Pro rejects `minimal`
(`400 INVALID_ARGUMENT`), and `low`, which she uses now, is its lowest level.

**Per day.** She wrote 129–156 private lines a day from 2026-10-31 to 2026-11-02. At about 140 answers a day on
3.1 Pro that is about $13 a day, or about $390 a month.

**The rest of the 7 days** (2026-10-27 … 11-02, $175 in all):
- `probe`, $58: my diagnostic of the morning of 2026-11-02, not a recurring cost.
- `video_note`, $39: her кружечки on fal.ai.
- `photo`, $8.
- `talk_summary`, $5.2: mostly the one-time build of the v5.20 summaries (231 calls on 2026-11-02). It runs on 3.1 Pro.
- `reply` (Agora on 3.1 Pro), $2.6.
- Everything else under $1.1 each.

## What her prompt is made of

The sizes come from `prompt_parts` on her answers' usage lines (v5.22), averaged over 70 answers of 2026-11-02. The
tokens are estimated at 2.72 characters per token, the ratio measured on her canon (8,400 characters, 3,089 tokens).

| Part | Characters | ≈ Tokens | Share | Changes |
|---|---|---|---|---|
| `history` (Gemini's window, `PRIVATE_HISTORY_N` 300) | 40,578 | 14,900 | 36% | at every message: a line in, the oldest out |
| `talk` (the v5.20 summaries, `TALK_PROMPT_WORDS` 4000) | 24,131 | 8,900 | 21% | every hour |
| `life` | 15,530 | 5,700 | 14% | every day |
| `canon` | 8,330 | 3,100 | 7% | never |
| `memories` | 5,675 | 2,100 | 5% | every day |
| `recall` | 3,476 | 1,300 | 3% | at every message |
| `agora_today` | 3,475 | 1,300 | 3% | when Agora talks |
| `facts` | 2,477 | 900 | 2% | when she keeps a fact |
| `plans` | 2,056 | 800 | 2% | every day |
| `thoughts` | 1,950 | 700 | 2% | a few times a day |
| `brief` (with the style line) | 1,695 | 600 | 1% | at every message (the style line) |
| `summary` | 1,078 | 400 | 1% | every session |
| `voice` | 885 | 300 | 1% | never |
| `today`, `mood`, `rules`, `world` | 1,430 | 500 | 1% | hourly, daily, never, every minute |
| **Total** | **~112,000** | **~41,000** | | |

## The cache: what the tests showed

- **Her live answers get no cache now.** Her 461 private calls on 3.1 Pro of 2026-10-30 … 11-02 all have `cache_read_tokens` 0.
  The place-and-time line (`world`, with the minute) is the third part of the instruction. So two answers share only
  the canon and the life (about 9,000 tokens) at their start, and the history, which comes after the instruction,
  changes its first line at every message anyway.
- **9,000 identical tokens gave no implicit cache either.** Three calls in a row with the canon and the life as the
  instruction had 0 cached tokens. Moving the same text from the instruction into the first message changed nothing.
- **At 41,000 tokens the implicit cache works, but not every time.** In three calls with the canon, the life and
  1,300 made-up lines (40,809 tokens), the second call, identical to the first, had 38,760 tokens cached. The third
  call had the same 40,809 tokens at its start plus 2 lines and had 0 cached. Google does not promise an implicit hit.
- **The explicit cache always hit** on 3.1 Pro: 41,998 of 41,998 tokens in 4 of 4 calls, and 3,089 of 3,089 in
  4 of 4 (gemini-speed.md, §With a cache and §The canon alone). It took 1.2–1.7 s to create.
- **The cache does not make 3.1 Pro faster**, because its time is the thinking (gemini-speed.md). It only lowers the
  price.

## The strategy

Four steps, cheapest first. The first needs no code; the third is the big one.

### 1. A shorter prompt — the owner's switches, no code

| Change | Saves per answer | What she loses |
|---|---|---|
| `PRIVATE_HISTORY_N` 300 → 150 | ~6,000 tokens (the window halves; the summaries grow by about 1,000) ≈ $0.012 | the older half of the talk word for word. The hourly summaries still cover it |
| `TALK_PROMPT_WORDS` 4000 → 2000 | ~4,400 tokens ≈ $0.009 | detail in the older summaries |
| a shorter life section (her canon's `kira.life.md`, the owner's text) | up to ~3,500 tokens ≈ $0.007 | detail of her past |

Together this is about **−25–30% per answer**, about $0.065 instead of $0.093, and the prompt gets shorter to read
too. The owner judges in real talk whether she loses anything.

### 2. The summaries off 3.1 Pro — a small code change

`talk_summary` runs on her reply model (`agents/agent.py`, `_talk_text`). In steady use that is about 30 calls a
day (hourly, four-hourly, weekly), about $0.65 a day. A setting for its own model (for example `gemini-2.5-flash`)
would save about $0.55 a day. The Agora replies (`reply`, about $0.4 a day) are the same kind of choice. Both are
small next to her answers.

### 3. A prompt built for the cache — a contract change, the owner's call

Order the prompt from what never changes to what changes at every message, and slide the history in blocks:

1. **Stable for the day** (the instruction): the canon, the voice palette, the brief without its style line, the
   rules, the life, the memories, the plans, the mood. About 12,500 tokens.
2. **Stable for the hour:** the talk summaries. About 8,900 tokens (or 4,500 after step 1).
3. **The history window, sliding in blocks.** The window starts at a line that moves on 50 lines at a time, so between
   two moves every new line only adds to the end. That makes it 250–300 lines (or 100–150 after step 1).
4. **At every message, last** (after the history, before his line): the place and time, the today block, the
   thoughts, the facts, Agora today, the recall, the last-session summary, the style line and the move. About 5,000
   tokens.

Then about 88% of the prompt is a start that repeats from one answer to the next. On a cache hit an answer's input
costs about $0.028 instead of $0.082 (5,000 tokens at $2 plus 36,000 at $0.50), so the answer costs about **$0.039
instead of $0.093 (−58%)**. With step 1 as well, it is about **$0.033 (−65%)**.

Two ways to get the hits:
- **Gemini's implicit cache.** It costs nothing extra and needs no code beyond the order, but hits are not promised:
  1 of 2 in the test above. It is the first thing to try, and `cache_read_tokens` on her usage lines already measures
  the hit rate.
- **An explicit cache, if the implicit hit rate is low.** It would be made when the start changes (each hour, each
  50 lines, at midnight), with a TTL of about 10 minutes renewed while they talk. Each one costs a write at the full
  input price (36,000 tokens ≈ $0.07) and storage of about $0.16 an hour while it lives. It pays off from about
  4 answers in its hour; in an hour with one answer it costs more than it saves.

**What it changes.**
- The prompt order is a contract (ARCHITECTURE.md §Prompt assembly). The per-message parts move out of the system
  instruction into the contents, after the history, which also changes the backup's and the tests' view of the
  prompt.
- Analytics now prices every input token at the full price. It would need the cache price for `cache_read_tokens`
  (a third number in `PRICE_MODELS`), or the saving would not show.
- Her answers may read differently with the time, today and the recall next to his last line. It may well help, but
  the owner judges.

### 4. Not on 3.1 Pro — for comparison only

A Flash model at `low` (3.8, 3.7, Argon) does not think and costs a fraction per token. That changes her model, its
filter and her language, which is outside this question; the speed tests are in gemini-speed.md.

## The plan in short

| Step | Work | Per answer | A month (~140 answers a day) |
|---|---|---|---|
| Now | — | $0.093 | ~$390 |
| 1. Shorter prompt | owner's switches | ~$0.065 | ~$275 |
| 2. Summaries on Flash | small code | — | −$16 |
| 3. Prompt for the cache | contract change + Analytics pricing | ~$0.033 on a hit | ~$140 if every answer hits, ~$275 if none does |

## Open questions

- **Cache prices.** The $0.50 read and $4.50 storage come from third-party tables; Google's pricing page decides.
- **Blocked calls.** On 2026-11-02, 33 of her 167 private calls failed. Whether Google bills the input of a
  prompt-stage block is not known here; if it does, every block costs a full answer's input.
- **A block at 22:18.** A test call with her whole private prompt, built as her code builds it, was blocked at the
  prompt stage (`prohibited_content`) 3 times in 3. That was after the owner's `/unblock` at 22:14 and her answer at
  22:15. Her next answer may block the same way.
