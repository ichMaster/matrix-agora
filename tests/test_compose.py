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
    assert set(SERVICES) == {"homeserver", "ada", "bruno", "kit", "claude", "usage-report", "panel"}  # v4.4


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
    cat = {"CAT_REACT_P", "CAT_PURR_P", "CAT_MAX_WORDS", "CAT_MEMORY_P", "CAT_NUDGE_IDLE_S", "CAT_NUDGES_PER_DAY",
           "CAT_NUDGE_HOURS"}
    assert cat <= env_keys(ROOT / ".env.example") and cat <= env_keys(ROOT / "server" / ".env.example")


def test_the_cats_example_values_are_the_agents_defaults(monkeypatch):
    """v4.3 review #11: an example value that drifts from the code default (2700 vs 1200) would silently override
    it once copied into an .env."""
    from agents.agent import Agent
    from agents.config import AgentConfig
    from agents.nudge import parse_hours
    from agents.roster import TYPES
    from tests.test_first_sync import CFG, FakeLLM
    example = dict(line.split("=", 1) for line in (ROOT / ".env.example").read_text().splitlines()
                   if line.startswith("CAT_"))
    for key in example:
        monkeypatch.delenv(key, raising=False)
    cat = Agent(AgentConfig(**{**CFG.__dict__, "name": "Кіт", "user_id": "@kit:agora.lan", "type": "creature",
                               "capabilities": TYPES["creature"]}), llm=FakeLLM())
    assert float(example["CAT_REACT_P"]) == cat.cat_react_p and float(example["CAT_PURR_P"]) == cat.cat_purr_p
    assert int(example["CAT_MAX_WORDS"]) == cat.cat_max_words and float(example["CAT_MEMORY_P"]) == cat.cat_memory_p
    assert int(example["CAT_NUDGE_IDLE_S"]) * 1000 == cat.nudge_idle_ms
    assert int(example["CAT_NUDGES_PER_DAY"]) == cat.nudges_per_day
    assert parse_hours(example["CAT_NUDGE_HOURS"]) == cat.nudge_hours


# --- v4.4: Claude's own service and env file; no API credential anywhere in the stack -------------------------------
def _forbidden(name: str) -> bool:
    from agents.claude_sdk import forbidden_vars  # the one list (v4.4 review #10)
    return bool(forbidden_vars({name: ""}))


def test_claude_runs_his_own_image_with_his_own_env_file_only():
    svc = SERVICES["claude"]
    assert svc["image"] == "ghcr.io/ichmaster/matrix-agora-agent-claude:${AGENT_IMAGE_TAG:-latest}"
    assert svc["command"] == ["agents/claude.toml"] and svc["init"] is True and svc["user"] == "1000:1000"
    assert svc["env_file"] == [{"path": "claude.env", "required": False}]           # never the shared .env
    assert svc["environment"]["CLAUDE_CONFIG_DIR"] == svc["environment"]["HOME"] == "/tmp/claude"
    assert svc["tmpfs"] == ["/tmp/claude:uid=1000,gid=1000,mode=0700,size=64m"]     # bounded; nothing survives
    assert svc["volumes"] == ["../state:/app/state"]


def test_no_service_and_no_env_example_names_a_forbidden_variable():
    for name, svc in SERVICES.items():
        env = svc.get("environment") or {}
        keys = env if isinstance(env, dict) else [e.split("=", 1)[0] for e in env]
        assert not [k for k in keys if _forbidden(k)], name
    for example in (".env.example", "server/.env.example", "server/claude.env.example"):
        assert not [k for k in env_keys(ROOT / example) if _forbidden(k)], example


def test_claudes_env_example_holds_his_settings_and_nothing_of_the_others():
    keys = env_keys(ROOT / "server" / "claude.env.example")
    assert {"CLAUDE_PASSWORD", "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_MODEL", "CLAUDE_CODE_MAX_OUTPUT_TOKENS"} <= keys
    assert not keys & {"GEMINI_API_KEY", "ADA_PASSWORD", "BRUNO_PASSWORD", "KIT_PASSWORD", "PANEL_TOKEN",
                       "REGISTRATION_TOKEN"}


def test_deploy_syncs_claudes_env_file_privately_and_it_never_enters_an_image():
    deploy = (ROOT / "server" / "deploy.sh").read_text()
    assert 'CLAUDE_ENV="$REPO_DIR/server/claude.env"' in deploy and 'chmod 600 ~/$REMOTE_DIR/claude.env' in deploy
    assert "--chmod" not in deploy                                  # the Mac's rsync has no --chmod
    assert "server/claude.env" in (ROOT / ".dockerignore").read_text().splitlines()
    assert "server/claude.env" in (ROOT / ".gitignore").read_text().splitlines()
    for ignore in (".gitignore", ".dockerignore"):  # review #15: any copy of a server env file, never the examples
        lines = (ROOT / ignore).read_text().splitlines()
        assert "server/*.env*" in lines and "!server/*.env.example" in lines, ignore
    dockerfile = (ROOT / "agents" / "Dockerfile").read_text()
    assert "FROM python:3.12-slim AS agent" in dockerfile and "FROM agent AS claude" in dockerfile
    assert "--group claude" in dockerfile



def test_claude_takes_the_room_and_the_turn_settings_from_the_shared_file():
    """Review #5: every agent computes waves and reservations from the same settings (no coordination), so Claude's
    service interpolates them from the shared .env — a single source; his own file holds only his own."""
    env = SERVICES["claude"]["environment"]
    for key in ("ROOM_ID", "OWNER", "TIMEZONE", "HISTORY_N", "REPLY_MAX_TOKENS", "MAX_BOT_TURNS", "OWNER_REPLIERS",
                "FALLBACK_S", "BOT_REPLY_P", "REPLY_DELAY_S", "BOT_WINDOW_S", "CAT_REACT_P", "CAT_PURR_P",
                "CLAUDE_HISTORY_N"):
        assert str(env[key]).startswith("${" + key + ":-"), key
    assert env_keys(ROOT / "server" / "claude.env.example") == {"CLAUDE_PASSWORD", "CLAUDE_CODE_OAUTH_TOKEN",
                                                                  "CLAUDE_MODEL", "CLAUDE_CODE_MAX_OUTPUT_TOKENS",
                                                                  "CLAUDE_TIMEOUT_S"}
