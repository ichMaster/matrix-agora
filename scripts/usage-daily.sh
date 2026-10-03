#!/usr/bin/env bash
# The daily token report (v3.1.1): reports/usage/YYYY-MM-DD.md + reports/usage/latest.md.
# Scheduled by scripts/install-usage-daily.sh (launchd, every day at 07:00); safe to run by hand.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
exec uv run agents/usage_report.py --write reports/usage
