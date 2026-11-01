"""v5.19 — the analytics (`agents/usage.py` `analyze`): one period and one agent (or all), by service, model, kind,
day and agent, with the trends, the previous period and the subscriptions' fees — pure, over made-up usage lines
(no text in any of them)."""

from datetime import date

import pytest

from agents.usage import (
    PriceBook,
    Row,
    analyze,
    fallback_usage_line,
    judge_usage_line,
    parse_subscription_prices,
    sdk_usage_line,
    stt_usage_line,
    trend,
    tts_usage_line,
    video_note_usage_line,
)

PRICES = PriceBook(price_in=0.30, price_out=2.50, models={"gemini-3.1-pro-preview": (2.0, 12.0),
                                                           "google/gemma-4-31b-it": (0.75, 1.0)},
                   seconds={"veed/fabric-1.0": 0.08})


def gem(day, kind="private", model="gemini-3.1-pro-preview", p=1_000_000, o=100_000, agent="kira", ok=True,
        blocked=None):
    return {"ts": f"{day}T12:00:00+02:00", "agent": agent, "kind": kind, "model": model, "prompt_tokens": p,
            "output_tokens": o, "total_tokens": p + o, "ok": ok, "engine": "gemini", "billing": "api",
            "blocked": blocked}


def kira_day(day):
    """One made-up day of hers across her seven services."""
    return [
        gem(day),                                                               # Pro: $2 + $1.2
        gem(day, "summary", "gemini-2.5-flash", 1_000_000, 0),                  # the default pair: $0.30
        gem(day, "embed", "gemini-embedding-001", 10_000, 0),                   # the default pair: $0.003
        judge_usage_line(f"{day}T12:00:00+02:00", "kira", "google/gemma-4-31b-it", 1_000_000, 0, True),  # $0.75
        video_note_usage_line(f"{day}T12:00:00+02:00", "kira", "veed/fabric-1.0", 20_000, True),        # $1.60
        tts_usage_line(f"{day}T12:00:00+02:00", "kira", "eleven_v4_turbo", 300, True),
        stt_usage_line(f"{day}T12:00:00+02:00", "kira", "nova-2", 4_000, True),
        fallback_usage_line(f"{day}T12:00:00+02:00", "kira", "private", "glm-4-6", True),
    ]


KIRA_DAY_COST = 2.0 + 1.2 + 0.30 + 0.003 + 0.75 + 1.60


def svc(report, name):
    return next(s for s in report["services"] if s["service"] == name)


def test_her_seven_services_grouped_with_their_models_billing_and_units():
    r = analyze(kira_day("2026-11-01"), date(2026, 11, 1), date(2026, 11, 1), "kira", PRICES)
    assert {s["service"] for s in r["services"]} == {"gemini", "openrouter", "fal", "elevenlabs", "deepgram", "novelai"}
    g = svc(r, "gemini")
    assert g["billing"] == "api" and g["calls"] == 3 and g["cost"] == pytest.approx(3.503)
    assert [m["model"] for m in g["models"]] == ["gemini-3.1-pro-preview", "gemini-2.5-flash", "gemini-embedding-001"]
    assert svc(r, "fal")["video_s"] == 20.0 and svc(r, "fal")["cost"] == pytest.approx(1.6)
    assert svc(r, "openrouter")["cost"] == pytest.approx(0.75)
    for sub, unit, value in (("elevenlabs", "characters", 300), ("deepgram", "audio_s", 4.0), ("novelai", "calls", 1)):
        s = svc(r, sub)
        assert s["billing"] == "subscription" and s["cost"] is None and s[unit] == value, sub  # never $0
    assert r["total"]["cost"] == pytest.approx(KIRA_DAY_COST) and r["total"]["complete"] is True
    assert r["services"][0]["service"] == "gemini" and r["services"][-1]["cost"] is None  # by cost, then calls


def test_claude_on_his_subscription_and_a_service_with_both_billings_is_mixed():
    lines = [sdk_usage_line("2026-11-01T10:00:00+02:00", "claude", "reply", "opus", {"input_tokens": 50,
                                                                                     "output_tokens": 5}, True),
             {**gem("2026-11-01", agent="claude"), "engine": "claude-sdk"}]
    r = analyze(lines, date(2026, 11, 1), date(2026, 11, 1), None, PRICES)
    assert svc(r, "claude-sdk")["billing"] == "mixed"


def test_the_period_is_inclusive_by_the_local_day_and_the_agent_filter_holds():
    lines = kira_day("2026-10-31") + kira_day("2026-11-01") + kira_day("2026-11-02") + [gem("2026-11-01", agent="ada")]
    r = analyze(lines, date(2026, 11, 1), date(2026, 11, 1), "kira", PRICES)
    assert r["total"]["calls"] == 8 and r["days"] == 1 and r["agents"] == [] and r["subscriptions"] == []
    every = analyze(lines, date(2026, 10, 31), date(2026, 11, 2), None, PRICES)
    assert every["total"]["calls"] == 25 and [a["agent"] for a in every["agents"]] == ["kira", "ada"]
    assert every["agents"][0]["services"][0] == "gemini"


def test_an_unpriced_model_is_none_listed_and_its_sums_are_incomplete():
    prices = PriceBook(models={"gemini-3.1-pro-preview": (2.0, 12.0)})  # no default pair: Flash has no price
    r = analyze([gem("2026-11-01"), gem("2026-11-01", "summary", "gemini-2.5-flash")], date(2026, 11, 1),
                date(2026, 11, 1), "kira", prices)
    g = svc(r, "gemini")
    assert g["cost"] == pytest.approx(3.2) and g["complete"] is False
    assert [m["cost"] for m in g["models"]] == [pytest.approx(3.2), None]
    assert r["unpriced"] == ["gemini-2.5-flash"] and r["total"]["complete"] is False
    assert {x["model"]: x["cost"] for x in r["rows"]} == {"gemini-2.5-flash": None,
                                                          "gemini-3.1-pro-preview": pytest.approx(3.2)}


def test_a_failed_call_without_counts_costs_nothing_and_is_never_unpriced():
    r = analyze([gem("2026-11-01", p=0, o=0, ok=False, blocked="prompt")], date(2026, 11, 1), date(2026, 11, 1),
                "kira", PriceBook())
    assert r["total"]["cost"] == 0 and r["unpriced"] == [] and r["total"]["failed"] == r["total"]["blocked"] == 1


def test_the_previous_period_has_the_same_length_and_ends_the_day_before():
    lines = kira_day("2026-10-25") + kira_day("2026-10-28") + kira_day("2026-11-01")
    r = analyze(lines, date(2026, 10, 29), date(2026, 11, 1), "kira", PRICES)
    assert (r["previous"]["since"], r["previous"]["until"]) == ("2026-10-25", "2026-10-28")
    assert r["previous"]["cost"] == pytest.approx(2 * KIRA_DAY_COST) and r["total"]["cost"] == pytest.approx(
        KIRA_DAY_COST)
    assert svc(r, "fal")["previous"] == {"cost": pytest.approx(3.2), "calls": 2, "tokens": 0}
    assert next(k for k in r["kinds"] if k["kind"] == "private")["previous"]["calls"] == 4  # Pro and the backup
    assert r["previous_cumulative"] == [pytest.approx(KIRA_DAY_COST), pytest.approx(KIRA_DAY_COST),
                                        pytest.approx(KIRA_DAY_COST), pytest.approx(2 * KIRA_DAY_COST)]


def test_every_day_is_in_the_series_with_its_moving_average_and_running_total():
    lines = kira_day("2026-10-26") + kira_day("2026-10-31") + kira_day("2026-11-02")
    r = analyze(lines, date(2026, 10, 31), date(2026, 11, 3), "kira", PRICES)
    ds = r["day_series"]
    assert [d["day"] for d in ds] == ["2026-10-31", "2026-11-01", "2026-11-02", "2026-11-03"]
    assert [d["calls"] for d in ds] == [8, 0, 8, 0]
    assert ds[0]["cost_by_service"]["fal"] == pytest.approx(1.6) and "elevenlabs" not in ds[0]["cost_by_service"]
    assert ds[0]["calls_by_service"]["elevenlabs"] == 1 and ds[1]["cost_by_service"] == {}
    # the first day's window reaches back to 10-26 (its first line): two costly days of six
    assert ds[0]["cost_avg7"] == pytest.approx(2 * KIRA_DAY_COST / 6)
    assert ds[-1]["cost_cumulative"] == pytest.approx(r["total"]["cost"])
    assert svc(r, "fal")["series"] == {"cost": [pytest.approx(1.6), 0, pytest.approx(1.6), 0], "calls": [1, 0, 1, 0]}


def test_the_trend_rises_falls_or_stays_flat():
    assert trend([1, 2, 3, 4, 5])["direction"] == "rising" and trend([1, 2, 3, 4, 5])["slope_per_week"] == 7
    assert trend([5, 4, 3, 2, 1])["direction"] == "falling"
    assert trend([2, 2, 2.01, 2, 2])["direction"] == "flat"           # under 5 % of the mean a day
    assert trend([0, 0, 9, 0, 9])["direction"] == "flat"              # fewer than 3 days that cost anything
    assert trend([3]) == {"slope_per_week": 0.0, "direction": "flat"}
    r = analyze(kira_day("2026-11-01"), date(2026, 11, 1), date(2026, 11, 2), "kira", PRICES)
    assert r["total"]["cost_per_day"] == pytest.approx(KIRA_DAY_COST / 2)
    assert r["trend"]["month_at_rate"] == pytest.approx(KIRA_DAY_COST / 2 * 30)


def test_the_subscriptions_fee_is_prorated_by_day_for_all_agents_only():
    prices = PriceBook(subscriptions={"elevenlabs": 99.0, "novelai": 25.0})
    r = analyze([], date(2026, 10, 17), date(2026, 11, 15), None, prices)   # 15 days of October, 15 of November
    fee = {s["service"]: s["period_cost"] for s in r["subscriptions"]}
    assert fee["elevenlabs"] == pytest.approx(99 * 15 / 31 + 99 * 15 / 30)
    assert fee["novelai"] == pytest.approx(25 * 15 / 31 + 25 * 15 / 30)
    assert analyze([], date(2026, 10, 17), date(2026, 11, 15), "kira", prices)["subscriptions"] == []


def test_no_data_gives_zeros_empty_lists_and_no_cost():
    r = analyze([], date(2026, 11, 1), date(2026, 11, 7), "kira", PRICES)
    assert r["total"]["calls"] == 0 and r["total"]["cost"] is None and r["total"]["cost_per_day"] is None
    assert r["services"] == r["kinds"] == r["rows"] == r["unpriced"] == []
    assert len(r["day_series"]) == 7 and r["trend"]["direction"] == "flat" and r["trend"]["month_at_rate"] is None


def test_the_kinds_carry_their_share_and_the_rows_their_atoms():
    r = analyze(kira_day("2026-11-01"), date(2026, 11, 1), date(2026, 11, 1), "kira", PRICES)
    share = {k["kind"]: k["share"] for k in r["kinds"]}
    assert share["video_note"] == pytest.approx(1.6 / KIRA_DAY_COST, abs=1e-4) and share["tts"] is None
    assert sum(v for v in share.values() if v) == pytest.approx(1, abs=1e-3)
    row = next(x for x in r["rows"] if x["service"] == "deepgram")
    assert set(row) == {"day", "agent", "service", "model", "kind", "calls", "failed", "blocked", "input", "output",
                        "tokens", "characters", "audio_s", "video_s", "billing", "cost"}
    assert row["cost"] is None and row["audio_s"] == 4.0


def test_the_row_counts_the_audio_heard():
    r = Row()
    r.add(Row(audio_ms=1500))
    assert r.audio_ms == 1500


def test_subscription_prices_parse_like_the_per_second_ones():
    assert parse_subscription_prices("elevenlabs=99, novelai=25") == ({"elevenlabs": 99.0, "novelai": 25.0}, [])
    assert parse_subscription_prices("elevenlabs=lots,=5,deepgram=-1") == ({}, ["elevenlabs=lots", "=5",
                                                                               "deepgram=-1"])
    assert parse_subscription_prices(None) == ({}, [])


def test_today_unfinished_and_the_days_before_the_first_line_leave_the_rate_and_the_trend():
    """Code review v5.19 #2: a flat $1 a day read «falling» every morning (today's $0.30 so far counted as a day),
    and an agent five days old always read «rising» (the zeros before its first line in the slope)."""
    steady = [gem(f"2026-11-0{d}", p=500_000, o=0) for d in range(1, 8)]          # Pro, $1 a day
    so_far = [gem("2026-11-08", p=150_000, o=0)]                                   # $0.30 so far today
    r = analyze(steady + so_far, date(2026, 11, 2), date(2026, 11, 8), "kira", PRICES, today=date(2026, 11, 8))
    assert r["total"]["cost_per_day"] == pytest.approx(1.0) and r["trend"]["direction"] == "flat"
    assert r["trend"]["month_at_rate"] == pytest.approx(30.0) and r["total"]["cost"] == pytest.approx(6.3)
    assert analyze(steady + so_far, date(2026, 11, 2), date(2026, 11, 8), "kira", PRICES)["trend"]["direction"] == (
        "falling")                                                                 # without today: as before
    young = analyze(steady, date(2026, 10, 9), date(2026, 11, 7), "kira", PRICES, today=date(2026, 11, 8))
    assert young["trend"]["direction"] == "flat" and young["total"]["cost_per_day"] == pytest.approx(1.0)
    only = analyze(so_far, date(2026, 11, 8), date(2026, 11, 8), "kira", PRICES, today=date(2026, 11, 8))
    assert only["total"]["cost_per_day"] == pytest.approx(0.3)                     # the only day stays
