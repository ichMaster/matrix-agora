"""v4.7 — the agents' tunable settings (the owner, 2026-10-11: «винести всі налаштування агентів на панель»).

`SCHEMA` is the single list of what the panel may tune: every non-secret setting an agent reads from its
environment, with its kind, bounds, code default, unit, a one-line description, a group, and the members it
concerns. The panel's overrides live in `state/settings.json` (written only by the panel); at its start an agent
applies those that concern it over its environment — code default < env < panel — and writes what it runs with to
`state/<name>.settings.json`, so the panel can show it. Secrets, the room and owner ids, `TIMEZONE` and paths are
never here (a test pins it). Pure but for the two small file helpers.
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

from agents.roster import Member

log = logging.getLogger("agent.settings")

OVERRIDES_FILE = "settings.json"
HOURS_RE = re.compile(r"^([01]?\d|2[0-3])-([01]?\d|2[0-4])$")


@dataclass(frozen=True)
class Setting:
    name: str
    kind: str                  # int | float | hours | choice | text
    default: str               # the code default, as the environment would hold it
    group: str                 # turns | personas | memory | cat | claude | gemini
    scope: str                 # shared | type:<t> | cap:<c> | engine:<e>
    description: str
    unit: str = ""
    low: float | None = None
    high: float | None = None
    choices: tuple[str, ...] = field(default_factory=tuple)


def _s(name, kind, default, group, scope, description, unit="", low=None, high=None, choices=()):
    return Setting(name, kind, default, group, scope, description, unit, low, high, tuple(choices))


SCHEMA: tuple[Setting, ...] = (
    # room & turns — every agent computes the turns from the same values (shared: a change restarts them all)
    _s("HISTORY_N", "int", "40", "turns", "shared", "Скільки останніх повідомлень бачить агент", "msgs", 5, 300),
    _s("REPLY_MAX_TOKENS", "int", "200", "turns", "shared", "Межа токенів на одну репліку (Gemini)", "tokens", 50, 2000),
    _s("MAX_BOT_TURNS", "int", "3", "turns", "shared", "Скільки реплік агентів за вікно хвилі", "turns", 1, 30),
    _s("BOT_WINDOW_S", "int", "600", "turns", "shared", "Вікно хвилі", "s", 30, 3600),
    _s("BOT_REPLY_P", "float", "0.5", "turns", "shared", "Імовірність відповіді агента агентові без звертання", "", 0, 1),
    _s("OWNER_REPLIERS", "int", "2", "turns", "shared", "Скільки агентів відповідає на повідомлення власника", "", 1, 5),
    _s("FALLBACK_S", "int", "30", "turns", "shared", "Коли інший агент відповідає за мовчазного обраного", "s", 5, 600),
    _s("REPLY_DELAY_S", "float", "4", "turns", "shared", "Найбільша пауза перед реплікою", "s", 1, 60),
    _s("CAT_REACT_P", "float", "0.3", "turns", "shared", "Як часто Кіт реагує без звертання", "", 0, 1),
    _s("CAT_PURR_P", "float", "0.8", "turns", "shared", "Яка частка реакцій Кота — муркотіння", "", 0, 1),
    # the personas
    _s("PERSONA_ASK_P", "float", "0.25", "personas", "type:persona", "Хід «запитати когось на ім'я»", "", 0, 1),
    _s("PERSONA_DISAGREE_P", "float", "0.15", "personas", "type:persona", "Хід «заперечити»", "", 0, 1),
    _s("PERSONA_PLAN_P", "float", "0.1", "personas", "type:persona", "Хід «згадати план»", "", 0, 1),
    _s("PERSONA_STORY_P", "float", "0.1", "personas", "type:persona", "Хід «історія з життя»", "", 0, 1),
    _s("LOCATION", "text", "Львів, Україна", "personas", "cap:world", "Де живуть персонажі"),
    # memory
    _s("MEMORY_DAYS", "int", "7", "memory", "cap:chronicle", "Скільки днів спогадів у промпті", "days", 1, 60),
    _s("MEMORY_WEEKS", "int", "4", "memory", "cap:chronicle", "Скільки тижневих підсумків", "weeks", 0, 26),
    _s("MEMORY_MONTHS", "int", "6", "memory", "cap:chronicle", "Скільки місячних підсумків", "months", 0, 24),
    _s("SESSION_IDLE_S", "int", "900", "memory", "cap:summary", "Тиша, після якої сесія закінчується", "s", 60, 86400),
    _s("SESSION_MAX_MESSAGES", "int", "200", "memory", "cap:summary", "Найбільша сесія", "msgs", 20, 2000),
    _s("SUMMARY_MAX_WORDS", "int", "200", "memory", "cap:summary", "Межа слів підсумку сесії", "words", 50, 1000),
    _s("PLAN_MAX_WORDS", "int", "120", "memory", "cap:plans", "Межа слів плану", "words", 30, 600),
    _s("PLAN_MUTATION_RATE", "float", "0.3", "memory", "cap:plans", "Частка пунктів плану, що зміняться", "", 0, 1),
    # the cat
    _s("CAT_MAX_WORDS", "int", "12", "cat", "type:creature", "Межа слів репліки Кота", "words", 3, 60),
    _s("CAT_MEMORY_P", "float", "0.25", "cat", "cap:pastlife", "Як часто Кіт згадує минуле життя", "", 0, 1),
    _s("CAT_NUDGE_IDLE_S", "int", "1200", "cat", "cap:nudge", "Тиша, після якої Кіт починає сам", "s", 300, 86400),
    _s("CAT_NUDGES_PER_DAY", "int", "6", "cat", "cap:nudge", "Найбільше ініціатив Кота на день", "", 0, 1000),
    _s("CAT_NUDGE_HOURS", "hours", "09-22", "cat", "cap:nudge", "Години, коли Кіт починає сам (HH-HH)"),
    # Claude
    _s("CLAUDE_MODEL", "choice", "opus", "claude", "engine:claude-sdk", "Модель Клода", choices=("opus", "sonnet", "haiku")),
    _s("CLAUDE_HISTORY_N", "int", "150", "claude", "engine:claude-sdk", "Вікно філософа", "msgs", 20, 500),
    _s("CLAUDE_TIMEOUT_S", "int", "300", "claude", "engine:claude-sdk", "Найдовша відповідь Клода", "s", 30, 1800),
    _s("CLAUDE_CODE_MAX_OUTPUT_TOKENS", "int", "0", "claude", "engine:claude-sdk", "Межа виводу (0 — без межі)",
       "tokens", 0, 64000),
    _s("CLAUDE_NEWS_EVERY_S", "int", "3600", "claude", "cap:news", "Як часто Клод приносить новину", "s", 600, 86400),
    _s("CLAUDE_NEWS_IDLE_S", "int", "300", "claude", "cap:news", "Тиша перед новиною", "s", 0, 86400),
    _s("CLAUDE_NEWS_PER_DAY", "int", "24", "claude", "cap:news", "Найбільше новин на день", "", 0, 200),
    _s("CLAUDE_NEWS_HOURS", "hours", "09-01", "claude", "cap:news", "Години новин (HH-HH)"),
    # Gemini
    # only models that run with thinking off — every call sends thinking_budget=0 (v4.7 review #1: 2.5 Pro cannot)
    _s("GEMINI_MODEL", "choice", "gemini-2.5-flash", "gemini", "engine:gemini", "Модель Gemini",
       choices=("gemini-2.5-flash", "gemini-2.5-flash-lite")),
)
BY_NAME: dict[str, Setting] = {s.name: s for s in SCHEMA}


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
    if setting.kind == "hours":
        return (text, None) if HOURS_RE.match(text) else (None, "not HH-HH")
    if setting.kind == "choice":
        return (text, None) if text in setting.choices else (None, "not one of " + ", ".join(setting.choices))
    if not text or len(text) > 120 or any(ch in text for ch in "\n\r\x00"):
        return None, "empty or too long"
    return text, None


def concerns(setting: Setting, member: Member) -> bool:
    """Whether a setting changes what `member` does — the agents a change restarts."""
    if setting.scope == "shared":
        return True
    kind, _, value = setting.scope.partition(":")
    if kind == "type":
        return member.type == value
    if kind == "cap":
        return value in member.capabilities
    if kind == "engine":
        return member.engine == value
    return False


def load_overrides(path: Path) -> dict[str, str]:
    """The panel's overrides: a missing or corrupt file means none; values are kept as written (checked on use)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if isinstance(k, str) and isinstance(v, str | int | float)}


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


def apply_overrides(env: MutableMapping[str, str], overrides: Mapping[str, str],
                    member: Member) -> tuple[list[str], list[str]]:
    """Set the valid overrides that concern `member` into `env` (code default < env < panel). Returns (applied,
    ignored) names — an unknown or invalid one is ignored; one that does not concern the member is neither."""
    applied, ignored = [], []
    for name, raw in sorted(overrides.items()):
        setting = BY_NAME.get(name)
        if setting is None:
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


def start(env: MutableMapping[str, str], state_dir: Path, member: Member) -> list[str]:
    """At an agent's start: apply the panel's overrides and write `state/<name>.settings.json`. Logs names only;
    a failure to write is logged by its type and never stops the agent."""
    applied, ignored = apply_overrides(env, load_overrides(state_dir / OVERRIDES_FILE), member)
    if applied:
        log.info("settings: overridden %s", ", ".join(applied))
    if ignored:
        log.warning("settings: ignored %s (unknown or invalid)", ", ".join(ignored))
    try:
        save_json(state_dir / f"{member.localpart}.settings.json", effective(env, member, applied))
    except OSError as exc:
        log.error("settings: effective values not written (%s)", type(exc).__name__)
    return applied
