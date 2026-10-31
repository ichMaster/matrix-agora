"""v5.16 — the search over a blocked prompt's parts (`agents/probe.py`): the smallest set Gemini still blocks, within
the budget of calls (pure but for the injected oracle — a fake that blocks a prompt holding given items or layers)."""

import asyncio

from agents.probe import OUTCOMES, Found, search

ITEMS = tuple(f"line:{i}" for i in range(40))
LAYERS = ("canon", "summary", "memories", "plans", "today", "mood", "private", "voice")


class Oracle:
    """Blocks a prompt holding every id of any one of `rules` (each a set of items and layers); records each call."""

    def __init__(self, *rules, fail_at=None):
        self.rules = [frozenset(r) for r in rules]
        self.calls = []
        self.fail_at = fail_at

    async def __call__(self, keep_items, keep_layers):
        self.calls.append((keep_items, keep_layers))
        if self.fail_at is not None and len(self.calls) == self.fail_at:
            return None
        held = keep_items | keep_layers
        return any(rule <= held for rule in self.rules)


def run(oracle, items=ITEMS, layers=LAYERS, cap=12) -> Found:
    return asyncio.run(search(items, layers, oracle, cap))


def test_one_blocking_item_among_forty_is_found_within_twelve_calls_wherever_it_is():
    for i in range(40):
        oracle = Oracle({f"line:{i}"})
        found = run(oracle)
        assert found == Found(found.calls, closed=(f"line:{i}",), outcome="found"), i
        assert found.calls == len(oracle.calls) <= 12
        assert oracle.calls[0] == (frozenset(ITEMS), frozenset(LAYERS))       # the whole prompt again, first
        assert oracle.calls[1] == (frozenset(), frozenset(LAYERS))            # then the base: no item


def test_two_items_that_block_only_together_are_both_found():
    for a, b in ((3, 30), (0, 1), (18, 39), (38, 39)):
        found = run(Oracle({f"line:{a}", f"line:{b}"}), cap=20)
        assert found.outcome == "found" and found.closed == (f"line:{a}", f"line:{b}"), (a, b)
        assert run(Oracle({f"line:{a}"}), cap=20).closed == (f"line:{a}",)    # neither alone stands for both
    capped = run(Oracle({"line:3", "line:30"}))                               # the default cap: a small set, both
    assert capped.outcome == "cap" and {"line:3", "line:30"} <= set(capped.closed) and len(capped.closed) <= 6


def test_two_causes_each_enough_alone_are_both_found_in_one_probe():
    oracle = Oracle({"line:4"}, {"line:27"})
    found = run(oracle, cap=40)
    assert found.outcome == "found" and set(found.closed) == {"line:4", "line:27"}
    assert oracle.calls[-1] == (frozenset(ITEMS) - {"line:4", "line:27"}, frozenset(LAYERS))  # what is left passes
    capped = run(Oracle({"line:4"}, {"line:27"}))                              # the default cap: the first, at least
    assert capped.calls <= 12 and "line:4" in capped.closed or "line:27" in capped.closed


def test_a_blocking_layer_is_named_and_nothing_is_closed():
    found = run(Oracle({"memories"}))
    assert found.outcome == "base_blocks" and found.layers == ("memories",) and found.closed == ()


def test_a_block_not_reproduced_takes_one_call_and_closes_nothing():
    oracle = Oracle()
    assert run(oracle) == Found(1, outcome="not_reproduced") and len(oracle.calls) == 1


def test_a_failed_call_closes_nothing():
    for at in (1, 2, 5):
        found = run(Oracle({"line:7"}, fail_at=at))
        assert found.outcome == "error" and found.closed == () and found.layers == (), at


def test_a_spent_budget_closes_the_smallest_set_seen_to_block_never_all():
    found = run(Oracle({"line:5"}), cap=4)                                    # whole, base, two halvings
    assert found.outcome == "cap" and "line:5" in found.closed and len(found.closed) == 10
    assert run(Oracle({"line:5"}), cap=2) == Found(2, outcome="cap")          # nothing narrowed: nothing closed
    assert run(Oracle({"line:5"}), cap=1) == Found(1, outcome="cap")          # the base not reached
    assert run(Oracle({"line:5"}), cap=0) == Found(0, outcome="cap")


def test_no_item_at_all_is_a_layers_block():
    found = run(Oracle({"canon", "voice"}), items=())
    assert found.outcome == "base_blocks" and set(found.layers) == {"canon", "voice"}


def test_the_outcomes_are_named():
    assert OUTCOMES == ("not_reproduced", "base_blocks", "found", "cap", "error")
