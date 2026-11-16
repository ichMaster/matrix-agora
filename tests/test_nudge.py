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
    initiative_due,
    last_speaker,
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


# --- v8.3 (AGORA-273): Лілі's own line — the room's rules -----------------------------------------------------------
LILI_IDLE, LILI_HOURS, POLL = 1_800_000, (9, 23), 60_000


def lili_due(now_ms, now, last_room, last_is_hers=False, sent=0, last_poll=None, per_day=4, hours=LILI_HOURS):
    return initiative_due(now_ms, now, last_room, last_is_hers, sent, last_poll, LILI_IDLE, per_day, hours, POLL)


def test_her_line_is_due_only_when_every_room_rule_holds():
    now_ms, now = at("14:00")
    quiet = now_ms - LILI_IDLE
    assert lili_due(now_ms, now, quiet)
    assert lili_due(now_ms, now, None)                                        # an empty room is quiet
    assert not lili_due(now_ms, now, quiet + 1)                               # the room spoke recently
    assert not lili_due(now_ms, now, quiet, last_is_hers=True)                # never twice in a row
    assert not lili_due(now_ms, now, quiet, sent=4)                           # the day's cap
    assert lili_due(now_ms, now, quiet, sent=3)
    assert not lili_due(now_ms, now, quiet, per_day=0)                        # 0: off
    assert not lili_due(now_ms, now, quiet, last_poll=now_ms - POLL + 1)      # polled a moment ago
    assert lili_due(now_ms, now, quiet, last_poll=now_ms - POLL)


@pytest.mark.parametrize("hhmm,due", [("08:59", False), ("09:00", True), ("22:59", True), ("23:00", False),
                                      ("03:00", False)])
def test_her_line_only_inside_her_hours(hhmm, due):
    now_ms, now = at(hhmm)
    assert lili_due(now_ms, now, None) is due
    assert lili_due(now_ms, now, None, hours=(22, 2)) is (hhmm in ("22:59", "23:00"))  # wrapping past midnight


def test_the_rooms_last_speaker_sees_through_purrs():
    """A purr after her line is nobody between (v4.2: purrs are transparent)."""
    timeline = [("Ада", 1, "$a", False), ("Лілі", 2, "$l", False), ("Кіт", 3, "$k", True)]
    assert last_speaker(timeline) == "Лілі"
    assert last_speaker([*timeline, ("Бруно", 4, "$b", False)]) == "Бруно"
    assert last_speaker([("Кіт", 1, "$k", True)]) is None and last_speaker([]) is None
    assert last_speaker([("Ich", 1, "$o")]) == "Ich"                          # an entry without the purr flag


def simulate_her_day(seed: int, per_day: int = 4, window_ms: int = 600_000) -> tuple[list, list]:
    """A day of the room's own talk — the owner's lines 5–180 minutes apart, each followed by a wave of up to four
    agent lines — ticked minute by minute; Lumi always has an offer, `initiative_due` decides, and a post appends her
    line (answered now and then by an agent, as R2 would)."""
    import random
    rng = random.Random(seed)
    day0, _ = at("00:00", "2026-11-16")
    talk, t = [], day0
    while t < day0 + 86_400_000:
        t += rng.randint(5, 180) * 60_000
        talk.append((t, "Ich"))
        u = t
        for _ in range(rng.randint(0, 4)):
            u += rng.randint(10, 90) * 1000
            talk.append((u, rng.choice(["Ада", "Бруно", "Леон", "Кіт"])))
    talk.sort()
    timeline, posted, last_poll, i = [], [], None, 0
    for minute in range(24 * 60):
        now = day0 + minute * 60_000
        while i < len(talk) and talk[i][0] <= now:
            timeline.append((talk[i][1], talk[i][0], f"$e{i}", False))
            i += 1
        local = datetime.fromtimestamp(now / 1000, KYIV)
        last_room = timeline[-1][1] if timeline else None
        if not initiative_due(now, local, last_room, last_speaker(timeline) == "Лілі", len(posted), last_poll,
                              LILI_IDLE, per_day, LILI_HOURS, POLL):
            continue
        last_poll = now
        before = list(timeline)
        timeline.append(("Лілі", now, f"$l{minute}", False))
        posted.append((now, local, before))
        if rng.random() < 0.7:
            timeline.append(("Ада", now + 30_000, f"$r{minute}", False))
    return posted, timeline


@pytest.mark.parametrize("seed", range(25))
def test_a_simulated_day_never_exceeds_her_cap_or_opens_a_line_inside_a_running_wave(seed):
    """ROADMAP v8.3 DoD: a simulated day with her initiative never exceeds the cap or opens a line inside a running
    wave — nor outside her hours, nor twice in a row with nobody between."""
    posted, _ = simulate_her_day(seed)
    assert len(posted) <= 4
    for now, local, before in posted:
        assert 9 <= local.hour < 23
        assert wave_count([*before, ("Лілі", now, "$l", False)], "Ich", now, 600_000) == 1   # her line opens the wave
        assert not before or now - before[-1][1] >= LILI_IDLE
        assert last_speaker(before) != "Лілі"


def test_simulated_days_do_give_her_a_say():
    assert sum(len(simulate_her_day(seed)[0]) for seed in range(25)) > 0
    assert all(not simulate_her_day(seed, per_day=0)[0] for seed in range(5))   # 0: off


def test_hours_parse():
    assert parse_hours("09-22") == (9, 22) and parse_hours("0-24") == (0, 24) and parse_hours("09-03") == (9, 3)
    for bad in ("9", "a-b", "10-25", "24-03", "09-09"):
        with pytest.raises(ValueError):
            parse_hours(bad)


@pytest.mark.parametrize("hhmm,due", [("08:59", False), ("09:00", True), ("23:59", True), ("00:30", True),
                                      ("02:59", True), ("03:00", False), ("05:00", False)])
def test_hours_may_wrap_past_midnight(hhmm, due):
    """«з 9 до 3 ночі» (owner, 2026-10-11): 09-03 runs from 09:00 to 03:00 the next night."""
    now_ms, now = at(hhmm)
    assert nudge_due(now_ms, now, None, None, 0, IDLE, 6, parse_hours("09-03")) is due


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
    people = ("ada", "bruno", "leon", "mia", "irma", "kira", "ustyna")                     # v5.5: six people; v6.4 seven
    assert chosen in (*people, "claude", "lili")  # v8.2: Лілі ranked
    answers = []
    for name in (*people, "claude", "lili"):  # v8.2: she may be the one
        me = roster[name]
        cfg = AgentConfig(**{**CFG.__dict__, "name": me.name, "user_id": me.user_id})
        d = decide_reply(kit.user_id, "рядок", "$nudge", 1, cfg, me, roster, owner_repliers_k=2, max_bot_turns=3,
                         bot_reply_p=1.0, reply_delay_s=4.0, rng=lambda: 0.0)
        answers.append(d.reply)
    assert answers.count(True) == 1                                                     # exactly one next speaker


def test_a_cat_only_typo_never_takes_down_the_others(tmp_path, monkeypatch):
    """Review #7: every agent parsed CAT_NUDGE_HOURS, so «22-09» crash-looped Ada and Bruno too."""
    from tests.test_first_sync import FakeLLM, make_agent
    monkeypatch.setenv("CAT_NUDGE_HOURS", "09:00-22:00")
    monkeypatch.setenv("CAT_NUDGE_IDLE_S", "not a number")
    make_agent(FakeLLM())                                                               # Ada starts
    with pytest.raises(ValueError):
        cat(tmp_path, SeqLLM())                                                         # the cat's own error


def test_the_silence_is_never_shorter_than_the_wave_window(tmp_path, monkeypatch):
    """Review #7: a nudge must land in an empty wave window, or R2 blocks every answer."""
    monkeypatch.setenv("CAT_NUDGE_IDLE_S", "300")
    monkeypatch.setenv("BOT_WINDOW_S", "600")
    assert cat(tmp_path, SeqLLM()).nudge_idle_ms == 600_000


def test_after_a_restart_the_silence_counts_from_the_start(tmp_path):
    """Review #9: a restart whose backfill failed left an empty timeline — quiet — and he nudged at the first tick."""
    agent = cat(tmp_path, SeqLLM("рядок"))
    agent.timeline = []
    agent.started_ms = agent.clock() - 60_000                                           # started a minute ago
    assert asyncio.run(agent.maybe_nudge()) is False
    agent.started_ms = agent.clock() - IDLE
    assert asyncio.run(agent.maybe_nudge()) is True


def test_a_telegram_names_claude_and_may_run_longer(tmp_path):
    """The owner, 2026-10-11: a sysadmin joke for Claude in telegraph style — named, so he may answer."""
    from agents.nudge import TELEGRAM_MATERIAL, TELEGRAM_MAX_WORDS
    long_joke = "CQ CQ КЛОД DE КІТ " + " ".join(f"слово{i}" for i in range(60)) + " 73 SK"
    llm = SeqLLM(long_joke)
    agent = cat(tmp_path, llm)
    day = kind_day("telegram")
    assert asyncio.run(agent.nudge(datetime.fromisoformat(day + "T14:00").replace(tzinfo=KYIV), 1)) == ("telegram", True)
    assert TELEGRAM_MATERIAL.format(name="Клод", upper="КЛОД") in llm.prompts[0] and NUDGE_RULE in llm.prompts[0]
    assert "«CQ CQ КЛОД DE КІТ»" in llm.prompts[0] and "73 SK" in llm.prompts[0]
    assert "звичайним текстом українською" in llm.prompts[0]                  # the joke itself in plain Ukrainian
    assert "до 40 слів" in llm.prompts[0]                                    # review #17: a budget, not a cut
    body = sent_body(agent)
    assert body.startswith("CQ CQ КЛОД DE КІТ") and len(body.split()) == TELEGRAM_MAX_WORDS
    from agents.roster import load_roster
    from agents.turns import mentions
    claude = load_roster("agora")["claude"]
    assert mentions(body, claude.name_forms, claude.user_id)                    # the call sign names him


def test_without_an_assistant_a_telegram_becomes_a_memory(tmp_path):
    llm = SeqLLM("Копії. Щоночі.")
    agent = cat(tmp_path, llm)
    agent.others = {uid: m for uid, m in agent.others.items() if m.type != "assistant"}
    day = kind_day("telegram")
    assert asyncio.run(agent.nudge(datetime.fromisoformat(day + "T14:00").replace(tzinfo=KYIV), 1)) == ("memory", True)
