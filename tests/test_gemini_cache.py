"""v7.5 (AGORA-256) — a companion's answers on Gemini: the start as the system instruction, the history then the tail
as the message, the start and the first lines of her history in an explicit context cache (made on the second answer
with the same start, reused, renewed, made again on a change, a call without it on any failure), and her window's
start in steps (the SDK faked; nothing reaches the network; made-up lines only)."""

import asyncio
from types import SimpleNamespace

from agents.gemini_cache import SEPARATOR, CachePlanner, channel_of
from agents.llm import GeminiClient
from agents.private import window_start
from agents.usage import PROMPT_SLOW

START = "КАНОН\n\nЖИТТЯ\n\nСПОГАДИ"
TAIL = "Зараз вечір.\n\nТи — Кіра."
HOUR = 3_600_000


# --- the plan (pure) ---------------------------------------------------------------------------------------------------
def history(n):
    return [f"Ich: рядок {i}" if i % 2 == 0 else f"Кіра: відповідь {i}" for i in range(n)]


def test_a_cache_is_made_on_the_second_answer_with_the_same_start_and_then_used():
    p = CachePlanner(ttl_s=600, rebuild_lines=40)
    assert p.plan("private", "m", START, history(10), 0).action == "plain"          # the first: quiet
    plan = p.plan("private", "m", START, history(12), 30)
    assert (plan.action, plan.lines, plan.why) == ("make", 10, "first")             # all but the newest two
    p.made("private", "c1", "m", START, history(12)[:10], 31)
    use = p.plan("private", "m", START, history(14), 60)
    assert (use.action, use.lines, use.name, use.renew) == ("use", 10, "c1", False)
    assert p.plan("private", "m", START, history(14), 400).renew is True            # past half its life: renewed


def test_a_quiet_hour_makes_none_and_a_changed_start_or_history_makes_another():
    p = CachePlanner(ttl_s=600, rebuild_lines=40)
    p.plan("private", "m", START, history(4), 0)
    assert p.plan("private", "m", START, history(6), 700).action == "plain"         # the second came after its life
    p.plan("private", "m", START, history(6), 710)
    p.made("private", "c1", "m", START, history(6)[:4], 711)
    assert p.plan("private", "m", "ІНШИЙ ПОЧАТОК", history(8), 720).action == "plain"   # a new start: first seen
    made = p.plan("private", "m", "ІНШИЙ ПОЧАТОК", history(8), 730)
    assert (made.action, made.why, made.old) == ("make", "start", "c1")
    p.made("private", "c2", "m", "ІНШИЙ ПОЧАТОК", history(8)[:6], 731)
    stepped = ["Ich: інший початок вікна", *history(8)[1:]]                          # the window stepped
    assert p.plan("private", "m", "ІНШИЙ ПОЧАТОК", stepped, 740).why == "history"
    p.made("private", "c3", "m", "ІНШИЙ ПОЧАТОК", history(8)[:6], 741)
    assert p.plan("private", "m", "ІНШИЙ ПОЧАТОК", history(60), 750).why == "grew"   # past the rebuild lines
    p.made("private", "c4", "m", "ІНШИЙ ПОЧАТОК", history(8)[:6], 751)
    assert p.plan("private", "m", "ІНШИЙ ПОЧАТОК", history(8), 1400).why == "quiet"   # its life over, a quiet start
    assert p.plan("private", "m", "ІНШИЙ ПОЧАТОК", history(8), 1410).why == "expired"


def test_a_failed_make_backs_off_with_plain_calls_and_agora_has_its_own_cache():
    p = CachePlanner(ttl_s=600)
    p.plan("private", "m", START, history(4), 0)
    assert p.plan("private", "m", START, history(6), 10).action == "make"
    p.failed("private", 10)
    assert p.plan("private", "m", START, history(6), 20).why == "backoff"
    assert p.plan("private", "m", START, history(6), 400).action == "make"          # after the backoff
    assert channel_of("reply") == "agora" and channel_of("private_nudge") == "private"
    assert p.held("agora") is None


# --- the window in steps (pure) ----------------------------------------------------------------------------------------
def test_the_windows_start_moves_in_steps_so_a_new_line_only_adds_to_its_end():
    times = [i * 10 * 60_000 for i in range(60)]                                     # a line every 10 minutes
    starts = {window_start(times, now, 6, 0, None, 2 * HOUR) for now in range(8 * HOUR, 10 * HOUR, 10 * 60_000)}
    assert len(starts) == 1                                                          # two hours, one start
    assert window_start(times, 10 * HOUR, 6, 0, None, 2 * HOUR) != starts.pop()     # then it steps
    assert window_start(times, 9 * HOUR, 6, 0) == window_start(times, 9 * HOUR, 6, 0, None, 0)  # 0: as before


# --- the client (the SDK faked) ----------------------------------------------------------------------------------------
class Caches:
    def __init__(self, fail=False):
        self.made, self.updated, self.deleted, self.fail = [], [], [], fail

    async def create(self, model, config):
        if self.fail:
            raise RuntimeError("too small")
        self.made.append((model, config))
        return SimpleNamespace(name=f"cachedContents/{len(self.made)}")

    async def update(self, name, config):
        self.updated.append(name)

    async def delete(self, name):
        self.deleted.append(name)


class Models:
    def __init__(self, fail_on_cache=False):
        self.calls, self.fail_on_cache = [], fail_on_cache

    async def generate_content(self, model, contents, config):
        self.calls.append({"contents": contents, "system": config.system_instruction,
                           "cached": config.cached_content})
        if self.fail_on_cache and config.cached_content:
            raise RuntimeError("cached content not found")
        return SimpleNamespace(
            text="Привіт!", usage_metadata=None,
            candidates=[SimpleNamespace(content=SimpleNamespace(parts=[SimpleNamespace(text="Привіт!", thought=False)]),
                                        finish_reason="STOP", safety_ratings=None)],
            prompt_feedback=None)


def gemini(caches=None, models=None, clock=None):
    g = GeminiClient.__new__(GeminiClient)
    g._client = SimpleNamespace(aio=SimpleNamespace(caches=caches or Caches(), models=models or Models()))
    g._sink = None
    g.model, g.reply_model, g.thinking_level = "gemini-2.5-flash", "gemini-3.1-pro-preview", "low"
    g.cache = CachePlanner(ttl_s=600, rebuild_lines=40)
    t = clock or [0.0]
    g._mono = lambda: t[0]
    return g


def answer(g, lines, kind="private", start=START):
    async def run():
        token = PROMPT_SLOW.set(start)
        try:
            return await g.reply("\n".join(lines), f"{start}\n\n{TAIL}", 4096, kind)
        finally:
            PROMPT_SLOW.reset(token)
    return asyncio.run(run())


def test_the_start_is_the_system_and_the_tail_follows_the_history_and_the_second_answer_reads_the_cache():
    caches, models = Caches(), Models()
    g = gemini(caches, models)
    assert answer(g, history(10))[0] == "Привіт!"
    plain = models.calls[-1]
    assert plain["system"] == START and plain["cached"] is None
    assert plain["contents"] == "\n".join(history(10)) + SEPARATOR + TAIL          # the tail next to his line
    answer(g, history(12))
    model, config = caches.made[0]
    assert model == "gemini-3.1-pro-preview" and config.system_instruction == START
    assert config.contents[0].parts[0].text == "\n".join(history(10))              # all but the newest two
    cached = models.calls[-1]
    assert cached["cached"] == "cachedContents/1" and cached["system"] is None
    assert cached["contents"] == "\n".join(history(12)[10:]) + SEPARATOR + TAIL
    answer(g, history(14))
    assert len(caches.made) == 1 and models.calls[-1]["cached"] == "cachedContents/1"


def test_a_cache_that_fails_is_a_plain_answer_never_silence():
    caches, models = Caches(fail=True), Models()
    g = gemini(caches, models)
    answer(g, history(10))
    assert answer(g, history(12))[0] == "Привіт!" and models.calls[-1]["cached"] is None
    gone = Models(fail_on_cache=True)
    g2 = gemini(Caches(), gone)
    answer(g2, history(10))
    assert answer(g2, history(12))[0] == "Привіт!"                                   # once more without it
    assert gone.calls[-2]["cached"] and gone.calls[-1]["cached"] is None and gone.calls[-1]["system"] == START


def test_a_background_call_and_an_unknown_start_go_as_before():
    models = Models()
    g = gemini(models=models)

    async def call(kind, slow):
        token = PROMPT_SLOW.set(slow)
        try:
            return await g.reply("Ich: привіт", "СИСТЕМА ЦІЛА", 4096, kind)
        finally:
            PROMPT_SLOW.reset(token)

    asyncio.run(call("private", None))                                              # no start known
    asyncio.run(call("summary", "СИСТЕМА"))                                         # not an answer
    for c in models.calls:
        assert (c["system"], c["contents"], c["cached"]) == ("СИСТЕМА ЦІЛА", "Ich: привіт", None)
    assert g.cache.held("private") is None
