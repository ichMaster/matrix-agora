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

from agents.life import LifeError, LifeStory, parse_life
from agents.pastlife import ThesesError, parse_theses
from agents.registry import REGISTRY_PATH, RegistryError, load_registry
from agents.roster import TYPES, RosterError, parse_member


class ConfigError(RuntimeError):
    """A missing or malformed configuration value."""


COMMON_CANON = Path("agents/canon/common.md")


@dataclass(frozen=True)
class AgentConfig:
    name: str
    user_id: str
    canon: str  # common + personal canon text, loaded once at startup
    homeserver: str
    room_id: str
    owner: str
    password: str
    life: LifeStory | None = None  # the life story (v2.2); optional only for tests
    simulation: str = "agora"  # the registry entry it joins (v3.3)
    type: str = "persona"  # the agent type (v4.1); it sets the capabilities
    engine: str = "gemini"
    capabilities: frozenset[str] = TYPES["persona"]
    natal: str = ""  # v4.2: the natal text (Lumi's natal.md format) for an agent with the `mood` capability
    theses: tuple = ()  # v4.3: the past-life theses (agents.pastlife.Thesis) for an agent with `pastlife`
    voice_spec: str = ""  # v5.9: the palette of tags verified on her voice, for an agent with `emotion`
    reading: str = ""  # v5.12: what she reads and how she sees the news, for an agent with `thoughts` (private canon)

    def can(self, capability: str) -> bool:
        return capability in self.capabilities

    @property
    def localpart(self) -> str:
        return self.user_id.split(":", 1)[0].lstrip("@")

    @property
    def state_file(self) -> Path:
        return Path("state") / f"{self.localpart}.json"

    @property
    def memory_file(self) -> Path:
        return Path("state") / f"{self.localpart}.memory.md"

    @property
    def lock_file(self) -> Path:
        return Path("state") / f"{self.localpart}.lock"


def _require(env: dict[str, str], key: str) -> str:
    value = env.get(key, "").strip()
    if not value:
        raise ConfigError(f"missing {key} (set it in .env)")
    return value


def load_canon(*paths: Path) -> str:
    """Common + personal canon (or a herald's own file alone); a missing or empty file refuses to start."""
    parts = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8").strip()
        except FileNotFoundError as exc:
            raise ConfigError(f"canon not found: {path}") from exc
        if not text:
            raise ConfigError(f"canon is empty: {path}")
        parts.append(text)
    return "\n\n".join(parts)


def load_config(toml_path: str | Path, env: dict[str, str] | None = None,
                registry_path: Path = REGISTRY_PATH) -> AgentConfig:
    """Load the agent TOML and the shared env; connection settings resolve through the simulation registry
    (v3.3). `env` and the registry path are injectable for tests."""
    toml_path = Path(toml_path)
    try:
        data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"agent config not found: {toml_path}") from exc
    try:
        member = parse_member(toml_path.stem, data, str(toml_path))
    except RosterError as exc:
        raise ConfigError(str(exc)) from exc
    # canon and life are required only when the agent's type has them (a persona has both)
    required = [k for k in ("name", "user_id", "canon", "life", "simulation") if k not in ("canon", "life") or member.can(k)]
    if member.can("mood"):
        required.append("natal")
    if member.can("pastlife"):
        required.append("memories")
    if member.can("emotion"):
        required.append("voice_spec")
    if member.can("thoughts"):
        required.append("reading")
    for key in required:
        if not str(data.get(key, "")).strip():
            raise ConfigError(f"{toml_path}: missing '{key}'")
    canon = ""
    if member.can("canon"):  # a herald's canon is his own file only (v5.1): common.md speaks to the room's speakers
        personal = Path(str(data["canon"]))
        canon = load_canon(personal) if member.type == "herald" else load_canon(COMMON_CANON, personal)
    life = None
    if member.can("life"):
        life_path = Path(str(data["life"]))
        try:
            life = parse_life(life_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ConfigError(f"life story not found: {life_path}") from exc
        except LifeError as exc:
            raise ConfigError(f"{life_path}: {exc}") from exc

    natal = ""
    if member.can("mood"):
        natal_path = Path(str(data["natal"]))
        try:
            lines = natal_path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError as exc:
            raise ConfigError(f"natal chart not found: {natal_path}") from exc
        natal = "\n".join(line for line in lines if not line.lstrip().startswith("#")).strip()
        if not natal:
            raise ConfigError(f"natal chart is empty: {natal_path}")

    theses: tuple = ()
    if member.can("pastlife"):
        theses_path = Path(str(data["memories"]))
        try:
            theses = parse_theses(theses_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ConfigError(f"past-life theses not found: {theses_path}") from exc
        except ThesesError as exc:
            raise ConfigError(f"{theses_path}: {exc}") from exc
        if not theses:
            raise ConfigError(f"past-life theses are empty: {theses_path}")

    voice_spec = ""
    if member.can("emotion"):  # v5.9: her palette of audio tags, next to her canon
        spec_path = Path(str(data["voice_spec"]))
        try:
            voice_spec = spec_path.read_text(encoding="utf-8").strip()
        except FileNotFoundError as exc:
            raise ConfigError(f"voice spec not found: {spec_path}") from exc
        if not voice_spec:
            raise ConfigError(f"voice spec is empty: {spec_path}")

    reading = ""
    if member.can("thoughts"):  # v5.12: what she reads, next to her canon; `#` lines are notes, never her words
        reading_path = Path(str(data["reading"]))
        try:
            lines = reading_path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError as exc:
            raise ConfigError(f"reading file not found: {reading_path}") from exc
        reading = "\n".join(line for line in lines if not line.lstrip().startswith("#")).strip()
        if not reading:
            raise ConfigError(f"reading file is empty: {reading_path}")

    if env is None:
        load_dotenv()
        env = dict(os.environ)

    user_id = str(data["user_id"]).strip()
    localpart = user_id.split(":", 1)[0].lstrip("@")
    sim_id = str(data["simulation"]).strip()
    try:
        sim = load_registry(registry_path).get(sim_id)
    except RegistryError as exc:
        raise ConfigError(str(exc)) from exc
    if sim is None:
        raise ConfigError(f"{toml_path}: unknown simulation {sim_id!r}")
    if localpart not in sim.agents:
        raise ConfigError(f"{toml_path}: {localpart!r} is not an agent of {sim_id!r}")
    return AgentConfig(
        name=str(data["name"]).strip(),
        user_id=user_id,
        canon=canon,
        homeserver=_require(env, sim.endpoints["homeserver"]),
        room_id=_require(env, sim.endpoints["room"]),
        owner=_require(env, "OWNER"),
        password=_require(env, f"{localpart.upper()}_PASSWORD"),
        life=life,
        simulation=sim_id,
        type=member.type,
        engine=member.engine,
        capabilities=member.capabilities,
        natal=natal,
        theses=theses,
        voice_spec=voice_spec,
        reading=reading,
    )
