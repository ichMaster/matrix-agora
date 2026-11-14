# One image for the Gemini agents (v3.2): the TOML picks the agent — `docker run <image> agents/ada.toml`.
# Nothing secret or lived is inside: env comes from the host's env files, state/ is a bind mount.
# Two targets (v4.4): `agent` (Ada, Bruno, Кіт) and `claude` (+ the Claude Agent SDK and its bundled CLI).
# v7.5: the heavy layers (the dependencies, the Claude SDK, the Codex CLI) come before the code, so a code change
# rebuilds and ships only the code's layer — a deploy of 2026-11-12 spent 40 minutes pulling them again.
FROM python:3.12-slim AS base

# v5.1 — ffmpeg encodes the voice messages (OGG/Opus); every speaker needs it from v5.3, so the shared layer has it
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.10 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH"

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-default-groups --no-install-project
RUN mkdir -p state reports && chown 1000:1000 state reports

# v7.4 — the Codex CLI for a companion's codex-gpt-6.1sol (the owner's ChatGPT plan): a pinned release, its checksum
# checked, one binary, nothing else kept; its login lives in state/<name>.codex/, never in the image
FROM python:3.12-slim AS codex
ARG CODEX_VERSION=0.167.1
ARG CODEX_SHA256=64bcc99c32e434b4bcb0508a97df9b7aeecdb97e956d976fb13661096ec4e3e2
RUN python -c "import hashlib, io, sys, tarfile, urllib.request; \
url = 'https://github.com/openai/codex/releases/download/rust-v${CODEX_VERSION}/codex-x86_64-unknown-linux-musl.tar.gz'; \
data = urllib.request.urlopen(url, timeout=300).read(); \
sys.exit('codex: checksum mismatch') if hashlib.sha256(data).hexdigest() != '${CODEX_SHA256}' else None; \
tarfile.open(fileobj=io.BytesIO(data)).extract('codex-x86_64-unknown-linux-musl', '/usr/local/bin')" \
    && mv /usr/local/bin/codex-x86_64-unknown-linux-musl /usr/local/bin/codex && chmod 755 /usr/local/bin/codex

FROM base AS agent
COPY agents/ agents/
COPY simulations.toml ./
USER 1000:1000
ENTRYPOINT ["python", "agents/agent.py"]
CMD ["agents/ada.toml"]

# v4.4 — Claude: the same image plus the `claude` dependency group (claude-agent-sdk bundles the Claude Code CLI).
# It runs on the owner's subscription only; its env file holds the OAuth token, never an API key.
FROM base AS claude
RUN uv sync --frozen --no-default-groups --group claude --no-install-project
COPY --from=codex /usr/local/bin/codex /usr/local/bin/codex
COPY agents/ agents/
COPY simulations.toml ./
USER 1000:1000
ENTRYPOINT ["python", "agents/agent.py"]
CMD ["agents/claude.toml"]
