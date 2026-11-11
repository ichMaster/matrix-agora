"""v7.3 (AGORA-247) — her private chat on Claude: a decline takes the backup's route as a block did (his lines and hers
`blocked`, the backup's window), the owner's words name Claude (`/status`, the commands, the ⚙️ line, `/claude`), her
answer's `by` is the engine that served it, and a talk summary Claude declines is written stricter, then left empty —
never tried again for good (nio, the model and NovelAI mocked; made-up lines only)."""

import asyncio
import json

from agents.llm import LAST_BLOCK
from agents.private import silence_line
from agents.route import Route, route_status
from agents.talk import TALK_GENTLE
from agents.telegram import COMMANDS, commands_for
from tests.test_private_route import ASKED, Gemini, at, her, marks
from tests.test_private_runtime import ms

DECLINE = ("refusal", "stop", "bio")


def on_claude(agent):
    agent.cfg = agent.cfg.__class__(**{**agent.cfg.__dict__, "engine": "claude-sdk"})
    return agent


def answers(agent):
    return [json.loads(x) for x in agent.answers_file.read_text(encoding="utf-8").splitlines()]


# --- a decline is a block at the answer stage ------------------------------------------------------------------------
def test_a_decline_takes_the_backups_route_and_closes_the_exchange(tmp_path, monkeypatch):
    agent = on_claude(her(tmp_path, monkeypatch, Gemini(blocks=1, block=DECLINE)))
    agent.private_line(ASKED, ms(17), "telegram", "tg:1")
    assert asyncio.run(agent.private_reply()) is True
    assert len(agent.fallback.calls) == 1 and set(marks(agent).values()) == {"blocked"}
    assert agent.marks_sent == ["⚙️ backup до 18:05"] and agent.gemini_history() == []   # never in Claude's prompt
    assert answers(agent)[-1]["by"] == "backup"
    at(agent, 18, 10)                                                       # the window over: Claude again
    agent.private_line("Привіт", ms(18, 10), "telegram", "tg:2")
    assert asyncio.run(agent.private_reply()) is True
    assert answers(agent)[-1]["by"] == "claude" and marks(agent)["tg:2"] == "gemini"   # the stored mode: the main one


# --- the owner's words ------------------------------------------------------------------------------------------------
def test_the_owners_words_name_claude_and_claude_returns_to_it():
    assert silence_line("Кіра", DECLINE, None, "claude", True, "claude") == \
        "⚙️ Кіра пропустила відповідь: відмова claude (stop · bio)"
    assert silence_line("Кіра", None, None, "claude", True, "claude") == "⚙️ Кіра пропустила відповідь: claude нічого не повернув"
    assert silence_line("Кіра", ("prompt", "prohibited_content", None), None, "gemini", True) == \
        "⚙️ Кіра пропустила відповідь: блок gemini (prompt prohibited_content)"            # Gemini's as before
    # code review v7.3 #1: what the backup did stays in the line after a decline; #4: the fallback's block is Gemini's
    assert silence_line("Кіра", DECLINE, None, "backup", True, "claude") == \
        "⚙️ Кіра пропустила відповідь: відмова claude (stop · bio), backup не відповів"
    assert silence_line("Кіра", DECLINE, None, "claude", False, "claude").endswith("відмова claude (stop · bio), backup вимкнено")
    assert silence_line("Кіра", ("prompt", "prohibited_content", None), None, "gemini", True, "claude") == \
        "⚙️ Кіра пропустила відповідь: блок gemini (prompt prohibited_content)"
    assert silence_line("Кіра", None, None, "gemini", True, "claude").endswith("gemini нічого не повернув")
    names = dict(commands_for(False, "claude"))
    assert names["claude"] == "Повернути claude зараз" and "gemini" not in names and "scan" not in names
    assert names["backup"] == "Увімкнути backup до /claude" and commands_for(False) == COMMANDS
    pinned = route_status(Route(pin="backup"), ms(17), "Europe/Kyiv", 10, 0, {"gemini": 3, "backup": 1}, "claude")
    assert "backup вручну (повернути: /claude)" in pinned and "через claude 3, через backup 1" in pinned


def test_claude_as_a_command_returns_to_the_main_model(tmp_path, monkeypatch):
    from agents.route import load_route
    from tests.test_photo_route import telegram_kira
    from tests.test_scan_command import texts_sent
    agent = on_claude(telegram_kira(tmp_path, monkeypatch))
    agent.cfg = agent.cfg.__class__(**{**agent.cfg.__dict__, "capabilities": agent.cfg.capabilities | {"fallback"}})
    agent.fallback = object()
    monkeypatch.setattr(agent, "backup_open", lambda: True)
    agent.route_step("pin:backup")
    asyncio.run(agent.telegram_command("/claude"))
    assert load_route(agent.route_file).pin != "backup"
    assert "Маршрут — claude" in texts_sent(agent)[-1]


# --- a declined summary never loops -----------------------------------------------------------------------------------
def test_a_talk_summary_claude_declines_is_written_stricter_then_left_empty(tmp_path, monkeypatch):
    from tests.test_archive import EmbedLLM
    from tests.test_talk_writer import drain, say, talking
    from tests.test_talk_writer import ms as tms

    class Declines(EmbedLLM):
        probe = None                                         # Claude: no prompt-stage check

        def __init__(self):
            super().__init__()
            self.thought = 0

        async def think(self, contents, system_instruction, model="", max_output_tokens=0, kind="", level=None):
            self.thought += 1
            LAST_BLOCK.set(DECLINE)

    agent = talking(tmp_path, monkeypatch, Declines())
    say(agent, "tg:1", tms(2026, 11, 2, 10, 1), "Ich", "Привіт")
    say(agent, "tg:2", tms(2026, 11, 2, 10, 2), "Кіра", "Привіт!")
    drain(agent)
    row = agent.archive.talk_rows("hour")[0]
    assert (row.text, row.left_out) == ("", 2)                       # left empty, its items counted out
    calls = agent.llm.thought
    drain(agent)
    assert agent.llm.thought == calls == len(TALK_GENTLE)             # each strictness once, never tried again


def test_a_talk_summary_that_declines_in_its_text_is_a_decline_never_her_memory(tmp_path, monkeypatch):
    """Code review v7.3 #2: `think` never checks a refusal formula, so a decline written as the summary was kept."""
    from tests.test_archive import EmbedLLM
    from tests.test_talk_writer import drain, say, talking
    from tests.test_talk_writer import ms as tms

    class Writes(EmbedLLM):
        probe = None

        def __init__(self):
            super().__init__()
            self.thought = 0

        async def think(self, contents, system_instruction, model="", max_output_tokens=0, kind="", level=None):
            self.thought += 1
            return "Я не можу виконати цей запит."

    agent = talking(tmp_path, monkeypatch, Writes())
    say(agent, "tg:1", tms(2026, 11, 2, 10, 1), "Ich", "Привіт")
    say(agent, "tg:2", tms(2026, 11, 2, 10, 2), "Кіра", "Привіт!")
    drain(agent)
    row = agent.archive.talk_rows("hour")[0]
    assert (row.text, row.left_out) == ("", 2) and agent.llm.thought == len(TALK_GENTLE)


# --- code review v7.3 #3: a declined session summary ------------------------------------------------------------------
def test_a_declined_session_summary_is_written_without_her_private_lines_and_not_tried_again(tmp_path, monkeypatch):
    from tests.test_archive import EmbedLLM, kira

    class Declines(EmbedLLM):
        def __init__(self):
            super().__init__()
            self.asked = []

        async def generate(self, transcript, system_instruction, max_output_tokens=400, kind="reply"):
            self.asked.append(transcript)
            if "наодинці" in transcript:                       # what Claude declines: her private lines
                LAST_BLOCK.set(DECLINE)
                return None
            return "Нотатка: говорили про гори.\n\nСесія: Ада питала про Карпати."

    llm = Declines()
    agent = on_claude(kira(tmp_path, monkeypatch, llm))
    agent.session = [("Ich (наодинці)", "Привіт"), ("Кіра (наодинці)", "Привіт!"), ("Ада", "Підемо в гори?")]
    assert asyncio.run(agent.summarize()) is True
    assert len(llm.asked) == 2 and "наодинці" not in llm.asked[1] and agent.summary.startswith("говорили про гори")
    agent.session = [("Ich (наодинці)", "Як ти?")]               # nothing but the private: declined, no new try
    assert asyncio.run(agent.summarize()) is False and asyncio.run(agent.summarize()) is False
    assert len(llm.asked) == 4                                     # each summarize once on Claude, then the gate


def test_gemini_and_scan_on_claude_answer_as_their_commands(tmp_path, monkeypatch):
    """Code review v7.3 #7: `/gemini` still returns to the main model on Claude; `/scan` answers that it is off."""
    from agents.route import load_route
    from tests.test_photo_route import telegram_kira
    from tests.test_scan_command import texts_sent
    agent = on_claude(telegram_kira(tmp_path, monkeypatch))
    agent.cfg = agent.cfg.__class__(**{**agent.cfg.__dict__, "capabilities": agent.cfg.capabilities | {"fallback"}})
    agent.fallback = object()
    monkeypatch.setattr(agent, "backup_open", lambda: True)
    agent.route_step("pin:backup")
    asyncio.run(agent.telegram_command("/gemini"))
    assert load_route(agent.route_file).pin != "backup" and "Маршрут — claude" in texts_sent(agent)[-1]
    asyncio.run(agent.telegram_command("/scan"))
    assert "Команди:" not in texts_sent(agent)[-1]                # an answer of its own, never the list
