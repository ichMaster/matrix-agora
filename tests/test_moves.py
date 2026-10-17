"""v4.6 (the owner, 2026-10-11): Ada's and Bruno's move per reply — answer, ask someone by name, disagree, a plan or a
life story — drawn from the event they answer, the same on every machine."""
import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

from agents.logic import BANNED_RE
from agents.moves import DEFAULT_WEIGHTS, Move, move_line, persona_move, weights_from
from agents.roster import load_roster

ROOM = load_roster("agora")
ADA, BRUNO = ROOM["ada"], ROOM["bruno"]


def draw(eid, me=ADA, weights=DEFAULT_WEIGHTS, plans=True, life=True):
    return persona_move(eid, me, ROOM, "Ich", weights, has_plans=plans, has_life=life)


def test_the_rates_follow_the_weights_and_a_plain_answer_is_the_most_common():
    n = 5000
    counts = {}
    for i in range(n):
        k = draw(f"$e{i}").kind
        counts[k] = counts.get(k, 0) + 1
    for kind, w in DEFAULT_WEIGHTS.items():
        assert abs(counts[kind] / n - w) < 0.02, kind
    assert abs(counts["answer"] / n - 0.4) < 0.02 and counts["answer"] == max(counts.values())


def test_the_move_is_the_same_for_the_same_event_and_differs_between_the_two():
    assert all(draw(f"$s{i}") == draw(f"$s{i}") for i in range(200))
    assert any(draw(f"$d{i}", ADA).kind != draw(f"$d{i}", BRUNO).kind for i in range(200))


def test_the_addressee_is_never_oneself_and_everyone_is_asked():
    for me in (ADA, BRUNO):
        asked = {m.addressee for m in (draw(f"$a{i}", me) for i in range(3000)) if m.kind == "ask"}
        others = {m.name for m in ROOM.values() if m.user_id != me.user_id and m.type != "herald"} | {"Ich"}
        assert "Гермес" not in asked  # v5.1: the herald takes no turn — a question to him would hang
        assert asked == others and me.name not in asked


def test_a_plan_without_plans_and_a_story_without_a_life_become_answers():
    for i in range(2000):
        m = draw(f"$f{i}", plans=False, life=False)
        assert m.kind in ("answer", "ask", "disagree")


@pytest.mark.parametrize("move,part", [
    (Move("ask", "Кіт"), "звернися на ім'я: Кіт"), (Move("disagree"), "не погоджуйся"),
    (Move("plan"), "«Твої плани»"), (Move("story"), "«Твоє життя досі»")])
def test_each_move_has_its_line_and_none_names_anyones_nature(move, part):
    line = move_line(move)
    assert line.startswith("Цього разу:") and part in line and not BANNED_RE.search(line)
    assert move_line(Move("answer")) is None


def test_bad_weights_fall_back_and_a_sum_above_one_is_scaled():
    w, bad = weights_from({"PERSONA_ASK_P": "x", "PERSONA_PLAN_P": "2"})
    assert bad == ["PERSONA_ASK_P", "PERSONA_PLAN_P"] and w == DEFAULT_WEIGHTS
    w, bad = weights_from({"PERSONA_ASK_P": "1", "PERSONA_DISAGREE_P": "1", "PERSONA_PLAN_P": "0", "PERSONA_STORY_P": "0"})
    assert bad == [] and w == {"ask": 0.5, "disagree": 0.5, "plan": 0.0, "story": 0.0}


def test_a_personas_prompt_carries_the_move_for_the_answered_event_and_the_others_never(monkeypatch, tmp_path):
    from agents.agent import Agent
    from tests.test_first_sync import CFG, FakeLLM
    agent = Agent(CFG, llm=FakeLLM(), roster=ROOM)
    agent.client = SimpleNamespace(room_send=AsyncMock(), room_typing=AsyncMock())
    agent.memory_file = tmp_path / "ada.memory.md"
    agent.clock = lambda: int(datetime(2026, 10, 11, 12, tzinfo=ZoneInfo("Europe/Kyiv")).timestamp() * 1000)
    eid = next(f"$m{i}" for i in range(500) if draw(f"$m{i}", plans=False).kind == "disagree")
    agent.last_owner = (eid, "як тобі?")
    asyncio.run(agent.reply("!room"))
    system = agent.llm.calls[-1][1]
    assert move_line(Move("disagree")) in system
    for other in ("kit", "claude"):
        m = ROOM[other]
        cfg = SimpleNamespace(type=m.type, can=lambda c, m=m: c in m.capabilities)
        stub = SimpleNamespace(cfg=cfg, me=m, roster=ROOM, move_weights=DEFAULT_WEIGHTS)
        assert Agent.draw_move(stub, eid, None) is None


@pytest.mark.parametrize("name,other,lens", [("ada", "Бруно", "зсередини"), ("bruno", "Ади", "назовні")])
def test_the_canon_gives_each_persona_curiosity_and_the_opposite_view(name, other, lens):
    """AGORA-071 (the owner, 2026-10-11): what each asks whom, and opposite views — the same situation, two sides."""
    from pathlib import Path
    text = Path(f"agents/canon/{name}.md").read_text(encoding="utf-8")
    assert "Цікавість." in text and "Погляди." in text and lens in text and "на інший бік" in text
    curiosity = text.split("Цікавість.", 1)[1].split("\n\n", 1)[0]
    for who in ("Кота", "Клода", other, "Ich"):
        assert who in curiosity, who
    assert not BANNED_RE.search(text)


def test_disagree_only_where_there_is_a_view_to_disagree_with():
    """v4.6 review #3: drawn for a reply to the owner too, «заперечити» turned a greeting into an argument."""
    line = move_line(Move("disagree"))
    assert "якщо в тому, на що відповідаєш, є думка" in line and "відповідай як звичайно" in line
