"""v7.6 (AGORA-262) — her own recall on Gemini in `lumi` mode: two declarations in a person's words; a function call
run and sent back with the model's own turn; at most `RECALL_TOOL_ROUNDS` rounds, a call past them answered «більше
нічого», a failing call nothing; each round its own usage line, the calls on the answer's; the tools in her cache and
its fingerprint, in the request only without one; the handlers never give a closed line, a line her prompt holds or a
day not yet come; the recall before an answer smaller in `lumi` on Gemini alone (the SDK faked; made-up lines only)."""

import asyncio
from datetime import date
from types import SimpleNamespace

from google.genai import types

from agents.gemini_cache import CachePlanner
from agents.lumi import Digest, save_digest
from agents.memory_tools import (
    DAY_TALK,
    NO_MORE,
    NOTHING,
    RECALL,
    ToolSet,
    day_result,
    declarations,
    parse_day,
)
from agents.usage import PROMPT_SLOW, TOOL_CALLS
from tests.test_gemini_cache import START, TAIL, Caches, gemini, history
from tests.test_lumi_gists import day as day_of
from tests.test_lumi_memory import NOW, lumi, ms, say


# --- the words and the day (pure) -----------------------------------------------------------------------------------
def test_the_declarations_are_two_and_in_a_persons_words():
    [tool] = declarations()
    names = [f.name for f in tool.function_declarations]
    assert names == [RECALL, DAY_TALK]
    words = " ".join(f.description + " ".join(p.description for p in f.parameters.properties.values())
                     for f in tool.function_declarations).lower()
    for banned in ("модел", "бот", "інструмент", "функц", "штучн", " ai", "tool"):
        assert banned not in words


def test_a_day_is_its_gist_and_summaries_today_her_digest_and_a_day_not_yet_come_nothing():
    today = date(2026, 11, 14)
    assert day_result(date(2026, 11, 15), today, "завтра", "x", ["y"], "z") == NOTHING      # her future: nothing
    assert day_result(None, today, "", None, [], None) == NOTHING
    assert day_result(today, today, "сьогодні", None, [], "Про Атакаму.") == "Сьогодні: Про Атакаму."
    assert day_result(today, today, "сьогодні", None, [], None) == NOTHING
    got = day_result(date(2026, 11, 13), today, "вчора", "Про зорі.", ["Година перша.", "Година друга."], None)
    assert got == "вчора:\n- Про зорі.\n- Година перша.\n- Година друга."
    capped = day_result(date(2026, 11, 13), today, "вчора", None, ["раз два три", "чотири п'ять"], None, max_words=4)
    assert capped == "вчора:\n- раз два три"
    assert day_result(date(2026, 11, 12), today, "позавчора", None, [], None) == NOTHING
    assert parse_day("2026-11-13") == date(2026, 11, 13) and parse_day("учора") is None and parse_day(None) is None


# --- the rounds (the SDK faked) ---------------------------------------------------------------------------------------
def answer_resp(text="Пам'ятаю!"):
    return SimpleNamespace(text=text, usage_metadata=None, prompt_feedback=None, candidates=[SimpleNamespace(
        content=types.Content(role="model", parts=[types.Part(text=text)]), finish_reason="STOP",
        safety_ratings=None)])


def call_resp(name=RECALL, args=None):
    content = types.Content(role="model", parts=[types.Part(function_call=types.FunctionCall(
        name=name, args=args if args is not None else {"query": "зорі"}))])
    return SimpleNamespace(text=None, usage_metadata=None, prompt_feedback=None,
                           candidates=[SimpleNamespace(content=content, finish_reason="STOP", safety_ratings=None)])


class Calling:
    """Gemini that asks to recall `asks` times, then answers; records each request."""

    def __init__(self, asks=1):
        self.asks, self.calls = asks, []

    async def generate_content(self, model, contents, config):
        self.calls.append({"contents": contents, "config": config})
        if self.asks:
            self.asks -= 1
            return call_resp()
        return answer_resp()


def recalling(models, ran, fail=False, rounds=3, caches=None):
    g = gemini(caches, models)
    lines = []
    g._sink = lambda kind, model, usage, ok, **kw: lines.append((kind, ok, TOOL_CALLS.get()))

    async def run(name, args):
        ran.append((name, dict(args)))
        if fail:
            raise RuntimeError("archive gone")
        return "вчора: про зорі"

    g.tools_for = lambda kind: ToolSet(declarations(), run, rounds) if kind == "private" else None
    return g, lines


def ask(g, n=10, kind="private"):
    async def go():
        token = PROMPT_SLOW.set(START)
        try:
            return await g.reply("\n".join(history(n)), f"{START}\n\n{TAIL}", 4096, kind)
        finally:
            PROMPT_SLOW.reset(token)
    return asyncio.run(go())


def test_a_call_is_run_and_sent_back_with_the_models_own_turn_and_the_answer_follows():
    models, ran = Calling(asks=1), []
    g, lines = recalling(models, ran)
    assert ask(g)[0] == "Пам'ятаю!"
    assert ran == [(RECALL, {"query": "зорі"})]
    first, second = models.calls
    assert first["config"].tools and isinstance(first["contents"], str)               # offered, no cache yet
    user, model_turn, back = second["contents"]
    assert user.parts[0].text == first["contents"] and model_turn.parts[0].function_call.name == RECALL
    assert back.parts[0].function_response.response == {"result": "вчора: про зорі"}
    assert lines == [("private_recall", True, None), ("private", True, 1)]          # each round its line
    assert TOOL_CALLS.get() is None


def test_the_rounds_are_capped_a_call_past_them_is_told_no_more_and_a_failing_call_is_nothing():
    models, ran = Calling(asks=99), []
    g, lines = recalling(models, ran, rounds=3)
    assert ask(g) is None                                                           # it never stopped asking
    assert len(ran) == 3 and len(models.calls) == 5
    assert [k for k, _, _ in lines].count("private_recall") == 4                     # each round its own line
    assert models.calls[-1]["contents"][-1].parts[0].function_response.response == {"result": NO_MORE}
    models2, ran2 = Calling(asks=1), []
    g2, _ = recalling(models2, ran2, fail=True)
    assert ask(g2)[0] == "Пам'ятаю!"
    assert models2.calls[1]["contents"][-1].parts[0].function_response.response == {"result": NOTHING}
    plain, ran3 = Calling(asks=0), []
    g3, lines3 = recalling(plain, ran3)
    assert ask(g3, kind="reply")[0] == "Пам'ятаю!" and plain.calls[0]["config"].tools is None  # Agora: none offered
    assert lines3 == [("reply", True, None)]


def test_with_her_cache_the_tools_are_the_caches_and_its_fingerprint_takes_them():
    caches, models, ran = Caches(), Calling(asks=0), []
    clock = [0.0]
    g, _ = recalling(models, ran, caches=caches)
    g._mono = lambda: clock[0]
    ask(g, 10)
    clock[0] = 30
    ask(g, 12)
    [(_, made)] = caches.made
    assert made.tools and made.tools[0].function_declarations[0].name == RECALL     # in the cache
    cached = models.calls[-1]
    assert cached["config"].cached_content and cached["config"].tools is None       # never beside a cache
    p = CachePlanner(ttl_s=600)
    p.plan("private", "m", f"{START}\0recall+day_talk/1", [], 0)
    p.made("private", "c1", "m", f"{START}\0recall+day_talk/1", [], 1)
    assert p.plan("private", "m", START, [], 5).action != "use"                     # without the tools: another


# --- the handlers (her agent, a made-up archive) ----------------------------------------------------------------------
def test_recall_never_gives_a_closed_line_nor_one_her_prompt_holds_and_a_day_not_yet_come_is_nothing(tmp_path,
                                                                                                    monkeypatch):
    agent = lumi(tmp_path, monkeypatch, n=2, batch=2)
    say(agent, "o1", ms(2026, 11, 2, 9), "Ich", "Ми говорили про зорі над Атакамою.")
    say(agent, "c1", ms(2026, 11, 2, 9, 1), "Ich", "Закрите про зорі.", mark="blocked")
    say(agent, "w1", ms(2026, 11, 14, 17), "Ich", "Ще раз про зорі сьогодні.")
    for i in range(3):                                                               # her window: the last four
        say(agent, f"w{i + 2}", ms(2026, 11, 14, 17, i + 1), "Кіра" if i % 2 == 0 else "Ich", f"Рядок {i}.")
    got = asyncio.run(agent._run_memory_tool(RECALL, {"query": "зорі"}))
    assert "Атакамою" in got and "Закрите" not in got and "сьогодні" not in got     # the window is in her prompt
    assert asyncio.run(agent._run_memory_tool(RECALL, {"query": "  "})) == NOTHING
    assert asyncio.run(agent._run_memory_tool(DAY_TALK, {"date": "2026-11-20"})) == NOTHING
    assert asyncio.run(agent._run_memory_tool("інше", {})) == NOTHING
    agent.archive.talk_put("gist_day", *day_of(2026, 11, 13), "Вчора про обсерваторію.", 3, 0, 0, NOW)
    agent.archive.talk_put("hour", *day_of(2026, 11, 13)[:1], day_of(2026, 11, 13)[0] + 3_600_000,
                           "Година про телескоп.", 3, 0, 0, NOW)
    yesterday = asyncio.run(agent._run_memory_tool(DAY_TALK, {"date": "2026-11-13"}))
    assert yesterday == "вчора:\n- Вчора про обсерваторію.\n- Година про телескоп."
    save_digest(agent.digest_file, Digest("2026-11-14", 0, "Сьогодні про небо."))
    assert asyncio.run(agent._run_memory_tool(DAY_TALK, {"date": "2026-11-14"})) == "Сьогодні: Сьогодні про небо."


def test_the_tools_are_offered_alone_with_him_in_lumi_and_the_recall_before_an_answer_shrinks_on_gemini_alone(
        tmp_path, monkeypatch):
    agent = lumi(tmp_path, monkeypatch)
    agent.lumi_recall_n, agent.recall_n = 4, 6
    assert agent._memory_tools("private").rounds == 3 and agent._memory_tools("private_nudge") is not None
    assert agent._memory_tools("reply") is None
    assert agent._answers_on_gemini()
    monkeypatch.setenv("ANSWER_MODEL", "api-sonnet")
    assert not agent._answers_on_gemini()                                          # on Sonnet the memory stays inline
    monkeypatch.delenv("ANSWER_MODEL")
    monkeypatch.delenv("MEMORY_MODE")
    assert agent._memory_tools("private") is None                                  # `layered`: none
    seen = []
    real = agent.recall_section

    async def spy(query, places, exclude, gemini=True, meaning=True, n=None):
        seen.append(n)
        return await real(query, places, exclude, gemini, meaning, n)

    agent.recall_section = spy
    agent.private_history = [("Ich", "Привіт")]
    say(agent, "p1", ms(2026, 11, 14, 17), "Ich", "Привіт")
    asyncio.run(agent._gemini_private_prompt("Бриф."))
    monkeypatch.setenv("MEMORY_MODE", "lumi")
    asyncio.run(agent._gemini_private_prompt("Бриф."))
    monkeypatch.setenv("ANSWER_MODEL", "api-sonnet")
    asyncio.run(agent._gemini_private_prompt("Бриф."))
    assert seen == [None, 4, None]
