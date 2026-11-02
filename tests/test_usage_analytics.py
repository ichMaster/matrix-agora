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


# --- v5.22: the calls' and the answers' time, the prompts, the photos and videos ---------------------------------------
def timed(ts, kind="private", engine="gemini", model="gemini-3.1-pro-preview", latency=1000, prompt=None,
          agent="kira", ok=True, video_ms=None, output=None):
    return {"ts": ts, "agent": agent, "kind": kind, "model": model, "prompt_tokens": prompt, "output_tokens": output,
            "total_tokens": None, "ok": ok, "engine": engine, "billing": "subscription" if engine == "novelai" else "api",
            "latency_ms": latency, "video_ms": video_ms}


def ans(ts, wait, delay=0, answered="owner", by="gemini", agent="kira", place="private", door="telegram"):
    return {"ts": ts, "agent": agent, "place": place, "door": door, "answered": answered,
            "wait_ms": None if answered == "none" else wait, "delay_ms": delay, "by": by, "parts": []}


def test_the_calls_time_by_service_model_and_kind_with_the_previous_median_and_the_days():
    from agents.usage import analyze_detail
    lines = [timed("2026-11-01T10:00:00+02:00", latency=1000), timed("2026-11-01T11:00:00+02:00", latency=3000),
             timed("2026-11-02T10:00:00+02:00", latency=2000), timed("2026-11-02T11:00:00+02:00", latency=None),
             timed("2026-11-02T12:00:00+02:00", "private", "novelai", "glm-4-6", latency=8000),
             timed("2026-10-30T12:00:00+02:00", latency=500)]                        # the previous period
    r = analyze_detail(lines, [], date(2026, 11, 1), date(2026, 11, 2))
    gem_, nov = {s["service"]: s for s in r["speed"]["services"]}["gemini"], r["speed"]["services"][0]
    assert (gem_["n"], gem_["median"], gem_["p95"], gem_["max"], gem_["mean"]) == (3, 2000, 3000, 3000, 2000)
    assert gem_["previous_median"] == 500 and gem_["series"] == [1000, 2000]          # a null time is skipped
    assert gem_["models"][0]["model"] == "gemini-3.1-pro-preview"
    assert nov["service"] == "novelai" and r["speed"]["slowest"] == {"service": "novelai", "p95": 8000}
    assert {k["kind"] for k in r["speed"]["kinds"]} == {"private"} and r["buckets"] == ["2026-11-01", "2026-11-02"]


def test_a_one_day_period_is_by_hour():
    from agents.usage import analyze_detail
    lines = [timed("2026-11-02T08:15:00+02:00", latency=1000), timed("2026-11-02T08:45:00+02:00", latency=3000),
             timed("2026-11-02T11:00:00+02:00", latency=5000)]
    r = analyze_detail(lines, [], date(2026, 11, 2), date(2026, 11, 2))
    series = r["speed"]["services"][0]["series"]
    assert r["by_hour"] and len(r["buckets"]) == 24 and series[8] == 1000 and series[11] == 5000 and series[9] is None


def test_the_answers_time_with_the_pause_apart_by_agent_door_and_writer():
    from agents.usage import analyze_detail
    answers = [ans("2026-11-02T10:00:00+02:00", 9000, 3000), ans("2026-11-02T10:05:00+02:00", 30000, 2000, by="backup"),
               ans("2026-11-02T11:00:00+02:00", 4000, 1000, answered="agent", agent="ada", place="agora", door="matrix"),
               ans("2026-11-02T12:00:00+02:00", None, None, answered="none"),
               ans("2026-11-01T12:00:00+02:00", 6000, 1000)]                         # the previous period
    r = analyze_detail([], answers, date(2026, 11, 2), date(2026, 11, 2), agent="kira")["answers"]
    assert r["owner"]["wait"]["median"] == 9000 and r["owner"]["wait"]["max"] == 30000
    assert r["owner"]["net"]["median"] == 6000 and r["owner"]["previous_median"] == 6000 and r["first"] == 1
    by = {(g["by"], g["answered"]): g for g in r["groups"]}
    assert by[("backup", "owner")]["wait"]["median"] == 30000 and by[("gemini", "owner")]["net"]["median"] == 6000
    assert ("gemini", "agent") not in by                                            # ada's, not kira's
    every = analyze_detail([], answers, date(2026, 11, 2), date(2026, 11, 2))["answers"]
    assert {(g["agent"], g["answered"]) for g in every["groups"]} == {("kira", "owner"), ("ada", "agent")}


def test_the_prompts_mean_and_max_by_service_kind_and_agent_and_novelai_is_absent():
    from agents.usage import analyze_detail
    lines = [timed("2026-11-02T10:00:00+02:00", prompt=40000), timed("2026-11-02T11:00:00+02:00", prompt=60000),
             timed("2026-11-02T12:00:00+02:00", "reflection", prompt=10000),
             timed("2026-11-02T12:00:00+02:00", "private", "novelai", "glm-4-6"),
             timed("2026-11-01T12:00:00+02:00", prompt=20000)]
    r = analyze_detail(lines, [], date(2026, 11, 2), date(2026, 11, 2))["prompts"]
    assert [s["service"] for s in r["services"]] == ["gemini"]
    g = r["services"][0]
    assert (g["calls"], g["mean"], g["max"], g["previous_mean"]) == (3, 36667, 60000, 20000)
    assert {k["kind"]: k["mean"] for k in r["kinds"]} == {"private": 50000, "reflection": 10000}
    assert r["agents"] == [{"agent": "kira", "calls": 3, "mean": 36667, "max": 60000, "previous_mean": 20000}]


def test_photos_and_videos_in_all_by_hour_and_an_hour_on_average_and_a_frame_is_never_a_photo():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from agents.usage import analyze_detail
    lines = [timed("2026-11-02T08:10:00+02:00", "photo", model="gemini-nano-banana-2.1", prompt=4600, output=1500),
             timed("2026-11-02T08:20:00+02:00", "photo", model="gemini-nano-banana-2.1", ok=False),
             timed("2026-11-02T09:00:00+02:00", "frame", model="gemini-nano-banana-2.1", prompt=4600, output=1500),
             timed("2026-11-02T09:01:00+02:00", "video_note", "fal", "veed/fabric-1.0", video_ms=20000)]
    now = datetime(2026, 11, 2, 10, 0, tzinfo=ZoneInfo("Europe/Kyiv"))
    prices = PriceBook(models={"gemini-nano-banana-2.1": (1.50, 30.0)}, seconds={"veed/fabric-1.0": 0.08})
    m = analyze_detail(lines, [], date(2026, 11, 2), date(2026, 11, 2), now=now, prices=prices)["media"]
    assert (m["photos"], m["videos"], m["frames"], m["hours"]) == (1, 1, 1, 10.0)
    assert (m["photos_per_hour"], m["videos_per_hour"]) == (0.1, 0.1)
    assert m["cost"] == {"photos": 0.0519, "videos": 1.6519}                          # the frame is the video's cost
    assert m["series"][8] == {"bucket": "08", "photos": 1, "videos": 0} and m["series"][9]["videos"] == 1


def test_no_data_gives_empty_blocks_and_a_corrupt_answer_line_is_skipped():
    import json

    from agents.usage import analyze_detail, parse_answers
    r = analyze_detail([], [], date(2026, 11, 1), date(2026, 11, 2))
    assert r["speed"] == {"services": [], "kinds": [], "slowest": None}
    assert r["answers"]["owner"]["wait"]["n"] == 0 and r["answers"]["groups"] == [] and r["answers"]["first"] == 0
    assert r["prompts"]["services"] == [] and r["media"]["photos"] == r["media"]["videos"] == 0
    good = ans("2026-11-02T10:00:00+02:00", 9000)
    records, bad = parse_answers([json.dumps(good), "{torn", json.dumps({**good, "answered": "bot"}), ""])
    assert records == [good] and bad == 2
