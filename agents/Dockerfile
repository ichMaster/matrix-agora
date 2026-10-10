# One image for the Gemini agents (v3.2): the TOML picks the agent — `docker run <image> agents/ada.toml`.
# Nothing secret or lived is inside: env comes from the host's env files, state/ is a bind mount.
# Two targets (v4.4): `agent` (Ada, Bruno, Кіт) and `claude` (+ the Claude Agent SDK and its bundled CLI).
FROM python:3.12-slim AS agent

COPY --from=ghcr.io/astral-sh/uv:0.10 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH"

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-default-groups --no-install-project
COPY agents/ agents/
COPY simulations.toml ./
RUN mkdir -p state reports && chown 1000:1000 state reports

USER 1000:1000
ENTRYPOINT ["python", "agents/agent.py"]
CMD ["agents/ada.toml"]

# v4.4 — Claude: the same image plus the `claude` dependency group (claude-agent-sdk bundles the Claude Code CLI).
# It runs on the owner's subscription only; its env file holds the OAuth token, never an API key.
FROM agent AS claude
USER root
RUN uv sync --frozen --no-default-groups --group claude --no-install-project
USER 1000:1000
CMD ["agents/claude.toml"]
