"""v5.24 — the scan (the owner, 2026-11-03: «чи можна зробити такий аналіз через опус як суддя … спочатку показує
скільки буде таких меседжів і потім yes це блокування»): Claude Opus 5.5, on the owner's API key, reads what Gemini can
read of Кіра's private talk since the last scan and names what may trip Gemini's prohibited-content filter; the
owner's `/scan yes` closes it (agents/agent.py). It only ever closes: its mistake costs a memory, never a block.

Pure but for `OpusJudge`, the only Anthropic API client in the codebase — `anthropic` is imported here, lazily, and
nowhere else (tests/test_claude_sdk.py), with the key passed explicitly from `OPUS_JUDGE_KEY`: never an `ANTHROPIC_*`
name, so Claude's container stays on the subscription alone (v4.4). Never a text in a log.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agents.world import local_now

log = logging.getLogger("agent.scan")

KEY_VAR = "OPUS_JUDGE_KEY"
MODEL = "claude-opus-5-5"
EFFORTS = ("low", "medium", "high")
MAX_TOKENS = 16_000
FALLBACK_BETA = "server-side-fallback-2026-07-01"  # `fallbacks: "default"`: a declined request re-run server-side
DAY_MS = 86_400_000
# the manual pass's rubric (2026-11-03): the strongest one a line carries
CODES = ("S", "D", "P", "M", "I", "X")
CODE_NAMES = {"S": "сцени", "D": "домінування", "P": "фото", "M": "вік", "I": "натяки", "X": "зброя"}
# a ref names its kind: an archive line or thought by its id, a fact or a summary by its place in the request
PREFIX_KIND = {"L": "line", "T": "thought", "F": "fact", "S": "summary"}

# Says what the chat is, never what she is: no word `BANNED_RE` catches (tests/test_scan.py)
SYSTEM = (
    "You review a private chat, in Ukrainian, between two adults, Ich and Кіра, together with what Кіра remembers of "
    "it: her facts about Ich, her own thoughts on their talk and her short summaries of it. These items go back, "
    "every time, into the context a strict content filter of an online service checks. That filter rejects the whole "
    "context when anything in it falls under its prohibited content, and it names nothing. Find the items that may "
    "trip it, so that they can be left out for good.\n\n"
    "Codes (give the strongest one an item carries):\n"
    "S — a sexual act, sexual touching or contact in a sexual scene, undressing or nudity, arousal, bodily fluids in a "
    "sexual context; for a fact, a sexual detail about either of them or their intimacy.\n"
    "D — dominance, ownership, power or control in a sexual context; violence, restraint or pain in a sexual context "
    "(the throat, bruises, pinning); feigned or absent consent.\n"
    "P — a request for, or a description of, a revealing, nude or sexual photo or video.\n"
    "M — a word or a reference that may read as a minor in a sexual or a flirting context («мала», «малишка», "
    "«дівчинка», «мамочка», «школярка», an age, childhood mixed with sex).\n"
    "I — clear sexual innuendo or a euphemism for sex, or an item that continues or answers such a scene.\n"
    "X — weapons, explosives, sabotage or terror, whatever the purpose.\n\n"
    "Not candidates: compliments on looks, ordinary flirting, a kiss or a hug outside a sexual scene, work, the city, "
    "plans, feelings, the sky, the weather, family, ordinary facts (a job, a city, tastes, habits).\n\n"
    "Judge each item among its neighbours. Put an item you are sure of in `candidates` and a doubtful one in "
    "`borderline`; leave everything else out. Answer with the refs exactly as given.")

SCHEMA = {
    "type": "object",
    "properties": {
        name: {"type": "array", "items": {
            "type": "object",
            "properties": {"ref": {"type": "string"}, "code": {"type": "string", "enum": list(CODES)}},
            "required": ["ref", "code"], "additionalProperties": False}}
        for name in ("candidates", "borderline")},
    "required": ["candidates", "borderline"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class ScanItem:
    """One thing Gemini can read: `kind` `line` (a private line), `thought` (her thought on the private talk), `fact`
    or `summary`; `speaker` is the line's, or a summary's level."""
    ref: str
    kind: str
    when_ms: int
    speaker: str
    text: str


@dataclass
class Found:
    """What a scan found, by ref: its code. A ref is never in both."""
    candidates: dict[str, str] = field(default_factory=dict)
    borderline: dict[str, str] = field(default_factory=dict)

    def add(self, other: Found) -> None:
        self.candidates.update(other.candidates)
        self.borderline.update({r: c for r, c in other.borderline.items() if r not in self.candidates})
        for ref in self.candidates:
            self.borderline.pop(ref, None)

    def __bool__(self) -> bool:
        return bool(self.candidates or self.borderline)


def scan_range(now_ms: int, last_end_ms: int | None, days: int) -> tuple[int, int]:
    """[start, end) of a scan (pure): from the last scan's end, at most `days` back; with none, `days` back."""
    floor = now_ms - max(int(days), 1) * DAY_MS
    start = max(floor, int(last_end_ms)) if last_end_ms else floor
    return min(start, now_ms), now_ms


def kind_of(ref: str) -> str | None:
    """`L12` → `line`, `T3` → `thought`, `F0` → `fact`, `S1` → `summary`; else None."""
    return PREFIX_KIND.get(ref[:1]) if ref[1:].isdigit() else None


def item_line(item: ScanItem, tz: str) -> str:
    """`<ref> <dd.mm HH:MM> <who>: <text>`, the text on one line."""
    when = local_now(item.when_ms, tz).strftime("%d.%m %H:%M")
    who = {"fact": "факт", "thought": "думка Кіри", "summary": f"підсумок {item.speaker}"}.get(item.kind, item.speaker)
    return f"{item.ref} {when} {who}: {' '.join((item.text or '').split())}"


def scan_request(items: Iterable[ScanItem], tz: str) -> tuple[str, str]:
    """(the system prompt, the user content) for one call (pure): the items in time order, a line each."""
    lines = [item_line(i, tz) for i in sorted(items, key=lambda x: (x.when_ms, x.ref))]
    return SYSTEM, "Items, oldest first:\n" + "\n".join(lines)


def parse_scan(raw: str | None, refs: set[str]) -> Found | None:
    """The structured answer (pure): `{"candidates": [{"ref", "code"}], "borderline": [...]}`. A ref the request did
    not hold or a code outside `CODES` is dropped; a ref in both lists is a candidate; a malformed answer is None,
    never a part of one."""
    try:
        data = json.loads(raw or "")
    except ValueError:
        return None
    if not isinstance(data, dict) or not all(isinstance(data.get(k), list) for k in ("candidates", "borderline")):
        return None
    found = Found()
    for name in ("candidates", "borderline"):
        for entry in data[name]:
            if not isinstance(entry, dict):
                return None
            ref, code = entry.get("ref"), entry.get("code")
            if isinstance(ref, str) and ref in refs and code in CODES:
                getattr(found, name)[ref] = code
    for ref in found.candidates:
        found.borderline.pop(ref, None)
    return found


def scan_counts(found: Found) -> dict[str, Any]:
    """What the command's answer names (pure): the candidate lines by code, the candidate facts, thoughts and
    summaries, and the borderline of every kind."""
    lines = {c: 0 for c in CODES}
    out: dict[str, Any] = {"lines": lines, "facts": 0, "thoughts": 0, "summaries": 0,
                           "borderline": len(found.borderline)}
    for ref, code in found.candidates.items():
        kind = kind_of(ref)
        if kind == "line":
            lines[code] += 1
        elif kind is not None:
            out[{"fact": "facts", "thought": "thoughts", "summary": "summaries"}[kind]] += 1
    return out


def counts_line(counts: dict[str, Any]) -> str:
    """The ⚙️ answer to `/scan` (pure): the counts only, never a text."""
    lines = counts["lines"]
    total = sum(lines.values())
    if not (total or counts["facts"] or counts["thoughts"] or counts["summaries"] or counts["borderline"]):
        return "⚙️ Нічого не знайдено"
    by_code = ", ".join(f"{CODE_NAMES[c]} {n}" for c, n in lines.items() if n)
    return (f"⚙️ Знайдено {total} рядків{f' ({by_code})' if by_code else ''}, {counts['facts']} фактів, "
            f"{counts['thoughts']} думок, {counts['summaries']} підсумків; межових: {counts['borderline']}. "
            "/scan yes — закрити знайдене, /scan all — разом з межовими")


DAY_KINDS = (("line", "рядки"), ("thought", "думки"), ("fact", "факти"), ("summary", "підсумки"))


def days_lines(items: list[ScanItem], found: Found, tz: str) -> str:
    """v5.24 (the owner, 2026-11-04: «я хочу бачити по днях скільки закриється зі всіх в цьому дні»; «так зроби
    статистику в телеграм теж») — the answer's breakdown by local day (pure): for each kind read that day, how many
    `/scan yes` closes, how many more `/scan all` does, of how many read; counts only, never a text."""
    days: dict[str, dict[str, list[int]]] = {}
    first: dict[str, int] = {}  # a day's earliest time, so the days go in order across a year's end
    for item in items:
        day = local_now(item.when_ms, tz).strftime("%d.%m")
        first[day] = min(first.get(day, item.when_ms), item.when_ms)
        row = days.setdefault(day, {}).setdefault(item.kind, [0, 0, 0])
        row[0] += item.ref in found.candidates
        row[1] += item.ref in found.borderline
        row[2] += 1
    order = sorted(days, key=first.__getitem__)
    lines = [f"{day}: " + ", ".join(f"{name} {days[day][kind][0]} + {days[day][kind][1]} з {days[day][kind][2]}"
                                    for kind, name in DAY_KINDS if kind in days[day]) for day in order]
    return "По днях — закриє /scan yes + ще /scan all, з прочитаного:\n" + "\n".join(lines)


def fact_hash(fact_id: str) -> str:
    """A fact by the sha256 of its id in the scan file — never the id, which is its text's slug."""
    return hashlib.sha256((fact_id or "").encode("utf-8")).hexdigest()


def load_scan(path: Path) -> dict[str, Any]:
    """The scan file (`state/<name>.scan.json`): the last list and the next scan's start; {} when missing or bad."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_scan(path: Path, data: dict[str, Any]) -> None:
    """Atomic, private from birth (0600) — refs, codes, hashes, times and counts, never a text."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, json.dumps(data, ensure_ascii=False).encode("utf-8"))
    finally:
        os.close(fd)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


UsageSink = Callable[..., None]  # (model, prompt_tokens, output_tokens, ok, latency_ms, cache_read, cache_write)


class OpusJudge:
    """The scan's call: one Messages API request per chunk of `chunk` items to `model`, adaptive thinking (the model's
    own) at `effort`, the answer as structured output, and the server-side fallback for a declined request. A refusal,
    an answer cut short or malformed, or any error ends the scan with None — nothing found, nothing closed. Logged by
    the stop reason, its category or the error's class, never a text."""

    def __init__(self, key: str, model: str = MODEL, effort: str = "medium", chunk: int = 400,
                 usage: UsageSink | None = None, client: Any = None, clock: Callable[[], float] = time.monotonic):
        self.key, self.model = key, model or MODEL
        self.effort = effort if effort in EFFORTS else "medium"
        self.chunk, self.usage, self._client, self.clock = max(int(chunk), 1), usage, client, clock

    def _make(self) -> Any:
        import anthropic  # v5.24: here alone, lazily — the suite imports this module without the package

        return anthropic.AsyncAnthropic(api_key=self.key)

    async def judge(self, items: list[ScanItem], tz: str) -> Found | None:
        found = Found()
        for i in range(0, len(items), self.chunk):
            part = await self._call(items[i:i + self.chunk], tz)
            if part is None:
                return None
            found.add(part)
        return found

    async def _call(self, items: list[ScanItem], tz: str) -> Found | None:
        system, user = scan_request(items, tz)
        t0 = self.clock()
        try:
            client = self._client if self._client is not None else self._make()
            self._client = client
            resp = await client.beta.messages.create(
                model=self.model, max_tokens=MAX_TOKENS, system=system,
                messages=[{"role": "user", "content": user}],
                output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": SCHEMA}},
                betas=[FALLBACK_BETA], fallbacks="default")
        except Exception as exc:  # noqa: BLE001 — a failed scan closes nothing
            self._account(None, False, t0)
            log.error("scan: the call failed (%s)", type(exc).__name__)
            return None
        stop = getattr(resp, "stop_reason", None)
        self._account(resp, stop not in ("refusal", "max_tokens"), t0)
        if stop == "refusal":
            details = getattr(resp, "stop_details", None)
            log.warning("scan: declined (%s)", getattr(details, "category", None) or "no category")
            return None
        if stop == "max_tokens":
            log.warning("scan: the answer was cut short")
            return None
        text = "".join(getattr(b, "text", "") for b in getattr(resp, "content", None) or []
                       if getattr(b, "type", "") == "text")
        found = parse_scan(text, {i.ref for i in items})
        if found is None:
            log.warning("scan: the answer did not parse")
        return found

    def _account(self, resp: Any, ok: bool, t0: float) -> None:
        if self.usage is None:
            return
        u = getattr(resp, "usage", None)

        def n(name: str) -> int:
            v = getattr(u, name, None)
            return v if isinstance(v, int) and not isinstance(v, bool) else 0

        read, write = n("cache_read_input_tokens"), n("cache_creation_input_tokens")
        prompt = n("input_tokens") + read + write if u is not None else None
        try:
            self.usage(getattr(resp, "model", None) or self.model, prompt,
                       n("output_tokens") if u is not None else None, ok,
                       int((self.clock() - t0) * 1000), read if u is not None else None,
                       write if u is not None else None)
        except Exception:
            log.exception("scan: usage accounting failed")
