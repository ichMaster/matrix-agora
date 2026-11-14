"""v7.5 (AGORA-256) — a companion's answers on Gemini read their start, and the first lines of her history, from an
explicit context cache, as Lumi does (`cachedContents` keyed by a fingerprint). Gemini's implicit cache read 0 tokens
of an identical 43,800-token start in 23 calls of 3.1 Pro preview (2026-11-12), so the cache is made on purpose.

This module is the plan alone, over plain data and an injected clock: what an answer does — `plain` (no cache),
`use` (the cache held, maybe renewed), or `make` (a new one, the old one deleted). The SDK calls live in
`GeminiClient` (`agents/llm.py`).

- **The key** is a fingerprint: sha256 of the model, the start and the cached history lines.
- **When one is made:** only on the second answer with the same start within its life, so a quiet hour stores
  nothing.
- **When it is used:** while it lives, the current history still begins with its lines, and fewer than
  `rebuild_lines` new lines have come since.
- **When it is made again:** a changed start, a changed or stepped history, the growth past `rebuild_lines`, or
  expiry. The reason is named for the owner's log (`why`) — names only, never a text.
- **On failure:** a failed make backs off for `BACKOFF_S`, with plain calls meanwhile.

One cache per channel. From 7.5.1 her private chat alone (private answers and writing first) has one: her Agora
answers go plain (`CACHED_CHANNELS`) — rare, and the room's 300-line window slides at every line, so an Agora cache held
the start alone, was read again almost never and cost its storage (Устина's week simulated, 2026-11-14: −$0.49 a busy
day at an hour's life; the owner: «роби тільки 2»).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

SEPARATOR = "\n\n———\n\n"  # between her history and the tail (the time, the recall, her brief, the move, the rules)
BACKOFF_S = 300
# a history that changed under its cache (her window slid by a count cap, a span softened, a line closed): for so long
# the cache holds the start alone, so it is not made again at every answer (Устина's 12-hour window outgrows
# `HISTORY_N` 300 on a busy day, 2026-11-12)
START_ONLY_S = 7200
KEEP_LAST = 2  # the newest history lines stay in the request: his line is never in the cache
CACHED_CHANNELS = frozenset({"private"})  # 7.5.1: her Agora answers without a cache


def channel_of(kind: str) -> str:
    return "agora" if kind == "reply" else "private"


def fingerprint(model: str, start: str, lines: list[str]) -> str:
    h = hashlib.sha256()
    for part in (model, start, "\n".join(lines)):
        h.update(part.encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()


@dataclass
class Held:
    name: str
    model: str
    start_fp: str
    fp: str          # of the start and the cached lines
    lines: int       # history lines in the cache
    expires: float   # on the planner's clock
    ttl: float
    tokens: int = 0  # v7.5 (AGORA-258): its size, for its storage line


@dataclass
class Plan:
    action: str                 # plain | use | make
    lines: int = 0              # history lines in the cache (use, make)
    renew: bool = False         # use: the TTL to be renewed
    why: str = ""               # make: first | expired | start | mode | history | grew; plain: quiet | backoff
    old: str | None = None      # make, or a quiet plain after the start changed: the cache to delete
    name: str | None = None     # use: the cache's name


@dataclass
class _Channel:
    held: Held | None = None
    seen: dict[str, float] = field(default_factory=dict)  # start fingerprint → when an answer last had it
    failed_until: float = float("-inf")
    start_only_until: float = float("-inf")
    dropped: str = ""  # why the last cache was let go before its make (code review v7.5 #7): its `why` for the log


class CachePlanner:
    def __init__(self, ttl_s: float = 600, rebuild_lines: int = 40, keep_last: int = KEEP_LAST) -> None:
        self.ttl = float(max(60, ttl_s))
        self.rebuild = max(1, int(rebuild_lines))
        self.keep_last = max(1, int(keep_last))
        self._channels: dict[str, _Channel] = {}

    def _ch(self, channel: str) -> _Channel:
        return self._channels.setdefault(channel, _Channel())

    def held(self, channel: str) -> Held | None:
        return self._ch(channel).held

    def plan(self, channel: str, model: str, start: str, lines: list[str], now: float,
             start_only: bool = False) -> Plan:
        """`start_only` (v7.6, AGORA-260): the cache holds the start alone, good for any history — her `lumi` memory,
        whose short window moves by whole batches, has little history worth a cache and would make it again at
        every batch."""
        ch = self._ch(channel)
        start_fp = fingerprint(model, start, [])
        h = ch.held
        if h is not None and now < h.expires and h.model == model and h.start_fp == start_fp and (
                # the start alone: good for any history — in `lumi` mode, or for `START_ONLY_S` after a history slid
                # under it, then a full cache again (v7.5 code review #9: it held the history out for good)
                (h.lines == 0 and (start_only or now < ch.start_only_until))
                or (h.lines > 0 and not start_only and h.lines <= len(lines)
                    and fingerprint(model, start, lines[:h.lines]) == h.fp and len(lines) - h.lines <= self.rebuild)):
            ch.seen[start_fp] = now
            return Plan("use", lines=h.lines, renew=h.expires - now < h.ttl / 2, name=h.name)
        if now < ch.failed_until:
            return Plan("plain", why="backoff")
        last = ch.seen.get(start_fp)
        ch.seen = {start_fp: now}  # only the latest start matters
        if last is None or now - last > self.ttl:
            # the first answer with this start: a cache only for a second one. A live cache of another start is of no
            # more use: deleted now, not stored to the end of its life (code review v7.5 #7)
            if h is not None and now < h.expires and (h.start_fp != start_fp or h.model != model):
                ch.held, ch.dropped = None, "start"
                return Plan("plain", why="quiet", old=h.name)
            return Plan("plain", why="quiet")
        if h is None:
            why, ch.dropped = ch.dropped or "first", ""
        elif now >= h.expires:
            why = "expired"
        elif h.start_fp != start_fp or h.model != model:
            why = "start"
        elif start_only and h.lines > 0:
            why = "mode"  # v7.6: her memory switched to `lumi`: the start alone from now on
        elif h.lines == 0:
            why = "grew"  # the history back in the cache: its start-only time is over, or `layered` again
        elif h.lines > len(lines) or fingerprint(model, start, lines[:h.lines]) != h.fp:
            why = "history"
        else:
            why = "grew"
        if why == "history":
            ch.start_only_until = now + START_ONLY_S
        lines_in = 0 if start_only or now < ch.start_only_until else max(0, len(lines) - self.keep_last)
        return Plan("make", lines=lines_in, why=why, old=h.name if h else None)

    def made(self, channel: str, name: str, model: str, start: str, lines: list[str], now: float,
             tokens: int = 0) -> None:
        self._ch(channel).held = Held(name, model, fingerprint(model, start, []), fingerprint(model, start, lines),
                                      len(lines), now + self.ttl, self.ttl, tokens)

    def renewed(self, channel: str, now: float) -> None:
        h = self._ch(channel).held
        if h is not None:
            h.expires = now + h.ttl

    def failed(self, channel: str, now: float) -> None:
        ch = self._ch(channel)
        ch.failed_until = now + BACKOFF_S

    def forget(self, channel: str) -> str | None:
        """The cache held is gone (a call with it failed): its name, to delete; the next answer goes plain."""
        ch = self._ch(channel)
        name, ch.held = (ch.held.name if ch.held else None), None
        return name
