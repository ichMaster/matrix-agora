#!/usr/bin/env bash
# Deploy the repo's server/ config to the Ubuntu host and apply it (ROADMAP v0.2).
# The ONLY path by which server config reaches the host — never hand-edit files there.
# Usage: server/deploy.sh [--dry-run]
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONF="$REPO_DIR/server_con.yaml"
COMPOSE="$REPO_DIR/server/docker-compose.yml"
LOCAL_ENV="$REPO_DIR/server/.env"
VOICE_ENV="$REPO_DIR/server/voice.env"     # v5.3: the ElevenLabs key, for the members who speak
CANON_DIR="$REPO_DIR/agents/canon"        # v5.9.1: the private canon (gitignored) — only this Mac and the host hold it
REMOTE_DIR="matrix-agora/server"
KEEP_IMAGES="${KEEP_IMAGES:-2}"   # the newest tags of each image kept besides those a container uses (2026-11-02)
MIN_FREE_GB="${MIN_FREE_GB:-10}"  # the free space the host needs before a pull (2026-11-02)
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
ssh "$TARGET" "mkdir -p ~/$REMOTE_DIR ~/matrix-agora/state ~/matrix-agora/reports ~/matrix-agora/claude-workspace ~/matrix-agora/canon"
CHANGES=$(rsync "${RSYNC_FLAGS[@]}" "$COMPOSE" "$TARGET:$REMOTE_DIR/docker-compose.yml")
if [ -f "$LOCAL_ENV" ]; then
  CHANGES+=$'\n'"$(rsync "${RSYNC_FLAGS[@]}" "$LOCAL_ENV" "$TARGET:$REMOTE_DIR/.env")"
else
  say "deploy: no local server/.env — leaving the host's .env untouched"
fi
# v6.2: every member's own env file, `server/<name>.env` for each `agents/<name>.toml` that has one — Claude's
# subscription token (v4.4), Hermes's password (v5.1), a companion's bot token and keys (v5.7) — no member named here
for TOML in "$REPO_DIR"/agents/*.toml; do
  NAME=$(basename "$TOML" .toml)
  MEMBER_ENV="$REPO_DIR/server/$NAME.env"
  [ -f "$MEMBER_ENV" ] || continue
  CHANGES+=$'\n'"$(rsync "${RSYNC_FLAGS[@]}" "$MEMBER_ENV" "$TARGET:$REMOTE_DIR/$NAME.env")"  # never printed: -i lists the name
  # private on the host too (the Mac's rsync cannot set modes)
  [ "$DRY_RUN" = 1 ] || ssh "$TARGET" "chmod 600 ~/$REMOTE_DIR/$NAME.env"
done
if [ -f "$VOICE_ENV" ]; then   # never printed: rsync -i lists the file name only
  CHANGES+=$'\n'"$(rsync "${RSYNC_FLAGS[@]}" "$VOICE_ENV" "$TARGET:$REMOTE_DIR/voice.env")"
  [ "$DRY_RUN" = 1 ] || ssh "$TARGET" "chmod 600 ~/$REMOTE_DIR/voice.env"
fi
if [ -f "$CANON_DIR/common.md" ]; then   # never printed: rsync -i lists the file names only; nothing on the host is ever removed
  CHANGES+=$'\n'"$(rsync "${RSYNC_FLAGS[@]}" "$CANON_DIR/" "$TARGET:matrix-agora/canon/")"
  # private on the host: folders 700, files 600 — v5.17: a folder must stay searchable (`kira.face/`, her photos'
  # references); a bare `chmod 600 canon/*` left it unreadable to her container
  [ "$DRY_RUN" = 1 ] || ssh "$TARGET" "find ~/matrix-agora/canon -type d -exec chmod 700 {} + && find ~/matrix-agora/canon -type f -exec chmod 600 {} +"
else
  say "deploy: no local agents/canon/ — leaving the host's canon untouched"
fi
if [ -n "${CHANGES//[[:space:]]/}" ]; then say "deploy: changed:"; say "$CHANGES"; else say "deploy: nothing to sync"; fi

# --- retention (2026-11-02: 37 builds' images, never removed, filled the host's disk and every agent stopped): this
# project's image tags no container uses, beyond the newest $KEEP_IMAGES of each image, are removed, then the
# untagged images — before the pull and after the new containers are up ---
retention() {
  ssh "$TARGET" bash -s -- "$KEEP_IMAGES" "$DRY_RUN" <<'EOF'
set -uo pipefail
keep=$1 dry=$2
used=$(docker ps -a --format '{{.Image}}' | sort -u)
old=$(for repo in $(docker images --filter "reference=ghcr.io/ichmaster/matrix-agora-*" --format '{{.Repository}}' | sort -u); do
  docker images "$repo" --format '{{.CreatedAt}}|{{.Repository}}:{{.Tag}}' | grep -v ':<none>$' | sort -r | cut -d'|' -f2 \
    | grep -vxF "$used" | tail -n +$((keep + 1))
done)
n=$(printf '%s' "$old" | grep -c . || true)
if [ "$dry" = 1 ]; then echo "deploy: retention: would remove $n old image tag(s)"; exit 0; fi
echo "deploy: retention: removing $n old image tag(s)"
[ -n "$old" ] && printf '%s\n' "$old" | xargs docker rmi >/dev/null 2>&1
docker image prune -f >/dev/null 2>&1
exit 0
EOF
}

free_gb() {
  ssh "$TARGET" "df --output=avail -BG \"\$(docker info -f '{{.DockerRootDir}}' 2>/dev/null || echo /)\" | tail -1 | tr -dc 0-9"
}

# --- apply ---
retention || say "deploy: retention failed — going on"
FREE=$(free_gb || true)
say "deploy: ${FREE:-?} GB free on the host (needs $MIN_FREE_GB)"
[ "${FREE:-0}" -ge "$MIN_FREE_GB" ] || [ "$DRY_RUN" = 1 ] || die "too little disk space on the host to pull — free some first"
if [ "$DRY_RUN" = 1 ]; then
  say "deploy: --dry-run: would run: ssh $TARGET 'cd ~/$REMOTE_DIR && docker compose pull && docker compose up -d'"
else
  say "deploy: apply (docker compose pull && docker compose up -d)"
  ssh "$TARGET" "cd ~/$REMOTE_DIR && { (docker compose pull && docker compose up -d) || (sudo -n docker compose pull && sudo -n docker compose up -d); }" \
    || die "compose pull/up failed on the host"
  retention || say "deploy: retention failed — going on"
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
