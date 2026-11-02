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

The `minimal` row for `gemini-3.8-flash` has no numbers because all three calls were rejected with a `ClientError`. That model does not accept the `minimal` level.

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

## Open questions before a switch

- **Quality.** Her language and character on a Flash model compared with 3.1 Pro. The owner judges this in a real conversation.
- **The safety filter.** Flash's filter is not Pro's. On 2026-11-02 one of her reflections blocked on Flash while the same lines passed on Pro, so a switch can change how often she is blocked.
- **Prices.** `gemini-3.7-flash` and `gemini-3.8-flash` have no entry in `PRICE_MODELS` (`server/.env`) yet, so Analytics shows them without a cost until their prices are added.
- **The settings.** `GEMINI_REPLY_MODEL`'s choices in the panel are currently `gemini-2.5-flash`, `gemini-2.5-flash-lite` and `gemini-3.1-pro-preview`. A new model needs to be added there. `THINKING_MODELS` in `agents/llm.py` sets `thinking_level` only for 3.1 Pro, so a new model also needs its thinking setting there.
