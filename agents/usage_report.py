"""Token report: uv run agents/usage_report.py [--days N] [--since YYYY-MM-DD] [--markdown]
                                            [--write [DIR]]

Reads every state/*.usage.jsonl and prints calls and tokens by day × agent ×
kind, with an estimated cost when PRICE_INPUT_PER_1M / PRICE_OUTPUT_PER_1M are
set in .env (USD per 1M tokens). Corrupt lines are skipped with a warning.

--write writes the daily report (statistics for yesterday, the last 7 days,
the month so far and today) to DIR/YYYY-MM-DD.md and DIR/latest.md
(default DIR: reports/usage); scripts/usage-daily.sh runs it every morning.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from agents.usage import aggregate, daily_report, parse_lines, render


def _price(name: str) -> float | None:
    raw = os.environ.get(name, "").strip()
    try:
        return float(raw) if raw else None
    except ValueError:
        print(f"warning: {name} is not a number — no cost column", file=sys.stderr)
        return None


def _days(raw: str) -> int:
    """At least 1 — 0 or less would put the window in the future (code review #3)."""
    n = int(raw)
    if n < 1:
        raise argparse.ArgumentTypeError("must be 1 or more")
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Gemini token usage by day, agent and kind.")
    ap.add_argument("--days", type=_days, default=7, help="last N days (default 7)")
    ap.add_argument("--since", type=date.fromisoformat, help="from this date (overrides --days)")
    ap.add_argument("--markdown", action="store_true", help="print a markdown table")
    ap.add_argument("--write", nargs="?", const="reports/usage", metavar="DIR",
                    help="write the daily report to DIR/YYYY-MM-DD.md and DIR/latest.md (default reports/usage)")
    ap.add_argument("--state-dir", default="state", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    load_dotenv()
    now = datetime.now(ZoneInfo(os.environ.get("TIMEZONE", "Europe/Kyiv")))
    since = args.since or (now.date() - timedelta(days=args.days - 1))
    lines: list[str] = []
    for path in sorted(Path(args.state_dir).glob("*.usage.jsonl")):
        lines += path.read_text(encoding="utf-8").splitlines()
    records, bad = parse_lines(lines)
    if bad:
        print(f"warning: skipped {bad} corrupt line(s)", file=sys.stderr)
    prices = _price("PRICE_INPUT_PER_1M"), _price("PRICE_OUTPUT_PER_1M")
    if args.write:
        print(write_daily(Path(args.write), daily_report(records, now, *prices), now.date()))
        return 0
    print(render(aggregate(records, since), *prices, markdown=args.markdown))
    return 0


def write_daily(out_dir: Path, text: str, day: date) -> Path:
    """DIR/YYYY-MM-DD.md + DIR/latest.md, each written atomically; returns the dated path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    dated = out_dir / f"{day.isoformat()}.md"
    for path in (dated, out_dir / "latest.md"):
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    return dated


if __name__ == "__main__":
    raise SystemExit(main())
