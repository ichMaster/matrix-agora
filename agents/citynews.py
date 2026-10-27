"""Lviv's news (v5.11; the owner, 2026-10-26) — Zaxid.net's feed, woven into a person's life rarely.

The feed (`https://zaxid.net/rss/all.xml`, no key) holds the latest ~50 items, about eight hours, so the day's items
are gathered by a fetch at most every three hours, merged by link and kept in `state/<name>.citynews.json` (the day,
the last fetch and the items — public news, no room text). At each hourly tick of her events the items not yet rolled
are rolled at `CITY_NEWS_P` (an item naming Lviv at five times that), at most one woven an hour and `CITY_NEWS_MAX`
a day; a woven item touches her life in one of five ways (`WAYS`) and becomes her event. Most news passes her by.
A real person stays real and a real tragedy never gets a victim from her life (`NEWS_RULES`). A failed fetch means
no news until the next try, never a blocked event roll. Pure but for the HTTP call and the file I/O; v5.12 reads the
same feed with the full text.
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
import os
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

log = logging.getLogger("agent.citynews")

FEED_URL = "https://zaxid.net/rss/all.xml"
REFRESH_MS = 3 * 3600 * 1000      # the feed covers ~8 hours: three fetches gather a day
RETRY_MS = 3600 * 1000            # a failed fetch is tried again in an hour
MAX_BYTES = 2_000_000
SUMMARY_MAX = 300
LVIV_RE = re.compile(r"(?<!\w)(?:льв[іо]в\w*|lviv\w*)", re.IGNORECASE)  # Львів, у Львові, львівський
LVIV_BOOST = 5
DC_DATE = "{http://purl.org/dc/elements/1.1/}date"
# how a woven item touches her life — the owner, 2026-10-26
WAYS = {
    "there": "ти була там чи поруч, на власні очі",
    "heard": "ти почула про це від когось із твоїх людей",
    "work": "це зачепило твою роботу",
    "people": "це зачепило когось із твоїх людей",
    "plans": "це змінило твої плани на день",
}
NEWS_RULES = (
    "Люди з новини — справжні й чужі тобі: ніхто з них не стає твоїм знайомим, другом чи родичем. Якщо це трагедія, "
    "ніхто з твого життя не стає її жертвою: ти можеш відчути її наслідки (тривожна ніч, перекрита вулиця, "
    "скасований концерт), але не привласнюй чужої втрати."
)


@dataclass(frozen=True)
class Item:
    title: str
    link: str
    summary: str
    published: str        # ISO 8601, UTC


def _clean(text: str | None) -> str:
    """The feed's description is escaped HTML in a broken CDATA wrapper: unescaped, untagged, one line."""
    text = html.unescape(text or "")
    text = text.replace("[CDATA[", "").replace("]]>", "").replace("]]", "")
    text = re.sub(r"<[^>]*>", " ", text)
    return " ".join(text.split())


def _published(item: ET.Element) -> datetime | None:
    raw = (item.findtext(DC_DATE) or "").strip()
    try:
        if raw:
            when = datetime.fromisoformat(raw)
        else:
            when = parsedate_to_datetime((item.findtext("pubDate") or "").strip())
    except (ValueError, TypeError):
        return None
    return when.astimezone(UTC) if when.tzinfo else None


def parse_feed(xml: str) -> list[Item]:
    """The feed's items with a title, an https link and a time; a document with a DOCTYPE or an entity is refused
    (ValueError), a broken one too."""
    if re.search(r"<!(?:DOCTYPE|ENTITY)", xml or "", re.IGNORECASE):
        raise ValueError("a feed with a DOCTYPE or an entity is refused")
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise ValueError("not a feed") from exc
    items = []
    for node in root.iter("item"):
        title = _clean(node.findtext("title"))
        link = (node.findtext("link") or "").strip()
        when = _published(node)
        if not title or not link.startswith("https://") or any(c.isspace() for c in link) or when is None:
            continue
        summary = _clean(node.findtext("description"))
        summary = "" if summary == title else summary[:SUMMARY_MAX]
        items.append(Item(title, link, summary, when.isoformat()))
    return items


def day_items(items: list[Item], day: date, tz: str) -> list[Item]:
    """The items published on the local `day`, oldest first, one per link."""
    zone = ZoneInfo(tz)
    seen, out = set(), []
    for it in sorted(items, key=lambda i: i.published):
        if it.link not in seen and datetime.fromisoformat(it.published).astimezone(zone).date() == day:
            seen.add(it.link)
            out.append(it)
    return out


def roll_news(items: list[Item], rolled: frozenset[str] | set[str], woven_today: int, p: float, cap: int,
              now: datetime, rng: Callable[[], float]) -> tuple[list[str], Item | None]:
    """One hourly tick: each item published by `now` and not rolled yet is rolled once, oldest first, until a hit —
    at most one an hour, none past the day's cap. Returns the links rolled now and the hit (or None)."""
    if woven_today >= cap or p <= 0:
        return [], None
    done = []
    for it in items:
        if it.link in rolled or datetime.fromisoformat(it.published) > now:
            continue
        done.append(it.link)
        chance = min(1.0, p * LVIV_BOOST) if LVIV_RE.search(f"{it.title} {it.summary}") else p
        if rng() < chance:
            return done, it
    return done, None


def pick_way(rng: Callable[[], float]) -> str:
    ways = list(WAYS)
    return ways[min(int(rng() * len(ways)), len(ways) - 1)]


def news_ask(item: Item, way: str) -> str:
    """The event call's ask for a woven item, in place of a kind."""
    about = f"«{item.title}»" + (f" — {item.summary}" if item.summary else "")
    return (f"Сьогодні в новинах (ZAXID.NET): {about}. Ця новина торкнулася твого життя так: {WAYS[way]}. "
            f"{NEWS_RULES}")


async def http_text(url: str = FEED_URL) -> str:
    """One GET with a 10 s timeout, at most MAX_BYTES."""
    import urllib.request

    def get() -> str:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (matrix-agora)"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read(MAX_BYTES).decode("utf-8", errors="replace")

    return await asyncio.to_thread(get)


async def fetch_citynews(fetch: Callable = http_text) -> list[Item]:
    """The feed's items; any failure raises — the caller logs its type and keeps the day's items it has."""
    return parse_feed(await fetch(FEED_URL))


def load(path: Path) -> tuple[str | None, int, list[Item]]:
    """(day, fetched_ms, items) from the file; (None, 0, []) when missing or corrupt."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        items = [Item(**{k: str(i[k]) for k in ("title", "link", "summary", "published")}) for i in data["items"]]
        return str(data["day"]), int(data["fetched_ms"]), items
    except (OSError, ValueError, KeyError, TypeError):
        return None, 0, []


def save(path: Path, day: str, fetched_ms: int, items: list[Item]) -> None:
    """Atomic, private from birth (0600); a failure is logged by its type."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            data = {"day": day, "fetched_ms": fetched_ms, "items": [asdict(i) for i in items]}
            os.write(fd, json.dumps(data, ensure_ascii=False).encode("utf-8"))
        finally:
            os.close(fd)
        os.replace(tmp, path)
    except OSError as exc:
        log.error("citynews not saved (%s)", type(exc).__name__)
