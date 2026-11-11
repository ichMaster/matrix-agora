"""v7.4 — a companion's answer models (`ANSWER_MODEL`): the choices, the engine each is served by, the model each
answers on and the setting of its thinking. Plain data with no imports, so the panel reads it without the clients."""

# the choices in the panel's order, and the engine each answer is served by (her answer line's `by`, the usage line's)
CHOICES = ("api-gemini-3.1pro", "api-gpt-6.1sol", "api-sonnet", "claudemax-opus", "codex-gpt-6.1sol")
ENGINE_OF = {"api-gemini-3.1pro": "gemini", "api-gpt-6.1sol": "openai", "api-sonnet": "anthropic",
             "claudemax-opus": "claude", "codex-gpt-6.1sol": "codex"}
# the model each choice answers on (the Gemini one is her `GEMINI_REPLY_MODEL`), and the setting of its thinking with
# the default the owner chose (2026-11-11: as they ran, the new ones at `medium`) — none of them can be off
MODEL_OF = {"api-gpt-6.1sol": "gpt-6.1-sol", "api-sonnet": "claude-sonnet-5-5", "claudemax-opus": "claude-opus-5-5",
            "codex-gpt-6.1sol": "gpt-6.1-sol"}
THINKING_OF = {"api-gemini-3.1pro": ("GEMINI_THINKING_LEVEL", "low"),
               "api-gpt-6.1sol": ("OPENAI_REASONING_EFFORT", "medium"),
               "api-sonnet": ("SONNET_EFFORT", "medium"),
               "claudemax-opus": ("OPUS_EFFORT", "high"),
               "codex-gpt-6.1sol": ("CODEX_REASONING_EFFORT", "medium")}
