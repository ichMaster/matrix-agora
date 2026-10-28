"""Her thoughts (v5.12; the owner, 2026-10-26) — what Кіра thinks of what she reads and of her talks.

One append-only file a day, `state/<name>.thoughts/YYYY-MM-DD.md`. A block is
`## HH:MM · <kind> · <place> · <source>`:
- the kind is `news` (on an item she read) or `reflection` (on a talk);
- the place is `thought`, or `thought_private` for a reflection on the private chat;
- the source is `zaxid`, `guardian`, `private` or `agora`.

A news thought's title and link follow on hidden lines, then the text on one line. Each thought is also a line of
her archive (`agents/archive.py`) under its place, recalled as «… я думала: …», never as something said. A
`thought_private` thought reaches only her private prompt and recall. A text or a title never carries a comment
marker, so a generated text is never read as one. Everything here is pure; the agent owns the clock, the calls and
the files.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from agents.world import PART_ADVERB, part_of_day

KINDS = ("news", "reflection")
PLACES = ("thought", "thought_private")  # the archive's places of her thoughts
SOURCES = ("zaxid", "guardian", "private", "agora")

THOUGHTS_TITLE = "Що ти сьогодні думала (це твої думки, а не сказане вголос):"
_BLOCK_RE = re.compile(r"^## (\d{2}:\d{2}) · (\w+) · (\w+) · (\w+)\s*$", re.MULTILINE)
_TITLE_RE = re.compile(r"<!-- title: (.*?) -->")
_LINK_RE = re.compile(r"<!-- link: (\S+) -->")
_TAG_RE = re.compile(r"\s*<!--.*?-->\s*", re.DOTALL)


@dataclass(frozen=True)
class Thought:
    time: str               # HH:MM, local
    kind: str               # KINDS
    place: str              # PLACES
    source: str             # SOURCES
    text: str
    title: str | None = None
    link: str | None = None


def _line(text: str | None) -> str:
    """One line, with no comment marker in it."""
    return " ".join((text or "").replace("<!--", "").replace("-->", "").split())


def parse_day(text: str | None) -> list[Thought]:
    """The day file → its thoughts, oldest first; a block of an unknown kind or place, or with no text, is skipped."""
    text = text or ""
    heads = list(_BLOCK_RE.finditer(text))
    out = []
    for i, m in enumerate(heads):
        if m[2] not in KINDS or m[3] not in PLACES or m[4] not in SOURCES:
            continue
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        chunk = text[m.end():end]
        title, link = _TITLE_RE.search(chunk), _LINK_RE.search(chunk)
        body = " ".join(_TAG_RE.sub("\n", chunk).split())
        if body:
            out.append(Thought(m[1], m[2], m[3], m[4], body, title[1] if title else None, link[1] if link else None))
    return out


def block(t: Thought) -> str:
    """One thought as appended to the day file."""
    title = f"<!-- title: {_line(t.title)} -->\n" if t.title else ""
    link = f"<!-- link: {t.link} -->\n" if t.link and not any(c.isspace() for c in t.link) else ""
    return f"\n## {t.time} · {t.kind} · {t.place} · {t.source}\n{title}{link}{_line(t.text)}\n"


def archive_key(day: str, t: Thought, n: int) -> str:
    """Its line's key in her archive: one per thought, so a second append is a no-op."""
    return f"thought:{day}:{t.time}:{n}"


def today_thoughts(thoughts: Iterable[Thought], private: bool, n: int) -> list[Thought]:
    """The last `n` thoughts a prompt may see: alone with the owner all of them, in Agora only the place `thought`."""
    seen = [t for t in thoughts if private or t.place == "thought"]
    return seen[-n:] if n > 0 else []


def thought_rows(thoughts: Iterable[Thought], private: bool, n: int) -> list[str]:
    """The last `n` of a day's thoughts a prompt may see, a line each with its part of the day — never a clock time;
    a news thought names its title, and alone with the owner carries its link."""
    rows = []
    for t in today_thoughts(thoughts, private, n):
        when = PART_ADVERB[part_of_day(int(t.time[:2]))]
        read = f", прочитавши «{t.title}»" if t.kind == "news" and t.title else ""
        link = f" (посилання: {t.link})" if private and t.kind == "news" and t.link else ""
        rows.append(f"- {when}{read}: {t.text}{link}")
    return rows


def thoughts_section(thoughts: Iterable[Thought], private: bool, n: int) -> str | None:
    """«Що ти сьогодні думала»: in Agora her `thought` place only, with no link; alone with the owner all of them,
    a news thought with its link — so a line she writes first can share it. None without one."""
    rows = thought_rows(thoughts, private, n)
    return THOUGHTS_TITLE + "\n" + "\n".join(rows) if rows else None
