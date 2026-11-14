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
    quiet = p.plan("private", "m", "ІНШИЙ ПОЧАТОК", history(8), 720)                # a new start: first seen
    assert (quiet.action, quiet.old) == ("plain", "c1") and p.held("private") is None   # the old one deleted now
    made = p.plan("private", "m", "ІНШИЙ ПОЧАТОК", history(8), 730)
    assert (made.action, made.why, made.old) == ("make", "start", None)
    p.made("private", "c2", "m", "ІНШИЙ ПОЧАТОК", history(8)[:6], 731)
    stepped = ["Ich: інший початок вікна", *history(8)[1:]]                          # the window stepped
    assert p.plan("private", "m", "ІНШИЙ ПОЧАТОК", stepped, 740).why == "history"
    p.made("private", "c3", "m", "ІНШИЙ ПОЧАТОК", history(8)[:6], 741)
    assert p.plan("private", "m", "ІНШИЙ ПОЧАТОК", history(60), 750).why == "grew"   # past the rebuild lines
    p.made("private", "c4", "m", "ІНШИЙ ПОЧАТОК", history(8)[:6], 751)
    assert p.plan("private", "m", "ІНШИЙ ПОЧАТОК", history(8), 1400).why == "quiet"   # its life over, a quiet start
    assert p.plan("private", "m", "ІНШИЙ ПОЧАТОК", history(8), 1410).why == "expired"


def test_a_cache_of_another_start_is_deleted_at_once_not_stored_to_the_end_of_its_life():
    """Code review v7.5 #7: her start changed and no second answer came — the old cache is deleted on the first."""
    caches, clock = Caches(), [0.0]
    g = gemini(caches, clock=clock)
    answer(g, history(10))
    clock[0] = 30
    answer(g, history(12))
    assert caches.made and caches.deleted == []
    clock[0] = 60
    answer(g, history(14), start="НОВИЙ ПОЧАТОК")                                     # a new hour's summary
    assert caches.deleted == ["cachedContents/1"] and g.cache.held("private") is None


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
        return SimpleNamespace(name=f"cachedContents/{len(self.made)}",
                               usage_metadata=SimpleNamespace(total_token_count=15_000))

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
    g.cache_lines = []
    g.cache_start_only = None
    g.cache_sink = lambda model, tokens, ttl_s, made: g.cache_lines.append((model, tokens, ttl_s, made))
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


def test_a_call_that_fails_on_the_cache_backs_off_instead_of_making_one_at_every_answer():
    """Code review v7.5 #1: the model keeps refusing the cache — one cache made, then plain answers for a while."""
    caches, models, clock = Caches(), Models(fail_on_cache=True), [0.0]
    g = gemini(caches, models, clock)
    answer(g, history(10))
    for i, t in enumerate([30, 60, 90, 120, 150]):
        clock[0] = t
        assert answer(g, history(12 + 2 * i))[0] == "Привіт!"
    assert len(caches.made) == 1 and caches.deleted == ["cachedContents/1"]
    assert len(models.calls) == 7                                                    # 1 plain, 1 failed + 1 plain, 4 plain
    clock[0] = 30 + 301                                                              # after the backoff: tried again
    answer(g, history(30))
    assert len(caches.made) == 2


def test_a_hang_on_the_cache_is_two_tries_as_ever_and_the_cache_is_kept(monkeypatch):
    """Code review v7.5 #2: both tries hang on the cache — silence after them, no two tries more without it."""
    from agents import llm

    class Hanging(Models):
        async def generate_content(self, model, contents, config):
            if config.cached_content:
                self.calls.append({"cached": config.cached_content})
                await asyncio.sleep(1)
            return await super().generate_content(model, contents, config)

    monkeypatch.setattr(llm, "REPLY_TIMEOUT_S", 0.01)
    caches, models, clock = Caches(), Hanging(), [0.0]
    g = gemini(caches, models, clock)
    answer(g, history(10))
    clock[0] = 30
    assert answer(g, history(12)) is None
    assert [c["cached"] for c in models.calls[1:]] == ["cachedContents/1", "cachedContents/1"]
    assert caches.deleted == [] and g.cache.held("private").name == "cachedContents/1"


def test_her_agora_answers_go_plain_with_the_start_split_and_never_make_a_cache():
    """7.5.1 (the owner, 2026-11-14: «роби тільки 2»): an Agora cache held the start alone and was read again almost
    never — her Agora answers go without one; the split stays."""
    caches, models, clock = Caches(), Models(), [0.0]
    g = gemini(caches, models, clock)
    for i, t in enumerate([0, 30, 60, 90]):
        clock[0] = t
        assert answer(g, history(10 + 2 * i), kind="reply")[0] == "Привіт!"
    assert caches.made == [] and g.cache.held("agora") is None and g.cache_lines == []
    assert all(c["cached"] is None and c["system"] == START for c in models.calls)
    assert models.calls[-1]["contents"].endswith(SEPARATOR + TAIL)
    answer(g, history(10))                                                           # her private chat keeps its own
    clock[0] = 120
    answer(g, history(12))
    assert len(caches.made) == 1


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


# --- v7.5 (AGORA-258): the cache in the numbers -----------------------------------------------------------------------
def test_a_cache_made_and_renewed_writes_its_lines_and_the_cost_prices_reads_and_storage():
    import json

    from agents.usage import aggregate, cache_usage_line, cost, parse_lines, parse_model_prices
    clock = [0.0]
    g = gemini(clock=clock)
    answer(g, history(10))
    clock[0] = 30
    answer(g, history(12))
    clock[0] = 400                                                                   # past half its life: renewed
    answer(g, history(14))
    # made at 30 for 600 s; renewed at 400 to 1,000 — 370 s more stored, not a whole TTL (code review v7.5 #5)
    assert g.cache_lines == [("gemini-3.1-pro-preview", 15_000, 600, True), ("gemini-3.1-pro-preview", 15_000, 370, False)]
    made = cache_usage_line("2026-11-12T20:00:00+02:00", "kira", "gemini-3.1-pro-preview", 15_000, 600, True)
    renew = cache_usage_line("2026-11-12T20:05:00+02:00", "kira", "gemini-3.1-pro-preview", 15_000, 600, False)
    answer_line = {"ts": "2026-11-12T20:01:00+02:00", "agent": "kira", "kind": "private",
                   "model": "gemini-3.1-pro-preview", "prompt_tokens": 20_000, "output_tokens": 1_000,
                   "total_tokens": 21_000, "ok": True, "engine": "gemini", "billing": "api",
                   "cache_read_tokens": 15_000}
    records, bad = parse_lines([json.dumps(x) for x in (made, renew, answer_line)])
    assert bad == 0 and made["kind"] == "cache" and made["prompt_tokens"] == 15_000 and renew["prompt_tokens"] == 0
    prices, wrong = parse_model_prices("gemini-3.1-pro-preview=2/12/0.2/4.5,old=2/12,bad=1/2/3/4/5")
    assert prices == {"gemini-3.1-pro-preview": (2.0, 12.0, 0.2, 4.5), "old": (2.0, 12.0)} and wrong == ["bad=1/2/3/4/5"]
    total = sum(cost(row, 0.3, 2.5, prices) for row in aggregate(records).values())
    # made: 15k read at $2; the answer: 5k at $2, 15k at $0.20, 1k out at $12; storage: 15k × 1,200 s at $4.5/h
    expected = 15_000 * 2 / 1e6 + 5_000 * 2 / 1e6 + 15_000 * 0.2 / 1e6 + 1_000 * 12 / 1e6 + 15_000 * (1200 / 3600) * 4.5 / 1e6
    assert abs(total - expected) < 1e-9
    assert abs(cost(aggregate(records[2:])[next(iter(aggregate(records[2:])))], 0.3, 2.5,
                    {"gemini-3.1-pro-preview": (2.0, 12.0)}) - (20_000 * 2 / 1e6 + 1_000 * 12 / 1e6)) < 1e-9  # old form


def test_a_day_of_renewals_alone_prices_their_storage():
    """Code review v7.5 #6: made before midnight, renewed after it — the day's storage is never $0."""
    from datetime import date

    from agents.usage import PriceBook, _atom_cost, _atoms, cache_usage_line, parse_model_prices
    prices, _ = parse_model_prices("gemini-3.1-pro-preview=2/12/0.2/4.5")
    line = cache_usage_line("2026-11-13T00:10:00+02:00", "kira", "gemini-3.1-pro-preview", 15_000, 1800, False)
    [row] = _atoms([line], date(2026, 11, 13), date(2026, 11, 13)).values()
    book = PriceBook(0.3, 2.5, prices)
    assert abs(_atom_cost(row, book) - 15_000 * 0.5 * 4.5 / 1e6) < 1e-12


def test_analytics_shows_the_share_of_her_prompt_read_from_the_cache(tmp_path):
    import json

    from panel.memory import analytics_view
    lines = [{"ts": f"2026-11-12T20:0{i}:00+02:00", "agent": "kira", "kind": "private",
              "model": "gemini-3.1-pro-preview", "prompt_tokens": 20_000, "output_tokens": 900, "total_tokens": 20_900,
              "ok": True, "engine": "gemini", "billing": "api", "cache_read_tokens": c, "latency_ms": 9000}
             for i, c in enumerate([0, 15_000, 15_000, 15_000])]
    (tmp_path / "kira.usage.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    from datetime import date, datetime
    from zoneinfo import ZoneInfo
    view = analytics_view(tmp_path, date(2026, 11, 12), date(2026, 11, 12), "kira", date(2026, 11, 12),
                          datetime(2026, 11, 12, 21, 0, tzinfo=ZoneInfo("Europe/Kyiv")))
    [row] = view["prompts"]["cache"]
    assert (row["agent"], row["kind"], row["calls"], row["prompt"], row["cached"], row["share"]) == \
        ("kira", "private", 4, 80_000, 45_000, 0.5625)


def test_a_caches_own_lines_are_no_calls_in_the_prompts_tables(tmp_path):
    """Code review v7.5 #4: one cache made and three renewed beside four answers — four calls of 20,000 tokens."""
    import json
    from datetime import date, datetime
    from zoneinfo import ZoneInfo

    from agents.usage import cache_usage_line
    from panel.memory import analytics_view
    lines = [{"ts": f"2026-11-12T20:0{i}:00+02:00", "agent": "kira", "kind": "private",
              "model": "gemini-3.1-pro-preview", "prompt_tokens": 20_000, "output_tokens": 900, "total_tokens": 20_900,
              "ok": True, "engine": "gemini", "billing": "api", "cache_read_tokens": 15_000, "latency_ms": 9000}
             for i in range(4)]
    lines += [cache_usage_line(f"2026-11-12T20:1{i}:00+02:00", "kira", "gemini-3.1-pro-preview", 15_000, 600, i == 0)
              for i in range(4)]
    (tmp_path / "kira.usage.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    view = analytics_view(tmp_path, date(2026, 11, 12), date(2026, 11, 12), "kira", date(2026, 11, 12),
                          datetime(2026, 11, 12, 21, 0, tzinfo=ZoneInfo("Europe/Kyiv")))
    prompts = view["prompts"]
    [svc] = prompts["services"]
    assert (svc["calls"], svc["mean"]) == (4, 20_000) and [m["calls"] for m in svc["models"]] == [4]
    assert [k["kind"] for k in prompts["kinds"]] == ["private"] and prompts["agents"][0]["calls"] == 4
    assert prompts["caches_made"] == 1 and [r["kind"] for r in prompts["cache"]] == ["private"]


def test_a_history_that_slides_under_its_cache_makes_the_cache_hold_the_start_alone_for_a_while():
    """Устина's 12-hour window outgrows `HISTORY_N` 300 on a busy day: its start slides by a line at every message."""
    from agents.gemini_cache import START_ONLY_S
    p = CachePlanner(ttl_s=600, rebuild_lines=40)
    window = [f"Ich: рядок {i}" for i in range(300)]
    p.plan("private", "m", START, window, 0)
    plan = p.plan("private", "m", START, window, 10)
    p.made("private", "c1", "m", START, window[:plan.lines], 11)
    slid = window[1:] + ["Ich: новий"]                                                # the oldest out, a new one in
    again = p.plan("private", "m", START, slid, 20)
    assert (again.action, again.why, again.lines) == ("make", "history", 0)          # the start alone now
    p.made("private", "c2", "m", START, [], 21)
    for n in range(2, 30):                                                           # it slides on: used every time
        assert p.plan("private", "m", START, window[n:] + ["Ich: x"] * n, 20 + n).action == "use"
    p.made("private", "c3", "m", "НОВИЙ ПОЧАТОК", [], 100)                           # a new hour's start, later on
    p.plan("private", "m", "НОВИЙ ПОЧАТОК", window, 20 + START_ONLY_S)
    assert p.plan("private", "m", "НОВИЙ ПОЧАТОК", window, 30 + START_ONLY_S).lines > 0   # history tried again
