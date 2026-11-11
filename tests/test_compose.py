"""The server stack contract (v3.2): the compose service set, the agent containers, the mounts, the env names."""

import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = yaml.safe_load((ROOT / "server" / "docker-compose.yml").read_text())
SERVICES = COMPOSE["services"]
IMAGE = "ghcr.io/ichmaster/matrix-agora-agent:${AGENT_IMAGE_TAG:-latest}"


def env_keys(path: Path) -> set[str]:
    return {line.split("=", 1)[0] for line in path.read_text().splitlines() if "=" in line and not line.startswith("#")}


def test_the_service_set():
    assert set(SERVICES) == {"homeserver", "ada", "bruno", "leon", "mia", "irma", "kira", "ustyna", "kit", "claude",
                             "hermes", "usage-report", "panel"}  # v5.1, v5.5, v6.3


def test_the_homeserver_stays_closed():
    env = SERVICES["homeserver"]["environment"]
    assert env["CONTINUWUITY_SERVER_NAME"] == "agora.lan"
    assert (env["CONTINUWUITY_ALLOW_FEDERATION"], env["CONTINUWUITY_ALLOW_ENCRYPTION"],
            env["CONTINUWUITY_ALLOW_REGISTRATION"]) == ("false", "false", "false")
    assert "@sha256:" in SERVICES["homeserver"]["image"]  # pinned, never an implicit pull


ROOM_ON_CLAUDE = ("ada", "bruno", "leon", "mia", "irma", "kit")  # v7.2: the room on Claude; Кіра back on Gemini (7.3.2)


def test_one_container_per_agent_from_one_image():
    for name in ("ada", "bruno", "leon", "mia", "irma", "kira", "ustyna", "kit"):  # v5.5: the newcomers, v6.3 Устина
        svc = SERVICES[name]
        on_claude = name in ROOM_ON_CLAUDE
        image = "ghcr.io/ichmaster/matrix-agora-agent-claude:${AGENT_IMAGE_TAG:-latest}" if on_claude else IMAGE
        assert svc["image"] == image and svc["command"] == [f"agents/{name}.toml"]
        assert svc["environment"]["HOMESERVER"] == "http://homeserver:8008"  # the compose network
        assert svc["volumes"] == ["../state:/app/state", CANON_MOUNT] and svc["user"] == "1000:1000"
        assert svc["stop_grace_period"] == "30s" and svc["restart"] == "unless-stopped"
        own = [{"path": f"{name}.env", "required": False}] if name in ("kira", "ustyna") else []  # v5.7, v6.3: her bot
        sub = [{"path": "subscription.env", "required": False}] if on_claude else []  # v7.2: the token, last
        assert svc["env_file"] == [{"path": ".env", "required": False}, {"path": "voice.env", "required": False},
                                   *own, *sub]  # v5.3: the voice key
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


CANON_MOUNT = "../canon:/app/agents/canon:ro"  # v5.9.1: the private canon, from the host, read-only


def test_the_private_canon_is_mounted_never_committed_never_baked():
    """The owner, 2026-10-26: agents/canon/ is private — gitignored, kept out of the public images, synced by
    deploy.sh to ~/matrix-agora/canon and mounted read-only where it is read; never into Claude's container."""
    assert "agents/canon/" in (ROOT / ".gitignore").read_text().splitlines()
    assert "agents/canon/" in (ROOT / ".dockerignore").read_text().splitlines()
    mounted = sorted(n for n, s in SERVICES.items() if CANON_MOUNT in s.get("volumes", []))
    assert mounted == sorted(["ada", "bruno", "leon", "mia", "irma", "kira", "ustyna", "kit", "hermes", "panel"])
    deploy = (ROOT / "server" / "deploy.sh").read_text()
    assert '"$CANON_DIR/" "$TARGET:matrix-agora/canon/"' in deploy and "--delete" not in deploy
    # v5.17 (the live test): folders 700, files 600 — `kira.face/` stays searchable to her container
    assert ("find ~/matrix-agora/canon -type d -exec chmod 700 {} + && "
            "find ~/matrix-agora/canon -type f -exec chmod 600 {} +") in deploy
    assert "chmod 600 ~/matrix-agora/canon/*" not in deploy


def test_deploy_pulls_before_up_and_prepares_the_mounts():
    deploy = (ROOT / "server" / "deploy.sh").read_text()
    assert "docker compose pull && docker compose up -d" in deploy
    assert "~/matrix-agora/state ~/matrix-agora/reports" in deploy


FAKE_DOCKER = """#!/usr/bin/env bash
case "$1 $2" in
  "ps -a") printf '%s\\n' ghcr.io/ichmaster/matrix-agora-agent:sha-old1 lumi:sha-1 ;;
  "images --filter") printf '%s\\n' ghcr.io/ichmaster/matrix-agora-agent ghcr.io/ichmaster/matrix-agora-panel ;;
  "images ghcr.io/ichmaster/matrix-agora-agent") printf '%s\\n' \\
      '2026-11-02 09:39:00 +0200 EET|ghcr.io/ichmaster/matrix-agora-agent:sha-new' \\
      '2026-11-01 09:00:00 +0200 EET|ghcr.io/ichmaster/matrix-agora-agent:sha-mid' \\
      '2026-10-31 09:00:00 +0200 EET|ghcr.io/ichmaster/matrix-agora-agent:sha-old2' \\
      '2026-10-30 09:00:00 +0200 EET|ghcr.io/ichmaster/matrix-agora-agent:sha-old1' \\
      '2026-10-29 09:00:00 +0200 EET|ghcr.io/ichmaster/matrix-agora-agent:<none>' ;;
  "images ghcr.io/ichmaster/matrix-agora-panel") printf '%s\\n' \\
      '2026-11-02 09:39:00 +0200 EET|ghcr.io/ichmaster/matrix-agora-panel:sha-new' ;;
  "rmi "*|"image prune") echo "$*" >> "$LOG" ;;
esac
"""


def retention_script() -> str:
    deploy = (ROOT / "server" / "deploy.sh").read_text()
    return deploy.split("<<'EOF'\n", 1)[1].split("\nEOF\n", 1)[0]


def run_retention(tmp_path, dry: str) -> tuple[str, list[str]]:
    (tmp_path / "docker").write_text(FAKE_DOCKER)
    (tmp_path / "docker").chmod(0o755)
    log = tmp_path / "docker.log"
    out = subprocess.run(["bash", "-s", "--", "2", dry], input=retention_script(), capture_output=True, text=True,
                         env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "LOG": str(log)}, check=True)
    return out.stdout, log.read_text().splitlines() if log.exists() else []


def test_deploy_keeps_the_images_in_use_and_the_two_newest_and_removes_the_rest(tmp_path):
    """2026-11-02: 37 builds' images, never removed, filled the host's disk and every agent stopped. Retention runs
    before the pull and after the new containers are up; only this project's tags, never one a container uses."""
    out, calls = run_retention(tmp_path, "0")
    assert out.strip() == "deploy: retention: removing 1 old image tag(s)"
    assert calls == ["rmi ghcr.io/ichmaster/matrix-agora-agent:sha-old2", "image prune -f"]  # sha-old1 is in use
    (tmp_path / "dry").mkdir()
    out, calls = run_retention(tmp_path / "dry", "1")
    assert out.strip() == "deploy: retention: would remove 1 old image tag(s)" and calls == []  # --dry-run
    deploy = (ROOT / "server" / "deploy.sh").read_text()
    assert 'KEEP_IMAGES="${KEEP_IMAGES:-2}"' in deploy and 'MIN_FREE_GB="${MIN_FREE_GB:-10}"' in deploy
    apply = deploy.split("# --- apply ---", 1)[1]
    assert apply.index("retention ||") < apply.index("free_gb") < apply.index("docker compose pull")
    assert apply.rindex("retention ||") > apply.index("docker compose pull && docker compose up -d")
    assert "too little disk space" in apply
    for never in ("system prune", "prune -a", "rmi -f", "--force"):
        assert never not in deploy


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
                              CANON_MOUNT,                                 # v5.9.1: Кіра's palette
                              "../claude-workspace:/claude-workspace",     # v4.7: Claude's files
                              "/etc/os-release:/host/os-release:ro",
                              f"{stack}:{stack}:ro"]                       # same path inside: compose resolves host paths
    assert "env_file" not in svc  # never the agents' keys or passwords in its environment
    assert set(svc["environment"]) == {"PANEL_TOKEN", "PRICE_INPUT_PER_1M", "PRICE_OUTPUT_PER_1M", "PRICE_MODELS",
                                       "PRICE_SECONDS",  # v5.18: her кружечки, per second
                                       "PRICE_SUBSCRIPTIONS",  # v5.19: the monthly fees, for the Analytics view
                                       "PRICE_IMAGES",  # v6.5: her fal photos, per image
                                       "TIMEZONE", "TZ", "STACK_DIR", "COMPOSE_PROJECT"}  # v5.1: PRICE_MODELS
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


def test_the_persona_move_weights_are_in_both_env_examples_with_the_code_defaults():
    """v4.6: the persona's move weights (ARCHITECTURE §Configuration)."""
    from agents.moves import DEFAULT_WEIGHTS, WEIGHT_VARS
    for path in (ROOT / ".env.example", ROOT / "server" / ".env.example"):
        assert set(WEIGHT_VARS.values()) <= env_keys(path)
        values = dict(line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines()
                      if line.startswith("PERSONA_"))
        assert {k: float(values[v]) for k, v in WEIGHT_VARS.items()} == DEFAULT_WEIGHTS


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
    assert svc["env_file"] == [{"path": "claude.env", "required": False}, {"path": "voice.env", "required": False}]  # never the shared .env
    assert svc["environment"]["CLAUDE_CONFIG_DIR"] == svc["environment"]["HOME"] == "/tmp/claude"
    assert svc["tmpfs"] == ["/tmp/claude:uid=1000,gid=1000,mode=0700,size=64m"]     # bounded; nothing survives
    assert svc["volumes"] == ["../state:/app/state", "../claude-workspace:/workspace"]  # v4.5: his own folder
    assert svc["environment"]["CLAUDE_WORKSPACE"] == "/workspace"
    assert "~/matrix-agora/claude-workspace" in (ROOT / "server" / "deploy.sh").read_text()


def test_no_service_and_no_env_example_names_a_forbidden_variable():
    for name, svc in SERVICES.items():
        env = svc.get("environment") or {}
        keys = env if isinstance(env, dict) else [e.split("=", 1)[0] for e in env]
        assert not [k for k in keys if _forbidden(k)], name
    for example in (".env.example", "server/.env.example", "server/claude.env.example",
                    "server/subscription.env.example"):  # v7.1: the subscription's file too
        assert not [k for k in env_keys(ROOT / example) if _forbidden(k)], example


def test_claudes_env_example_holds_his_settings_and_nothing_of_the_others():
    keys = env_keys(ROOT / "server" / "claude.env.example")
    assert {"CLAUDE_PASSWORD", "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_MODEL", "CLAUDE_CODE_MAX_OUTPUT_TOKENS"} <= keys
    assert not keys & {"GEMINI_API_KEY", "ADA_PASSWORD", "BRUNO_PASSWORD", "KIT_PASSWORD", "PANEL_TOKEN",
                       "REGISTRATION_TOKEN"}


def test_deploy_syncs_claudes_env_file_privately_and_it_never_enters_an_image():
    deploy = (ROOT / "server" / "deploy.sh").read_text()
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
                "CLAUDE_HISTORY_N", "CLAUDE_NEWS_EVERY_S", "CLAUDE_NEWS_IDLE_S", "CLAUDE_NEWS_PER_DAY",
                "CLAUDE_NEWS_HOURS"):
        assert str(env[key]).startswith("${" + key + ":-"), key
    assert env_keys(ROOT / "server" / "claude.env.example") == {"CLAUDE_PASSWORD", "CLAUDE_CODE_OAUTH_TOKEN",
                                                                  "CLAUDE_MODEL", "CLAUDE_CODE_MAX_OUTPUT_TOKENS",
                                                                  "CLAUDE_TIMEOUT_S", "GUARDIAN_API_KEY"}


def test_both_env_examples_price_the_pro_model_by_its_own_pair():
    """v5.1: Hermes's digests run on gemini-3.1-pro-preview — priced as Pro, not as Flash; v5.24: the scan's Opus 5.5
    by its own pair too."""
    from agents.usage import parse_model_prices
    for path in (ROOT / ".env.example", ROOT / "server" / ".env.example"):
        values = dict(line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines()
                      if line and not line.startswith("#") and "=" in line)
        assert parse_model_prices(values["PRICE_MODELS"]) == (
            {"gemini-3.1-pro-preview": (2.0, 12.0), "claude-opus-5-5": (4.0, 20.0)}, []), path



# --- v5.1: Hermes's own service and env file ---------------------------------------------------------------------------
def test_hermes_runs_the_shared_image_with_the_shared_file_and_his_own():
    svc = SERVICES["hermes"]
    assert svc["image"] == CLAUDE_IMAGE and svc["command"] == ["agents/hermes.toml"] and svc["init"] is True  # v7.2
    assert svc["env_file"] == [{"path": ".env", "required": False}, {"path": "hermes.env", "required": False},
                               {"path": "voice.env", "required": False},
                               {"path": "subscription.env", "required": False}]
    assert svc["environment"]["HOMESERVER"] == "http://homeserver:8008" and svc["user"] == "1000:1000"
    assert svc["volumes"] == ["../state:/app/state", CANON_MOUNT] and "ports" not in svc and svc["stop_grace_period"] == "30s"
    others = [n for n, s in SERVICES.items() if n != "hermes"
              and any((e.get("path") if isinstance(e, dict) else e) == "hermes.env" for e in s.get("env_file", []))]
    assert others == []                                             # his key reaches no other container


def test_hermes_env_example_holds_his_password_and_key_only():
    assert env_keys(ROOT / "server" / "hermes.env.example") == {"HERMES_PASSWORD", "DEEPGRAM_API_KEY"}  # v5.3: the
    # ElevenLabs key moved to voice.env
    assert not [k for k in env_keys(ROOT / "server" / "hermes.env.example") if _forbidden(k)]
    for example in (".env.example", "server/.env.example"):
        assert not env_keys(ROOT / example) & {"ELEVENLABS_API_KEY", "DEEPGRAM_API_KEY", "HERMES_PASSWORD"}, example


def test_deploy_syncs_every_members_env_file_privately_and_names_none():
    """v6.2: one loop over the members' TOMLs — Claude's, Hermes's, Кіра's and, from v6.3, Устина's own env file each
    reaches the host as `server/<name>.env` 0600; no line of the deploy names a member's file."""
    deploy = (ROOT / "server" / "deploy.sh").read_text()
    assert 'for TOML in "$REPO_DIR"/agents/*.toml; do' in deploy and 'MEMBER_ENV="$REPO_DIR/server/$NAME.env"' in deploy
    assert '"$MEMBER_ENV" "$TARGET:$REMOTE_DIR/$NAME.env"' in deploy and 'chmod 600 ~/$REMOTE_DIR/$NAME.env' in deploy
    for toml in (ROOT / "agents").glob("*.toml"):
        assert f"{toml.stem}.env" not in deploy, toml.stem
    assert 'chmod 600 ~/$REMOTE_DIR/voice.env' in deploy                       # not a member's: by name, as before


def test_ustynas_env_example_has_kiras_keys_and_no_example_holds_a_value():
    # v6.2: a second companion's own file, the same shape as Кіра's
    assert env_keys(ROOT / "server" / "ustyna.env.example") == env_keys(ROOT / "server" / "kira.env.example")
    for example in sorted((ROOT / "server").glob("*.env.example")):
        lines = [x for x in example.read_text().splitlines() if x and not x.startswith("#")]
        assert all(x.endswith("=") for x in lines if x.split("=")[0] in {"TELEGRAM_BOT_TOKEN", "TELEGRAM_OWNER_ID",
                   "DEEPGRAM_API_KEY", "NOVELAI_API_TOKEN", "FAL_KEY", "GUARDIAN_API_KEY"}), example.name


def test_hermes_settings_are_in_both_env_examples_with_the_schema_defaults():
    from agents.settings import SCHEMA
    hermes = {s.name: s.default for s in SCHEMA if s.name.startswith("HERMES_")}
    for path in (ROOT / ".env.example", ROOT / "server" / ".env.example"):
        values = dict(line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines()
                      if line.startswith("HERMES_"))
        assert values == hermes, path


def test_the_panel_gets_the_model_prices():
    assert SERVICES["panel"]["environment"]["PRICE_MODELS"] == "${PRICE_MODELS:-}"
    assert SERVICES["panel"]["environment"]["PRICE_SECONDS"] == "${PRICE_SECONDS:-}"  # v5.18
    assert SERVICES["panel"]["environment"]["PRICE_SUBSCRIPTIONS"] == "${PRICE_SUBSCRIPTIONS:-}"  # v5.19
    assert SERVICES["panel"]["environment"]["PRICE_IMAGES"] == "${PRICE_IMAGES:-}"  # v6.5


def test_both_env_examples_price_her_kruzhechky_per_second():
    """v5.18: her кружечок's model on fal bills per second of video — priced by PRICE_SECONDS, never by tokens."""
    from agents.usage import parse_second_prices
    for path in (ROOT / ".env.example", ROOT / "server" / ".env.example"):
        values = dict(line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines()
                      if line and not line.startswith("#") and "=" in line)
        assert parse_second_prices(values["PRICE_SECONDS"]) == ({"veed/fabric-1.0": 0.08,
                                                                 "fal-ai/kling-video/ai-avatar/v2/standard": 0.0562,
                                                                 "fal-ai/kling-video/ai-avatar/v2/pro": 0.115}, []), path


def test_both_env_examples_price_her_fal_photos_per_image():
    """v6.5: her photos on fal (Seedream 4) bill per image — priced by PRICE_IMAGES, never by tokens."""
    from agents.usage import parse_image_prices
    for path in (ROOT / ".env.example", ROOT / "server" / ".env.example"):
        values = dict(line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines()
                      if line and not line.startswith("#") and "=" in line)
        assert parse_image_prices(values["PRICE_IMAGES"]) == ({"fal-ai/bytedance/seedream/v4/edit": 0.03,
                                                               "fal-ai/bytedance/seedream/v4/text-to-image": 0.03},
                                                              []), path



def test_the_shared_server_example_never_invites_hermes_secrets():
    """Review #10: the server's .env is read by every Gemini container — the ElevenLabs key never goes there."""
    lines = [line for line in (ROOT / "server" / ".env.example").read_text(encoding="utf-8").splitlines()
             if "ELEVENLABS_API_KEY" in line or "hermes.env" in line]
    assert lines and all("never" in line or "only in" in line for line in lines), lines
    assert "dev mode" not in "\n".join(lines)



def test_the_voice_settings_are_in_both_env_examples_with_the_schema_defaults():
    """v5.3: each agent's voice id name, the share and the speakers' budget; v5.4: the owner's cloned voice; v5.5:
    the four newcomers' voices and passwords."""
    from agents.settings import BY_NAME
    ids = ("ADA_VOICE_ID", "BRUNO_VOICE_ID", "KIT_VOICE_ID", "CLAUDE_VOICE_ID", "OWNER_VOICE_ID", "LEON_VOICE_ID",
           "MIA_VOICE_ID", "IRMA_VOICE_ID", "KIRA_VOICE_ID", "LEON_PASSWORD", "MIA_PASSWORD", "IRMA_PASSWORD",
           "KIRA_PASSWORD")
    for path in (ROOT / ".env.example", ROOT / "server" / ".env.example"):
        values = dict(line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines()
                      if line and not line.startswith("#") and "=" in line)
        assert {k: values[k] for k in ids} == dict.fromkeys(ids, "")
        assert values["VOICE_REPLY_P"] == BY_NAME["VOICE_REPLY_P"].default
        assert values["VOICE_MONTHLY_CHARS"] == BY_NAME["VOICE_MONTHLY_CHARS"].default



def test_the_voice_key_reaches_exactly_the_members_who_speak():
    """v5.3: server/voice.env — the ElevenLabs key alone, for every speaker (v5.5: the four newcomers too) and hermes;
    never the panel or the report; synced privately."""
    readers = {n for n, svc in SERVICES.items()
               if any((e.get("path") if isinstance(e, dict) else e) == "voice.env" for e in svc.get("env_file", []))}
    assert readers == {"ada", "bruno", "leon", "mia", "irma", "kira", "ustyna", "kit", "claude", "hermes"}  # v5.5, v6.3
    assert env_keys(ROOT / "server" / "voice.env.example") == {"ELEVENLABS_API_KEY"}
    deploy = (ROOT / "server" / "deploy.sh").read_text()
    assert 'VOICE_ENV="$REPO_DIR/server/voice.env"' in deploy and "chmod 600 ~/$REMOTE_DIR/voice.env" in deploy
    env = SERVICES["claude"]["environment"]
    assert env["CLAUDE_VOICE_ID"] == "${CLAUDE_VOICE_ID:-}" and env["VOICE_REPLY_P"] == "${VOICE_REPLY_P:-1.0}"
    assert env["VOICE_MONTHLY_CHARS"] == "${VOICE_MONTHLY_CHARS:-200000}"  # v5.5: the owner


# --- v5.7: Кіра's own env file -----------------------------------------------------------------------------------------
def test_kiras_env_file_reaches_her_container_only():
    readers = {n for n, svc in SERVICES.items()
               if any((e.get("path") if isinstance(e, dict) else e) == "kira.env" for e in svc.get("env_file", []))}
    assert readers == {"kira"}  # her bot's token and the owner's id reach no other container


def test_each_companion_reads_her_own_env_file_and_never_the_others():
    """v6.2 review #4 / v6.3: Устина's service reads `ustyna.env` and never `kira.env`; Кіра's never `ustyna.env`."""
    def files(name):
        return [(e.get("path") if isinstance(e, dict) else e) for e in SERVICES[name].get("env_file", [])]
    assert "ustyna.env" in files("ustyna") and "kira.env" not in files("ustyna")
    assert "kira.env" in files("kira") and "ustyna.env" not in files("kira")
    readers = {n for n in SERVICES if "ustyna.env" in files(n)}
    assert readers == {"ustyna"} and SERVICES["ustyna"]["command"] == ["agents/ustyna.toml"]


def test_kiras_env_example_holds_the_bot_the_owner_and_her_hearing_only():
    assert env_keys(ROOT / "server" / "kira.env.example") == {"TELEGRAM_BOT_TOKEN", "TELEGRAM_OWNER_ID",
                                                               "DEEPGRAM_API_KEY", "GEMINI_REPLY_MODEL",
                                                               "PRIVATE_FIRST_DOOR", "ELEVENLABS_MODEL",
                                                               "VOICE_STABILITY",  # v5.8, v5.8.2, v5.9
                                                               "GUARDIAN_API_KEY",  # v5.12: her reading
                                                               "NOVELAI_API_TOKEN", "FALLBACK_MODEL",  # v5.14
                                                                # v5.15: the judge
                                                               "FAL_KEY",  # v5.18: her кружечок
                                                               "OPENAI_API_KEY", "SONNET_API_KEY"}  # v7.4: her answers
    for example in (".env.example", "server/.env.example"):
        assert not env_keys(ROOT / example) & {"TELEGRAM_BOT_TOKEN", "TELEGRAM_OWNER_ID"}, example


def test_deploy_syncs_kiras_env_file_privately_and_it_is_never_committed_or_baked():
    from fnmatch import fnmatch
    deploy = (ROOT / "server" / "deploy.sh").read_text()
    assert 'chmod 600 ~/$REMOTE_DIR/$NAME.env' in deploy and (ROOT / "agents" / "kira.toml").exists()  # v6.2: the loop
    for ignore in (".gitignore", ".dockerignore"):
        lines = (ROOT / ignore).read_text().splitlines()
        assert any(fnmatch("server/kira.env", p) for p in lines if p and not p.startswith(("#", "!"))), ignore
        assert not any(fnmatch("server/kira.env", p[1:]) for p in lines if p.startswith("!")), ignore


def test_both_env_examples_name_the_subscriptions_fees_empty():
    """v5.19: the monthly fees are the owner's to set; the examples carry the name, empty."""
    for path in (ROOT / ".env.example", ROOT / "server" / ".env.example"):
        assert "\nPRICE_SUBSCRIPTIONS=\n" in path.read_text(encoding="utf-8"), path


# --- v7.1: every agent on Claude, by its TOML's engine ---------------------------------------------------------------
CLAUDE_IMAGE = "ghcr.io/ichmaster/matrix-agora-agent-claude:${AGENT_IMAGE_TAG:-latest}"


def env_files(svc: dict) -> list[str]:
    return [f["path"] if isinstance(f, dict) else f for f in svc.get("env_file") or []]


def claude_service_problems(svc: dict) -> list[str]:
    """What a service of an agent on Claude (not Claude himself) lacks: the Claude image (the SDK's bundled CLI), the
    subscription's file last of its env files, and the CLI's home and config on a bounded tmpfs."""
    problems = []
    if svc.get("image") != CLAUDE_IMAGE:
        problems.append("image")
    files = env_files(svc)
    if not files or files[-1] != "subscription.env" or ".env" not in files:
        problems.append("subscription.env")
    env = svc.get("environment") or {}
    if not (env.get("HOME") == env.get("CLAUDE_CONFIG_DIR") == "/tmp/claude"):
        problems.append("config dir")
    if not any(t.startswith("/tmp/claude:") and "size=" in t for t in svc.get("tmpfs") or []):
        problems.append("tmpfs")
    return problems


def agent_services():
    from agents.roster import load_member
    for name, svc in SERVICES.items():
        command = svc.get("command") or []
        if command and str(command[0]).startswith("agents/") and str(command[0]).endswith(".toml"):
            yield name, svc, load_member(ROOT / command[0])


def test_every_agent_on_claude_runs_the_claude_image_with_the_subscription_and_none_on_gemini_sees_it():
    seen = 0
    for name, svc, member in agent_services():
        seen += 1
        if member.engine == "claude-sdk" and member.type != "assistant":
            assert claude_service_problems(svc) == [], name
        else:
            assert "subscription.env" not in env_files(svc), name  # the token never reaches a Gemini agent
    assert seen >= 10


def test_the_rule_holds_on_a_made_up_service_on_claude():
    ada = SERVICES["ustyna"]  # a service still on Gemini (Устина until v7.4)
    assert claude_service_problems(ada) == ["image", "subscription.env", "config dir", "tmpfs"]
    moved = {**ada, "image": CLAUDE_IMAGE,
             "env_file": [*ada["env_file"], {"path": "subscription.env", "required": False}],
             "environment": {**ada["environment"], "HOME": "/tmp/claude", "CLAUDE_CONFIG_DIR": "/tmp/claude"},
             "tmpfs": ["/tmp/claude:uid=1000,gid=1000,mode=0700,size=64m"]}
    assert claude_service_problems(moved) == []
    early = {**moved, "env_file": [{"path": "subscription.env", "required": False}, *ada["env_file"]]}
    assert claude_service_problems(early) == ["subscription.env"]  # last: no other file may override the token


def test_the_subscription_file_holds_the_token_alone_and_is_synced_privately_never_committed():
    import fnmatch
    example = ROOT / "server" / "subscription.env.example"
    lines = [x for x in example.read_text().splitlines() if x and not x.startswith("#")]
    assert lines == ["CLAUDE_CODE_OAUTH_TOKEN="]
    deploy = (ROOT / "server" / "deploy.sh").read_text()
    assert '"$SUBSCRIPTION_ENV" "$TARGET:$REMOTE_DIR/subscription.env"' in deploy
    assert "chmod 600 ~/$REMOTE_DIR/subscription.env" in deploy
    for ignore in (".gitignore", ".dockerignore"):
        patterns = [x for x in (ROOT / ignore).read_text().splitlines() if x and not x.startswith(("#", "!"))]
        assert any(fnmatch.fnmatch("server/subscription.env", p) for p in patterns), ignore
