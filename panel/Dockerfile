# The panel (v3.3): FastAPI + the static page. Read-only views of docker, state/ and the host.
# Nothing secret or lived is inside: PANEL_TOKEN comes from the host's server/.env, state/ is a mount.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.10 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH"

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --only-group panel --no-install-project
COPY agents/ agents/
COPY panel/ panel/
COPY simulations.toml ./

USER 1000:1000
EXPOSE 8090
ENTRYPOINT ["uvicorn", "--factory", "panel.app:create_app", "--host", "0.0.0.0", "--port", "8090"]
