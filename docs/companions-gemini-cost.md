# Gemini 3.1 Pro: what Кіра's and Устина's talk costs, and four ways to cut it

**Written:** 2026-11-12, at the owner's request («зроби детальний аналіз як зекономити на gemini 3.1 pro запитах»).
He keeps both companions on Gemini 3.1 Pro («наразі найліпша їх поведінка на 3.1 про»), so this analysis looks for
savings on that model, not a move to another one.

**Data:** the week 2026-11-04 … 11-10, from three sources:
- the panel's Analytics (her usage lines: calls, tokens, prices, prompt parts);
- the host, read as counts only: the cache tokens on her usage lines, and the lines of her private chat by speaker
  and time — never a text.

Кіра talked all 7 days. Устина went live on 11-08, so her numbers cover 3 days.

**Earlier:** [gemini-cost.md](gemini-cost.md) (2026-11-02, Кіра alone, before the hourly memory and the scan) and
[gemini-speed.md](gemini-speed.md).

## In short

- **The bill.** 3.1 Pro cost **$96.78** for Кіра in 7 days (≈ $13.8 a day) and **$76.35** for Устина in 3 days
  (≈ $25 a day, her first and busiest days). At this pace that is **≈ $415 and ≈ $760 a month**.
- **Where it goes.** Her answers to you in the private chat take **84%** of Кіра's 3.1 Pro cost and **75%** of
  Устина's. Of one answer, **77%** is the input (her prompt) and **23%** the output (the thinking at `low` and the
  reply).
- **The prompt.** It is about **29,100 tokens** for Кіра and **19,900** for Устина. Google's cache served **0.1%** of
  those tokens, so every token is paid at the full price.
- **Blocks.** Blocked calls, the scan and its probes cost about **9%** of Кіра's 3.1 Pro and **23%** of Устина's, if
  Google bills a blocked prompt, which is not verified.
- **Four scenarios:**

  | Scenario | Saving |
  |---|---|
  | A. a shorter prompt (settings) | −8–10% |
  | B. the background and the blocks | −10–20% |
  | C. the prompt laid out for the cache | about −30% net |
  | D. Google's Flex tier | −50%, its speed to be tested first |

  C and D together come to about −65–70%.

## 1. The prices

From Google's pricing page (AI Studio, checked 2026-11-12), for prompts up to 200,000 tokens:

| 3.1 Pro (`gemini-3.1-pro-preview`) | Input | Output (thinking included) | Cache read | Cache storage |
|---|---|---|---|---|
| Standard (what both companions use now) | $2.00 / 1M | $12.00 / 1M | $0.20 / 1M | $4.50 / 1M tokens an hour |
| **Flex** | $1.00 / 1M | $6.00 / 1M | $0.20 / 1M | $4.50 / 1M an hour |
| Priority | $3.60 / 1M | $21.60 / 1M | $0.36 / 1M | $8.10 / 1M an hour |

The panel prices 3.1 Pro at $2 and $12 (`PRICE_MODELS`) and every input token at the full price, cached or not.
With 0.1% cached, that is right today.

## 2. The week in numbers

### Everything they cost

| | Кіра (7 days) | Устина (3 days) |
|---|---|---|
| **All services** | $159.06 | $127.93 |
| Gemini 3.1 Pro (her answers, her summaries, the scan) | **$96.78 (61%)** | **$76.35 (60%)** |
| Photos: Google's image model | $13.28 | $13.29 |
| Clips: Omni Flash | $11.18 | $11.17 |
| fal.ai: кружечки, Устина's Seedream photos | $32.75 | $25.44 |
| Gemini 2.5 Flash (the other background calls) | $3.06 | $1.69 |
| Anthropic API (the old scan's Opus, gone) | $2.01 | — |
| ElevenLabs, NovelAI, Deepgram, Claude on Max | subscriptions | subscriptions |

### Your messages and her answers

| | Кіра | Устина |
|---|---|---|
| Your lines in her private chat | **1,330** (≈ 190 a day) | **1,050** (≈ 350 a day) |
| Her lines there | 1,284 | 1,005 |
| Her answers to you through Gemini 3.1 Pro | 994 | 833 |
| … through the backup (NovelAI, a subscription) | 277 (22%) | 152 (15%) |
| … through Claude (the 7.3 test) | 22 | — |
| She wrote first | 31 | 18 |
| Her answers in Agora | 10 | 19 |
| Your lines that came right after one of yours (no answer between, within 60 s) | 165 (12%) | 194 (18%) |
| Your median reply time after her line | 40 s | 34 s |

Your bursts are already answered once: she never answers between two of your lines that come close together. So
there is little left to save by waiting longer before an answer.

### 3.1 Pro calls by kind

**Кіра** — 1,739 calls, $96.78:

| Kind | What it is | Calls | Blocked | Prompt / call | Output / call | Cost | Share |
|---|---|---|---|---|---|---|---|
| `private` | her answer to you | 1,074 | 78 | 29,127 | 1,471 | **$81.52** | **84.2%** |
| `talk_summary` | her memory of your talk, by the hour and the day | 285 | 44 | 5,096 | 1,280 | $7.28 | 7.5% |
| `scan_check` | the scan of the hours that block (v5.24) | 113 | 64 | 12,260 | 0 | $2.77 | 2.9% |
| `private_nudge` | she writes first | 33 | 4 | 27,920 | 1,895 | $2.59 | 2.7% |
| `reply` | her answer in Agora | 12 | 0 | 33,644 | 1,306 | $1.00 | 1.0% |
| `talk_check` | which periods need a summary | 168 | 0 | 2,542 | 0 | $0.85 | 0.9% |
| `probe` | the scan's checks of a blocked prompt | 44 | 42 | 6,452 | 0 | $0.57 | 0.6% |
| `summary` | the session summary | 10 | 5 | 5,073 | 786 | $0.20 | 0.2% |

**Устина** — 1,908 calls, $76.35:

| Kind | Calls | Blocked | Prompt / call | Output / call | Cost | Share |
|---|---|---|---|---|---|---|
| `private` | 1,047 | **195 (19%)** | 19,936 | 1,252 | **$57.48** | **75.3%** |
| `talk_summary` | 331 | 108 | 6,178 | 890 | $7.63 | 10.0% |
| `scan_check` | 314 | 166 | 10,804 | 0 | $6.79 | 8.9% |
| `probe` | 108 | 107 | 6,546 | 0 | $1.41 | 1.9% |
| `private_nudge` | 21 | 6 | 21,988 | 1,428 | $1.28 | 1.7% |
| `reply` | 21 | 1 | 15,678 | 1,089 | $0.93 | 1.2% |
| `talk_check` | 52 | 0 | 4,242 | 0 | $0.44 | 0.6% |
| `summary` | 14 | 10 | 10,852 | 480 | $0.38 | 0.5% |

**Calls per your message.** On 3.1 Pro there are 1.31 calls for each of your lines with Кіра (1,739 ÷ 1,330) and 1.82
with Устина (1,908 ÷ 1,050). The service calls, which are everything but her answers:

| | Calls | Share of calls | Cost | Share of cost |
|---|---|---|---|---|
| Кіра | 620 | 36% | $11.7 | 12% |
| Устина | 819 | 43% | $16.6 | 22% |

Устина's share is higher because her prompt blocks more and the scan works harder.

### One answer

| | Кіра | Устина |
|---|---|---|
| Input: the prompt | 29,127 tokens → **$0.058** | 19,936 tokens → **$0.040** |
| Output: the thinking at `low` and the reply | 1,471 tokens → $0.018 | 1,252 tokens → $0.015 |
| **One call** | **$0.076** | **$0.055** |
| One answer delivered, with blocked calls and second tries | $0.082 | $0.069 |

`low` is 3.1 Pro's lowest thinking level, so the output cannot be cut further on this model.

### What her prompt is made of

Averaged over her week's answers (the parts of `prompt_parts`, in tokens):

| Part | Кіра | Share | Устина | Share | Changes |
|---|---|---|---|---|---|
| `talk` — her memory of your talk (`TALK_PROMPT_WORDS`) | 7,119 | 24% | 2,012 | 10% | every hour |
| `history` — your talk word for word (`PRIVATE_HISTORY_HOURS`) | 5,963 | 20% | 5,179 | 26% | at every message |
| `life` — her life story (private version) | 3,267 | 11% | 3,580 | 18% | every day (the chapter) |
| `canon` — who she is (private version) | 2,566 | 9% | 4,025 | 20% | never |
| `memories` — her day memories | 2,815 | 10% | 241 | 1% | every day |
| `recall` — lines found by meaning (`RECALL_N`) | 1,918 | 7% | 310 | 2% | at every message |
| `brief` — the chat's rules and the style line | 1,098 | 4% | 1,326 | 7% | at every message (the style line) |
| `agora_today` | 1,039 | 4% | 684 | 3% | when Agora talks |
| `facts` | 981 | 3% | 542 | 3% | when she keeps a fact |
| `plans` | 700 | 2% | 630 | 3% | every day |
| `thoughts` | 553 | 2% | 181 | 1% | a few times a day |
| `summary`, `voice`, `mood`, `today`, `world`, `rules` | ~1,230 | 4% | ~1,220 | 6% | session, never, day, hour, minute, never |
| **Total** | **≈ 29,250** | | **≈ 19,940** | | |

About **18,400 tokens of Кіра's prompt (63%)** and **12,000 of Устина's (60%)** change at most once an hour. Besides
the history, only about 5,000 tokens of each change with every message.

### The cache: almost nothing

| | Prompt tokens on 3.1 Pro (`private`) | Served from the cache | Calls with any cache |
|---|---|---|---|
| Кіра | 31,282,080 | 22,264 (**0.1%**) | 1 of 1,074 |
| Устина | 20,873,315 | 20,327 (**0.1%**) | 5 of 1,047 |

Gemini caches implicitly only when the **start** of a prompt repeats. Her prompt starts with the stable parts, but
the per-message parts sit inside the same system instruction (the style line, the place and time, the recall), and
the history after it starts at a different line each time. So no two answers share a long enough start.

### What the blocks cost

The panel counts a blocked call's prompt as spent. Whether Google bills the input of a prompt-stage block is not
verified (§Open questions).

| | Кіра | Устина |
|---|---|---|
| Blocked `private` calls (their prompt) | 78 → $4.5 | 195 → $7.8 |
| The scan (`scan_check` + `probe`) | $3.3 | $8.2 |
| Blocked `talk_summary` and `summary` calls | $0.5 | $1.5 |
| **Total** | **≈ $8.4 (9%)** | **≈ $17.5 (23%)** |

### By day

| Day | Кіра: calls / cost | Устина: calls / cost |
|---|---|---|
| 11-04 | 364 / $16.8 | — |
| 11-05 | 383 / $23.1 | — |
| 11-06 | 271 / $17.7 | — |
| 11-07 | 286 / $16.2 | — |
| 11-08 | 240 / $11.7 | 919 / $31.1 |
| 11-09 | 139 / $8.3 | 617 / $29.3 |
| 11-10 | 56 / $2.9 | 372 / $16.0 |

The cost follows how much you write: a busy day with one companion costs $17–31.

## 3. Four scenarios

The savings are on this week's 3.1 Pro numbers: Кіра $96.78 for 7 days, Устина $76.35 for 3 days.

### A. A shorter prompt (settings and her texts, no code)

| Change | Кіра | Устина |
|---|---|---|
| `TALK_PROMPT_WORDS` 4000 → 2000 | −3,500 tokens | (her `talk` is 2,000 already) |
| `RECALL_N` 10 → 5 | −950 | −150 |
| Her private canon and life a third shorter (your texts) | −1,900 | −2,500 |
| **Per answer** | −4,500 tokens (−15% input) → **$0.067** instead of $0.076 | −3,000 (−15%) → **$0.049** instead of $0.055 |
| **Saving** | **≈ −$10 a week (−10%)** | **≈ −$6 per 3 days (−8%)** |

- **Work:** settings in the panel, and an edit of her private canon and life, which are yours.
- **Risk:** less detail of what she remembers and of her past. Only you can judge in talk whether she loses anything.
- `PRIVATE_HISTORY_HOURS` (Кіра 6 h) is the other lever, but the word-for-word talk is what keeps her answers
  connected.

### B. The background and the blocks (settings, one small code change)

| Change | Кіра | Устина |
|---|---|---|
| Her talk summaries on 3.1 Pro's Flex tier (D) instead of Standard: half price, same model, same quality | −$3.6 | −$3.8 |
| …or on Gemini 2.5 Flash, as her other background calls are: about $1.3 instead of $7.3–7.6 | −$6.0 | −$6.3 |
| The scan held to fewer checks (`SCAN_AUTO_HOUR_MAX` 3 → 1, `SCAN_CALLS_MAX` 40 → 15) | −$1.7 | −$4.1 |
| `/backup` by hand when the talk turns to what Gemini blocks: no blocked calls first | up to −$4.5 | up to −$7.8 |
| **Saving** | **≈ −$6–12 a week (−6–12%)** | **≈ −$8–18 per 3 days (−10–24%)** |

- **Work:** Flex for the background is one `service_tier` on those calls (google-genai 2.28 has
  `ServiceTier.FLEX`). Flash for the summaries is a setting of its own, and the scan's limits are panel settings.
- **Risk:**
  - Summaries on Flash are what v5.20 moved away from: you chose 3.1 Pro for her memory. Flex keeps the model.
  - A scan held back softens fewer blocked hours, so more of her answers go to the backup.

### C. The prompt laid out for the cache (v7.5, widened to Gemini)

Order her prompt from what never changes to what changes at every message:
1. the canon, the voice, the rules, the life, the plans, the mood, the session summary;
2. the day memories, the facts and the talk summaries, which change at most hourly;
3. the history window, moved forward in blocks of about 50 lines, so a new line only adds to its end;
4. last, next to your line: the style line, the place and time, the today block, the recall, Agora today and the
   thoughts.

About 80% of the prompt then repeats from one answer to the next:

| | Кіра | Устина |
|---|---|---|
| Repeating start (cache read at $0.20) | ≈ 23,200 tokens | ≈ 16,150 |
| Changing end (full price, $2) | ≈ 5,950 | ≈ 3,790 |
| Input per answer on a hit | **$0.017** instead of $0.058 | **$0.011** instead of $0.040 |
| One answer on a hit | **$0.034** (−55%) | **$0.026** (−53%) |

There are two ways to get the hits:
- **Implicit (free):** Gemini caches a repeating start by itself, but a hit is not promised. In the 2026-11-02 test it
  hit 1 time in 2 at 41,000 tokens. Saving: anywhere from 0 to ≈ $46 a week for Кіра and ≈ $31 per 3 days for
  Устина. Her usage lines already measure it (`cache_read_tokens`).
- **Explicit (sure):**
  - **What it costs.** The start is cached on purpose with a short life (~10 min, renewed while you talk). Each
    rebuild — hourly, and when the history block moves — costs one full-price read of the start (≈ $0.05 for Кіра,
    ≈ $0.03 for Устина). It also costs storage: ≈ $0.10 an hour for Кіра and ≈ $0.07 for Устина. That is ≈ $0.20
    and ≈ $0.14 per active hour.
  - **Net.** At your ~11–20 messages per active hour that comes to **≈ −$27 a week for Кіра (−28%)** and
    **≈ −$24 per 3 days for Устина (−31%)**.
  - **Quiet hours.** In an hour with one or two messages the cache costs more than it saves, so it is made only
    once a second message comes within its life.
- **Work:**
  - The prompt order is a contract, and v7.5 already plans it for Claude; this widens it to Gemini.
  - The per-message parts move from the system instruction into the message, after the history.
  - Analytics needs the cache price (a third number in `PRICE_MODELS`), or the saving will not show.
- **Risk:** with the time, the recall and the style line next to your last line, her answers may read differently. It
  may help, but you judge.

### D. Google's Flex tier

The same model and the same answers, at half the price: $1 and $6 instead of $2 and $12. The cache read stays $0.20.
In the code it is one field on the call.

| | Кіра | Устина |
|---|---|---|
| Everything on 3.1 Pro at Flex | **−$48 a week (−50%)** | **−$38 per 3 days (−50%)** |
| The background only (summaries, the scan, the checks) | −$5.8 (−6%) | −$8.3 (−11%) |

- **Work:** one setting per companion (Standard or Flex, for her answers and for her background apart), and Flex's
  price in Analytics.
- **Risk:** Google sells Flex for work that can wait. How long her answer takes on it, and how often Flex refuses for
  lack of capacity, is **not measured**.
- **Test first:** about 20 of her answer-sized calls at Flex, measured against her week's Standard numbers, which
  costs about $0.8. A Flex call that is refused or too slow falls back to Standard at once.
- **Then:**
  - If an answer stays within a few seconds of today's 14 s, put everything on Flex.
  - If not, put the background on Flex and keep her answers on Standard.

### The scenarios side by side

| Scenario | Work | Risk to her behaviour | Кіра a month | Устина a month (at her first days' pace) |
|---|---|---|---|---|
| Now | — | — | ≈ $415 | ≈ $760 |
| A. Shorter prompt | your settings and texts | detail of her memory and past | ≈ $375 | ≈ $700 |
| B. Background and blocks | settings + Flex on the background | fewer hours softened by the scan | ≈ $370 | ≈ $620 |
| C. Prompt for the cache | v7.5 for Gemini (a contract) | the prompt's order | ≈ $300 | ≈ $520 |
| D. Flex | one setting + a test | none expected; her answer time to check | ≈ $210 | ≈ $380 |
| **C + D** | both | as both | **≈ $140** | **≈ $250** |

## 4. Recommendation

1. **D first:** test Flex on about 20 answer-sized calls (≈ $0.8).
   - The background goes onto Flex in any case: no risk to how she answers.
   - Her answers go onto it too if their time holds.
2. **B's scan limits for Устина:** her scan and probes are 11% of her 3.1 Pro.
3. **C in v7.5:** the prompt for the cache, Gemini included. It is the largest saving that keeps Standard.
4. **A only if needed:** it trades her memory for money, and the others do not.

## Open questions

- **Blocked prompts.** Does Google bill the input of a prompt-stage block? If not, the blocks cost about half of
  what §What the blocks cost shows.
- **Flex.** What is its time and refusal rate for 3.1 Pro from our host, at her hours?
- **The implicit cache.** What hit rate does it reach once the prompt is reordered? Her usage lines will show it the
  first day.
- **Устина's pace.** Her three days were her first, so a quieter week will lower her monthly figure.
