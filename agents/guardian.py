"""Claude's news source (the owner, 2026-10-11): The Guardian Open Platform, as in Lumi (core/news.py).

Two tools for his news call, served in-process to the SDK (`claude_sdk.guardian_server`) so the key never
reaches the model or the CLI:
`search` (the newest articles for an English query, optionally a section, within the last days) and `read` (one
article's text by its content id — never a raw URL). One host, `content.guardianapis.com`; the key comes from
`GUARDIAN_API_KEY` and is never logged; a failure is logged by its type and comes back to the model as an error.
"""

from __future__ import annotations

import html
import json
import logging
import re
import urllib.parse
from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from typing import Any

log = logging.getLogger("agent.guardian")

KEY_VAR = "GUARDIAN_API_KEY"
BASE_URL = "https://content.guardianapis.com"
SERVER = "guardian"
TOOLS = [f"mcp__{SERVER}__search", f"mcp__{SERVER}__read"]  # the names the CLI gives the two tools
MAX_RESULTS = 8
MAX_CHARS = 3000
_ID_RE = re.compile(r"^[a-z0-9-]+(?:/[a-z0-9-]+)+$")
_TAG_RE = re.compile(r"<[^>]+>")

Fetch = Callable[[str], Awaitable[dict]]


def plain(text: str | None) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG_RE.sub(" ", text or ""))).strip()


def search_url(key: str, query: str, section: str | None, days: int, today: date, cap: int = MAX_RESULTS,
               base: str = BASE_URL) -> str:
    params = {
        "q": query.strip(),
        "order-by": "newest",
        "from-date": (today - timedelta(days=max(1, min(days, 14)))).isoformat(),
        "show-fields": "trailText",
        "page-size": str(max(1, min(cap, MAX_RESULTS))),
        "api-key": key,
    }
    if section and re.fullmatch(r"[a-z-]+", section.strip()):
        params["section"] = section.strip()
    return f"{base}/search?" + urllib.parse.urlencode(params)


def read_url(key: str, content_id: str, base: str = BASE_URL) -> str | None:
    if not _ID_RE.match(content_id or ""):
        return None
    return f"{base}/{content_id}?" + urllib.parse.urlencode({"show-fields": "bodyText,trailText", "api-key": key})


def results(payload: dict) -> list[dict[str, str]]:
    """The search hits as plain data: id, title, url, date, section, trail."""
    out = []
    for r in ((payload or {}).get("response") or {}).get("results") or []:
        if not isinstance(r, dict):
            continue
        out.append({"id": str(r.get("id", "")), "title": plain(r.get("webTitle")), "url": str(r.get("webUrl", "")),
                    "date": str(r.get("webPublicationDate", ""))[:10], "section": str(r.get("sectionName", "")),
                    "trail": plain((r.get("fields") or {}).get("trailText"))})
    return out


def article(payload: dict, max_chars: int = MAX_CHARS) -> dict[str, str] | None:
    c = ((payload or {}).get("response") or {}).get("content")
    if not isinstance(c, dict):
        return None
    fields = c.get("fields") or {}
    body = plain(fields.get("bodyText"))
    return {"title": plain(c.get("webTitle")), "url": str(c.get("webUrl", "")),
            "date": str(c.get("webPublicationDate", ""))[:10], "text": body[:max_chars]}


async def http_fetch(url: str) -> dict:
    import aiohttp  # matrix-nio's own dependency

    # an error's text carries the URL — and the key: callers log its type only
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session, session.get(url) as resp:
        resp.raise_for_status()
        return await resp.json()


class Guardian:
    """The two tools' handlers over an injectable `fetch` (tests pass canned payloads)."""

    def __init__(self, key: str, *, fetch: Fetch = http_fetch, today: Callable[[], date] = date.today,
                 base: str = BASE_URL) -> None:
        self._key = key
        self._fetch = fetch
        self._today = today
        self._base = base

    async def search(self, args: dict[str, Any]) -> dict[str, Any]:
        query = str(args.get("query") or "").strip()
        if not query:
            return _error("query is empty")
        days = args.get("days") if isinstance(args.get("days"), int) else 3
        url = search_url(self._key, query, args.get("section") if isinstance(args.get("section"), str) else None,
                         days, self._today(), base=self._base)
        try:
            hits = results(await self._fetch(url))
        except Exception as exc:  # noqa: BLE001 — the model reads an error, the log a type, never the key
            log.warning("guardian search failed (%s)", type(exc).__name__)
            return _error("the Guardian did not answer")
        return _text(json.dumps(hits, ensure_ascii=False) if hits else "no articles found")

    async def read(self, args: dict[str, Any]) -> dict[str, Any]:
        url = read_url(self._key, str(args.get("id") or ""), base=self._base)
        if url is None:
            return _error("not a Guardian content id (e.g. world/2026/oct/11/some-title)")
        try:
            item = article(await self._fetch(url))
        except Exception as exc:  # noqa: BLE001
            log.warning("guardian read failed (%s)", type(exc).__name__)
            return _error("the Guardian did not answer")
        return _text(json.dumps(item, ensure_ascii=False)) if item else _error("no such article")


def _text(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def _error(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "is_error": True}


SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "English keywords"},
        "section": {"type": "string", "description": "optional Guardian section id: world, science, technology…"},
        "days": {"type": "integer", "description": "how many days back (1–14, default 3)"},
    },
    "required": ["query"],
}
READ_SCHEMA = {"type": "object", "properties": {"id": {"type": "string", "description": "a result's id"}},
               "required": ["id"]}

