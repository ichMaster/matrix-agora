"""Agent configuration: the per-agent TOML plus the shared .env.

Pure loading only — no network. The password comes from <NAME>_PASSWORD in the
environment, where <NAME> is the user_id localpart upper-cased (ada -> ADA_PASSWORD).
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


class ConfigError(RuntimeError):
    """A missing or malformed configuration value."""


@dataclass(frozen=True)
class AgentConfig:
    name: str
    user_id: str
    persona: str
    homeserver: str
    room_id: str
    owner: str
    password: str

    @property
    def localpart(self) -> str:
        return self.user_id.split(":", 1)[0].lstrip("@")

    @property
    def state_file(self) -> Path:
        return Path("state") / f"{self.localpart}.json"


def _require(env: dict[str, str], key: str) -> str:
    value = env.get(key, "").strip()
    if not value:
        raise ConfigError(f"missing {key} (set it in .env)")
    return value


def load_config(toml_path: str | Path, env: dict[str, str] | None = None) -> AgentConfig:
    """Load the agent TOML and the shared env. `env` is injectable for tests."""
    toml_path = Path(toml_path)
    try:
        data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"agent config not found: {toml_path}") from exc
    for key in ("name", "user_id", "persona"):
        if not str(data.get(key, "")).strip():
            raise ConfigError(f"{toml_path}: missing '{key}'")

    if env is None:
        load_dotenv()
        env = dict(os.environ)

    user_id = str(data["user_id"]).strip()
    localpart = user_id.split(":", 1)[0].lstrip("@")
    return AgentConfig(
        name=str(data["name"]).strip(),
        user_id=user_id,
        persona=str(data["persona"]).strip(),
        homeserver=_require(env, "HOMESERVER"),
        room_id=_require(env, "ROOM_ID"),
        owner=_require(env, "OWNER"),
        password=_require(env, f"{localpart.upper()}_PASSWORD"),
    )
