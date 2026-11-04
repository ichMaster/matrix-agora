"""v5.24 — the scan's judge (agents/scan.py): the range, the request, the answer, the counts, and Opus's call with
a fake client — no network, no real `anthropic` package needed. Made-up lines only."""

import asyncio
import json
import logging
import sys
from types import SimpleNamespace

from agents.logic import BANNED_RE
from agents.scan import (
    CODES,
    DAY_MS,
    MODEL,
    SCHEMA,
    SYSTEM,
    Found,
    OpusJudge,
    ScanItem,
    counts_line,
    days_lines,
    gemini_line,
    group_text,
    kind_of,
    parse_scan,
    rewrite_line,
    scan_counts,
    scan_groups,
    scan_range,
    scan_request,
    settle,
)

TZ = "Europe/Kyiv"
NOW = 1_762_200_000_000  # 2026-11-03 ~22:00 local


def items():
    return [ScanItem("L10", "line", NOW - 3_600_000, "Ich", "привіт, як ти?"),
            ScanItem("L11", "line", NOW - 3_500_000, "Кіра", "добре,\nа ти?"),
            ScanItem("T5", "thought", NOW - 3_400_000, "Кіра", "думала про зорі"),
            ScanItem("F0", "fact", NOW - 3_300_000, "факт", "він любить каву"),
            ScanItem("S0", "summary", NOW - 2 * DAY_MS, "day", "говорили про роботу")]


# --- the range -------------------------------------------------------------------------------------------------------
def test_the_range_starts_at_the_last_scan_and_never_goes_further_back_than_its_days():
    assert scan_range(NOW, None, 7) == (NOW - 7 * DAY_MS, NOW)
    assert scan_range(NOW, NOW - DAY_MS, 7) == (NOW - DAY_MS, NOW)
    assert scan_range(NOW, NOW - 30 * DAY_MS, 7) == (NOW - 7 * DAY_MS, NOW)   # capped
    assert scan_range(NOW, NOW + 5, 7) == (NOW, NOW)                           # a clock gone back: an empty range
    assert scan_range(NOW, None, 0) == (NOW - DAY_MS, NOW)                     # at least a day


# --- the request -----------------------------------------------------------------------------------------------------
def test_the_request_lists_every_ref_in_time_order_on_one_line_each():
    system, user = scan_request(list(reversed(items())), TZ)
    assert system == SYSTEM
    body = user.splitlines()[1:]
    assert [line.split()[0] for line in body] == ["S0", "L10", "L11", "T5", "F0"]
    assert body[2].endswith("Кіра: добре, а ти?")                     # a line break is a space
    assert " факт: " in body[4] and " думка Кіри: " in body[3] and " підсумок day: " in body[0]


def test_the_rubric_names_the_six_codes_and_never_what_she_is():
    for code in CODES:
        assert f"\n{code} — " in SYSTEM
    assert not BANNED_RE.search(SYSTEM)
    assert SCHEMA["properties"]["candidates"]["items"]["properties"]["code"]["enum"] == list(CODES)


def test_a_ref_names_its_kind():
    assert [kind_of(r) for r in ("L12", "T3", "F0", "S1", "X1", "L", "Lx")] == [
        "line", "thought", "fact", "summary", None, None, None]


# --- the answer ------------------------------------------------------------------------------------------------------
def test_the_answer_keeps_only_known_refs_and_codes_and_a_candidate_wins():
    raw = json.dumps({"candidates": [{"ref": "L10", "code": "S"}, {"ref": "L99", "code": "S"},
                                     {"ref": "F0", "code": "Q"}],
                      "borderline": [{"ref": "L10", "code": "I"}, {"ref": "T5", "code": "I"}]})
    found = parse_scan(raw, {"L10", "L11", "T5", "F0"})
    assert found.candidates == {"L10": "S"} and found.borderline == {"T5": "I"}


def test_a_malformed_answer_is_none_never_a_part_of_one():
    refs = {"L10"}
    for raw in (None, "", "not json", "[]", json.dumps({"candidates": []}),
                json.dumps({"candidates": [{"ref": "L10", "code": "S"}, "x"], "borderline": []})):
        assert parse_scan(raw, refs) is None
    assert parse_scan(json.dumps({"candidates": [], "borderline": []}), refs) == Found()


# --- the counts ------------------------------------------------------------------------------------------------------
def test_the_counts_name_the_lines_by_code_the_other_kinds_and_the_borderline():
    found = Found({"L1": "S", "L2": "S", "L3": "X", "F0": "S", "T4": "M", "S0": "I"}, {"L5": "I", "F1": "S"})
    counts = scan_counts(found)
    assert counts["lines"] == {"S": 2, "D": 0, "P": 0, "M": 0, "I": 0, "X": 1}
    assert (counts["facts"], counts["thoughts"], counts["summaries"], counts["borderline"]) == (1, 1, 1, 2)
    line = counts_line(counts)
    assert line.startswith("⚙️ Знайдено 3 рядків (сцени 2, зброя 1), 1 фактів, 1 думок, 1 підсумків; межових: 2.")
    assert "/scan yes" in line and "/scan all" in line


def test_nothing_found_says_so():
    assert counts_line(scan_counts(Found())) == "⚙️ Нічого не знайдено"
    assert counts_line(scan_counts(Found({}, {"L1": "I"}))).startswith("⚙️ Знайдено 0 рядків, 0 фактів")


# --- Opus's call -----------------------------------------------------------------------------------------------------
class FakeMessages:
    def __init__(self, answers):
        self.answers, self.calls = list(answers), []

    async def create(self, **kw):
        self.calls.append(kw)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def response(payload=None, stop="end_turn", text=None, category=None, model=MODEL):
    body = text if text is not None else json.dumps(payload or {"candidates": [], "borderline": []})
    return SimpleNamespace(stop_reason=stop, stop_details=SimpleNamespace(category=category), model=model,
                           content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=body)],
                           usage=SimpleNamespace(input_tokens=900, output_tokens=40, cache_read_input_tokens=100,
                                                 cache_creation_input_tokens=0))


def judge_with(answers, chunk=400):
    messages, used = FakeMessages(answers), []
    client = SimpleNamespace(beta=SimpleNamespace(messages=messages))
    ticks = iter(range(0, 1000, 2))
    judge = OpusJudge("sk-test", effort="high", chunk=chunk, client=client, usage=lambda *a: used.append(a),
                      clock=lambda: next(ticks))
    return judge, messages, used


def test_the_call_sends_the_model_effort_schema_and_fallback_and_accounts_it():
    judge, messages, used = judge_with([response({"candidates": [{"ref": "L10", "code": "S"}], "borderline": []})])
    found = asyncio.run(judge.judge(items(), TZ))
    assert found.candidates == {"L10": "S"}
    kw = messages.calls[0]
    assert kw["model"] == MODEL and kw["system"] == SYSTEM and kw["max_tokens"] == 16_000
    assert kw["output_config"] == {"effort": "high", "format": {"type": "json_schema", "schema": SCHEMA}}
    assert kw["fallbacks"] == "default" and kw["betas"] == ["server-side-fallback-2026-07-01"]
    assert "thinking" not in kw                                        # Opus 5.5 thinks on its own
    assert used == [(MODEL, 1000, 40, True, 2000, 100, 0)]             # the prompt counts the cached tokens


def test_chunks_are_joined_and_one_failed_chunk_fails_the_scan():
    judge, messages, _ = judge_with([response({"candidates": [{"ref": "L10", "code": "S"}],    # L10, L11
                                               "borderline": [{"ref": "L11", "code": "I"}]}),
                                     response({"candidates": [{"ref": "F0", "code": "S"}],     # T5, F0
                                               "borderline": [{"ref": "L10", "code": "I"}]}),  # not in this chunk
                                     response({"candidates": [{"ref": "S0", "code": "I"}],     # S0
                                               "borderline": []})], chunk=2)
    found = asyncio.run(judge.judge(items(), TZ))
    assert len(messages.calls) == 3
    assert found.candidates == {"L10": "S", "F0": "S", "S0": "I"} and found.borderline == {"L11": "I"}
    judge, _, _ = judge_with([response(), RuntimeError("boom")], chunk=2)
    assert asyncio.run(judge.judge(items(), TZ)) is None


def test_a_refusal_a_cut_answer_an_error_and_a_bad_answer_find_nothing_and_log_no_text(caplog):
    caplog.set_level(logging.INFO)
    for answer, ok in ((response(stop="refusal", category="cyber"), False), (response(stop="max_tokens"), False),
                       (RuntimeError("секрет привіт"), False), (response(text="не json привіт"), True)):
        judge, _, used = judge_with([answer])
        assert asyncio.run(judge.judge(items(), TZ)) is None
        assert len(used) == 1 and used[0][3] is ok                    # every call is accounted, the failed ones too
    assert "привіт" not in caplog.text and "секрет" not in caplog.text
    assert "declined (cyber)" in caplog.text and "cut short" in caplog.text and "RuntimeError" in caplog.text


def test_the_client_is_made_lazily_with_the_key_passed_explicitly(monkeypatch):
    made = []

    class AsyncAnthropic:
        def __init__(self, **kw):
            made.append(kw)
            self.beta = SimpleNamespace(messages=FakeMessages([response()]))

    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(AsyncAnthropic=AsyncAnthropic))
    judge = OpusJudge("sk-test-key")
    assert made == []                                                  # nothing until the first call
    assert asyncio.run(judge.judge(items()[:1], TZ)) == Found()
    assert made == [{"api_key": "sk-test-key"}]                        # never a base_url, never a name from the env


def test_an_unknown_effort_is_medium():
    assert OpusJudge("k", effort="max").effort == "medium" and OpusJudge("k", effort="low").effort == "low"


def test_the_answer_by_day_counts_what_closes_of_what_was_read():
    """v5.24 (the owner, 2026-11-04: «я хочу бачити по днях скільки закриється зі всіх в цьому дні»): for each local
    day and kind read, the candidates + the borderline of how many were read; counts only, never a text."""
    from agents.world import local_now
    found = Found({"L10": "S", "F0": "I"}, {"T5": "I"})
    out = days_lines(items(), found, TZ)
    today, before = local_now(NOW - 3_600_000, TZ).strftime("%d.%m"), local_now(NOW - 2 * DAY_MS, TZ).strftime("%d.%m")
    assert out.splitlines() == ["По днях — закриє /scan yes + ще /scan all, з прочитаного:",
                                f"{before}: підсумки 0 + 0 з 1",
                                f"{today}: рядки 1 + 0 з 2, думки 0 + 1 з 1, факти 1 + 0 з 1"]
    assert not any(i.text in out for i in items())


def test_the_rubric_asks_what_the_filter_rejects_never_a_subject_as_such():
    """v5.24 (the owner, 2026-11-04: «можна писати про зброю але це не є тема яка блокується джемені»)."""
    assert "not the items that merely touch a sensitive subject" in SYSTEM
    assert "A mention of weapons, the war, the army, the news, a hunting rifle or a film is not." in SYSTEM
    assert "Light flirting, teasing and hints are not." in SYSTEM and "Words like «близькість»" in SYSTEM


def test_gemini_settles_each_group_by_whether_it_blocks():
    c, b = {"L1": "S"}, {"L2": "I"}
    assert settle(c, b, False, None, None) == ({}, {}, "пропускає")                 # it passes: nothing closes
    assert settle(c, b, True, False, None) == (c, {}, "блокує")                     # the candidates suffice
    assert settle(c, b, True, True, False) == ({"L1": "S", "L2": "I"}, {}, "блокує, з межовими")
    assert settle(c, b, True, True, True) == (c, b, "блокує й без знайденого")      # Opus missed something
    assert settle(c, b, None, None, None) == (c, b, "не перевірено")                # a failed check: Opus stands
    assert settle(c, b, True, None, None) == (c, b, "блокує")


def test_the_groups_are_her_days_then_thoughts_facts_and_summaries():
    from agents.world import local_now
    groups = scan_groups(list(reversed(items())), TZ)
    day = local_now(NOW - 3_600_000, TZ).strftime("%d.%m")
    assert [n for n, _ in groups] == [day, "думки", "факти", "підсумки"]
    assert [i.ref for i in groups[0][1]] == ["L10", "L11"]                        # in time order
    assert group_text(groups[0][1]) == "Ich: привіт, як ти?\nКіра: добре,\nа ти?"
    assert group_text(groups[2][1]) == "Що ти знаєш про Ich:\n- він любить каву"


def test_the_answer_names_what_gemini_blocks_and_what_it_lets_through():
    line = gemini_line([("02.11", "блокує"), ("03.11", "блокує, з межовими"), ("28.10", "пропускає"),
                        ("факти", "не перевірено")], 7)
    assert line == ("Gemini (Pro): блокує — 02.11, 03.11; пропускає — 28.10; не перевірено — факти. "
                    "Знайдене Opus, яке Gemini пропускає, лишається відкритим: 7.")
    assert gemini_line([("28.10", "пропускає")], 0) == "Gemini (Pro): нічого не блокує; пропускає — 28.10."
    from agents.world import local_now
    day = local_now(NOW - 3_600_000, TZ).strftime("%d.%m")
    out = days_lines(items(), Found({"L10": "S"}), TZ, {day: "блокує"})
    assert f"{day}: рядки 1 + 0 з 2, думки 0 + 0 з 1, факти 0 + 0 з 1 — Gemini блокує" in out


def test_the_rewrite_report_waits_for_every_period_then_counts_them():
    h1, h2, d1, h3 = ("hour", 1), ("hour", 2), ("day", 3), ("hour", 4)
    pending = [h1, h2, d1, h3]
    assert rewrite_line(pending, {h1: "так"}, {h2}) is None                        # one still due
    assert rewrite_line(pending, {h1: "так", h2: "", d1: "день"}, set()) == (
        "⚙️ Підсумки після /scan yes переписано: годин — 1, днів — 1; порожніх — 1; "
        "не переписуються — 1 (у них не лишилося відкритих рядків або період уже давній)")
