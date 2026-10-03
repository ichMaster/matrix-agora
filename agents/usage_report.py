"""Token report: uv run agents/usage_report.py [--days N] [--since YYYY-MM-DD] [--markdown]

Reads every state/*.usage.jsonl and prints calls and tokens by day × agent ×
kind, with an estimated cost when PRICE_INPUT_PER_1M / PRICE_OUTPUT_PER_1M are
set in .env (USD per 1M tokens). Corrupt lines are skipped with a warning.
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

from agents.usage import aggregate, parse_lines, render


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
    ap.add_argument("--state-dir", default="state", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    load_dotenv()
    today = datetime.now(ZoneInfo(os.environ.get("TIMEZONE", "Europe/Kyiv"))).date()
    since = args.since or (today - timedelta(days=args.days - 1))
    lines: list[str] = []
    for path in sorted(Path(args.state_dir).glob("*.usage.jsonl")):
        lines += path.read_text(encoding="utf-8").splitlines()
    records, bad = parse_lines(lines)
    if bad:
        print(f"warning: skipped {bad} corrupt line(s)", file=sys.stderr)
    print(render(aggregate(records, since), _price("PRICE_INPUT_PER_1M"), _price("PRICE_OUTPUT_PER_1M"),
                 markdown=args.markdown))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
