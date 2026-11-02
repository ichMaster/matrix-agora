"""v5.22 — the answer's time: each answer an agent sends adds a line to `state/<name>.answers.jsonl` (0600, no text):
where it went, what it answered, how long that message waited, the deliberate pause in it, who wrote it and what went
with it (nio, Telegram and Gemini mocked; the clocks injected)."""
import asyncio
import json
import os
import stat
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agents.agent import Agent
from agents.usage import answer_line
from tests.test_photo_route import her as photo_her
from tests.test_photo_route import ogg  # noqa: F401 — her voice, encoded
from tests.test_private_route import ASKED, Backup, Gemini
from tests.test_private_route import her as route_her
from tests.test_private_runtime import ms
from tests.test_responder import CFG, CompleteLLM

TS = "2026-11-02T12:00:00+02:00"


def lines(agent) -> list[dict]:
    path = agent.answers_file
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def test_the_line_names_where_what_how_long_and_who_never_a_text():
    line = answer_line(TS, "kira", "private", "telegram", "owner", 4200.4, 1500, "gemini", ["voice", "photo", "voice"])
    assert line == {"ts": TS, "agent": "kira", "place": "private", "door": "telegram", "answered": "owner",
                    "wait_ms": 4200, "delay_ms": 1500, "by": "gemini", "parts": ["photo", "voice"]}
    first = answer_line(TS, "kira", "private", "telegram", "none", 900, None, "gemini")
    assert first["wait_ms"] is None and first["delay_ms"] is None and first["parts"] == []  # writing first


def agora(tmp_path, text="Звісно, давай."):
    agent = Agent(CFG, llm=CompleteLLM(text, "stop"))
    agent.memory_file = tmp_path / "ada.memory.md"
    agent.client = SimpleNamespace(room_send=AsyncMock(), room_typing=AsyncMock())
    agent.ensure_today = AsyncMock()
    agent.tts = None
    return agent


def test_an_agora_answer_to_the_owner_holds_his_wait_and_the_pause(tmp_path):
    agent = agora(tmp_path)
    owner = agent.names.get(agent.cfg.owner, agent.cfg.owner)
    agent.timeline = [(owner, ms(17), "$ich1", False)]
    agent.last_owner = ("$ich1", "Привіт")
    agent.clock = lambda: ms(17) + 7_500
    assert asyncio.run(agent.reply("!room", delay_ms=3_000)) is True
    [line] = lines(agent)
    assert {k: line[k] for k in ("place", "door", "answered", "wait_ms", "delay_ms", "by", "parts")} == {
        "place": "agora", "door": "matrix", "answered": "owner", "wait_ms": 7_500, "delay_ms": 3_000,
        "by": "gemini", "parts": []}
    assert stat.S_IMODE(os.stat(agent.answers_file).st_mode) == 0o600 and "Звісно" not in json.dumps(line)


def test_an_agora_answer_to_another_agent_is_named_so(tmp_path):
    agent = agora(tmp_path)
    agent.timeline = [("Бруно", ms(17), "$bruno1", False)]
    agent._texts = {"$bruno1": "А ти як думаєш?"}
    agent._current = lambda trigger, at_ms=None: True
    agent.clock = lambda: ms(17) + 2_000
    assert asyncio.run(agent.reply("!room", "$bruno1", delay_ms=1_000)) is True
    assert lines(agent)[0]["answered"] == "agent" and lines(agent)[0]["wait_ms"] == 2_000


def test_a_silence_writes_no_line(tmp_path):
    agent = agora(tmp_path, text="PASS")
    asyncio.run(agent.reply("!room"))
    assert lines(agent) == []


@pytest.mark.usefixtures("ogg")
def test_her_private_answer_in_telegram_holds_his_wait_the_pause_and_her_voice_and_photo(tmp_path, monkeypatch):
    agent = photo_her(tmp_path, monkeypatch, "Ось я 🙂\nСЕЛФІ: я на балконі")
    agent.rng = lambda: 0.0                                                   # the pause: 1 s
    agent.private_line("скинь селфі", ms(17), "telegram", "tg:1")             # the fixture's clock is ms(18)
    assert asyncio.run(agent.private_reply()) is True
    [line] = lines(agent)
    assert {k: line[k] for k in ("place", "door", "answered", "wait_ms", "delay_ms", "by", "parts")} == {
        "place": "private", "door": "telegram", "answered": "owner", "wait_ms": 3_600_000, "delay_ms": 1_000,
        "by": "gemini", "parts": ["photo", "voice"]}


def test_her_answer_through_the_backup_is_named_so_and_writing_first_answers_nothing(tmp_path, monkeypatch):
    agent = route_her(tmp_path, monkeypatch, Gemini(blocks=1), Backup())
    agent.private_line(ASKED, ms(17), "telegram", "tg:1")
    assert asyncio.run(agent.private_reply()) is True
    assert asyncio.run(agent.private_reply(nudge=True)) is True
    backup, first = lines(agent)
    assert backup["by"] == "backup" and backup["answered"] == "owner" and backup["wait_ms"] == 3_600_000
    assert first["answered"] == "none" and first["wait_ms"] is None and first["delay_ms"] is None


def test_his_line_while_she_answers_waits_from_its_own_time_never_from_her_answer(tmp_path, monkeypatch):
    """Code review v5.22 #3: her answer moved `last_private_ms`, so his next line's wait counted from her answer."""
    agent = route_her(tmp_path, monkeypatch, Gemini(), Backup())
    agent.private_line(ASKED, ms(17), "telegram", "tg:1")
    assert asyncio.run(agent.private_reply()) is True                       # her answer at the fixture's ms(18)
    agent.private_line("а ще?", ms(17) + 1_800_000, "telegram", "tg:2")     # sent while she was answering
    assert asyncio.run(agent.private_reply()) is True
    first, second = lines(agent)
    assert first["wait_ms"] == 3_600_000 and second["wait_ms"] == 1_800_000
