#!/usr/bin/env bash
# Run one agent in the foreground (dev mode on the Mac). Ctrl+C stops it.
# Usage: scripts/run-agent.sh <name> — any agent listed in simulations.toml (v4.1: the roster, not a fixed pair)
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
name="${1:-}"
agents="$(uv run python -m agents.roster)"
if [[ -z "$name" ]] || ! grep -qxF -- "$name" <<<"$agents"; then
  echo "usage: scripts/run-agent.sh <name>   (one of: $(tr '\n' ' ' <<<"$agents"))" >&2
  exit 2
fi
exec uv run agents/agent.py "agents/$name.toml"
