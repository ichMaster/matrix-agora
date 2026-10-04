"""The server stack contract (v3.2): the compose service set, the agent containers, the mounts, the env names."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = yaml.safe_load((ROOT / "server" / "docker-compose.yml").read_text())
SERVICES = COMPOSE["services"]
IMAGE = "ghcr.io/ichmaster/matrix-agora-agent:${AGENT_IMAGE_TAG:-latest}"


def env_keys(path: Path) -> set[str]:
    return {line.split("=", 1)[0] for line in path.read_text().splitlines() if "=" in line and not line.startswith("#")}


def test_the_service_set():
    assert set(SERVICES) == {"homeserver", "ada", "bruno", "usage-report"}


def test_the_homeserver_stays_closed():
    env = SERVICES["homeserver"]["environment"]
    assert env["CONTINUWUITY_SERVER_NAME"] == "agora.lan"
    assert (env["CONTINUWUITY_ALLOW_FEDERATION"], env["CONTINUWUITY_ALLOW_ENCRYPTION"],
            env["CONTINUWUITY_ALLOW_REGISTRATION"]) == ("false", "false", "false")
    assert "@sha256:" in SERVICES["homeserver"]["image"]  # pinned, never an implicit pull


def test_one_container_per_agent_from_one_image():
    for name in ("ada", "bruno"):
        svc = SERVICES[name]
        assert svc["image"] == IMAGE and svc["command"] == [f"agents/{name}.toml"]
        assert svc["environment"]["HOMESERVER"] == "http://homeserver:8008"  # the compose network
        assert svc["volumes"] == ["../state:/app/state"] and svc["user"] == "1000:1000"
        assert svc["stop_grace_period"] == "30s" and svc["restart"] == "unless-stopped"
        assert svc["env_file"] == [{"path": ".env", "required": False}]
        assert "ports" not in svc  # agents listen on nothing


def test_the_daily_report_reads_state_and_writes_reports():
    svc = SERVICES["usage-report"]
    assert svc["image"] == IMAGE and svc["entrypoint"] == ["python", "agents/usage_daily.py"]
    assert svc["volumes"] == ["../state:/app/state:ro", "../reports:/app/reports"]
    assert "ports" not in svc


def test_server_env_example_carries_every_agent_variable():
    agent_keys = env_keys(ROOT / ".env.example")
    server_keys = env_keys(ROOT / "server" / ".env.example")
    assert agent_keys <= server_keys
    assert server_keys - agent_keys == {"REGISTRATION_TOKEN", "AGENT_IMAGE_TAG"}


def test_deploy_pulls_before_up_and_prepares_the_mounts():
    deploy = (ROOT / "server" / "deploy.sh").read_text()
    assert "docker compose pull && docker compose up -d" in deploy
    assert "~/matrix-agora/state ~/matrix-agora/reports" in deploy


def test_python_is_never_pid_1():
    # PID 1 ignores SIGTERM without a handler: stops would wait the grace period and end in SIGKILL (code review #1)
    for name in ("ada", "bruno", "usage-report"):
        assert SERVICES[name]["init"] is True, name
