# The panel (v3.3 views, v3.4 actions): FastAPI + the static page, plus the docker CLI and compose plugin so
# a start can create a missing container with the real stack's compose file.
# Nothing secret or lived is inside: PANEL_TOKEN comes from the host's server/.env, state/ is a mount.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.10 /uv /usr/local/bin/uv
COPY --from=docker:27-cli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=docker/compose-bin:v2.39.4 /docker-compose /usr/local/lib/docker/cli-plugins/docker-compose
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH" DOCKER_CONFIG=/tmp/.docker

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --only-group panel --no-install-project
COPY agents/ agents/
COPY panel/ panel/
COPY simulations.toml ./

USER 1000:1000
EXPOSE 8090
ENTRYPOINT ["uvicorn", "--factory", "panel.app:create_app", "--host", "0.0.0.0", "--port", "8090"]
