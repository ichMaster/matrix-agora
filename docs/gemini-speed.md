# Gemini models: the speed of Кіра's private answer

**Measured:** 2026-11-02, on the server, inside Кіра's container.
**Question (the owner):** her private answer on `gemini-3.1-pro-preview` takes ~17 s; the goal is ~5 s.

## Method

- **The prompt.** Her real private prompt as her own code builds it:
  - the instruction with every layer: the canon, the life, memories, plans, today, mood, thoughts, facts, the recall, the talk summaries, the private brief and the photo skill;
  - Gemini's open history window;
  - a made-up line of the owner's at the end («привіт, як ти?»).

  That is **41,218 input tokens** per call.
- **The calls.** Three calls per model, one after another, with the same prompt and `max_output_tokens` 4096.
- **What was recorded.** Only the wall time and the token counts. The answers' texts were not read or kept.
- **Blocks.** No call was blocked.

## Results

| Model | Thinking | Time per call (s) | Output tokens | Thinking tokens |
|---|---|---|---|---|
| `gemini-3.1-pro-preview` (now) | `low` | 12.9 · 14.4 · 13.3 | 122–146 | 980–1,160 |
| `gemini-3.5-flash` | `low` | 5.4 · 7.3 · 8.6 | 57–115 | 357–1,108 |
| `gemini-3.8-flash` | `low` | 4.3 · 4.5 · 4.4 | 90–190 | 0 |
| `gemini-3.8-flash` | `minimal` | — | — | — |
| `gemini-3.7-flash` | `low` | 3.3 · 4.1 · 3.9 | 77–189 | 0 |
| `gemini-3-flash-preview` | `minimal` | 3.1 · 3.6 · 3.1 | 218–330 | 0 |
| `gemini-2.5-flash` | off (`thinking_budget` 0) | 2.0 · 1.7 · 1.8 | 103–137 | 0 |
| `gemini-4-argon` (added later the same day) | `low` | 6.7 · 5.2 · 5.5 | 125–196 | 0 |

The `minimal` row for `gemini-3.8-flash` has no numbers because all three calls were rejected with a `ClientError`. That model does not accept the `minimal` level.

`gemini-4-argon` (Gemini 4 Argon) was measured later on 2026-11-02, in the same way, with a prompt of 42,112 tokens. It accepted `low` and did not think.

## What the numbers say

**Thinking takes most of the time on 3.1 Pro.**
- 3.1 Pro thinks for about 1,000 tokens before each answer, even at `low`.
- Its output runs at about 10 ms per token. So most of its 13–14 s goes on thinking, not on the answer or on reading the 41k-token prompt.
- The live median of 17.2 s also includes the time before the call (the today block, the recall, building the prompt) and the time after it (her voice note).

**Prompt caching would not bring 17 s down to 5 s.**
- Reading the prompt is a small part of the time.
- Caching mainly lowers the input cost.

**Which models reach 5 s.**
- **Under 5 s:** `gemini-3.8-flash` and `gemini-3.7-flash`, both at `low`, where neither model thought at all. Also `gemini-3-flash-preview` at `minimal`, though its answers ran about twice as long as the others.
- **Not reliably:** `gemini-3.5-flash` still thinks, and its time varies from 5 to 9 s.
- **Fastest:** `gemini-2.5-flash` with no thinking, at about 2 s.
- **Not measured here:** the voice note (ElevenLabs, ~1–3 s) and a photo (15–35 s) come on top of any model's time.

## With a cache

**Measured:** 2026-11-02, later the same day, on the server, inside Кіра's container.
**Question (the owner):** the same models with a cache, a few calls each, with only a few lines of text added at the end of each call.

### Method

- **The prompt.** Her real private prompt again: the instruction and Gemini's history window, 41,998 tokens.
- **The explicit cache.** For each model that has one, the instruction and the history went into an explicit cache once (`caches.create`, TTL 600 s). Then 4 calls followed, each sending only the end of the talk: made-up lines, 1, 3, 5 and then 7 of them, his line last. The cache was deleted afterwards.
- **Gemini 4 Argon.** It has no explicit cache (`createCachedContent` is not among its methods). It got the same 4 calls with the whole prompt each time, so only Gemini's implicit cache of a repeated start could help.
- **What was recorded.** The wall time, the token counts and the cached tokens. No answer's text was read or kept.

### Results

Each cell lists the 4 calls, with 1, 3, 5 and 7 lines added at the end. The last column is the same model in the first test, without a cache.

| Model | Thinking | Cache | Time per call (s) | Cached tokens | Thinking tokens | Without a cache (s) |
|---|---|---|---|---|---|---|
| `gemini-3.1-pro-preview` | `low` | explicit | 15.4 · 12.7 · 12.2 · 21.4 | 41,998 | 1,084–1,305 | 12.9 · 14.4 · 13.3 |
| `gemini-3.8-flash` | `low` | explicit | 3.7 · 3.8 · 22.0 · 3.2 | 41,998 | 0 | 4.3 · 4.5 · 4.4 |
| `gemini-3.7-flash` | `low` | explicit | 3.4 · 3.1 · 3.2 · 5.2 | 41,998 | 0 | 3.3 · 4.1 · 3.9 |
| `gemini-3.5-flash` | `low` | explicit | 2.1 · 2.2 · 2.9 · 2.8 | 41,998 | 0 | 5.4 · 7.3 · 8.6 |
| `gemini-3-flash-preview` | `minimal` | explicit | 3.1 · 2.4 · 2.4 · 2.5 | 41,998 | 0 | 3.1 · 3.6 · 3.1 |
| `gemini-2.5-flash` | off | explicit | 1.6 · 1.2 · 1.8 · 2.2 | 41,998 | 0 | 2.0 · 1.7 · 1.8 |
| `gemini-4-argon` | `low` | implicit | 8.8 · 8.9 · 26.0 · 6.0 | 40,063–40,113 | 0 | 6.7 · 5.2 · 5.5 |

Notes on the table:
- **Creating a cache** took 1.3–1.7 s on every model.
- **Argon's second call** (3 lines added) was blocked at the answer stage, although the added lines were neutral and made up.
- **Spikes.** Single calls of 21–26 s appeared on three models (3.1 Pro, 3.8 Flash, Argon) with no change in their tokens.

### What the cache numbers say

**On 3.1 Pro the cache changes nothing.** It still thinks for about 1,100–1,300 tokens before each answer, so the calls take 12–21 s with the prompt cached or not.

**On the Flash models it saves under a second.** That is about 0.5–1 s per call for 3.8, 3.7 and 3-flash-preview, and almost nothing for 2.5 Flash, which was already about 2 s.

**3.5 Flash was the exception.** It went from 5–9 s to 2–3 s, but in these calls it also did not think at all, while in the first test it thought for 357–1,108 tokens. So most of that gain is the missing thinking, not the cache.

**Gemini caches a repeated start on its own.** Argon's 2nd and 3rd calls in the first test already had 40,063 of their 42,112 tokens cached, with no cache made in code.

**Her live answers would not get that implicit cache as the prompt is built now.** Her instruction changes near its start at every message, for example:
- the place-and-time line, which carries the minute;
- the today block;
- the recall;
- the style line, drawn anew each time.

Gemini's history comes after the instruction, so the common start would hold the canon and little more. For the cache to cover most of the prompt, the parts that change at every message would have to move after the history. That is a change to the prompt order, which is a contract in ARCHITECTURE.md.

**What the cache does buy is price, not speed.** Google bills cached input tokens at a fraction of the normal input price, and an explicit cache adds a storage charge per hour.

## The canon alone

**Measured:** 2026-11-02, after the cache test, on the server, inside Кіра's container.
**Question (the owner):** the canon alone, with no dynamic content, with a cache and without.

### Method

- **The prompt.** The instruction is her canon and the rules line only: `build_instruction` with no other section. It has no place-and-time line, no today block, no mood, thoughts, facts, recall or talk summaries, no style line, and no history window. That is 8,400 characters, 3,089 tokens.
- **The calls.** Each model got 4 calls, carrying the same made-up lines as the cache test: 1, 3, 5 and then 7 of them, his line last.
- **Without a cache.** The instruction was sent whole with each call.
- **With a cache.** The instruction went into an explicit cache once (`caches.create`, TTL 600 s), and each call sent only the made-up lines. The cache was deleted afterwards. Argon has no explicit cache, so it is in the first run only.
- **What was recorded.** The wall time, the token counts and the cached tokens. No answer's text was read or kept.

### Results

Each cell lists the 4 calls, with 1, 3, 5 and 7 lines. The last column is the same model with her whole prompt (about 42,000 tokens) and no cache, from the first test.

| Model | Thinking | No cache (s) | Explicit cache (s) | Thinking tokens (no cache · cache) | Her whole prompt (s) |
|---|---|---|---|---|---|
| `gemini-3.1-pro-preview` | `low` | 13.2 · 9.8 · 11.9 · 10.0 | 9.0 · 11.2 · 10.9 · 7.1 | 880–1,167 · 523–1,026 | 12.9 · 14.4 · 13.3 |
| `gemini-3.8-flash` | `low` | 2.1 · 1.9 · 2.3 · 2.8 | 3.1 · 2.9 · 2.6 · 2.3 | 0 · 0 | 4.3 · 4.5 · 4.4 |
| `gemini-3.7-flash` | `low` | 2.6 · 2.6 · 2.8 · 2.5 | 2.3 · 2.5 · 2.4 · 2.5 | 0 · 0 | 3.3 · 4.1 · 3.9 |
| `gemini-3.5-flash` | `low` | 3.9 · 5.0 · 4.7 · 5.1 | 1.7 · 6.0 · 5.5 · 4.4 | 410–620 · 0–666 | 5.4 · 7.3 · 8.6 |
| `gemini-3-flash-preview` | `minimal` | 1.1 · 1.6 · 1.2 · 1.5 | 1.3 · 1.5 · 1.4 · 1.2 | 0 · 0 | 3.1 · 3.6 · 3.1 |
| `gemini-2.5-flash` | off | 0.8 · 0.9 · 0.7 · 0.9 | 0.8 · 0.8 · 0.8 · 0.8 | 0 · 0 | 2.0 · 1.7 · 1.8 |
| `gemini-4-argon` | `low` | 4.2 · 3.8 · 4.7 · 3.8 | — | 0 | 6.7 · 5.2 · 5.5 |

Notes on the table:
- **No implicit cache.** Without an explicit cache, no call had a cached token, on any model.
- **The explicit cache** took 1.2–1.4 s to create and was accepted at 3,089 tokens on every model that has one, 3.1 Pro included.
- **No blocks.** None of the 52 calls was blocked, Argon's included.
- **Shorter answers.** The answers were 21–112 tokens, against 57–330 with her whole prompt. A shorter answer takes less time to write, so part of the gain below comes from that.

### What the canon-alone numbers say

**With a prompt this small, the cache makes no difference.** On every model the times with and without the cache lie within the same range, about ±0.5 s.

**The size of the prompt does make a difference.** Going from about 42,000 tokens to 3,000 saved:
- about 1–2 s on the Flash models, roughly half their time;
- about 1–2 s on Argon;
- about 2–3 s on 3.1 Pro.

**On 3.1 Pro the thinking is still most of the time.** It thought for 520–1,170 tokens before each answer, and its times follow those counts. Its fastest call (7.1 s) had its smallest count (523). With no history and no dynamic sections it still took 7–13 s.

**3.5 Flash's thinking comes and goes.** At `low` it thought for 410–666 tokens in most calls and for 0 in one, and its time follows that: 1.7 s with no thinking, 4–6 s with it.

**The canon is a small part of her prompt.** It is about 3,000 of her 42,000 tokens. The rest is the dynamic sections and Gemini's history window. So caching the static start of her prompt (the canon) would save no time that can be measured, and little on the price.

### 3.8 Flash at higher thinking levels

**Question (the owner):** does 3.8 Flash think at all? At `low` it never had a thinking token in 15 calls.

**Method.** The canon alone again, 3 calls at each level with 1, 3 and 5 made-up lines. The thoughts were requested (`include_thoughts`), so a thought would show as a part of the answer even if no count came back. Only the parts were counted; no text was read.

| Level | Time per call (s) | Thinking tokens | Thought parts | Output tokens |
|---|---|---|---|---|
| `low` | 2.4 · 3.2 · 2.4 | 0 | 0 | 37–52 |
| `medium` | 11.6 · 9.4 · 13.0 | 679–891 | 1 in each call | 26–49 |
| `high` | 13.9 · 16.1 · 16.3 | 853–1,261 | 1 in each call | 30–52 |

**At `low` it does not think at all.** There was no thinking token and no thought part.

**At `medium` and `high` it does think, and it gets slow.** It thought for 680–1,260 tokens per answer and took 9–16 s. That is as slow as 3.1 Pro at `low`, which took 10–13 s for 880–1,170 thinking tokens on the same prompt. So with thinking on, 3.8 Flash is no faster than 3.1 Pro. It is fast at `low` only because it does not think there.

## Open questions before a switch

- **Quality.** Her language and character on a Flash model compared with 3.1 Pro. The owner judges this in a real conversation.
- **The safety filter.** Flash's filter is not Pro's. On 2026-11-02 one of her reflections blocked on Flash while the same lines passed on Pro, so a switch can change how often she is blocked.
- **Prices.** `gemini-3.7-flash`, `gemini-3.8-flash` and `gemini-4-argon` have no entry in `PRICE_MODELS` (`server/.env`) yet, so Analytics shows them without a cost until their prices are added.
- **Gemini 4 Argon.** It has no explicit cache, and its filter blocked a neutral made-up exchange at the answer stage once in 7 calls.
- **The prompt order for a cache.** A cache would only cover most of her live prompt if the parts that change at every message moved after the history. That is a contract change, so it is the owner's call.
- **The settings.** `GEMINI_REPLY_MODEL`'s choices in the panel are currently `gemini-2.5-flash`, `gemini-2.5-flash-lite` and `gemini-3.1-pro-preview`. A new model needs to be added there. `THINKING_MODELS` in `agents/llm.py` sets `thinking_level` only for 3.1 Pro, so a new model also needs its thinking setting there.
