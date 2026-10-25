#!/usr/bin/env bash
# Deploy the repo's server/ config to the Ubuntu host and apply it (ROADMAP v0.2).
# The ONLY path by which server config reaches the host — never hand-edit files there.
# Usage: server/deploy.sh [--dry-run]
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONF="$REPO_DIR/server_con.yaml"
COMPOSE="$REPO_DIR/server/docker-compose.yml"
LOCAL_ENV="$REPO_DIR/server/.env"
CLAUDE_ENV="$REPO_DIR/server/claude.env"   # v4.4: Claude's own env file (the subscription's OAuth token)
HERMES_ENV="$REPO_DIR/server/hermes.env"   # v5.1: Hermes's own env file (his password, the Deepgram key)
VOICE_ENV="$REPO_DIR/server/voice.env"     # v5.3: the ElevenLabs key, for the members who speak
KIRA_ENV="$REPO_DIR/server/kira.env"       # v5.7: Кіра's bot token, the owner's Telegram id, her Deepgram key
REMOTE_DIR="matrix-agora/server"
DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

say() { printf '%s\n' "$*"; }
die() { say "deploy: ERROR: $*" >&2; exit 1; }

# --- read host/user from server_con.yaml (never the password: key auth only) ---
[ -f "$CONF" ] || die "missing $CONF"
HOST=$(awk -F': *' '$1=="host"{print $2}' "$CONF" | tr -d '"')
USER=$(awk -F': *' '$1=="user"{print $2}' "$CONF" | tr -d '"')
[ -n "$HOST" ] && [ -n "$USER" ] || die "server_con.yaml must define host and user"
TARGET="$USER@$HOST"

# --- preflight: the compose gate ---
say "deploy: preflight (compose config)"
REGISTRATION_TOKEN=dummy docker compose -f "$COMPOSE" config -q || die "compose preflight failed"

# --- key auth (one-time ssh-copy-id fallback, interactive) ---
if ! ssh -o BatchMode=yes -o ConnectTimeout=10 "$TARGET" true 2>/dev/null; then
  say "deploy: key auth not set up; running ssh-copy-id (you will be asked for the password once)"
  [ "$DRY_RUN" = 1 ] && die "--dry-run: key auth missing; run without --dry-run once to set it up"
  ssh-copy-id "$TARGET"
  ssh -o BatchMode=yes -o ConnectTimeout=10 "$TARGET" true || die "key auth still failing"
fi

# --- sync: compose always; .env only if it exists locally (never clobber the host's) ---
RSYNC_FLAGS=(-ai --checksum)
[ "$DRY_RUN" = 1 ] && RSYNC_FLAGS+=(-n)
say "deploy: sync → $TARGET:~/$REMOTE_DIR/"
# state/ and reports/ exist as the host user before compose bind-mounts them (else docker makes them root's)
ssh "$TARGET" "mkdir -p ~/$REMOTE_DIR ~/matrix-agora/state ~/matrix-agora/reports ~/matrix-agora/claude-workspace"
CHANGES=$(rsync "${RSYNC_FLAGS[@]}" "$COMPOSE" "$TARGET:$REMOTE_DIR/docker-compose.yml")
if [ -f "$LOCAL_ENV" ]; then
  CHANGES+=$'\n'"$(rsync "${RSYNC_FLAGS[@]}" "$LOCAL_ENV" "$TARGET:$REMOTE_DIR/.env")"
else
  say "deploy: no local server/.env — leaving the host's .env untouched"
fi
if [ -f "$CLAUDE_ENV" ]; then   # never printed: rsync -i lists the file name only
  CHANGES+=$'\n'"$(rsync "${RSYNC_FLAGS[@]}" "$CLAUDE_ENV" "$TARGET:$REMOTE_DIR/claude.env")"
  # private on the host too (the Mac's rsync cannot set modes): the subscription's token, Claude's password
  [ "$DRY_RUN" = 1 ] || ssh "$TARGET" "chmod 600 ~/$REMOTE_DIR/claude.env"
fi
if [ -f "$HERMES_ENV" ]; then   # never printed: rsync -i lists the file name only
  CHANGES+=$'\n'"$(rsync "${RSYNC_FLAGS[@]}" "$HERMES_ENV" "$TARGET:$REMOTE_DIR/hermes.env")"
  [ "$DRY_RUN" = 1 ] || ssh "$TARGET" "chmod 600 ~/$REMOTE_DIR/hermes.env"
fi
if [ -f "$VOICE_ENV" ]; then   # never printed: rsync -i lists the file name only
  CHANGES+=$'\n'"$(rsync "${RSYNC_FLAGS[@]}" "$VOICE_ENV" "$TARGET:$REMOTE_DIR/voice.env")"
  [ "$DRY_RUN" = 1 ] || ssh "$TARGET" "chmod 600 ~/$REMOTE_DIR/voice.env"
fi
if [ -f "$KIRA_ENV" ]; then   # never printed: rsync -i lists the file name only
  CHANGES+=$'\n'"$(rsync "${RSYNC_FLAGS[@]}" "$KIRA_ENV" "$TARGET:$REMOTE_DIR/kira.env")"
  [ "$DRY_RUN" = 1 ] || ssh "$TARGET" "chmod 600 ~/$REMOTE_DIR/kira.env"
fi
if [ -n "${CHANGES//[[:space:]]/}" ]; then say "deploy: changed:"; say "$CHANGES"; else say "deploy: nothing to sync"; fi

# --- apply ---
if [ "$DRY_RUN" = 1 ]; then
  say "deploy: --dry-run: would run: ssh $TARGET 'cd ~/$REMOTE_DIR && docker compose pull && docker compose up -d'"
else
  say "deploy: apply (docker compose pull && docker compose up -d)"
  ssh "$TARGET" "cd ~/$REMOTE_DIR && { (docker compose pull && docker compose up -d) || (sudo -n docker compose pull && sudo -n docker compose up -d); }" \
    || die "compose pull/up failed on the host"
fi

# --- verify: the homeserver answers ---
say "deploy: verify http://$HOST:8008/_matrix/client/versions"
for i in $(seq 1 12); do
  if curl -fsS -m 5 "http://$HOST:8008/_matrix/client/versions" >/dev/null 2>&1; then
    say "deploy: OK — homeserver answers"
    exit 0
  fi
  sleep 5
done
die "homeserver did not answer within 60 s"
