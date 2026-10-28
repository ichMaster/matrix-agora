"""v4.7 — the agents' tunable settings (the owner, 2026-10-11: «винести всі налаштування агентів на панель»), under
their service (the owner: the agents will join more than the Matrix room — a portal with a diary, a gallery, news).

`SCHEMA` is the single list of what the panel may tune: every non-secret setting an agent reads from its
environment, with its kind, bounds, code default, unit, a one-line description, a group, the members it concerns
(`scope`), and its `service`:
- a **service** setting belongs to a simulation kind (`matrix-chat`: the turns, the cat in the room, the personas'
  moves, Claude's news, the chat sessions) — its value is per simulation, shared by that simulation's agents;
- an **agent** setting (`service` None) is the agent's own whatever the service — memory, plans, where it lives,
  its model — its value is per agent.

The panel's overrides live in `state/settings.json` (written only by the panel):
`{"services": {<simulation id>: {name: value}}, "agents": {<agent>: {name: value}}}`. At its start an agent applies
its simulation's service overrides, then its own — code default < env < panel — and writes what it runs with to
`state/<name>.settings.json`. Secrets, the room and owner ids, `TIMEZONE` and paths are never here (a test pins it).
Pure but for the small file helpers.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass, field
from pathlib import Path

from agents.nudge import parse_hours
from agents.roster import Member

log = logging.getLogger("agent.settings")

OVERRIDES_FILE = "settings.json"
HOURS_RE = re.compile(r"^([01]?\d|2[0-3])-([01]?\d|2[0-4])$")
VOICE_ID_RE = re.compile(r"^[A-Za-z0-9]{10,40}$")  # an ElevenLabs voice id — the panel and the voice share it (#6)
ID_RE = re.compile(rf"^(?:{VOICE_ID_RE.pattern[1:-1]})?$")  # the `id` kind: such an id, or empty (none)
CHAT = "matrix-chat"  # the simulation kind of Agora (simulations.toml)


@dataclass(frozen=True)
class Setting:
    name: str
    kind: str                  # int | float | hours | choice | text | id (v5.1: letters and digits, empty = none) |
                               # weights (v5.11: the events' `kind:weight,…`)
    default: str               # the code default, as the environment would hold it
    group: str                 # a group within its scope (see GROUPS)
    scope: str                 # the members it concerns: shared | type:<t> | cap:<c> | engine:<e>
    service: str | None        # the simulation kind it belongs to, or None: the agent's own
    description: str
    unit: str = ""
    low: float | None = None
    high: float | None = None
    choices: tuple[str, ...] = field(default_factory=tuple)


def _s(name, kind, default, group, scope, service, description, unit="", low=None, high=None, choices=()):
    return Setting(name, kind, default, group, scope, service, description, unit, low, high, tuple(choices))


SCHEMA: tuple[Setting, ...] = (
    # ── the Matrix chat (Agora): its settings belong to the simulation ──
    # room & turns — every agent computes the turns from the same values (shared: a change restarts them all)
    _s("HISTORY_N", "int", "40", "turns", "shared", CHAT, "Скільки останніх повідомлень бачить агент", "msgs", 5, 300),
    _s("REPLY_MAX_TOKENS", "int", "200", "turns", "shared", CHAT, "Межа токенів на одну репліку (Gemini)", "tokens", 50, 2000),
    _s("MAX_BOT_TURNS", "int", "3", "turns", "shared", CHAT, "Скільки реплік агентів за вікно хвилі", "turns", 1, 30),
    _s("BOT_WINDOW_S", "int", "600", "turns", "shared", CHAT, "Вікно хвилі", "s", 30, 3600),
    _s("BOT_REPLY_P", "float", "0.5", "turns", "shared", CHAT, "Імовірність відповіді агента агентові без звертання", "", 0, 1),
    _s("OWNER_REPLIERS", "int", "2", "turns", "shared", CHAT, "Скільки агентів відповідає на повідомлення власника", "", 1, 5),
    _s("FALLBACK_S", "int", "30", "turns", "shared", CHAT, "Коли інший агент відповідає за мовчазного обраного", "s", 5, 600),
    _s("REPLY_DELAY_S", "float", "4", "turns", "shared", CHAT, "Найбільша пауза перед реплікою", "s", 1, 60),
    _s("CAT_REACT_P", "float", "0.3", "turns", "shared", CHAT, "Як часто Кіт реагує без звертання", "", 0, 1),
    _s("CAT_PURR_P", "float", "0.8", "turns", "shared", CHAT, "Яка частка реакцій Кота — муркотіння", "", 0, 1),
    # the personas' moves in the talk
    _s("PERSONA_ASK_P", "float", "0.25", "moves", "type:persona", CHAT, "Хід «запитати когось на ім'я»", "", 0, 1),
    _s("PERSONA_DISAGREE_P", "float", "0.15", "moves", "type:persona", CHAT, "Хід «заперечити»", "", 0, 1),
    _s("PERSONA_PLAN_P", "float", "0.1", "moves", "type:persona", CHAT, "Хід «згадати план»", "", 0, 1),
    _s("PERSONA_STORY_P", "float", "0.1", "moves", "type:persona", CHAT, "Хід «історія з життя»", "", 0, 1),
    _s("PERSONA_THOUGHT_P", "float", "0.1", "moves", "cap:thoughts", None, "Хід «згадати прочитане чи подумане»", "",
       0, 1),  # v5.12: hers only — a person without `thoughts` falls back to a plain answer
    # the cat in the room
    _s("CAT_MAX_WORDS", "int", "12", "cat", "type:creature", CHAT, "Межа слів репліки Кота", "words", 3, 60),
    _s("CAT_MEMORY_P", "float", "0.25", "cat", "cap:pastlife", CHAT, "Як часто Кіт згадує минуле життя", "", 0, 1),
    _s("CAT_NUDGE_IDLE_S", "int", "1200", "cat", "cap:nudge", CHAT, "Тиша, після якої Кіт починає сам", "s", 300, 86400),
    _s("CAT_NUDGES_PER_DAY", "int", "6", "cat", "cap:nudge", CHAT, "Найбільше ініціатив Кота на день", "", 0, 1000),
    _s("CAT_NUDGE_HOURS", "hours", "09-22", "cat", "cap:nudge", CHAT, "Години, коли Кіт починає сам (HH-HH)"),
    # Claude in the room
    _s("CLAUDE_HISTORY_N", "int", "150", "claude", "engine:claude-sdk", CHAT, "Вікно філософа", "msgs", 20, 500),
    _s("CLAUDE_NEWS_EVERY_S", "int", "3600", "claude", "cap:news", CHAT, "Як часто Клод приносить новину", "s", 600, 86400),
    _s("CLAUDE_NEWS_IDLE_S", "int", "300", "claude", "cap:news", CHAT, "Тиша перед новиною", "s", 0, 86400),
    _s("CLAUDE_NEWS_PER_DAY", "int", "24", "claude", "cap:news", CHAT, "Найбільше новин на день", "", 0, 200),
    _s("CLAUDE_NEWS_HOURS", "hours", "09-01", "claude", "cap:news", CHAT, "Години новин (HH-HH)"),
    # Hermes, the herald (v5.1): his digests of the room — read only by the member with `digest`
    _s("HERMES_DIGEST_EVERY_S", "int", "14400", "hermes", "cap:digest", CHAT, "Як часто Гермес приносить підсумок",
       "s", 3600, 86400),
    _s("HERMES_DIGEST_MIN_MESSAGES", "int", "5", "hermes", "cap:digest", CHAT,
       "Найменше нових повідомлень для підсумку", "msgs", 1, 500),
    _s("HERMES_DIGEST_MAX_CHARS", "int", "1500", "hermes", "cap:digest", CHAT, "Найдовший підсумок (~1000 знаків — хвилина)",
       "chars", 300, 3000),
    _s("HERMES_DIGEST_HOURS", "hours", "09-23", "hermes", "cap:digest", CHAT, "Години підсумків за розкладом (HH-HH)"),
    _s("HERMES_TTS_MONTHLY_CHARS", "int", "150000", "hermes", "cap:digest", CHAT,
       "Межа озвучених знаків на місяць (0 — лише текст)", "chars", 0, 1_000_000),
    _s("HERMES_VOICE_ID", "id", "", "hermes", "cap:digest", CHAT, "Голос Гермеса (ElevenLabs voice id; порожньо — текст)"),
    # v5.3 — the speakers' voices: one budget for all of them (Hermes keeps his own); v5.5: 200,000 (the owner)
    _s("VOICE_MONTHLY_CHARS", "int", "200000", "voice", "cap:voice", CHAT,
       "Межа озвучених знаків агентів на місяць (0 — лише текст)", "chars", 0, 1_000_000),
    # the chat's sessions
    _s("SESSION_IDLE_S", "int", "900", "session", "cap:summary", CHAT, "Тиша, після якої сесія закінчується", "s", 60, 86400),
    _s("SESSION_MAX_MESSAGES", "int", "200", "session", "cap:summary", CHAT, "Найбільша сесія", "msgs", 20, 2000),
    _s("SUMMARY_MAX_WORDS", "int", "200", "session", "cap:summary", CHAT, "Межа слів підсумку сесії", "words", 50, 1000),
    # ── the agent's own, whatever the service ──
    _s("MEMORY_DAYS", "int", "7", "memory", "cap:chronicle", None, "Скільки днів спогадів у промпті", "days", 1, 60),
    _s("MEMORY_WEEKS", "int", "4", "memory", "cap:chronicle", None, "Скільки тижневих підсумків", "weeks", 0, 26),
    _s("MEMORY_MONTHS", "int", "6", "memory", "cap:chronicle", None, "Скільки місячних підсумків", "months", 0, 24),
    _s("PLAN_MAX_WORDS", "int", "120", "plans", "cap:plans", None, "Межа слів плану", "words", 30, 600),
    _s("PLAN_MUTATION_RATE", "float", "0.3", "plans", "cap:plans", None, "Частка пунктів плану, що зміняться", "", 0, 1),
    _s("LOCATION", "text", "Львів, Україна", "life", "cap:world", None, "Де живе"),
    # v5.3 — its own voice (the base is the agent's <NAME>_VOICE_ID) and how often it speaks in it
    _s("VOICE_ID", "id", "", "voice", "cap:voice", None, "Голос (ElevenLabs voice id; порожньо — текст)"),
    _s("VOICE_REPLY_P", "float", "1.0", "voice", "cap:voice", None,
       "Частка реплік голосом (на голос Ich — завжди)", "", 0, 1),
    # v5.9 — a speaker's own ElevenLabs model and voice settings (Кіра: eleven_v4_turbo, 0.3 — the owner's ear)
    _s("ELEVENLABS_MODEL", "choice", "eleven_turbo_v2_5", "voice", "cap:voice", None, "Модель голосу (ElevenLabs)",
       choices=("eleven_turbo_v2_5", "eleven_flash_v2_5", "eleven_multilingual_v2", "eleven_v3", "eleven_v4_turbo",
                "eleven_v4")),
    _s("VOICE_STABILITY", "float", "0.5", "voice", "cap:voice", None, "Стабільність голосу (менше — живіше)", "", 0, 1),
    _s("VOICE_SPEED", "float", "1.0", "voice", "cap:voice", None, "Швидкість голосу", "", 0.7, 1.2),
    # v5.6 — the private chat with the owner: writing first after a long silence
    _s("PRIVATE_IDLE_S", "int", "21600", "private", "cap:private", None,
       "Тиша в особистому чаті, після якої пише першою", "s", 1800, 604800),
    _s("PRIVATE_NUDGES_PER_DAY", "int", "2", "private", "cap:private", None,
       "Скільки разів на день може написати першою", "", 0, 10),
    _s("PRIVATE_HOURS", "hours", "10-22", "private", "cap:private", None, "Години, коли може написати першою (HH-HH)"),
    # v5.8.2 (the owner, 2026-10-25): where she writes first — `last`: the door he used last; or always one door
    _s("PRIVATE_FIRST_DOOR", "choice", "last", "private", "cap:private", None,
       "Куди пише першою (last — туди, де він писав останнім)", choices=("last", "telegram", "matrix")),
    # v5.8 — the archive (`recall`): how many recalled lines enter a prompt, and Agora's lines of today in the private
    # chat
    _s("RECALL_N", "int", "6", "memory", "cap:recall", None, "Скільки рядків пригадує перед відповіддю", "lines", 0, 20),
    # v5.8 — facts about the owner (`facts`): the store's size, how many reach her private prompt, a fact's length
    _s("FACTS_MAX", "int", "100", "memory", "cap:facts", None, "Скільки фактів про Ich зберігає", "facts", 10, 500),
    _s("FACTS_IN_PROMPT", "int", "25", "memory", "cap:facts", None, "Скільки фактів бачить в особистому чаті", "facts",
       0, 100),
    _s("FACT_MAX_CHARS", "int", "240", "memory", "cap:facts", None, "Найдовший факт", "chars", 80, 600),
    _s("PRIVATE_AGORA_N", "int", "20", "private", "cap:recall", None,
       "Скільки сьогоднішніх рядків Агори бачить в особистому чаті", "lines", 0, 60),
    # v5.11 — events of her life (`events`): the hourly roll, the kinds' weights, her waking hours
    _s("EVENT_P", "float", "0.12", "life", "cap:events", None, "Ймовірність події щогодини", "", 0, 1),
    _s("EVENT_WEIGHTS", "weights", "everyday:6,joyful:2,inspiring:2,heavy:1", "life", "cap:events", None,
       "Ваги подій (everyday, joyful, inspiring, heavy)"),
    _s("EVENT_HOURS", "hours", "08-23", "life", "cap:events", None, "Години, коли з нею стаються події (HH-HH)"),
    _s("CITY_NEWS_P", "float", "0.01", "life", "cap:events", None,
       "Ймовірність, що новина Львова торкнеться її життя (про Львів — уп'ятеро)", "", 0, 1),
    _s("CITY_NEWS_MAX", "int", "2", "life", "cap:events", None, "Скільки новин на день може торкнутися її життя",
       "", 0, 5),
    # v5.12 — she reads the news and thinks (`thoughts`): the reading's period, hours, picks and the Guardian's sections;
    # the reflection's period; how many of today's thoughts her prompts carry
    _s("READING_EVERY_S", "int", "10800", "life", "cap:thoughts", None, "Як часто читає новини", "s", 1800, 86400),
    _s("READING_HOURS", "hours", "08-01", "life", "cap:thoughts", None, "Години, коли читає новини (HH-HH)"),
    _s("READING_PICKS", "int", "2", "life", "cap:thoughts", None, "Скільки новин найбільше прочитає за раз", "", 0, 5),
    _s("READING_SECTIONS", "text", "science,world,environment,technology,culture", "life", "cap:thoughts", None,
       "Розділи The Guardian, які гортає (через кому)"),
    _s("REFLECT_EVERY_S", "int", "3600", "life", "cap:thoughts", None, "Як часто думає про свої розмови", "s", 600,
       86400),
    _s("THOUGHTS_IN_PROMPT", "int", "3", "life", "cap:thoughts", None, "Скільки сьогоднішніх думок бачить у розмові",
       "", 0, 10),
    # only models that run with thinking off — every call sends thinking_budget=0 (v4.7 review #1: 2.5 Pro cannot)
    _s("GEMINI_MODEL", "choice", "gemini-2.5-flash", "model", "engine:gemini", None, "Модель Gemini",
       choices=("gemini-2.5-flash", "gemini-2.5-flash-lite")),
    # v5.8 — the agent's answers on a model of their own (empty: GEMINI_MODEL); a thinking model (3.1 Pro) answers
    # through the thinking path at this level, under its own cap (the thinking counts toward it)
    _s("GEMINI_REPLY_MODEL", "choice", "", "model", "engine:gemini", None, "Модель відповідей (порожньо — та сама)",
       choices=("", "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-3.1-pro-preview")),
    _s("GEMINI_THINKING_LEVEL", "choice", "low", "model", "engine:gemini", None, "Як довго думає модель відповідей",
       choices=("low", "medium", "high")),
    _s("REPLY_THINK_MAX_TOKENS", "int", "4096", "model", "engine:gemini", None,
       "Межа токенів відповіді, що думає (з думанням)", "tokens", 1024, 32768),
    _s("CLAUDE_MODEL", "choice", "opus", "model", "engine:claude-sdk", None, "Модель Клода", choices=("opus", "sonnet", "haiku")),
    _s("CLAUDE_TIMEOUT_S", "int", "300", "model", "engine:claude-sdk", None, "Найдовша відповідь Клода", "s", 30, 1800),
    _s("CLAUDE_CODE_MAX_OUTPUT_TOKENS", "int", "0", "model", "engine:claude-sdk", None, "Межа виводу (0 — без межі)",
       "tokens", 0, 64000),
)
BY_NAME: dict[str, Setting] = {s.name: s for s in SCHEMA}
# the groups in their order, for a service's card and for an agent's tab
SERVICE_GROUPS = (("turns", "Room & turns"), ("moves", "Ада і Бруно: ходи"), ("cat", "Кіт у кімнаті"),
                  ("claude", "Клод у кімнаті"), ("hermes", "Гермес"), ("voice", "Голоси агентів"),
                  ("session", "Сесії розмови"))
AGENT_GROUPS = (("memory", "Пам'ять"), ("plans", "Плани"), ("life", "Життя"), ("model", "Модель"),
                ("voice", "Голос"), ("private", "Особистий чат"))


def validate(name: str, raw: object) -> tuple[str | None, str | None]:
    """(the value as the environment holds it, None) or (None, why). Only the schema's names."""
    setting = BY_NAME.get(name)
    if setting is None:
        return None, "unknown setting"
    text = str(raw).strip() if raw is not None else ""
    if setting.kind in ("int", "float"):
        try:
            number = float(text)
        except ValueError:
            return None, "not a number"
        if not math.isfinite(number) or setting.kind == "int" and number != int(number):
            return None, "not a whole number" if setting.kind == "int" else "not a number"
        if setting.low is not None and number < setting.low or setting.high is not None and number > setting.high:
            return None, f"outside {setting.low:g}..{setting.high:g}"
        return (str(int(number)) if setting.kind == "int" else f"{number:g}"), None
    if setting.kind == "hours":  # the agents' own parser: a value it cannot use is refused (v4.7 review #2)
        try:
            parse_hours(text)
        except ValueError:
            return None, "not HH-HH with two different hours"
        return (text, None) if HOURS_RE.match(text) else (None, "not HH-HH")
    if setting.kind == "weights":  # v5.11: the agents' own parser, as for the hours
        from agents.events import format_weights, parse_weights
        try:
            return format_weights(parse_weights(text)), None
        except ValueError:
            return None, "not kind:weight of everyday, joyful, inspiring, heavy"
    if setting.kind == "choice":
        return (text, None) if text in setting.choices else (None, "not one of " + ", ".join(setting.choices))
    if setting.kind == "id":  # v5.1: an ElevenLabs voice id — letters and digits; empty means none
        return (text, None) if ID_RE.match(text) else (None, "not 10–40 letters and digits (or empty)")
    if not text or len(text) > 120 or any(ch in text for ch in "\n\r\x00"):
        return None, "empty or too long"
    return text, None


def concerns(setting: Setting, member: Member) -> bool:
    """Whether a setting changes what `member` does — the agents a change restarts. A herald (v5.1) reads only the
    settings of his own capabilities: a turn setting or the room's model never restarts him."""
    kind, _, value = setting.scope.partition(":")
    if member.type == "herald" and kind != "cap":
        return False
    if setting.scope == "shared":
        return True
    if kind == "type":
        return member.type == value
    if kind == "cap":
        return value in member.capabilities
    if kind == "engine":
        return member.engine == value
    return False


def load_overrides(path: Path) -> dict[str, dict[str, dict[str, str]]]:
    """The panel's overrides, `{"services": {sim: {name: value}}, "agents": {agent: {name: value}}}`: a missing or
    corrupt file means none; values are kept as written (checked on use)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = None
    out: dict[str, dict[str, dict[str, str]]] = {"services": {}, "agents": {}}
    if not isinstance(data, dict):
        return out
    for part in ("services", "agents"):
        section = data.get(part)
        if not isinstance(section, dict):
            continue
        for owner, values in section.items():
            if isinstance(owner, str) and isinstance(values, dict):
                out[part][owner] = {str(k): str(v) for k, v in values.items()
                                    if isinstance(k, str) and isinstance(v, str | int | float)}
    return out


def save_json(path: Path, data: Mapping) -> None:
    """Atomic, private from birth (0600)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True).encode("utf-8"))
    finally:
        os.close(fd)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def in_scope(setting: Setting, sim_kind: str | None) -> bool:
    """A service setting of this simulation kind (`sim_kind`), or an agent setting (`sim_kind` None)."""
    return setting.service == sim_kind if sim_kind is not None else setting.service is None


def apply_overrides(env: MutableMapping[str, str], overrides: Mapping[str, Mapping[str, Mapping[str, str]]],
                    member: Member, simulation: object | None) -> tuple[list[str], list[str]]:
    """Set into `env` the valid overrides that concern `member`: its simulation's service settings, then its own
    agent settings (code default < env < panel). Returns (applied, ignored) names — an unknown, invalid or
    out-of-scope one is ignored; one that does not concern the member is neither."""
    applied, ignored = [], []
    layers = []
    if simulation is not None:
        layers.append((overrides.get("services", {}).get(simulation.id, {}), simulation.kind))
    layers.append((overrides.get("agents", {}).get(member.localpart, {}), None))
    for values, sim_kind in layers:
        for name, raw in sorted(values.items()):
            setting = BY_NAME.get(name)
            if setting is None or not in_scope(setting, sim_kind):
                ignored.append(name)
                continue
            if not concerns(setting, member):
                continue
            value, _why = validate(name, raw)
            if value is None:
                ignored.append(name)
                continue
            env[name] = value
            applied.append(name)
    return applied, ignored


def effective(env: Mapping[str, str], member: Member, applied: list[str]) -> dict[str, dict[str, str]]:
    """What `member` runs with, for the panel: every setting that concerns it, its value and its source."""
    out = {}
    for setting in SCHEMA:
        if not concerns(setting, member):
            continue
        if setting.name in applied:
            out[setting.name] = {"value": env[setting.name], "source": "panel"}
        elif env.get(setting.name, "") != "":
            out[setting.name] = {"value": str(env[setting.name]), "source": "env"}
        else:
            out[setting.name] = {"value": setting.default, "source": "default"}
    return out


def _stray_keys(path: Path) -> list[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return sorted(str(k) for k in data if k not in ("services", "agents")) if isinstance(data, dict) else []


def start(env: MutableMapping[str, str], state_dir: Path, member: Member,
          registry_path: Path | None = None) -> list[str]:
    """At an agent's start: apply its simulation's and its own overrides and write `state/<name>.settings.json`.
    Logs names only; an unreadable registry means no service overrides; a failure to write is logged by its type —
    nothing here ever stops the agent."""
    from agents.registry import REGISTRY_PATH, RegistryError, load_registry, simulation_of
    try:
        simulation = simulation_of(load_registry(registry_path or REGISTRY_PATH), member.localpart)
    except (RegistryError, OSError) as exc:
        log.warning("settings: no simulation registry (%s) — only the agent's own overrides", type(exc).__name__)
        simulation = None
    # v5.3 — each agent's own voice is its base: <NAME>_VOICE_ID becomes VOICE_ID unless VOICE_ID is set
    if not str(env.get("VOICE_ID", "")).strip():
        env["VOICE_ID"] = str(env.get(f"{member.localpart.upper()}_VOICE_ID", "")).strip()
    stray = _stray_keys(state_dir / OVERRIDES_FILE)
    if stray:  # an older flat file, or a hand edit: said by name, never applied (078 review #4)
        log.warning("settings: %s ignored — not under services/agents", ", ".join(stray))
    applied, ignored = apply_overrides(env, load_overrides(state_dir / OVERRIDES_FILE), member, simulation)
    if applied:
        log.info("settings: overridden %s", ", ".join(applied))
    if ignored:
        log.warning("settings: ignored %s (unknown, invalid or out of scope)", ", ".join(ignored))
    try:
        save_json(state_dir / f"{member.localpart}.settings.json", effective(env, member, applied))
    except OSError as exc:
        log.error("settings: effective values not written (%s)", type(exc).__name__)
    return applied
