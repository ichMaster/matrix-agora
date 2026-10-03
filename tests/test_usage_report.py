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
