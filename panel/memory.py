"""The agents' recorded life, read-only (v3.3): summary, day memories, digests, plans, today, tokens.

Paths are built only from a registry agent name and fixed patterns. A missing file is "not written yet";
an unreadable state/ is {"available": false} — never a 500. Plans' hidden mutation tags never leave this
module raw: they become `deviation: true` for the owner's eyes only.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from agents.emotion import TAG_MODELS
from agents.emotion import TAG_RE as VOICE_TAG_RE
from agents.facts import load_facts
from agents.usage import Row, aggregate, cost, month_chars, parse_lines, parse_model_prices

DAYS_SHOWN = 60
log = logging.getLogger("panel.memory")
_WARNED: set[str] = set()  # the malformed PRICE_MODELS entries already named in the log
ITEM_RE = re.compile(r"^\s*(?:[-•*]|\d+[.)])\s+(.*\S)\s*$")
TAG_RE = re.compile(r"\s*<!--.*?-->")
MUTATION_RE = re.compile(r"<!--\s*mutation:")
# the hour it was built for; from v5.11 with the day's event count (` e2`) when events fell (review #1)
TODAY_TAG = re.compile(r"^<!--\s*(\d{4}-\d{2}-\d{2})T(\d{2})(?:\s+e\d+)?\s*-->\s*")
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


def weather_view(state_dir: Path, name: str, today: date) -> dict | None:
    """v5.10 — a person's day of Lviv weather from `<name>.weather.json`: today's line, or None (another day, not
    fetched yet, unreadable — never a 500)."""
    from agents.weather import load_weather
    line = load_weather(state_dir / f"{name}.weather.json", today.isoformat())
    return {"date": today.isoformat(), "line": line} if line else None


def events_view(state_dir: Path, name: str, today: date, days: int = 7) -> list[dict] | None:
    """v5.11 — her events of the last `days` days from `<name>.events/`, newest day first, each event's time, kind,
    source, text and (for news) link; an empty day is left out. None when the folder is unreadable — never a 500."""
    from agents.events import parse_day
    folder = state_dir / f"{name}.events"
    if not folder.exists():
        return []
    if not folder.is_dir():
        return None
    out = []
    for back in range(days):
        day = today - timedelta(days=back)
        events = parse_day(_read(folder / f"{day.isoformat()}.md")).events
        if events:
            out.append({"date": day.isoformat(), "events": [
                {"time": e.time, "kind": e.kind, "source": e.source, "text": e.text, "link": e.link} for e in events]})
    return out


def thoughts_view(state_dir: Path, name: str, today: date, days: int = 7) -> list[dict] | None:
    """v5.12 — her thoughts of the last `days` days from `<name>.thoughts/`, newest day first, each thought's time,
    kind, place, source, title, text and (for news) link; an empty day is left out. None when the folder is unreadable
    — never a 500."""
    from agents.thoughts import parse_day
    folder = state_dir / f"{name}.thoughts"
    if not folder.exists():
        return []
    if not folder.is_dir():
        return None
    out = []
    for back in range(days):
        day = today - timedelta(days=back)
        thoughts = parse_day(_read(folder / f"{day.isoformat()}.md"))
        if thoughts:
            out.append({"date": day.isoformat(), "thoughts": [
                {"time": t.time, "kind": t.kind, "place": t.place, "source": t.source, "title": t.title,
                 "text": t.text, "link": t.link} for t in thoughts]})
    return out


def pastlife_view(theses: Path | None) -> dict | None:
    """v4.3 — how many past-life theses the agent holds; None without the file or when it does not parse."""
    from agents.pastlife import ThesesError, parse_theses
    text = _read(theses) if theses else None
    if not text:
        return None
    try:
        return {"theses": len(parse_theses(text))}
    except ThesesError:
        return None


def nudge_view(state_dir: Path, name: str, today: date, tz: str | None = None, kind: str = "nudge") -> dict | None:
    """v4.3 — the cat's initiative from `<name>.nudge.json` (times and a count, no texts): the last nudge sent and
    today's count. No file yet → none sent; an unreadable file → None, never a 500."""
    try:
        data = json.loads((state_dir / f"{name}.{kind}.json").read_text(encoding="utf-8"))  # v4.5: or .news
        sent = data.get("sent_ms")
        last = (datetime.fromtimestamp(int(sent) / 1000, ZoneInfo(tz or os.environ.get("TIMEZONE", "Europe/Kyiv")))
                .isoformat(timespec="seconds") if sent is not None else None)
        count = int(data["count"]) if str(data["day"]) == today.isoformat() else 0
    except FileNotFoundError:
        return {"last": None, "today": 0}
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError):
        return None
    return {"last": last, "today": count}


RATELIMIT_FIELDS = ("status", "utilization", "resets_at", "rate_limit_type", "muted_until", "auth", "model",
                    "last_error", "updated_at")


def ratelimit_view(state_dir: Path, name: str) -> dict | None:
    """v4.4 — Claude's last limit event and auth check from `<name>.ratelimit.json` (times and words, no texts, no
    token). Missing or unreadable → None, never a 500."""
    try:
        data = json.loads((state_dir / f"{name}.ratelimit.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return {k: data.get(k) if isinstance(data.get(k), str | int | float) or data.get(k) is None else None
            for k in RATELIMIT_FIELDS}


def _usage_records(path: Path) -> list[dict]:
    try:
        return parse_lines(path.read_text(encoding="utf-8").splitlines())[0]
    except FileNotFoundError:
        return []


def digest_view(state_dir: Path, name: str, today: date, tz: str | None = None) -> dict | None:
    """v5.1 — Hermes's digests: the last one sent and today's count (`<name>.digest.json`), this month's spoken
    characters (his usage file), the cap and whether a voice id is set (`<name>.settings.json` — a boolean, never
    the id). No texts. No file yet → none sent; anything unreadable → None, never a 500."""
    try:
        data = json.loads((state_dir / f"{name}.digest.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        data = {}
    except (OSError, ValueError):
        return None
    try:
        sent = data.get("last_ms")
        last = (datetime.fromtimestamp(int(sent) / 1000, ZoneInfo(tz or os.environ.get("TIMEZONE", "Europe/Kyiv")))
                .isoformat(timespec="seconds") if sent is not None else None)
        count = int(data.get("count") or 0) if str(data.get("day")) == today.isoformat() else 0
        spoken = month_chars(_usage_records(state_dir / f"{name}.usage.jsonl"), name, today.strftime("%Y-%m"))
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return None
    cap, voice = None, None
    try:
        runs = json.loads((state_dir / f"{name}.settings.json").read_text(encoding="utf-8"))
        cap = int(runs["HERMES_TTS_MONTHLY_CHARS"]["value"])
        voice = bool(str(runs["HERMES_VOICE_ID"]["value"]).strip())
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass  # not started yet, or an older file: the card shows what it knows
    return {"last": last, "today": count, "month_chars": spoken, "cap": cap, "voice": voice}


def facts_view(state_dir: Path, name: str) -> list[dict] | None:
    """v5.8 — a person's facts about the owner (`<name>.facts/`): pin 1 first, then 2, then 0, oldest first; an
    unreadable folder is None, never a 500."""
    try:
        facts = load_facts(state_dir / f"{name}.facts")
    except Exception:  # noqa: BLE001
        return None
    order = {1: 0, 2: 1, 0: 2}
    return [{"id": f.id, "pin": f.pin, "source": f.source, "added": f.added, "text": f.text}
            for f in sorted(facts, key=lambda f: (order[f.pin], f.added, f.id))]


def archive_view(state_dir: Path, name: str) -> dict | None:
    """v5.8 — the archive's size (`<name>.archive.db`, opened read-only): lines and how many are embedded. No file
    yet is zero; an unreadable one is None, never a 500."""
    path = state_dir / f"{name}.archive.db"
    if not path.exists():
        return {"lines": 0, "embedded": 0}
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            lines, embedded = con.execute("SELECT COUNT(*), COUNT(emb) FROM lines").fetchone()
            marks: dict = {}
            if "mark" in {r[1] for r in con.execute("PRAGMA table_info(lines)")}:  # v5.13: an older one has none
                marks = dict(con.execute("SELECT mark, COUNT(*) FROM lines GROUP BY mark").fetchall())
        finally:
            con.close()
    except sqlite3.Error:
        return None
    return {"lines": int(lines), "embedded": int(embedded),  # v5.14: the lines closed to Gemini, by mark
            "waiting": int(marks.get("waiting", 0)), "censored": int(marks.get("censored", 0))}


def route_view(state_dir: Path, name: str, today: date, now_ms: int | None = None) -> dict | None:
    """v5.14 — her private answer's route (`<name>.route.json`, `agents/route.py`): the pin, the window's end (ISO, or
    null) and whether it is still open at `now_ms` (the file keeps an ended one until Gemini answers again — review
    #3), today's blocks, today's answers by Gemini and by the backup, and (v5.15) today's lines the judge rated and
    flagged. No file yet → auto, nothing open;
    unreadable → None, never a 500. No text is in it."""
    from agents.route import load_route

    path = state_dir / f"{name}.route.json"
    try:
        if path.exists():
            json.loads(path.read_text(encoding="utf-8"))  # a corrupt file is "unreadable" here, `auto` for her
        route = load_route(path)
        tz = ZoneInfo(os.environ.get("TIMEZONE", "Europe/Kyiv"))
        start = int(datetime(today.year, today.month, today.day, tzinfo=tz).timestamp() * 1000)
    except (OSError, ValueError):
        return None
    window = (datetime.fromtimestamp(route.window_until_ms / 1000, tz).isoformat(timespec="minutes")
              if route.window_until_ms is not None else None)
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    answers = route.answers if route.day == today.isoformat() else {"gemini": 0, "backup": 0}
    judged = route.judged if route.day == today.isoformat() else {"rated": 0, "flagged": 0}  # v5.15: the judge
    return {"pin": route.pin, "window_until": window,
            "window_open": route.window_until_ms is not None and now_ms < route.window_until_ms,
            "blocks_today": sum(1 for t in route.blocks if t >= start),
            "answers": {"gemini": int(answers.get("gemini", 0)), "backup": int(answers.get("backup", 0))},
            "judged": {"rated": int(judged.get("rated", 0)), "flagged": int(judged.get("flagged", 0))}}


def models_view(state_dir: Path, name: str, voice_spec: Path | None = None) -> dict | None:
    """v5.9 (AGORA-121) — what a Gemini speaker runs on, from what it wrote at its start (`<name>.settings.json`):
    the answers' and the background model, the thinking level, the voice's model and settings, and with a palette
    (`emotion`) its tags and whether the voice performs them. Never the voice id or the palette's text; unreadable is
    None, never a 500."""
    try:
        data = json.loads((state_dir / f"{name}.settings.json").read_text(encoding="utf-8"))
        value = {k: str(v.get("value", "")) for k, v in data.items() if isinstance(v, dict)}
    except (OSError, ValueError, AttributeError):
        return None
    background = value.get("GEMINI_MODEL") or "gemini-2.5-flash"
    answers = value.get("GEMINI_REPLY_MODEL") or background
    view = {"answers": answers, "background": background,
            "thinking": value.get("GEMINI_THINKING_LEVEL") if answers != background or answers.startswith("gemini-3")
            else None,
            "voice": None, "emotion": None}
    if "ELEVENLABS_MODEL" in value or "VOICE_STABILITY" in value:
        model = value.get("ELEVENLABS_MODEL") or "eleven_turbo_v2_5"
        view["voice"] = {"model": model, "stability": value.get("VOICE_STABILITY") or "0.5",
                         "speed": value.get("VOICE_SPEED") or "1.0"}
        if voice_spec is not None:
            try:
                tags = list(dict.fromkeys(f"[{t}]" for t in VOICE_TAG_RE.findall(voice_spec.read_text(encoding="utf-8"))))
            except (OSError, ValueError):  # v5.9 review #6: not UTF-8 is no chips, never a 500
                tags = []
            view["emotion"] = {"tags": tags, "performed": model in TAG_MODELS}
    return view


def memory_view(state_dir: Path, name: str, today: date, natal: Path | None = None, with_mood: bool = False,
                memories: Path | None = None, with_nudge: bool = False, with_ratelimit: bool = False,
                with_news: bool = False, with_digest: bool = False, with_facts: bool = False,
                with_archive: bool = False, with_models: bool = False, voice_spec: Path | None = None,
                with_events: bool = False, with_thoughts: bool = False, with_route: bool = False) -> dict:
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
        "weather": weather_view(state_dir, name, today) if with_mood else None,         # v5.10: Кіра's Lviv
        "pastlife": pastlife_view(memories),
        "nudge": nudge_view(state_dir, name, today) if with_nudge else None,
        "ratelimit": ratelimit_view(state_dir, name) if with_ratelimit else None,
        "news": nudge_view(state_dir, name, today, kind="news") if with_news else None,  # v4.5: Claude's news
        "digest": digest_view(state_dir, name, today) if with_digest else None,           # v5.1: Hermes
        "facts": facts_view(state_dir, name) if with_facts else None,                    # v5.8: Кіра's facts
        # AGORA-116: «Update now» pressed and not yet done by her
        "facts_pending": (state_dir / f"{name}.facts.request").exists() if with_facts else None,
        "archive": archive_view(state_dir, name) if with_archive else None,              # v5.8: her archive
        "models": models_view(state_dir, name, voice_spec) if with_models else None,     # v5.9: models, voice
        "events": events_view(state_dir, name, today) if with_events else None,          # v5.11: her events
        "thoughts": thoughts_view(state_dir, name, today) if with_thoughts else None,    # v5.12: her thoughts
        "route": route_view(state_dir, name, today) if with_route else None,             # v5.14: her backup
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
    models, bad_prices = parse_model_prices(os.environ.get("PRICE_MODELS"))  # v5.1: Hermes's Pro calls priced as Pro
    for entry in sorted(set(bad_prices) - _WARNED):  # review #12: named once per entry — a price spec, never a secret
        log.warning("PRICE_MODELS entry %r is not model=in/out — ignored", entry)
        _WARNED.add(entry)
    priced = p_in is not None and p_out is not None or bool(models)

    def money(r):  # v4.4: only `api` tokens are priced; a subscription row has no cost, never $0
        c = cost(r, p_in, p_out, models) if priced else None
        return round(c, 6) if c is not None else None

    out_rows, per_agent, per_day, agent_rows = [], {}, {}, {}
    total_row = Row()
    total = {"calls": 0, "failed": 0, "input": 0, "output": 0, "total": 0, "characters": 0, "blocked": 0}
    for (day, ag, kind), r in rows.items():
        out_rows.append({"day": day, "agent": ag, "kind": kind, "calls": r.calls, "failed": r.failed,
                         "input": r.prompt, "output": r.output, "total": r.total, "cost": money(r),
                         "engine": r.engine or "gemini", "billing": r.billing or "api", "characters": r.characters,
                         "blocked": r.blocked})
        agent_rows.setdefault(ag, Row()).add(r)
        total_row.add(r)
        for acc in (per_agent.setdefault(ag, dict.fromkeys(total, 0)), total):
            acc["calls"] += r.calls
            acc["failed"] += r.failed
            acc["input"] += r.prompt
            acc["output"] += r.output
            acc["total"] += r.total
            acc["characters"] += r.characters  # v5.1: text to speech
            acc["blocked"] += r.blocked  # v5.13: Gemini's safety blocks
        per_day.setdefault(day, {}).setdefault(ag, 0)
        per_day[day][ag] += r.total

    blocked_today: dict[str, int] = {}  # v5.13: the card's «Blocks today», from the rows already read
    for (day, ag, _), r in rows.items():
        if day == today.isoformat():
            blocked_today[ag] = blocked_today.get(ag, 0) + r.blocked
    for ag, t in per_agent.items():
        t.update(cost=money(agent_rows[ag]), engine=agent_rows[ag].engine or "gemini",
                 billing=agent_rows[ag].billing or "api", blocked_today=blocked_today.get(ag, 0))
    total["cost"] = money(total_row)
    return {
        "available": True, "since": since.isoformat(), "until": today.isoformat(), "priced": priced,
        "default_priced": p_in is not None and p_out is not None,  # v5.1 review #5: the room's own models
        "corrupt_lines": bad, "rows": out_rows, "per_agent": per_agent, "total": total,
        "per_day": [{"day": (since + timedelta(days=i)).isoformat(),
                     "agents": per_day.get((since + timedelta(days=i)).isoformat(), {})} for i in range(days)],
    }
