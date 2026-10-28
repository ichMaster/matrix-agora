"""v5.12 — what Кіра reads (ROADMAP §v5.12; features/voice-emotion.md §Reading and thoughts).

Two sources, each item one shape (`Item`):
- **Zaxid.net**, Lviv's outlet: the day's items come from v5.11's feed (`state/<name>.citynews.json`, refreshed by
  her events), and the full text of an item she picks is the article page's JSON-LD `articleBody` — no HTML is
  scraped, and only an https link on zaxid.net is ever fetched;
- **The Guardian**, so she may pick what Claude did not: the newest items of the sections of her interests
  (`READING_SECTIONS`) through `agents/guardian.py`'s helpers, with her own `GUARDIAN_API_KEY`. Without the key
  the Guardian is skipped, logged once. She keeps no state with Claude and never reads his.

`state/<name>.reading.json` keeps the items she has seen (ids and times, never a text), so nothing is read twice, and
the times of her last reading and of her last reflection on each place. A failure is logged by its type only (a
Guardian URL carries the key). Pure but for the HTTP calls (`Sources`, injectable) and the file I/O.
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.parse
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from agents import citynews
from agents.citynews import http_text
from agents.guardian import MAX_RESULTS, article, http_fetch, plain, read_url, results, search_url, section_ok

log = logging.getLogger("agent.reading")

ARTICLE_MAX_CHARS = 4000                 # the full text a thought is built on: the gist of an article, not a book
SEEN_KEEP_MS = 7 * 24 * 3600 * 1000      # a seen id is forgotten after a week: the feeds never go back that far
DEFAULT_SECTIONS = "science,world,environment,technology,culture"
_LD_RE = re.compile(r"<script[^>]*type\s*=\s*[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", re.DOTALL | re.IGNORECASE)


@dataclass(frozen=True)
class Item:
    source: str           # zaxid | guardian
    id: str               # the link (Zaxid.net) or the content id (the Guardian)
    title: str
    summary: str          # the feed's description or the Guardian's trail text
    link: str             # https
    published: str        # ISO 8601 (a date for the Guardian)


def _bodies(node) -> Iterable[str]:
    """Every string `articleBody` in a JSON-LD value: an object, a list of them, or an `@graph`."""
    if isinstance(node, dict):
        body = node.get("articleBody")
        if isinstance(body, str):
            yield body
        for key in ("@graph", "mainEntity"):
            yield from _bodies(node.get(key))
    elif isinstance(node, list):
        for x in node:
            yield from _bodies(x)


def article_body(page: str | None) -> str | None:
    """The article's text from its page's JSON-LD (`articleBody`), one line, cut at `ARTICLE_MAX_CHARS`; None when
    no block holds one. A block that does not parse is skipped."""
    for raw in _LD_RE.findall(page or ""):
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        for body in _bodies(data):
            text = plain(body)
            if text:
                return text[:ARTICLE_MAX_CHARS]
    return None


def zaxid_link_ok(link: str) -> bool:
    """Only an https page on zaxid.net is fetched for its full text."""
    try:
        url = urllib.parse.urlsplit(link or "")
    except ValueError:
        return False
    host = (url.hostname or "").lower()
    return url.scheme == "https" and (host == "zaxid.net" or host.endswith(".zaxid.net"))


def from_citynews(items: Iterable[citynews.Item]) -> list[Item]:
    """v5.11's kept feed items, as hers to read."""
    return [Item("zaxid", i.link, i.title, i.summary, i.link, i.published) for i in items]


def guardian_items(hits: Iterable[dict]) -> list[Item]:
    """The Guardian's search hits with an id and an https link."""
    out = []
    for h in hits:
        cid, url = h.get("id", ""), h.get("url", "")
        if cid and h.get("title") and url.startswith("https://"):
            out.append(Item("guardian", cid, h["title"], h.get("trail", ""), url, h.get("date", "")))
    return out


def parse_sections(raw: str | None) -> list[str]:
    """`READING_SECTIONS`: comma-separated section ids; a malformed one is dropped."""
    out = []
    for s in (raw if raw is not None else DEFAULT_SECTIONS).split(","):
        s = s.strip()
        if section_ok(s) and s not in out:
            out.append(s)
    return out


def fresh(items: Iterable[Item], seen: dict[str, int]) -> list[Item]:
    """The items she has not seen, one per id, in their order."""
    out, ids = [], set()
    for it in items:
        if it.id not in seen and it.id not in ids:
            ids.add(it.id)
            out.append(it)
    return out


class Sources:
    """The two sources' network side over injectable fetches (tests pass canned ones; the defaults are looked up at
    call time, so the test fixture's guard catches a test that forgot to)."""

    def __init__(self, key: str, *, fetch_json: Callable[[str], Awaitable[dict]] | None = None,
                 fetch_text: Callable[[str], Awaitable[str]] | None = None) -> None:
        self._key = key or ""
        self._fetch_json = fetch_json
        self._fetch_text = fetch_text
        self._warned = False

    async def _json(self, url: str) -> dict:
        return await (self._fetch_json or http_fetch)(url)

    async def _text(self, url: str) -> str:
        return await (self._fetch_text or http_text)(url)

    async def guardian(self, sections: list[str], today: date) -> list[Item]:
        """The newest items of each section from the last day, one per id; no key → none, logged once."""
        if not self._key:
            if not self._warned:
                log.info("reading: no GUARDIAN_API_KEY — the Guardian is skipped")
                self._warned = True
            return []
        out: list[Item] = []
        for section in sections:
            try:
                hits = results(await self._json(search_url(self._key, "", section, 1, today, MAX_RESULTS)))
            except Exception as exc:  # noqa: BLE001 — the URL carries the key: its type only
                log.warning("reading: the Guardian's %s did not answer (%s)", section, type(exc).__name__)
                continue
            out.extend(guardian_items(hits))
        return fresh(out, {})

    async def full_text(self, item: Item) -> str | None:
        """The text of an item she picked, or None (a page with no body, a refused link, a failure)."""
        try:
            if item.source == "zaxid":
                return article_body(await self._text(item.link)) if zaxid_link_ok(item.link) else None
            if item.source == "guardian" and self._key:
                url = read_url(self._key, item.id)
                art = article(await self._json(url), ARTICLE_MAX_CHARS) if url else None
                return (art or {}).get("text") or None
        except Exception as exc:  # noqa: BLE001
            log.warning("reading: the %s article was not read (%s)", item.source, type(exc).__name__)
        return None


@dataclass
class ReadingState:
    seen: dict[str, int] = field(default_factory=dict)        # id → when she saw it (ms)
    last_reading_ms: int = 0
    reflected: dict[str, int] = field(default_factory=dict)   # place → the last line's time she reflected on (ms)


def load_state(path: Path) -> ReadingState:
    """The kept state; a missing or corrupt file is a fresh start."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return ReadingState({str(k): int(v) for k, v in dict(data.get("seen") or {}).items()},
                            int(data.get("last_reading_ms") or 0),
                            {str(k): int(v) for k, v in dict(data.get("reflected") or {}).items()})
    except (OSError, ValueError, TypeError, AttributeError):
        return ReadingState()


def save_state(path: Path, state: ReadingState, now_ms: int) -> None:
    """Atomic, private from birth (0600); the ids seen over a week ago are dropped. A failure is logged by its type."""
    state.seen = {k: v for k, v in state.seen.items() if now_ms - v < SEEN_KEEP_MS}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            data = {"seen": state.seen, "last_reading_ms": state.last_reading_ms, "reflected": state.reflected}
            os.write(fd, json.dumps(data).encode("utf-8"))
        finally:
            os.close(fd)
        os.replace(tmp, path)
    except OSError as exc:
        log.error("reading: the state was not saved (%s)", type(exc).__name__)


# --- the reading and the reflection: the schedule and the three requests (pure) -------------------------------
SHOWN_PER_SOURCE = 20       # the freshest a reading shows of each source: a screen of titles, not the whole day
REFLECT_LINES = 40          # the most a reflection reads of a place's new lines
PICK_MAX_TOKENS = 20
THOUGHT_MAX_TOKENS = 220
REFLECTION_MAX_TOKENS = 320
SOURCE_LABEL = {"zaxid": "ZAXID.NET", "guardian": "The Guardian"}
_PICKS_RE = re.compile(r"^[\d\s,;.]+$")


def reading_due(now_ms: int, last_ms: int, every_ms: int, in_window: bool) -> bool:
    """A reading in her reading hours, once a period."""
    return in_window and now_ms - last_ms >= every_ms


def reflect_due(now_ms: int, last_ms: int, every_ms: int) -> bool:
    return now_ms - last_ms >= every_ms


def shown(zaxid: list[Item], guardian: list[Item]) -> list[Item]:
    """What a reading shows: the freshest of each source, Lviv's first."""
    return [*zaxid[-SHOWN_PER_SOURCE:], *guardian[:SHOWN_PER_SOURCE]]


def _context(canon: str, mood: str | None, recent: list[str]) -> list[str]:
    parts = [canon]
    if mood:
        parts.append(f"Настрій дня: {mood}")
    if recent:
        parts.append("Що ти останнім часом думала:\n" + "\n".join(f"- {t}" for t in recent))
    return parts


def pick_request(name: str, canon: str, reading: str, mood: str | None, recent: list[str], items: list[Item],
                 cap: int) -> tuple[str, str]:
    """The pick: the fresh titles and descriptions, numbered — which of them she would open, at most `cap`."""
    system = "\n\n".join([*_context(canon, mood, recent), f"Що ти читаєш і як:\n{reading}", (
        f"Ти — {name}. Зараз ти гортаєш новини в телефоні. Нижче — свіжі заголовки, кожен з номером. Вибери "
        f"щонайбільше {cap} з тих, які ти справді відкрила б і прочитала, — те, що тебе зачепить. Якщо нічого не "
        "зачіпає, відповідай 0. Відповідай лише номерами через кому, без жодних слів.")])
    rows = []
    for i, it in enumerate(items, 1):
        about = f" — {it.summary}" if it.summary else ""
        rows.append(f"{i}. [{SOURCE_LABEL.get(it.source, it.source)}] {it.title}{about}")
    return system, "\n".join(rows)


def parse_picks(text: str | None, n: int, cap: int) -> list[int]:
    """The picked items' indexes (0-based), in order, each once, at most `cap`; `0`, garbage or words → none."""
    text = (text or "").strip()
    if not text or not _PICKS_RE.match(text):
        return []
    out: list[int] = []
    for raw in re.findall(r"\d+", text):
        k = int(raw)
        if 1 <= k <= n and k - 1 not in out:
            out.append(k - 1)
    return out[:max(0, cap)]


def thought_request(name: str, canon: str, mood: str | None, recalled: str | None, item: Item,
                    body: str) -> tuple[str, str]:
    """A thought on an item she read: first person, 1–3 sentences, only the article's facts, her own view."""
    parts = _context(canon, mood, [])
    if recalled:
        parts.append(recalled)
    parts.append(
        f"Ти — {name}. Ти щойно прочитала в телефоні статтю ({SOURCE_LABEL.get(item.source, item.source)}). "
        "Напиши, що ти про неї думаєш, — для себе, від першої особи, одне-три речення, українською. Спирайся лише "
        "на факти зі статті: не вигадуй чисел, цитат чи імен, яких у ній немає. Погляд і почуття — твої. Люди з "
        "новин тобі незнайомі. Ти це прочитала, а не шукала. Якщо колись ти думала про це інакше, можеш передумати "
        "— скажи як є. Не вигадуй, що хтось із твоїх знайомих чи з Агори щось сказав або зробив. Без лапок і без "
        "заголовка.")
    return "\n\n".join(parts), f"Заголовок: {item.title}\n\n{body}"


def reflection_request(name: str, canon: str, mood: str | None, recent: list[str], place: str,
                       lines: list[tuple[str, str]]) -> tuple[str, str]:
    """A reflection on a talk: one or two thoughts of hers, never anyone's invented words or deeds."""
    where = "з Ich наодинці, в окремій розмові" if place == "private" else "в Агорі"
    system = "\n\n".join([*_context(canon, mood, recent), (
        f"Ти — {name}. Нижче — останні рядки твоєї розмови {where}. Подумай про неї сама з собою: що тобі "
        "запам'яталося, що ти думаєш про сказане, що сказала б наступного разу. Напиши одну або дві думки від "
        "першої особи, кожну з нового рядка, одне-два речення кожна, українською. Нічого не вигадуй: ні слів, ні "
        "вчинків Ich чи інших — лише те, що є в рядках; твої почуття й думки — твої. Це не повідомлення, його "
        "ніхто не побачить.")])
    return system, "\n".join(f"{who}: {text}" for who, text in lines)


def split_reflection(text: str | None) -> list[str]:
    """At most two thoughts, a line each (a list's marks dropped)."""
    out = []
    for raw in (text or "").splitlines():
        t = " ".join(re.sub(r"^\s*(?:[-–—•*]|\d+[.)])\s*", "", raw).split())
        if t:
            out.append(t)
    return out[:2]
