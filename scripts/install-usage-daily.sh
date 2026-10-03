#!/usr/bin/env bash
# Installs the macOS launchd job that writes the daily token report at 07:00 (and at login);
# a Mac asleep at 07:00 runs it on wake. Re-run after moving the repo; --uninstall removes it.
set -euo pipefail
label=lan.agora.usage-report
plist="$HOME/Library/LaunchAgents/$label.plist"
domain="gui/$(id -u)"
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

launchctl bootout "$domain/$label" 2>/dev/null || true
if [[ "${1:-}" == "--uninstall" ]]; then
  rm -f "$plist"
  echo "removed $label"
  exit 0
fi

uv_bin="$(command -v uv)" || { echo "uv not found on PATH" >&2; exit 1; }
mkdir -p "$repo/reports/usage" "$(dirname "$plist")"
cat > "$plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key><array><string>$repo/scripts/usage-daily.sh</string></array>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>$(dirname "$uv_bin"):/usr/bin:/bin</string></dict>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>7</integer><key>Minute</key><integer>0</integer></dict>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$repo/reports/usage/daily.log</string>
  <key>StandardErrorPath</key><string>$repo/reports/usage/daily.log</string>
</dict>
</plist>
PLIST
plutil -lint -s "$plist"
launchctl bootstrap "$domain" "$plist"
echo "installed $label: every day at 07:00 -> $repo/reports/usage/latest.md"
