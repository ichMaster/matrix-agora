"""The agents' recorded life, read-only (v3.3): summary, day memories, digests, plans, today, tokens.

Paths are built only from a registry agent name and fixed patterns. A missing file is "not written yet";
an unreadable state/ is {"available": false} — never a 500. Plans' hidden mutation tags never leave this
module raw: they become `deviation: true` for the owner's eyes only.
"""

from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from agents.usage import aggregate, cost, parse_lines

DAYS_SHOWN = 60
ITEM_RE = re.compile(r"^\s*(?:[-•*]|\d+[.)])\s+(.*\S)\s*$")
TAG_RE = re.compile(r"\s*<!--.*?-->")
MUTATION_RE = re.compile(r"<!--\s*mutation:")
TODAY_TAG = re.compile(r"^<!--\s*(\d{4}-\d{2}-\d{2})T(\d{2})\s*-->\s*")
DATE_FILE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")


def local_today(tz: str | None = None) -> date:
    return datetime.now(ZoneInfo(tz or os.environ.get("TIMEZONE", "Europe/Kyiv"))).date()


def _read(path: Path) -> str | None:
    """A missing or unreadable file is None; bad bytes (a torn append) are replaced — never a 500 (v4.2 review #9)."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    return text or None


def _stamp(path: Path) -> str | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")
    except OSError:
        return None


def plan_items(text: str) -> list[dict]:
    items = []
    for line in text.splitlines():
        m = ITEM_RE.match(line)
        if m:
            items.append({"text": TAG_RE.sub("", m[1]).strip(), "deviation": bool(MUTATION_RE.search(line))})
    if not items:
        items = [{"text": TAG_RE.sub("", ln).strip(), "deviation": bool(MUTATION_RE.search(ln))}
                 for ln in text.splitlines() if ln.strip()]
    return items


def readable(state_dir: Path) -> bool:
    return os.access(state_dir, os.R_OK | os.X_OK)


def mood_view(state_dir: Path, name: str, today: date, natal: Path | None) -> dict | None:
    """v4.2 — the day's horoscope: today's reading from `<name>.mood.log` (its resolution, the full reading) and the
    day's biorhythms from the natal file's birth date. None until the day's reading exists."""
    from agents.mood import biorhythms, parse_birth_date, reading_from_log, split_resolution
    reading = reading_from_log(_read(state_dir / f"{name}.mood.log") or "", today.isoformat())
    if not reading:
        return None
    birth = parse_birth_date(_read(natal) or "") if natal else None
    cycles = [{"name": c.name, "value": round(c.value, 2), "label": c.label} for c in biorhythms(birth, today)] \
        if birth else []
    return {"date": today.isoformat(), "resolution": split_resolution(reading), "reading": reading, "biorhythms": cycles}


def memory_view(state_dir: Path, name: str, today: date, natal: Path | None = None, with_mood: bool = False) -> dict:
    if not readable(state_dir):
        return {"available": False}
    summary_path = state_dir / f"{name}.memory.md"
    summary = _read(summary_path)
    days_dir = state_dir / f"{name}.days"
    days = []
    if days_dir.is_dir():
        files = sorted((p for p in days_dir.iterdir() if DATE_FILE.match(p.name)), reverse=True)
        for p in files[:DAYS_SHOWN]:
            text = _read(p)
            if text:
                days.append({"date": p.stem, "text": text, "words": len(text.split())})
    digests = {}
    for layer, folder in (("year", "years"), ("month", "months"), ("week", "weeks")):
        d = state_dir / f"{name}.{folder}"
        latest = max((p for p in d.iterdir() if p.suffix == ".md"), default=None) if d.is_dir() else None
        digests[layer] = {"period": latest.stem, "text": _read(latest)} if latest else None
    monday = today - timedelta(days=today.weekday())
    plans_dir = state_dir / f"{name}.plans"
    plans = {}
    for horizon, fname, period in (("year", f"year-{today.year}.md", str(today.year)),
                                   ("month", f"month-{today:%Y-%m}.md", f"{today:%Y-%m}"),
                                   ("week", f"week-{monday.isoformat()}.md", monday.isoformat()),
                                   ("day", f"{today.isoformat()}.md", today.isoformat())):
        text = _read(plans_dir / fname)
        plans[horizon] = {"period": period, "items": plan_items(text)} if text else None
    today_raw = _read(state_dir / f"{name}.today.md")
    today_view = None
    if today_raw and (m := TODAY_TAG.match(today_raw)) and m[1] == today.isoformat():
        body = today_raw[m.end():].strip()
        today_view = {"hour": int(m[2]), "text": body, "first_line": body.splitlines()[0] if body else ""}
    return {
        "available": True,
        "summary": {"text": summary, "written_at": _stamp(summary_path), "words": len(summary.split())} if summary else None,
        "days": days, "digests": digests, "plans": plans, "today": today_view,
        "mood": mood_view(state_dir, name, today, natal) if with_mood else None,
    }


def _price(name: str) -> float | None:
    raw = os.environ.get(name, "").strip()
    try:
        return float(raw) if raw else None
    except ValueError:
        return None


def usage_view(state_dir: Path, days: int, today: date, agent: str | None = None) -> dict:
    if not readable(state_dir):
        return {"available": False}
    lines: list[str] = []
    for path in sorted(state_dir.glob("*.usage.jsonl")):
        try:
            lines += path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
    records, bad = parse_lines(lines)
    if agent:
        records = [r for r in records if r.get("agent") == agent]
    since = today - timedelta(days=days - 1)
    rows = aggregate(records, since, today)
    p_in, p_out = _price("PRICE_INPUT_PER_1M"), _price("PRICE_OUTPUT_PER_1M")
    priced = p_in is not None and p_out is not None

    def money(r):
        return round(cost(r, p_in, p_out), 6) if priced else None

    out_rows, per_agent, per_day = [], {}, {}
    total = {"calls": 0, "failed": 0, "input": 0, "output": 0, "total": 0}
    for (day, ag, kind), r in rows.items():
        out_rows.append({"day": day, "agent": ag, "kind": kind, "calls": r.calls, "failed": r.failed,
                         "input": r.prompt, "output": r.output, "total": r.total, "cost": money(r)})
        for acc in (per_agent.setdefault(ag, dict.fromkeys(total, 0)), total):
            acc["calls"] += r.calls
            acc["failed"] += r.failed
            acc["input"] += r.prompt
            acc["output"] += r.output
            acc["total"] += r.total
        per_day.setdefault(day, {}).setdefault(ag, 0)
        per_day[day][ag] += r.total

    def priced_total(t):
        if not priced:
            return None
        return round(t["input"] / 1e6 * p_in + t["output"] / 1e6 * p_out, 6)

    for t in [*per_agent.values(), total]:
        t["cost"] = priced_total(t)
    return {
        "available": True, "since": since.isoformat(), "until": today.isoformat(), "priced": priced,
        "corrupt_lines": bad, "rows": out_rows, "per_agent": per_agent, "total": total,
        "per_day": [{"day": (since + timedelta(days=i)).isoformat(),
                     "agents": per_day.get((since + timedelta(days=i)).isoformat(), {})} for i in range(days)],
    }
