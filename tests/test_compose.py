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
    assert set(SERVICES) == {"homeserver", "ada", "bruno", "kit", "usage-report", "panel"}  # v4.2: the cat


def test_the_homeserver_stays_closed():
    env = SERVICES["homeserver"]["environment"]
    assert env["CONTINUWUITY_SERVER_NAME"] == "agora.lan"
    assert (env["CONTINUWUITY_ALLOW_FEDERATION"], env["CONTINUWUITY_ALLOW_ENCRYPTION"],
            env["CONTINUWUITY_ALLOW_REGISTRATION"]) == ("false", "false", "false")
    assert "@sha256:" in SERVICES["homeserver"]["image"]  # pinned, never an implicit pull


def test_one_container_per_agent_from_one_image():
    for name in ("ada", "bruno", "kit"):
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
    assert server_keys - agent_keys == {"REGISTRATION_TOKEN", "AGENT_IMAGE_TAG", "PANEL_TOKEN", "PANEL_IMAGE_TAG", "DOCKER_GID", "PANEL_BIND", "STACK_DIR"}


def test_deploy_pulls_before_up_and_prepares_the_mounts():
    deploy = (ROOT / "server" / "deploy.sh").read_text()
    assert "docker compose pull && docker compose up -d" in deploy
    assert "~/matrix-agora/state ~/matrix-agora/reports" in deploy


def test_python_is_never_pid_1():
    # PID 1 ignores SIGTERM without a handler: stops would wait the grace period and end in SIGKILL (code review #1).
    # Every agent the registry lists, not a hand-kept list — the cat's service was unpinned (v4.2 review #12).
    import tomllib
    agents = tomllib.loads((ROOT / "simulations.toml").read_text(encoding="utf-8"))["agora"]["agents"]
    assert "kit" in agents
    for name in (*agents, "usage-report"):
        assert SERVICES[name]["init"] is True, name


def test_the_panel_gets_only_its_own_settings_and_the_stack_at_its_host_path():
    svc = SERVICES["panel"]
    stack = "${STACK_DIR:-/home/ich/matrix-agora}/server"
    assert svc["image"] == "ghcr.io/ichmaster/matrix-agora-panel:${PANEL_IMAGE_TAG:-latest}"
    assert svc["ports"] == ["${PANEL_BIND:-127.0.0.1}:8090:8090"] and svc["init"] is True  # code review #1
    assert svc["user"] == "1000:1000" and svc["group_add"] == ["${DOCKER_GID:-999}"]
    assert svc["volumes"] == ["/var/run/docker.sock:/var/run/docker.sock",
                              "../state:/app/state",                       # v3.4: forget writes here
                              "/etc/os-release:/host/os-release:ro",
                              f"{stack}:{stack}:ro"]                       # same path inside: compose resolves host paths
    assert "env_file" not in svc  # never the agents' keys or passwords in its environment
    assert set(svc["environment"]) == {"PANEL_TOKEN", "PRICE_INPUT_PER_1M", "PRICE_OUTPUT_PER_1M", "TIMEZONE", "TZ",
                                       "STACK_DIR", "COMPOSE_PROJECT"}
    assert svc["environment"]["COMPOSE_PROJECT"] == "server"
    assert not svc.get("privileged") and "cap_add" not in svc and "network_mode" not in svc


def test_no_service_publishes_the_panel_on_every_interface():
    # docker-published ports bypass ufw: the panel binds one address, never 0.0.0.0 / [::] (code review #1)
    for port in SERVICES["panel"]["ports"]:
        assert port.count(":") >= 2 and not port.startswith(("0.0.0.0", "[::]", "8090:"))


def test_the_cats_settings_are_in_both_env_examples():
    """v4.2–v4.3: the cat's env names (ARCHITECTURE §Configuration)."""
    cat = {"CAT_REACT_P", "CAT_PURR_P", "CAT_MAX_WORDS", "CAT_MEMORY_P"}
    assert cat <= env_keys(ROOT / ".env.example") and cat <= env_keys(ROOT / "server" / ".env.example")
