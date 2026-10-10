"""The cat's past-life memories (v4.3): fixed, authored theses he retells in his own words.

`agents/canon/<name>.memories.md` holds one thesis per line as `- [tags] text`; headings and prose around them are
for the editor. Which one he remembers is a pure function of the event, the message he answers and what he has
already told this run — no shared state, nothing written anywhere. Everything here is pure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

THESIS_RE = re.compile(r"^- \[([^\]]*)\]\s+(\S.*)$")
APOSTROPHES = str.maketrans({"’": "'", "ʼ": "'", "‘": "'", "`": "'"})
# the prompt section; the rule rides with the material so the reply rules stay the same for every agent
PASTLIFE_PREFIX = "Спогад з минулого життя (перекажи своїми словами, уривком, не цитуй): "
VERBATIM_WORDS = 5  # a reply copying this many consecutive words of its thesis is not his own words


class ThesesError(ValueError):
    """A malformed theses file."""


@dataclass(frozen=True)
class Thesis:
    tags: tuple[str, ...]  # lowercase stems or terms, matched at a word start in the message
    text: str


def _norm(text: str) -> str:
    return (text or "").translate(APOSTROPHES).lower()


def parse_theses(text: str) -> tuple[Thesis, ...]:
    """Every `- [a, b] text` line; anything else is ignored, but a line that starts like a thesis must be one."""
    out = []
    for n, line in enumerate((text or "").splitlines(), 1):
        if not line.startswith("- ["):
            continue
        m = THESIS_RE.match(line.rstrip())
        tags = tuple(t for t in (_norm(t).strip() for t in m.group(1).split(",")) if t) if m else ()
        if not m or not tags:
            raise ThesesError(f"line {n}: expected '- [tags] text'")
        out.append(Thesis(tags, m.group(2).strip()))
    return tuple(out)


def tag_found(tag: str, said: str) -> bool:
    """A tag counts at a word start only — «бекап» in «бекапом», never «чат» in «почати» (v4.3 review #3)."""
    return re.search(r"(?<!\w)" + re.escape(tag), said) is not None


def pick_memory(event_id: str, last_text: str, theses: tuple[Thesis, ...], told: set[int] | frozenset[int]) -> int | None:
    """The index of the thesis to retell: not yet told this run (all again once every one is told), a tag starting
    a word of `last_text` preferred, then `uniform(event_id, "memory")` — the same answer for the same inputs."""
    # a local import: turns imports config, which reads the theses through this module
    from agents.turns import uniform

    if not theses:
        return None
    candidates = [i for i in range(len(theses)) if i not in told] or list(range(len(theses)))
    said = _norm(last_text)
    matching = [i for i in candidates if any(tag_found(tag, said) for tag in theses[i].tags)]
    pool = matching or candidates
    return pool[min(int(uniform(event_id, "memory") * len(pool)), len(pool) - 1)]


def pastlife_section(thesis: Thesis) -> str:
    return PASTLIFE_PREFIX + thesis.text
