"""v5.16 — Gemini checks the parts of a blocked prompt: the smallest set of its parts that Gemini still blocks.

After a block at the prompt stage, her prompt is sent again in parts to the same model (`agents/llm.py`'s `probe`),
which only says whether it blocks. The search here is over opaque ids — the closable items (her history's lines, the
recalled lines and facts, the pinned facts, today's thoughts) and the fixed layers (the canon, the memories, …) — and
an injected oracle, `blocked(keep_items, keep_layers)`: no text ever enters it. First the whole prompt again (a block
not reproduced closes nothing), then the base — every layer, no item (a block there is a fixed layer's, named, and
nothing is closed), then the items by delta debugging (QuickXplain), down to a set every one of whose items is needed. Under
the budget of calls, the smallest set seen to block is the answer: closing it always removes a blocked combination —
but never the whole set, which would close all she knows to Gemini.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field

from agents.logic import build_instruction
from agents.responder import build_transcript

Oracle = Callable[[frozenset, frozenset], Awaitable[bool | None]]
OUTCOMES = ("not_reproduced", "base_blocks", "found", "cap", "error")


@dataclass(frozen=True)
class Found:
    calls: int
    closed: tuple[str, ...] = ()   # the items to close: `found` and `cap` only
    layers: tuple[str, ...] = ()   # the fixed layers that block: `base_blocks` only — named, never closed
    outcome: str = "found"


class _Spent(Exception):
    """The budget of calls is spent."""


class _Failed(Exception):
    """The oracle failed: nothing is closed."""


async def _minimal(found: tuple[str, ...], test: Callable[[tuple[str, ...]], Awaitable[bool]],
                   best: list[tuple[str, ...]]) -> tuple[str, ...]:
    """Junker's QuickXplain from a set known to block, the empty set known to pass: halve, find what the second half
    adds to the first, then what the first adds to that — some 2k·log2(n/k) calls for k items that block together
    (ddmin takes 42 calls for a pair among 40). It counts on Gemini's filter blocking more as more is added, never
    less. `best[0]` follows the smallest set seen to block, for a spent budget; the result keeps the items' order."""

    async def blocks(keep: tuple[str, ...]) -> bool:
        if await test(keep):
            if len(keep) < len(best[0]):
                best[0] = keep
            return True
        return False

    async def qx(base: tuple[str, ...], added: bool, cs: tuple[str, ...]) -> tuple[str, ...]:
        if added and await blocks(base):
            return ()
        if len(cs) == 1:
            return cs
        half = (len(cs) + 1) // 2
        c1, c2 = cs[:half], cs[half:]
        d2 = await qx(base + c1, True, c2)
        d1 = await qx(base + d2, bool(d2), c1)
        return d1 + d2

    return await qx((), False, found)


async def search(items: Sequence[str], layers: Sequence[str], blocked: Oracle, cap: int) -> Found:
    """The smallest blocked set of a blocked prompt's parts, in at most `cap` calls of `blocked` (True: Gemini
    blocks the prompt built from these items and layers; False: it passes; None: the call failed)."""
    calls = 0
    all_items, all_layers = tuple(dict.fromkeys(items)), tuple(dict.fromkeys(layers))

    async def ask(keep_items: tuple[str, ...], keep_layers: tuple[str, ...]) -> bool:
        nonlocal calls
        if calls >= cap:
            raise _Spent
        calls += 1
        answer = await blocked(frozenset(keep_items), frozenset(keep_layers))
        if answer is None:
            raise _Failed
        return bool(answer)

    best: list[tuple[str, ...]] = [all_items]
    in_layers = False
    try:
        if not await ask(all_items, all_layers):
            return Found(calls, outcome="not_reproduced")
        if not all_items or await ask((), all_layers):  # the base: every layer, no item
            in_layers = True
            best = [all_layers]
            layers_found = await _minimal(all_layers, lambda s: ask((), s), best)
            return Found(calls, layers=layers_found, outcome="base_blocks")
        closed = await _minimal(all_items, lambda s: ask(s, all_layers), best)
        return Found(calls, closed=closed, outcome="found")
    except _Spent:
        if in_layers:
            return Found(calls, layers=best[0], outcome="base_blocks")
        if calls < 2 or best[0] == all_items:  # the base not reached, or no part narrowed: never all of them
            return Found(calls, outcome="cap")
        return Found(calls, closed=best[0], outcome="cap")
    except _Failed:
        return Found(calls, outcome="error")


# --- v5.16: her private prompt in parts — it holds texts, in memory only, until the probe ends; the search above sees
# only the ids ------------------------------------------------------------------------------------------------------------
CLOSABLE = ("recalled", "facts", "thoughts")  # the sections drawn from the items, never layers


@dataclass
class PromptParts:
    """Her private prompt for Gemini as it was built: the fixed layers by name (`build_instruction`'s sections but the
    closable ones; `name` is never a layer) and the closable items by id — her history's lines (`line:<key>`; None: a
    line with no key, never closable), the recall's groups (each line by id: `line:<key>`, a fact `fact:<id>`, a
    thought `thought:<key>`), the facts the section showed and today's thoughts — with the renderers that drew them.
    `render` builds the instruction and the transcript again from what is kept."""
    layers: dict = field(default_factory=dict)
    history: list = field(default_factory=list)      # [(id | None, (speaker, entry))]
    groups: list = field(default_factory=list)       # [[(id, Line)]]
    facts: list = field(default_factory=list)        # [(id, Fact)]
    thoughts: list = field(default_factory=list)     # [(id, Thought)]
    draw_recalled: Callable = lambda groups: None
    draw_facts: Callable = lambda facts: None
    draw_thoughts: Callable = lambda thoughts: None

    def item_ids(self) -> tuple[str, ...]:
        ids = [i for i, _ in self.history if i] + [i for group in self.groups for i, _ in group]
        return tuple(dict.fromkeys(ids + [i for i, _ in self.facts] + [i for i, _ in self.thoughts]))

    def layer_names(self) -> tuple[str, ...]:
        return tuple(k for k, v in self.layers.items() if k != "name" and v)

    def render(self, keep_items=None, keep_layers=None) -> tuple[str, str]:
        """(the system instruction, the transcript) from the kept items and layers (None: all of them)."""
        items = set(self.item_ids() if keep_items is None else keep_items)
        layers = set(self.layer_names() if keep_layers is None else keep_layers)
        sections = {k: v if k == "name" or k in layers else ("" if k == "canon" else None)
                    for k, v in self.layers.items()}
        groups = [[line for i, line in group if i in items] for group in self.groups]
        sections["recalled"] = self.draw_recalled([g for g in groups if g])
        sections["facts"] = self.draw_facts([f for i, f in self.facts if i in items])
        sections["thoughts"] = self.draw_thoughts([t for i, t in self.thoughts if i in items])
        return (build_instruction(**sections),
                build_transcript([entry for i, entry in self.history if i is None or i in items]))
