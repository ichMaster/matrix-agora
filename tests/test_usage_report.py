import json
from datetime import date
from types import SimpleNamespace

import pytest

from agents import usage_report
from agents.usage import aggregate, cost, daily_report, parse_lines, render, usage_line

META = SimpleNamespace(prompt_token_count=1200, candidates_token_count=80, total_token_count=1280)

# --- parsing, aggregation, cost, render ---
LINES = [
    json.dumps(usage_line("2026-10-02T10:00:00+03:00", "ada", "reply", "m", META, True)),
    json.dumps(usage_line("2026-10-02T11:00:00+03:00", "ada", "reply", "m", META, True)),
    "{not json",
    json.dumps(usage_line("2026-10-03T09:00:00+03:00", "bruno", "plan", "m", None, False)),
    "",
]


def test_corrupt_lines_are_skipped_and_counted():
    recs, bad = parse_lines(LINES)
    assert len(recs) == 3 and bad == 1


@pytest.mark.parametrize("line", [
    '{"ts": "2026-10-03T10:00:00", "agent": "ada", "kind": "reply", "prompt_tokens": "12", "ok": true}',
    '{"ts": "2026-10-03T10:00:00", "agent": "ada", "kind": "reply", "prompt_tokens": true, "ok": true}',
    '{"ts": "2026-10-03T10:00:00", "agent": "ada", "kind": "reply", "ok": "yes"}',
    '{"ts": 20261003, "agent": "ada", "kind": "reply", "ok": true}',
    '{"ts": "2026-10-03T10:00:00", "agent": ["ada"], "kind": "reply", "ok": true}',
    '["2026-10-03"]', '"text"', "null", "5",
])
def test_well_formed_json_with_a_bad_shape_is_corrupt_not_a_crash(line):
    recs, bad = parse_lines([LINES[0], line])
    assert (len(recs), bad) == (1, 1)
    assert render(aggregate(recs), 0.30, 2.50) != "no data"  # code review #1


def test_aggregate_sums_and_window():
    recs, _ = parse_lines(LINES)
    rows = aggregate(recs)
    r = rows[("2026-10-02", "ada", "reply")]
    assert (r.calls, r.prompt, r.output, r.total) == (2, 2400, 160, 2560)
    assert rows[("2026-10-03", "bruno", "plan")].failed == 1
    assert ("2026-10-02", "ada", "reply") not in aggregate(recs, since=date(2026, 10, 3))


def test_cost_and_absent_prices():
    r = aggregate(parse_lines(LINES)[0])[("2026-10-02", "ada", "reply")]
    assert cost(r, 0.30, 2.50) == pytest.approx(2400 / 1e6 * 0.30 + 160 / 1e6 * 2.50)
    assert cost(r, None, 2.50) is None


def test_render_plain_markdown_totals_and_no_data():
    rows = aggregate(parse_lines(LINES)[0])
    plain = render(rows, None, None)
    assert "cost" not in plain and "TOTAL" in plain
    md = render(rows, 0.30, 2.50, markdown=True)
    assert md.startswith("| day | agent | kind |") and "cost $" in md
    assert "| TOTAL | all |" in md
    assert render({}, None, None) == "no data"


def test_report_command_end_to_end(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("PRICE_INPUT_PER_1M", raising=False)
    monkeypatch.delenv("PRICE_OUTPUT_PER_1M", raising=False)
    monkeypatch.setattr(usage_report, "load_dotenv", lambda: None)
    assert usage_report.main(["--state-dir", str(tmp_path), "--since", "2026-10-01"]) == 0
    assert capsys.readouterr().out.strip() == "no data"          # no files
    (tmp_path / "ada.usage.jsonl").write_text("\n".join(LINES), encoding="utf-8")
    monkeypatch.setenv("PRICE_INPUT_PER_1M", "0.30")
    monkeypatch.setenv("PRICE_OUTPUT_PER_1M", "2.50")
    usage_report.main(["--state-dir", str(tmp_path), "--since", "2026-10-01", "--markdown"])
    out, err = capsys.readouterr()
    assert "skipped 1 corrupt" in err and "| 2026-10-02 | ada | reply | 2 |" in out and "cost $" in out


@pytest.mark.parametrize("days", ["0", "-3", "x"])
def test_days_below_one_is_rejected_not_silent(tmp_path, days, capsys):
    with pytest.raises(SystemExit) as exc:
        usage_report.main(["--state-dir", str(tmp_path), "--days", days])
    assert exc.value.code == 2 and "--days" in capsys.readouterr().err  # code review #3


# --- the daily report (v3.1.1) ---
KYIV = __import__("zoneinfo").ZoneInfo("Europe/Kyiv")


def rec(ts, agent="ada", kind="reply", p=1000, o=100, ok=True):
    return {"ts": ts, "agent": agent, "kind": kind, "model": "m", "prompt_tokens": p, "output_tokens": o,
            "total_tokens": None if p is None else p + o, "ok": ok}


DAILY = [
    rec("2026-10-01T10:00:00+03:00", p=500, o=50),                          # the day before yesterday
    rec("2026-10-02T09:00:00+03:00"),
    rec("2026-10-02T09:05:00+03:00", agent="bruno"),
    rec("2026-10-02T23:59:00+03:00", kind="summary", p=3000, o=300),
    rec("2026-10-02T12:00:00+03:00", kind="plan", p=None, o=None, ok=False),
    rec("2026-09-20T12:00:00+03:00", p=7000, o=700),                        # outside the 7 days
    rec("2026-10-03T08:00:00+03:00", agent="bruno"),                        # today
]


def test_daily_report_sections_and_statistics():
    from datetime import datetime
    md = daily_report(DAILY, datetime(2026, 10, 3, 7, 0, tzinfo=KYIV), 0.30, 2.50)
    assert md.startswith("# Token usage — 2026-10-03")
    assert "Prices: $0.30 input / $2.50 output" in md
    y = md.split("## Yesterday — 2026-10-02")[1].split("## Last 7 days")[0]
    assert "| ada | 3 | 1 | 4,000 | 400 | 4,400 |" in y and "| bruno | 1 | 0 | 1,000 | 100 | 1,100 |" in y
    assert "| **all** | 4 | 1 | 5,000 | 500 | 5,500 |" in y
    assert "vs 2026-10-01: calls +300%, tokens +900%, cost +900%" in y
    kinds = y.split("### By kind")[1].split("### By agent")[0]
    assert kinds.index("| summary |") < kinds.index("| reply |") < kinds.index("| plan |")  # by share of tokens
    assert "| summary | 1 | 60% | 3,000 | 300 | 0 |" in kinds and "| reply | 2 | 40% | 1,000 | 100 | 0 |" in kinds
    week = md.split("## Last 7 days — 2026-09-26 … 2026-10-02")[1].split("## Month")[0]
    assert week.count("| 2026-") == 7 and "| 2026-09-26 | 0 |" in week          # empty days are listed
    assert "| **total** | 5 | 1 | 5,500 | 550 | 6,050 |" in week and "Busiest day: 2026-10-02" in week
    month = md.split("## Month so far — 2026-10 (days 1–2 of 31)")[1].split("## Today")[0]
    assert "5 calls · 1 failed · 6,050 tokens" in month
    assert f"projected month ${(5500 * 0.30 + 550 * 2.50) / 1e6 / 2 * 31:.2f}" in month
    today = md.split("## Today so far — until 07:00")[1]
    assert "| bruno | 1 | 0 | 1,000 | 100 | 1,100 |" in today and "Calls by kind: reply 1." in today


def test_daily_report_without_prices_or_data():
    from datetime import datetime
    md = daily_report([], datetime(2026, 10, 3, 7, 0, tzinfo=KYIV))
    assert "No prices set" in md and "cost" not in md and "$" not in md.replace("`", "")
    assert "No Gemini calls." in md and "No Gemini calls yet." in md


def test_on_the_first_the_month_is_the_whole_previous_month():
    from datetime import datetime
    one = rec("2026-10-31T12:00:00+02:00", p=1_000_000, o=100_000)            # $0.30 + $0.25
    md = daily_report([one], datetime(2026, 11, 1, 7, 0, tzinfo=KYIV), 0.30, 2.50)
    assert "## Month so far — 2026-10 (days 1–31 of 31)" in md
    assert "$0.5500 · projected month $0.55" in md


def test_write_daily_end_to_end(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(usage_report, "load_dotenv", lambda: None)
    monkeypatch.delenv("PRICE_INPUT_PER_1M", raising=False)
    monkeypatch.delenv("PRICE_OUTPUT_PER_1M", raising=False)
    state, out = tmp_path / "state", tmp_path / "reports"
    state.mkdir()
    (state / "ada.usage.jsonl").write_text("\n".join(json.dumps(r) for r in DAILY), encoding="utf-8")
    assert usage_report.main(["--state-dir", str(state), "--write", str(out)]) == 0
    dated = capsys.readouterr().out.strip()
    assert dated.endswith(".md") and (out / "latest.md").read_text() == (out / dated.rsplit("/", 1)[1]).read_text()
    assert "# Token usage — " in (out / "latest.md").read_text() and not list(out.glob("*.tmp"))
    (out / "latest.md").write_text("old", encoding="utf-8")
    usage_report.main(["--state-dir", str(state), "--write", str(out)])
    assert (out / "latest.md").read_text() != "old"                          # rewritten every run


# --- v5.1: Hermes's Pro calls priced as Pro, his voice in characters --------------------------------------------------
def hermes_lines():
    from agents.usage import tts_usage_line
    pro = SimpleNamespace(prompt_token_count=10_000, candidates_token_count=400, thoughts_token_count=1_600,
                          total_token_count=12_000)
    return [usage_line("2026-10-02T14:00:00+03:00", "hermes", "digest_voice", "gemini-3.1-pro-preview", pro, True),
            tts_usage_line("2026-10-02T14:00:05+03:00", "hermes", "eleven_turbo_v2_5", 1200, True)]


def test_the_daily_report_prices_pro_by_its_pair_and_shows_characters():
    from datetime import datetime
    models = {"gemini-3.1-pro-preview": (2.0, 12.0)}
    md = daily_report(hermes_lines(), datetime(2026, 10, 3, 7, 0, tzinfo=KYIV), 0.30, 2.50, models)
    assert "gemini-3.1-pro-preview $2 / $12" in md
    y = md.split("## Yesterday — 2026-10-02")[1].split("## Last 7 days")[0]
    assert "| **all** | 2 | 0 | 10,000 | 2,000 | 12,000 | 1,200 | 0.0440 |" in y   # 10k·2 + 2k·12 per 1M
    assert "| chars |" in y.split("### By agent × kind")[1]


def test_the_report_command_reads_price_models_and_warns_on_a_bad_entry(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(usage_report, "load_dotenv", lambda: None)
    monkeypatch.setenv("PRICE_INPUT_PER_1M", "0.30")
    monkeypatch.setenv("PRICE_OUTPUT_PER_1M", "2.50")
    monkeypatch.setenv("PRICE_MODELS", "gemini-3.1-pro-preview=2/12, broken")
    (tmp_path / "hermes.usage.jsonl").write_text("\n".join(json.dumps(x) for x in hermes_lines()), encoding="utf-8")
    usage_report.main(["--state-dir", str(tmp_path), "--since", "2026-10-01", "--markdown"])
    out, err = capsys.readouterr()
    assert "'broken'" in err and "| 2026-10-02 | hermes | digest_voice | 1 | 0 | 10000 | 2000 | 12000 | 0 | api | 0.0440 |" in out
    assert "| 2026-10-02 | hermes | tts | 1 | 0 | 0 | 0 | 0 | 1200 | subscription | — |" in out


def test_with_only_a_models_pair_the_report_never_prints_a_made_up_zero():
    """Review #5: the shipped examples set PRICE_MODELS and leave the Flash pair empty — the Flash rows' cost is
    unknown, so a total, an average or a projection that includes them is «—», never $0.0000."""
    from datetime import datetime
    models = {"gemini-3.1-pro-preview": (2.0, 12.0)}
    md = daily_report(DAILY + hermes_lines(), datetime(2026, 10, 3, 7, 0, tzinfo=KYIV), None, None, models)
    assert "No prices set" not in md and "Prices: gemini-3.1-pro-preview $2 / $12." in md
    assert "Other models have no price" in md
    assert "$0.0000" not in md and "projected month —" in md and ", cost —." in md
    hermes_only = daily_report(hermes_lines(), datetime(2026, 10, 3, 7, 0, tzinfo=KYIV), None, None, models)
    assert "| hermes | 2 | 0 | 10,000 | 2,000 | 12,000 | 1,200 | 0.0440 |" in hermes_only  # his own rows priced


FAL = "fal-ai/kling-video/ai-avatar/v2/standard"


def kira_video_lines():
    from agents.usage import video_note_usage_line
    return [video_note_usage_line("2026-10-02T18:00:00+03:00", "kira", FAL, 10000, True),
            video_note_usage_line("2026-10-02T18:30:00+03:00", "kira", FAL, None, False, "answer")]


def test_the_daily_report_prices_a_kruzhechok_per_second_and_shows_the_seconds():
    """v5.18: her кружечок is a `video_note` row — its seconds in a `video s` column, priced by PRICE_SECONDS."""
    from datetime import datetime
    md = daily_report(kira_video_lines(), datetime(2026, 10, 3, 7, 0, tzinfo=KYIV), None, None, {}, {FAL: 0.0562})
    assert f"{FAL} $0.0562 per second" in md
    y = md.split("## Yesterday — 2026-10-02")[1].split("## Last 7 days")[0]
    assert "| **all** | 2 | 1 | 0 | 0 | 0 | 10 | 0.5620 |" in y
    assert "| video s |" in y.split("### By agent × kind")[1]
    unpriced = daily_report(kira_video_lines(), datetime(2026, 10, 3, 7, 0, tzinfo=KYIV), 0.3, 2.5, {})
    assert "| **all** | 2 | 1 | 0 | 0 | 0 | 10 | — |" in unpriced                    # no price per second: «—»


def test_the_report_command_reads_price_seconds_and_warns_on_a_bad_entry(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(usage_report, "load_dotenv", lambda: None)
    for name in ("PRICE_INPUT_PER_1M", "PRICE_OUTPUT_PER_1M", "PRICE_MODELS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PRICE_SECONDS", f"{FAL}=0.0562, broken")
    (tmp_path / "kira.usage.jsonl").write_text("\n".join(json.dumps(x) for x in kira_video_lines()), encoding="utf-8")
    usage_report.main(["--state-dir", str(tmp_path), "--since", "2026-10-01", "--markdown"])
    out, err = capsys.readouterr()
    assert "PRICE_SECONDS entry 'broken'" in err
    assert "| 2026-10-02 | kira | video_note | 2 | 1 | 0 | 0 | 0 | 10 | api | 0.5620 |" in out


# --- v5.19: the analytics on the command line --------------------------------------------------------------------
def analytics_state(tmp_path):
    from agents.usage import stt_usage_line, tts_usage_line, video_note_usage_line
    lines = [rec("2026-10-30T10:00:00+02:00", "kira", "private"), rec("2026-11-01T10:00:00+02:00", "kira", "summary"),
             rec("2026-11-01T11:00:00+02:00", "ada", "reply"),
             video_note_usage_line("2026-11-01T12:00:00+02:00", "kira", "veed/fabric-1.0", 10_000, True),
             tts_usage_line("2026-11-01T12:00:00+02:00", "kira", "eleven_v4_turbo", 250, True),
             stt_usage_line("2026-11-01T12:00:00+02:00", "kira", "nova-2", 3_000, True)]
    (tmp_path / "kira.usage.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    return tmp_path


def by(tmp_path, capsys, *extra):
    assert usage_report.main(["--state-dir", str(tmp_path), "--since", "2026-10-31", "--until", "2026-11-01",
                              *extra]) == 0
    return capsys.readouterr().out


@pytest.mark.parametrize("group, labels", [
    ("service", ["gemini", "fal", "elevenlabs", "deepgram"]),
    ("model", ["gemini / m", "fal / veed/fabric-1.0", "elevenlabs / eleven_v4_turbo", "deepgram / nova-2"]),
    ("kind", ["summary", "reply", "video_note", "tts", "stt"]),
    ("day", ["2026-11-01"]),
    ("agent", ["kira", "ada"]),
])
def test_by_prints_each_grouping_and_a_total(analytics_env, tmp_path, capsys, group, labels):
    out = by(analytics_state(tmp_path), capsys, "--by", group)
    assert f"all agents · 2026-10-31 … 2026-11-01 (2 days) — by {group}" in out and "TOTAL" in out
    for label in labels:
        assert label in out, label
    assert "2026-10-30" not in out                     # before --since


def test_by_service_for_one_agent_prices_and_counts_her_units(analytics_env, tmp_path, capsys):
    out = by(analytics_state(tmp_path), capsys, "--by", "service", "--agent", "kira", "--markdown")
    assert out.startswith("kira · 2026-10-31") and "| service | calls |" in out and "ada" not in out
    rows = {line.split("|")[1].strip(): line for line in out.splitlines() if line.startswith("| ")}
    assert rows["fal"].rstrip(" |").endswith("0.8000") and "10" in rows["fal"]   # 10 s at $0.08
    assert rows["elevenlabs"].rstrip(" |").endswith("—") and "250" in rows["elevenlabs"]  # a subscription, never $0
    assert "3" in rows["deepgram"] and "Subscriptions" not in out                  # one agent: no fee


def test_by_service_with_all_agents_adds_the_fees_and_names_the_unpriced(analytics_env, tmp_path, capsys,
                                                                         monkeypatch):
    monkeypatch.setenv("PRICE_SUBSCRIPTIONS", "elevenlabs=31,bad")
    monkeypatch.setenv("PRICE_INPUT_PER_1M", "")
    analytics_state(tmp_path)
    assert usage_report.main(["--state-dir", str(tmp_path), "--since", "2026-10-31", "--until", "2026-11-01",
                              "--by", "service"]) == 0
    out, err = capsys.readouterr()
    assert "Subscriptions for the period: elevenlabs $2.03 ($31 a month)." in out   # 31/31 + 31/30
    assert "No price (a cost with them is «≥»): m." in out and "≥0.8000" in out
    assert "PRICE_SUBSCRIPTIONS entry 'bad' is not service=usd — ignored" in err


def test_until_with_days_counts_back_and_a_reversed_period_is_an_error(analytics_env, tmp_path, capsys):
    analytics_state(tmp_path)
    assert usage_report.main(["--state-dir", str(tmp_path), "--until", "2026-10-30", "--days", "1", "--by",
                              "day"]) == 0
    out = capsys.readouterr().out
    assert "2026-10-30 … 2026-10-30" in out and "2026-11-01" not in out
    assert usage_report.main(["--state-dir", str(tmp_path), "--since", "2026-11-02", "--until", "2026-11-01",
                              "--by", "day"]) == 2


def test_without_by_the_report_is_as_before(analytics_env, tmp_path, capsys):
    out = by(analytics_state(tmp_path), capsys)
    assert "by service" not in out and "kira" in out


@pytest.fixture
def analytics_env(monkeypatch):
    monkeypatch.setattr(usage_report, "load_dotenv", lambda: None)
    for name, value in (("PRICE_INPUT_PER_1M", "0.30"), ("PRICE_OUTPUT_PER_1M", "2.50"), ("PRICE_MODELS", ""),
                        ("PRICE_SECONDS", "veed/fabric-1.0=0.08"), ("PRICE_SUBSCRIPTIONS", "")):
        monkeypatch.setenv(name, value)
