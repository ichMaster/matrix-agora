#!/usr/bin/env bash
# Run one agent in the foreground (dev mode on the Mac). Ctrl+C stops it.
# Usage: scripts/run-agent.sh ada|bruno
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
name="${1:-}"
case "$name" in
  ada|bruno) exec uv run agents/agent.py "agents/$name.toml" ;;
  *) echo "usage: scripts/run-agent.sh ada|bruno" >&2; exit 2 ;;
esac
