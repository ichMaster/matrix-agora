"""v7.5 (the owner, 2026-11-14: «скороти всім агентам окрім Кіри і Устини вікно до 3х годин») — the room's lines a
reply sees, by the hour: each line's time kept beside it, the last `AGORA_HISTORY_HOURS` hours of the window and at
least `AGORA_HISTORY_MIN` lines; 0 — the whole window, as before; each speaker's own setting, never the herald's
(nio and the model mocked; made-up lines only)."""

import asyncio

from agents.responder import Reply
from agents.settings import BY_NAME, concerns
from tests.test_answers import agora
from tests.test_settings import ROOM

HOUR = 3_600_000
T = 1_794_600_000_000


class Watcher:
    def __init__(self):
        self.lines = []

    async def respond(self, turn):
        self.lines.append(list(turn.lines))
        return Reply("Звісно.", "stop")


def seeded(tmp_path, hours=3, floor=2):
    agent = agora(tmp_path)
    agent.agora_history_hours, agent.agora_history_min = hours, floor
    for i, h in enumerate([10, 8, 6, 2.5, 1, 0.2]):                                  # hours before T
        agent._add_context("Ада" if i % 2 else "Ich", f"рядок {i}", int(T - h * HOUR))
    agent.clock = lambda: T
    return agent


def test_the_window_is_the_last_hours_at_least_the_floor_and_off_at_zero(tmp_path):
    agent = seeded(tmp_path)
    assert [t for _, t in agent.agora_lines()] == ["рядок 3", "рядок 4", "рядок 5"]   # 2.5 h, 1 h, 12 min ago
    agent.agora_history_min = 5
    assert len(agent.agora_lines()) == 5                                              # the floor: a quiet room
    agent.agora_history_hours = 0
    assert len(agent.agora_lines()) == 6                                              # off: the whole window


def test_a_reply_is_composed_on_the_window_and_the_times_stay_beside_the_lines(tmp_path):
    agent = seeded(tmp_path)
    agent.responder = watcher = Watcher()
    asyncio.run(agent._compose("Інструкція."))
    assert [t for _, t in watcher.lines[0]] == ["рядок 3", "рядок 4", "рядок 5"]
    agent._add_context("Кіт", "Мур!", T)
    agent._add_context("Кіт", "Мур!", T + 1)                                        # a purr collapses, its time too
    assert len(agent.history) == len(agent.history_ts) and agent.history_ts[-1] == T + 1
    agent.history_n = 3
    agent._add_context("Ich", "ще", T + 2)
    assert len(agent.history) == len(agent.history_ts) == 3                          # capped together


def test_each_speaker_has_its_own_window_setting_and_the_herald_none():
    for name in ("AGORA_HISTORY_HOURS", "AGORA_HISTORY_MIN"):
        s = BY_NAME[name]
        assert s.service is None and s.scope == "speaker"                            # an agent's own, per agent
        assert {n for n, m in ROOM.items() if concerns(s, m)} == {n for n, m in ROOM.items() if m.type != "herald"}
    assert BY_NAME["AGORA_HISTORY_HOURS"].default == "0"                             # off unless set
