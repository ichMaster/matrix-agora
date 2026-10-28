"""The life story: dated chapters from birth to death (ARCHITECTURE §Canon).

Pure parsing and selection. Visibility is a hard rule: the conversational
section shows the past chapters' openings and the current chapter — never a
future chapter and never the death date. Only the planner reads the next
chapter, as silent direction.

v5.11: a chapter may carry a dated list of events (`### Події`, one
`- YYYY-MM-DD · known|surprise · text` a line). The list is cut out of the
chapter's body, so no prompt that shows the chapter shows it; only the code
that delivers an event on its date, and the plans' known events ahead, read it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from itertools import pairwise

BIRTH_RE = re.compile(r"^Народження:\s*(\d{4})-(\d{2})-(\d{2})(?:\s+(\d{2}):(\d{2}))?,\s*(.+?)\s*$", re.MULTILINE)
DEATH_RE = re.compile(r"^Смерть:\s*(\d{4})-(\d{2})-(\d{2})\s*$", re.MULTILINE)
CHAPTER_RE = re.compile(r"^## (\d{4})–(\d{4}) · (.+?)\s*$", re.MULTILINE)
# v5.11: the chapter's dated events — the subsection runs to the next heading or the chapter's end
EVENTS_HEAD_RE = re.compile(r"^### Події\s*$", re.MULTILINE)
NEXT_HEAD_RE = re.compile(r"^#{2,3} ", re.MULTILINE)
EVENT_LINE_RE = re.compile(r"^-\s*(\d{4}-\d{2}-\d{2})\s*·\s*(\w+)\s*·\s*(\S.*?)\s*$")
EVENT_KINDS = ("known", "surprise")


class LifeError(ValueError):
    """A malformed life story."""


@dataclass(frozen=True)
class LifeEvent:
    """A dated turning point of a chapter: `known` ahead (it feeds her plans) or a `surprise` (on its date only)."""

    date: date
    kind: str
    text: str


@dataclass(frozen=True)
class Chapter:
    start: int
    end: int
    title: str
    body: str
    events: tuple[LifeEvent, ...] = ()

    @property
    def opening(self) -> str:
        return self.body.split("\n\n", 1)[0].strip()


@dataclass(frozen=True)
class LifeStory:
    birth: date
    birth_time: str
    birth_place: str
    death: date
    chapters: tuple[Chapter, ...]


def parse_life(text: str) -> LifeStory:
    b = BIRTH_RE.search(text)
    d = DEATH_RE.search(text)
    if not b or not d:
        raise LifeError("life story needs 'Народження:' and 'Смерть:' header lines")
    heads = list(CHAPTER_RE.finditer(text))
    if not heads:
        raise LifeError("life story has no '## YYYY–YYYY · title' chapters")
    chapters = []
    for i, m in enumerate(heads):
        body_end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        start, end = int(m[1]), int(m[2])
        body, events = _split_events(text[m.end():body_end], start, end)
        chapters.append(Chapter(start, end, m[3], body, events))
    for a, nxt in pairwise(chapters):
        if a.start > a.end or nxt.start <= a.end:
            raise LifeError(f"chapters overlap or are out of order: {a.start}–{a.end} / {nxt.start}–{nxt.end}")
    return LifeStory(
        birth=date(int(b[1]), int(b[2]), int(b[3])),
        birth_time=f"{b[4]}:{b[5]}" if b[4] else "",
        birth_place=b[6],
        death=date(int(d[1]), int(d[2]), int(d[3])),
        chapters=tuple(chapters),
    )


def _split_events(chunk: str, start: int, end: int) -> tuple[str, tuple[LifeEvent, ...]]:
    """The chapter's body without its `### Події` subsection, and the subsection's events."""
    head = EVENTS_HEAD_RE.search(chunk)
    if head is None:
        return chunk.strip(), ()
    nxt = NEXT_HEAD_RE.search(chunk, head.end())
    stop = nxt.start() if nxt else len(chunk)
    events = []
    for line in chunk[head.end():stop].splitlines():
        if not line.strip():
            continue
        m = EVENT_LINE_RE.match(line.strip())
        if not m:
            raise LifeError(f"chapter {start}–{end}: an event line is not '- YYYY-MM-DD · known|surprise · text'")
        if m[2] not in EVENT_KINDS:
            raise LifeError(f"chapter {start}–{end}: unknown event kind {m[2]!r} (known | surprise)")
        try:
            day = date.fromisoformat(m[1])
        except ValueError:
            raise LifeError(f"chapter {start}–{end}: bad event date {m[1]}") from None
        if not start <= day.year <= end:
            raise LifeError(f"chapter {start}–{end}: the event of {m[1]} is outside the chapter's years")
        # one line of single spaces, as the day file keeps it — else it never matches there (review #2)
        events.append(LifeEvent(day, m[2], " ".join(m[3].split())))
    body = (chunk[:head.start()].rstrip() + "\n\n" + chunk[stop:].lstrip()).strip()
    return body, tuple(sorted(events, key=lambda e: e.date))


def events_due(story: LifeStory, day: date) -> list[LifeEvent]:
    """Every event of the story dated `day`, known or surprise — delivered on its date, never before."""
    return [e for c in story.chapters for e in c.events if e.date == day]


def known_ahead(story: LifeStory, today: date, until: date) -> list[LifeEvent]:
    """The known events after today up to `until`, for her plans — never a surprise."""
    return [e for c in story.chapters for e in c.events if e.kind == "known" and today < e.date <= until]


def current_chapter(story: LifeStory, today: date) -> Chapter | None:
    y = today.year
    inside = [c for c in story.chapters if c.start <= y <= c.end]
    if inside:
        return inside[0]
    before = [c for c in story.chapters if c.start <= y]
    return before[-1] if before else None


def next_chapter(story: LifeStory, today: date) -> Chapter | None:
    """The planner's silent direction — never shown in a conversational prompt."""
    cur = current_chapter(story, today)
    later = [c for c in story.chapters if c.start > (cur.end if cur else today.year)]
    return later[0] if later else None


def life_section(story: LifeStory, today: date) -> str:
    """«Твоє життя досі»: past openings + the current chapter. Never the future — so the current chapter shows
    only when it began: its end year is the future, and the last chapter's is the death year (v4.2 review #5)."""
    cur = current_chapter(story, today)
    parts = ["Твоє життя досі:"]
    for c in story.chapters:
        if cur is not None and c.end < cur.start:
            parts.append(f"{c.start}–{c.end} · {c.title}: {c.opening}")
    if cur is not None:
        parts.append(f"Зараз (з {cur.start} · {cur.title}):\n{cur.body}")
    return "\n\n".join(parts)
