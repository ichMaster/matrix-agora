"""The image holds no secrets and no lived state (v3.2): pinned through .dockerignore and the Dockerfile."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IGNORED = {line.strip() for line in (ROOT / ".dockerignore").read_text().splitlines()
           if line.strip() and not line.startswith("#")}


def test_secrets_and_state_never_enter_the_build_context():
    for path in (".env", "server/.env", "server_con.yaml", "state/", "reports/", ".git/", ".claude/"):
        assert path in IGNORED, path


def test_the_dockerfile_copies_only_code_and_never_secrets():
    copies = [line.split()[1:] for line in (ROOT / "agents" / "Dockerfile").read_text().splitlines()
              if line.startswith("COPY ") and "--from=" not in line]
    sources = {src for args in copies for src in args[:-1]}
    assert sources == {"pyproject.toml", "uv.lock", "agents/", "simulations.toml"}


def test_the_panel_image_copies_code_only():
    copies = [line.split()[1:] for line in (ROOT / "panel" / "Dockerfile").read_text().splitlines()
              if line.startswith("COPY ") and "--from=" not in line]
    assert {src for args in copies for src in args[:-1]} == {"pyproject.toml", "uv.lock", "agents/", "panel/", "simulations.toml"}
    assert "--only-group panel" in (ROOT / "panel" / "Dockerfile").read_text()  # not the agents' libraries


def test_the_panel_gets_docker_and_compose_from_official_images():
    text = (ROOT / "panel" / "Dockerfile").read_text()
    assert "COPY --from=docker:27-cli /usr/local/bin/docker " in text
    assert "COPY --from=docker/compose-bin:v2" in text and "cli-plugins/docker-compose" in text


def test_the_agent_image_has_ffmpeg_for_the_voice_messages():
    """v5.1: Hermes encodes his digests to OGG/Opus; both targets inherit the layer from the base (v7.5)."""
    text = (ROOT / "agents" / "Dockerfile").read_text()
    base = text.split("FROM python:3.12-slim AS codex")[0]
    assert "AS base" in base and "apt-get install -y --no-install-recommends ffmpeg" in base
    assert "rm -rf /var/lib/apt/lists/*" in base


def test_the_heavy_layers_come_before_the_code_so_a_deploy_ships_only_the_code():
    """v7.5: a deploy of 2026-11-12 spent 40 minutes pulling the Claude SDK's and Codex's layers again, rebuilt after
    every code change; now the code is the last layer of each target."""
    text = (ROOT / "agents" / "Dockerfile").read_text()
    claude = text.split("FROM base AS claude")[1]
    assert claude.index("--group claude") < claude.index("COPY --from=codex") < claude.index("COPY agents/")
    agent = text.split("FROM base AS agent")[1].split("FROM base AS claude")[0]
    assert agent.strip().startswith("COPY agents/")
