"""The life story: dated chapters from birth to death (ARCHITECTURE §Canon).

Pure parsing and selection. Visibility is a hard rule: the conversational
section shows the past chapters' openings and the current chapter — never a
future chapter and never the death date. Only the planner reads the next
chapter, as silent direction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from itertools import pairwise

BIRTH_RE = re.compile(r"^Народження:\s*(\d{4})-(\d{2})-(\d{2})(?:\s+(\d{2}):(\d{2}))?,\s*(.+?)\s*$", re.MULTILINE)
DEATH_RE = re.compile(r"^Смерть:\s*(\d{4})-(\d{2})-(\d{2})\s*$", re.MULTILINE)
CHAPTER_RE = re.compile(r"^## (\d{4})–(\d{4}) · (.+?)\s*$", re.MULTILINE)


class LifeError(ValueError):
    """A malformed life story."""


@dataclass(frozen=True)
class Chapter:
    start: int
    end: int
    title: str
    body: str

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
        chapters.append(Chapter(int(m[1]), int(m[2]), m[3], text[m.end():body_end].strip()))
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
    """«Твоє життя досі»: past openings + the current chapter. Never the future."""
    cur = current_chapter(story, today)
    parts = ["Твоє життя досі:"]
    for c in story.chapters:
        if cur is not None and c.end < cur.start:
            parts.append(f"{c.start}–{c.end} · {c.title}: {c.opening}")
    if cur is not None:
        parts.append(f"Зараз ({cur.start}–{cur.end} · {cur.title}):\n{cur.body}")
    return "\n\n".join(parts)
