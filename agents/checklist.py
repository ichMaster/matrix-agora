"""v9.2 (AGORA-282) — her checklist: what she and the owner arranged and what she means to do herself, and what came
of it (ROADMAP §v9.2, ARCHITECTURE §Memory).

The owner, 2026-11-18: «має бути чекліст що вже виконалось а що ні»; «щоб вона могла щось спланувати сама … це буде
як правило в ході розмов зі мною. І щоб вона могла позначити це виконано чи ні, бо зараз вона читає це в переписці і
думає що подія виконана хоча такого не було».

`state/<name>.checklist.jsonl` is an append-only log, one JSON object a line, 0600:
- `{"ts", "op": "add", "id", "what", "who", "ich", "due", "made_ms", "from", "by"[, "plan_day"]}` — an item: its
  number, what, with whom, whether it concerns Ich, when it is due (`YYYY-MM-DD` or `YYYY-MM-DDTHH:MM`, or null),
  when it was made, the archive key of his line it came from (or null), and who wrote it (`her` | `plan` | `owner`);
- `{"ts", "op": "mark", "id", "status", "due", "by"}` — a later status: `done`, `missed`, `cancelled` or `moved`
  (with its new time).

Nothing in it is ever rewritten: the list is folded from it. Pure but for the two small file helpers; the clock is
given. The words are a person's — never a tool's, a function's or a model's.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from pathlib import Path

from agents.plans import ITEM_RE, TAG_RE
from agents.world import stamp

STATUSES = ("done", "missed", "cancelled", "moved")
BYS = ("her", "plan", "owner")
WORDS = {"planned": "заплановано", "overdue": "час минув — не знаєш, чи це було", "moved": "перенесено",
         "done": "зроблено", "missed": "не відбулося", "cancelled": "скасовано"}
# her own words for a status (`plan_mark`'s enum), and the panel's
HER_STATUS = {"зроблено": "done", "не вийшло": "missed", "скасовано": "cancelled", "перенесено": "moved"}
PLAN_STATUS = {"postponed": "moved", "cancelled": "cancelled"}  # a day plan's hidden tag → its outcome; else done
DUE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2})?$")
TITLE = "Твої справи і домовленості (що з цього було, а що ні, — ти знаєш лише звідси):"
FROM_PLAN = "з твого плану на день"


@dataclass(frozen=True)
class Item:
    id: int
    what: str
    who: str = ""
    ich: bool = False
    due: str | None = None       # "YYYY-MM-DD" | "YYYY-MM-DDTHH:MM" | None
    made_ms: int = 0
    by: str = "her"
    plan_day: str | None = None
    status: str = "planned"      # planned | done | missed | cancelled | moved
    marked_ms: int | None = None  # when its last status came


# --- the file (the only I/O here) ----------------------------------------------------------------------------------
def load(path: Path) -> tuple[list[dict], int]:
    """The log's entries in order and how many lines were corrupt (skipped); none when there is no file."""
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [], 0
    entries, corrupt = [], 0
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            corrupt += 1
            continue
        if isinstance(entry, dict) and entry.get("op") in ("add", "mark") and isinstance(entry.get("id"), int):
            entries.append(entry)
        else:
            corrupt += 1
    return entries, corrupt


def append(path: Path, entries: list[dict]) -> None:
    """Appends whole lines, the file private from birth (0600); never rewrites one."""
    if not entries:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(fd, "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries).encode("utf-8"))
    finally:
        os.close(fd)


# --- the entries -----------------------------------------------------------------------------------------------------
def _ms(ts: str) -> int | None:
    try:
        return int(datetime.fromisoformat(ts).timestamp() * 1000)
    except (TypeError, ValueError):
        return None


def next_id(entries: list[dict]) -> int:
    return max((e["id"] for e in entries if e.get("op") == "add"), default=0) + 1


def add_entry(item_id: int, what: str, now: datetime, who: str = "", ich: bool = False, due: str | None = None,
              source: str | None = None, by: str = "her", plan_day: str | None = None) -> dict:
    entry = {"ts": now.isoformat(timespec="seconds"), "op": "add", "id": item_id, "what": " ".join(what.split()),
             "who": " ".join((who or "").split()), "ich": bool(ich), "due": due,
             "made_ms": int(now.timestamp() * 1000), "from": source, "by": by}
    if plan_day:
        entry["plan_day"] = plan_day
    return entry


def mark_entry(item_id: int, status: str, now: datetime, due: str | None = None, by: str = "her") -> dict:
    return {"ts": now.isoformat(timespec="seconds"), "op": "mark", "id": item_id, "status": status, "due": due,
            "by": by}


def fold(entries: list[dict]) -> list[Item]:
    """The list, in the order the items were added: each with its last status and its current due. A mark of an
    unknown number, or with an unknown status, changes nothing."""
    items: dict[int, Item] = {}
    for e in entries:
        if e.get("op") == "add" and e["id"] not in items and str(e.get("what", "")).strip():
            due = e.get("due") if isinstance(e.get("due"), str) and DUE_RE.match(e["due"]) else None
            items[e["id"]] = Item(e["id"], str(e["what"]), str(e.get("who") or ""), bool(e.get("ich")), due,
                                  int(e.get("made_ms") or 0), e.get("by") if e.get("by") in BYS else "her",
                                  e.get("plan_day") if isinstance(e.get("plan_day"), str) else None)
        elif e.get("op") == "mark" and e["id"] in items and e.get("status") in STATUSES:
            item = items[e["id"]]
            due = e.get("due") if isinstance(e.get("due"), str) and DUE_RE.match(e["due"]) else None
            items[e["id"]] = replace(item, status=e["status"], marked_ms=_ms(str(e.get("ts"))),
                                     due=due if e["status"] == "moved" and due else item.due)
    return list(items.values())


def parse_due(day: object, at: object = None) -> str | None:
    """Her `date` («РРРР-ММ-ДД») and `time` («ГГ:ХХ») as a due; anything unreadable — no time at all (None)."""
    try:
        d = date.fromisoformat(str(day).strip()[:10])
    except ValueError:
        return None
    text = str(at or "").strip()
    m = re.match(r"^([01]?\d|2[0-3]):([0-5]\d)$", text)
    return f"{d.isoformat()}T{int(m.group(1)):02d}:{m.group(2)}" if m else d.isoformat()


def due_moment(due: str | None, tz) -> datetime | None:
    """When a due has passed: a timed one at its minute, a day's at that day's end (her next midnight)."""
    if not due:
        return None
    if "T" in due:
        return datetime.fromisoformat(due).replace(tzinfo=tz)
    d = date.fromisoformat(due) + timedelta(days=1)
    return datetime(d.year, d.month, d.day, tzinfo=tz)


def is_open(item: Item) -> bool:
    """Still to come or still unknown: hers or the owner's, planned or moved — a day plan's outcome never is."""
    return item.by != "plan" and item.status in ("planned", "moved")


def state_of(item: Item, now: datetime) -> str:
    """Its status as the prompt names it: an open item whose time has passed with no mark — `overdue`."""
    passed = due_moment(item.due, now.tzinfo)
    if is_open(item) and passed is not None and passed <= now:
        return "overdue"
    return item.status


def mark_problem(items: list[Item], item_id: object, status: str, due: str | None = None) -> str | None:
    """Why a mark cannot be made, in words — or None when it can."""
    if isinstance(item_id, bool) or not isinstance(item_id, int):
        return "Потрібен номер справи зі списку."
    item = next((x for x in items if x.id == item_id), None)
    if item is None:
        return f"Справи №{item_id} у списку немає."
    if status not in STATUSES:
        return "Можна позначити лише: зроблено, не вийшло, скасовано або перенесено."
    if status == "moved" and not due:
        return "Щоб перенести, потрібна нова дата."
    if not is_open(item):
        return f"Справа №{item_id} уже позначена: {WORDS[item.status]}."
    return None


# --- her prompt's section -------------------------------------------------------------------------------------------
def _when(item: Item, now: datetime) -> str:
    if item.due and "T" in item.due:
        return stamp(datetime.fromisoformat(item.due).replace(tzinfo=now.tzinfo), now)
    if item.due:
        d = date.fromisoformat(item.due)
        return stamp(datetime(d.year, d.month, d.day, 12, tzinfo=now.tzinfo), now, fine=False)
    made = datetime.fromtimestamp(item.made_ms / 1000, now.tzinfo)
    return f"без дати, записано {stamp(made, now)}"


def line(item: Item, now: datetime) -> str:
    """«№3 [заплановано] сходити в кіно (з Ich) — завтра (19.11, 19:00)»."""
    who = f" ({FROM_PLAN})" if item.by == "plan" else f" (з {item.who})" if item.who else ""
    return f"№{item.id} [{WORDS[state_of(item, now)]}] {item.what}{who} — {_when(item, now)}"


def section_lines(items: list[Item], now: datetime, private: bool, days: int, cap: int) -> list[str]:
    """The lines her prompt shows (pure): every open item — the soonest due first, one without a time last —, then
    what closed within the last `days` days, the newest first; at most `cap`, the open ones first. In Agora
    (`private` False) never an item that concerns Ich."""
    seen = [x for x in items if private or not x.ich]
    far = datetime.max.replace(tzinfo=now.tzinfo)
    opened = sorted((x for x in seen if is_open(x)), key=lambda x: (due_moment(x.due, now.tzinfo) or far, x.id))
    since = int((now - timedelta(days=max(days, 0))).timestamp() * 1000)
    closed = sorted((x for x in seen if not is_open(x) and (x.marked_ms or x.made_ms) >= since),
                    key=lambda x: (x.marked_ms or x.made_ms, x.id), reverse=True)
    return [line(x, now) for x in (opened + closed)[:max(cap, 0)]]


# --- her life's day plan, once its day has ended -------------------------------------------------------------------
def plan_outcomes(text: str, day: date, first_id: int, now: datetime) -> list[dict]:
    """A past day plan's items with their outcome, from each one's hidden tag (pure): `postponed` — moved,
    `cancelled` — cancelled, any other — done. Two entries an item (its add and its mark), `by` `plan` with its
    `plan_day`; the tag never in the text. Called only once the day has ended: she never learns an outcome ahead."""
    out, n = [], first_id
    for raw in (text or "").splitlines():
        m = ITEM_RE.match(raw)
        if not m:
            continue
        tag = re.search(r"<!--\s*mutation:\s*(\w+)\s*-->", m.group(1))
        what = TAG_RE.sub("", m.group(1)).strip()
        if not what:
            continue
        out.append(add_entry(n, what, now, due=day.isoformat(), by="plan", plan_day=day.isoformat()))
        out.append(mark_entry(n, PLAN_STATUS.get(tag.group(1) if tag else "", "done"), now, by="plan"))
        n += 1
    return out
