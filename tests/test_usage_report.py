import json
from datetime import date
from types import SimpleNamespace

import pytest

from agents import usage_report
from agents.usage import aggregate, cost, parse_lines, render, usage_line

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
