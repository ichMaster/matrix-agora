"""The cat starts conversations (v4.3): when, what kind, the state file, and the line itself."""

import asyncio
import json
import os
import stat
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

from agents.agent import Agent
from agents.config import AgentConfig
from agents.mood import MoodState
from agents.nudge import (
    COMMAND_MATERIAL,
    HOROSCOPE_MATERIAL,
    NUDGE_KINDS,
    NUDGE_RULE,
    NudgeState,
    load_nudge_state,
    nudge_due,
    nudge_kind,
    parse_hours,
    save_nudge_state,
)
from agents.pastlife import PASTLIFE_PREFIX, Thesis
from agents.roster import TYPES, load_roster
from agents.turns import decide_reply, next_speaker, wave_count
from tests.test_first_sync import CFG

KYIV = ZoneInfo("Europe/Kyiv")
IDLE = 1_200_000  # CAT_NUDGE_IDLE_S default: 20 min (owner, 2026-10-10)
HOURS = (9, 22)


def at(hhmm: str, day: str = "2026-10-12") -> tuple[int, datetime]:
    when = datetime.strptime(f"{day} {hhmm}", "%Y-%m-%d %H:%M").replace(tzinfo=KYIV)
    return int(when.timestamp() * 1000), when


# --- nudge_due ------------------------------------------------------------------------------------------------------
def test_the_default_silence_is_twenty_minutes(tmp_path):
    """The owner's choice (2026-10-10): CAT_NUDGE_IDLE_S defaults to 1200 s."""
    assert cat(tmp_path, SeqLLM()).nudge_idle_ms == IDLE == 1_200_000


def test_due_after_silence_in_the_daytime_under_the_cap():
    now_ms, now = at("14:00")
    assert nudge_due(now_ms, now, now_ms - IDLE, None, 0, IDLE, 6, HOURS)
    assert not nudge_due(now_ms, now, now_ms - IDLE + 1, None, 0, IDLE, 6, HOURS)        # the room spoke recently
    assert not nudge_due(now_ms, now, now_ms - IDLE, now_ms - IDLE + 1, 0, IDLE, 6, HOURS)  # the last attempt
    assert nudge_due(now_ms, now, now_ms - IDLE, now_ms - IDLE, 5, IDLE, 6, HOURS)
    assert not nudge_due(now_ms, now, now_ms - IDLE, None, 6, IDLE, 6, HOURS)              # the daily cap
    assert nudge_due(now_ms, now, None, None, 0, IDLE, 6, HOURS)                            # an empty room is quiet


@pytest.mark.parametrize("hhmm,due", [("08:59", False), ("09:00", True), ("21:59", True), ("22:00", False),
                                      ("03:14", False)])
def test_only_inside_the_hours(hhmm, due):
    now_ms, now = at(hhmm)
    assert nudge_due(now_ms, now, None, None, 0, IDLE, 6, HOURS) is due


def test_hours_parse():
    assert parse_hours("09-22") == (9, 22) and parse_hours("0-24") == (0, 24)
    for bad in ("22-09", "9", "a-b", "10-25"):
        with pytest.raises(ValueError):
            parse_hours(bad)


def test_the_kind_is_deterministic_and_all_three_occur():
    kinds = [nudge_kind(f"2026-10-{d:02d}", n) for d in range(1, 29) for n in range(1, 7)]
    assert kinds == [nudge_kind(f"2026-10-{d:02d}", n) for d in range(1, 29) for n in range(1, 7)]
    assert set(kinds) == set(NUDGE_KINDS)


# --- the state file -------------------------------------------------------------------------------------------------
def test_state_round_trip_private_and_textless(tmp_path):
    path = tmp_path / "kit.nudge.json"
    assert load_nudge_state(path, "2026-10-12") == NudgeState(None, "2026-10-12", 0)        # missing → fresh
    save_nudge_state(path, NudgeState(123, "2026-10-12", 2))
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert json.loads(path.read_text()) == {"last_ms": 123, "day": "2026-10-12", "count": 2, "sent_ms": None}
    assert load_nudge_state(path, "2026-10-12") == NudgeState(123, "2026-10-12", 2)
    assert load_nudge_state(path, "2026-10-13") == NudgeState(123, "2026-10-13", 0)        # a new day, the gap kept
    save_nudge_state(path, NudgeState(200, "2026-10-12", 3, 150))
    assert load_nudge_state(path, "2026-10-12") == NudgeState(200, "2026-10-12", 3, 150)
    path.write_text("{not json")
    assert load_nudge_state(path, "2026-10-12") == NudgeState(None, "2026-10-12", 0)        # corrupt → fresh


# --- the agent ------------------------------------------------------------------------------------------------------
class SeqLLM:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.prompts = []

    async def generate(self, transcript, system_instruction, max_output_tokens=400, kind="reply"):
        self.prompts.append(system_instruction)
        return self.replies.pop(0) if self.replies else "мрр"


THESES = (Thesis(("бекап",), "Бекапи були щоночі, відновлення жодного разу."),)


def cat(tmp_path, llm, hhmm="14:00", theses=THESES, mood=None):
    cfg = AgentConfig(**{**CFG.__dict__, "name": "Кіт", "user_id": "@kit:agora.lan", "type": "creature",
                         "capabilities": TYPES["creature"] - {"mood"} | ({"mood"} if mood else set()),
                         "theses": theses})
    agent = Agent(cfg, llm=llm)
    agent.client = SimpleNamespace(room_send=AsyncMock(), room_typing=AsyncMock())
    agent.memory_file = tmp_path / "kit.memory.md"
    agent.started = True
    now_ms, now = at(hhmm)
    agent.clock = lambda: now_ms
    agent.timeline = [("Ich", now_ms - IDLE - 1, "$old", False)]
    agent.history = [("Ich", "знову забули зробити бекап")]
    if mood:
        agent.mood = MoodState(now.date().isoformat(), mood, mood)
    return agent


def sent_body(agent):
    return agent.client.room_send.await_args.kwargs["content"]["body"]


def kind_day(kind, n=1):
    """A day whose n-th nudge is `kind`."""
    return next(f"2026-{m:02d}-{d:02d}" for m in range(1, 13) for d in range(1, 29)
                if nudge_kind(f"2026-{m:02d}-{d:02d}", n) == kind)


def test_a_nudge_after_silence_is_sent_and_counted(tmp_path):
    agent = cat(tmp_path, SeqLLM("Бекапи. Ніхто не перевіряв."))
    assert asyncio.run(agent.maybe_nudge()) is True
    assert sent_body(agent) == "Бекапи. Ніхто не перевіряв."
    state = json.loads(agent.nudge_file.read_text())
    assert state["count"] == 1 and set(state) == {"last_ms", "day", "count", "sent_ms"}  # no text, ever
    assert state["sent_ms"] == state["last_ms"] == agent.clock()
    assert asyncio.run(agent.maybe_nudge()) is False                                    # the gap holds


def test_a_restart_neither_re_nudges_at_once_nor_exceeds_the_cap(tmp_path):
    agent = cat(tmp_path, SeqLLM("рядок"))
    now_ms = agent.clock()
    save_nudge_state(agent.nudge_file, NudgeState(now_ms - 60_000, "2026-10-12", 1))
    assert asyncio.run(agent.maybe_nudge()) is False                                    # attempted a minute ago
    save_nudge_state(agent.nudge_file, NudgeState(now_ms - IDLE, "2026-10-12", 6))
    assert asyncio.run(agent.maybe_nudge()) is False                                    # the day's cap
    agent.client.room_send.assert_not_awaited()


def test_at_night_he_stays_silent(tmp_path):
    agent = cat(tmp_path, SeqLLM("рядок"), hhmm="23:30")
    assert asyncio.run(agent.maybe_nudge()) is False
    agent.client.room_send.assert_not_awaited()


@pytest.mark.parametrize("kind", NUDGE_KINDS)
def test_the_material_follows_the_kind(tmp_path, kind):
    llm = SeqLLM("Небо каже: rm -rf сумнівів.")
    agent = cat(tmp_path, llm, mood="Колючий і сонний.")
    day = kind_day(kind)
    now = datetime.fromisoformat(day + "T14:00").replace(tzinfo=KYIV)
    agent.mood = MoodState(day, "Колючий і сонний.", "Колючий і сонний.")
    assert asyncio.run(agent.nudge(now, 1)) == (kind, True)
    prompt = llm.prompts[0]
    assert NUDGE_RULE in prompt
    assert (PASTLIFE_PREFIX in prompt) is (kind == "memory")
    assert (COMMAND_MATERIAL in prompt) is (kind == "command")
    assert (HOROSCOPE_MATERIAL in prompt) is (kind == "horoscope")


def test_without_the_days_mood_a_horoscope_nudge_becomes_a_memory(tmp_path):
    llm = SeqLLM("Копії. Щоночі.")
    agent = cat(tmp_path, llm)                                                          # no mood
    day = kind_day("horoscope")
    assert asyncio.run(agent.nudge(datetime.fromisoformat(day + "T14:00").replace(tzinfo=KYIV), 1)) == ("memory", True)
    assert PASTLIFE_PREFIX in llm.prompts[0] and agent.told == {0}


def test_the_room_speaking_during_generation_drops_the_nudge(tmp_path):
    class Interrupting(SeqLLM):
        async def generate(self, transcript, system_instruction, max_output_tokens=400, kind="reply"):
            agent.timeline.append(("Ich", agent.clock(), "$new", False))  # the owner writes meanwhile
            return "рядок"

    agent = cat(tmp_path, Interrupting())
    assert asyncio.run(agent.maybe_nudge()) is False
    agent.client.room_send.assert_not_awaited()
    state = json.loads(agent.nudge_file.read_text())
    assert state["count"] == 0 and state["last_ms"] == agent.clock()                    # an attempt, not a nudge


@pytest.mark.parametrize("reply", ["PASS", "Ти теж бот.", "Мрр… *позіхає*"])  # review #2: never a purr
def test_a_silent_attempt_spaces_the_next_but_does_not_count(tmp_path, reply):
    agent = cat(tmp_path, SeqLLM(reply))
    assert asyncio.run(agent.maybe_nudge()) is False
    agent.client.room_send.assert_not_awaited()
    state = json.loads(agent.nudge_file.read_text())
    assert state["count"] == 0 and state["last_ms"] == agent.clock()


def test_a_persona_never_nudges_whatever_the_silence(tmp_path):
    from tests.test_first_sync import FakeLLM, make_agent
    agent = make_agent(FakeLLM())
    agent.memory_file = tmp_path / "ada.memory.md"
    agent.started = True
    now_ms, _ = at("14:00")
    agent.clock = lambda: now_ms
    agent.timeline = [("Ich", now_ms - 10 * IDLE, "$old", False)]
    assert not agent.cfg.can("nudge")
    assert asyncio.run(agent.maybe_nudge()) is False
    agent.client.room_send.assert_not_awaited()
    assert not agent.nudge_file.exists()


# --- a nudge in the room: a fresh wave, one next speaker ------------------------------------------------------------
def test_a_nudge_after_silence_opens_a_fresh_wave_with_one_next_speaker():
    roster = load_roster("agora")
    kit, now = roster["kit"], 10 * IDLE
    timeline = [("Ада", 1_000, "$a", False), ("Бруно", 2_000, "$b", False), ("Ада", 3_000, "$c", False),
                ("Кіт", now, "$nudge", False)]
    assert wave_count(timeline, "Ich", now, 600_000) == 1                               # the window emptied
    chosen = next_speaker("$nudge", kit.user_id, "рядок", roster)
    assert chosen in ("ada", "bruno")
    answers = []
    for name in ("ada", "bruno"):
        me = roster[name]
        cfg = AgentConfig(**{**CFG.__dict__, "name": me.name, "user_id": me.user_id})
        d = decide_reply(kit.user_id, "рядок", "$nudge", 1, cfg, me, roster, owner_repliers_k=2, max_bot_turns=3,
                         bot_reply_p=1.0, reply_delay_s=4.0, rng=lambda: 0.0)
        answers.append(d.reply)
    assert answers.count(True) == 1                                                     # exactly one next speaker
