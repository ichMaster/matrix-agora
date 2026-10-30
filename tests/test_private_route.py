"""v5.14 — her private answer through the route: Gemini; a block or a refusal sends the backup, which answers and opens
the window; the window is the backup's alone; at the window's end both start together and Gemini's line wins; pins
over the rules; the backup's prompt and budget; and nothing of the backup's talk reaches Gemini (nio, Gemini and
NovelAI mocked; an injected clock)."""

import asyncio
import logging

from agents.fallback import FallbackResponder
from agents.llm import LAST_BLOCK
from agents.logic import BUDGET_CUTS, fit_budget
from agents.route import Route, load_route, save_route
from tests.test_archive import EmbedLLM, kira
from tests.test_private_runtime import SECRET, ms

ASKED = f"те, на що Gemini відмовить {SECRET}"


class Gemini(EmbedLLM):
    """Gemini: refuses the next `blocks` answers (`LAST_BLOCK` set, None), answers the rest."""

    def __init__(self, blocks=0):
        super().__init__()
        self.text, self.blocks, self.transcripts = "Від Gemini.", blocks, []

    async def generate(self, transcript, system_instruction, max_output_tokens=400, kind="reply"):
        self.transcripts.append(transcript)
        if self.blocks:
            self.blocks -= 1
            LAST_BLOCK.set(("refusal", "виконати цей запит", None))
            return None
        return await super().generate(transcript, system_instruction, max_output_tokens, kind)


class Backup:
    """GLM-4.6 on NovelAI, canned."""

    def __init__(self, text="[softly] Від резерву, сонце.", delay=0.0):
        self.text, self.delay, self.calls = text, delay, []

    async def reply(self, transcript, instruction, max_tokens=400, kind="private"):
        self.calls.append({"transcript": transcript, "instruction": instruction, "kind": kind,
                           "max_tokens": max_tokens})
        if self.delay:
            await asyncio.sleep(self.delay)
        return (self.text, "stop") if self.text else None


def her(tmp_path, monkeypatch, gemini=None, backup=None):
    agent = kira(tmp_path, monkeypatch, gemini or Gemini())
    agent.cfg = agent.cfg.__class__(**{**agent.cfg.__dict__, "capabilities": agent.cfg.capabilities | {"fallback"}})
    agent.fallback = backup or Backup()
    agent.fallback_responder = FallbackResponder(agent.fallback)
    agent.fallback_window_s, agent.fallback_day_max = 300, 10
    agent.fallback_context, agent.fallback_history_n = 32000, 60
    return agent


def marks(agent):
    return dict(agent.archive.db.execute("SELECT key, mark FROM lines WHERE place = 'private'").fetchall())


def at(agent, hour, minute=0):
    agent.clock = lambda: ms(hour, minute)


def test_in_geminis_state_nothing_else_is_called_and_the_lines_stay_gemini(tmp_path, monkeypatch):
    agent = her(tmp_path, monkeypatch)
    agent.private_line("Привіт", ms(17), "telegram", "tg:1")
    assert asyncio.run(agent.private_reply()) is True
    assert agent.fallback.calls == [] and set(marks(agent).values()) == {"gemini"}
    r = load_route(agent.route_file)
    assert (r.window_until_ms, r.answers) == (None, {"gemini": 1, "backup": 0})


def test_a_refusal_sends_the_backup_which_answers_opens_the_window_and_marks_the_talk_waiting(tmp_path, monkeypatch,
                                                                                             caplog):
    caplog.set_level(logging.INFO)
    agent = her(tmp_path, monkeypatch, Gemini(blocks=1))
    agent.private_line(ASKED, ms(17), "telegram", "tg:1")
    assert asyncio.run(agent.private_reply()) is True
    assert len(agent.fallback.calls) == 1 and ASKED in agent.fallback.calls[0]["transcript"]
    r = load_route(agent.route_file)
    assert r.window_until_ms == ms(18, 5) and r.answers == {"gemini": 0, "backup": 1} and len(r.blocks) == 1
    assert set(marks(agent).values()) == {"waiting"}                       # his line and hers
    assert agent.gemini_history() == [] and len(agent.private_history) == 2
    assert agent.session == []                                             # the summary is Gemini's
    assert "answered (telegram) by the backup" in caplog.text or "answered by the backup" in caplog.text
    assert SECRET not in caplog.text and "Від резерву" not in caplog.text


def test_a_long_line_the_history_cuts_is_closed_to_gemini_too(tmp_path, monkeypatch):
    """Review #1: the history holds a line over `ENTRY_MAX_CHARS` cut, with «…» — closed in that form as well, or every
    next Gemini call carries it (a block that comes back until a restart)."""
    from agents.logic import ENTRY_MAX_CHARS
    long_line = f"{ASKED} " + "довгий рядок " * (ENTRY_MAX_CHARS // 13)
    long_answer = "[softly] " + "довга відповідь " * (ENTRY_MAX_CHARS // 15)
    gemini = Gemini(blocks=1)
    agent = her(tmp_path, monkeypatch, gemini, Backup(long_answer))
    agent.private_line(long_line, ms(17), "telegram", "tg:1")
    assert asyncio.run(agent.private_reply()) is True
    assert [len(t) for _, t in agent.private_history] == [ENTRY_MAX_CHARS + 1] * 2   # both cut in her history
    assert agent.gemini_history() == []
    at(agent, 18, 6)                                                       # after the window: Gemini's again
    agent.private_line("А тепер про погоду", ms(18, 6), "telegram", "tg:2")
    assert asyncio.run(agent.private_reply()) is True
    assert "А тепер про погоду" in gemini.transcripts[-1]
    assert ASKED not in gemini.transcripts[-1] and "довга відповідь" not in gemini.transcripts[-1]


def test_in_the_window_the_backup_alone_answers_and_its_talk_never_reaches_gemini(tmp_path, monkeypatch):
    gemini = Gemini()
    agent = her(tmp_path, monkeypatch, gemini)
    save_route(agent.route_file, Route(window_until_ms=ms(18, 5)))
    agent.private_line(ASKED, ms(17, 59), "telegram", "tg:1")
    embedded = len(gemini.embedded)
    assert asyncio.run(agent.private_reply()) is True
    assert gemini.transcripts == [] and len(gemini.embedded) == embedded   # no answer, no recall embedding
    assert set(marks(agent).values()) == {"waiting"}
    at(agent, 18, 6)                                                       # the window's end
    agent.private_line("Добре, а тепер про погоду", ms(18, 6), "telegram", "tg:2")
    assert asyncio.run(agent.private_reply()) is True
    assert ASKED not in gemini.transcripts[-1] and "Від резерву" not in gemini.transcripts[-1]
    assert "Добре, а тепер про погоду" in gemini.transcripts[-1]
    assert load_route(agent.route_file).window_until_ms is None            # Gemini's again
    assert agent.private_history[-1] == ("Кіра", "Від Gemini.")


def test_at_the_windows_end_a_block_takes_the_backups_ready_line_and_opens_the_next_window(tmp_path, monkeypatch):
    agent = her(tmp_path, monkeypatch, Gemini(blocks=1), Backup(delay=0.01))
    save_route(agent.route_file, Route(window_until_ms=ms(17, 50)))
    agent.private_line(ASKED, ms(17, 59), "telegram", "tg:1")
    assert asyncio.run(agent.private_reply()) is True
    assert len(agent.fallback.calls) == 1 and agent.private_history[-1][1].endswith("Від резерву, сонце.")
    assert load_route(agent.route_file).window_until_ms == ms(18, 5)
    assert marks(agent)["tg:1"] == "waiting"


def test_at_the_windows_end_geminis_line_wins_and_the_backup_is_cancelled(tmp_path, monkeypatch):
    agent = her(tmp_path, monkeypatch, Gemini(), Backup(delay=5))
    save_route(agent.route_file, Route(window_until_ms=ms(17, 50)))
    agent.private_line("Привіт", ms(17, 59), "telegram", "tg:1")
    assert asyncio.run(asyncio.wait_for(agent.private_reply(), 2)) is True  # never waits for the backup
    assert agent.private_history[-1] == ("Кіра", "Від Gemini.") and marks(agent)["tg:1"] == "gemini"


def test_pins_override_the_rules(tmp_path, monkeypatch):
    agent = her(tmp_path, monkeypatch)
    save_route(agent.route_file, Route(pin="backup"))
    agent.private_line("Привіт", ms(17), "telegram", "tg:1")
    asyncio.run(agent.private_reply())
    assert len(agent.fallback.calls) == 1 and agent.llm.transcripts == []
    pinned = her(tmp_path / "g", monkeypatch, Gemini(blocks=1))
    save_route(pinned.route_file, Route(pin="gemini"))
    pinned.private_line(ASKED, ms(17), "telegram", "tg:1")
    asyncio.run(pinned.private_reply())
    r = load_route(pinned.route_file)
    assert len(pinned.fallback.calls) == 1 and r.window_until_ms is None and len(r.blocks) == 1


def test_a_line_she_writes_first_in_the_window_is_the_backups_and_marks_none_of_his(tmp_path, monkeypatch):
    agent = her(tmp_path, monkeypatch)
    agent.private_line("Добраніч", ms(1), "telegram", "tg:1")
    agent._unanswered = []
    save_route(agent.route_file, Route(window_until_ms=ms(18, 5)))
    assert asyncio.run(agent.private_reply(nudge=True)) is True
    assert agent.fallback.calls[0]["kind"] == "private_nudge"
    got = marks(agent)
    assert got["tg:1"] == "gemini" and sorted(got.values()) == ["gemini", "waiting"]


def test_a_dropped_backup_answer_is_silence_and_his_line_still_waits(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    agent = her(tmp_path, monkeypatch, Gemini(), Backup("Привет! Это ты?"))
    save_route(agent.route_file, Route(window_until_ms=ms(18, 5)))
    agent.private_line(ASKED, ms(17, 59), "telegram", "tg:1")
    assert asyncio.run(agent.private_reply()) is False
    assert "backup: dropped (russian)" in caplog.text and marks(agent)["tg:1"] == "waiting"
    assert load_route(agent.route_file).answers == {"gemini": 0, "backup": 0}


def test_without_the_backup_a_refusal_is_v5_13s_silence_with_his_line_waiting(tmp_path, monkeypatch):
    agent = her(tmp_path, monkeypatch, Gemini(blocks=1))
    agent.fallback = agent.fallback_responder = None
    agent.private_line(ASKED, ms(17), "telegram", "tg:1")
    assert asyncio.run(agent.private_reply()) is False
    assert marks(agent)["tg:1"] == "waiting" and not agent.route_file.exists()


def test_a_fact_the_backup_asks_her_to_keep_waits(tmp_path, monkeypatch):
    agent = her(tmp_path, monkeypatch, Gemini(), Backup("Звісно. ЗАПАМ'ЯТАЙ: Ich любить грозу"))
    agent.facts_dir = tmp_path / "kira.facts"
    agent.facts_max, agent.fact_max_chars, agent.facts_in_prompt = 50, 240, 10
    save_route(agent.route_file, Route(window_until_ms=ms(18, 5)))
    agent.private_line("Запам'ятай, я люблю грозу", ms(17, 59), "telegram", "tg:1")
    asyncio.run(agent.private_reply())
    assert "грозу" in (agent.facts_now(gemini=False) or "") and "грозу" not in (agent.facts_now() or "")


# --- the backup's prompt and its budget --------------------------------------------------------------------------------
def test_the_budget_cuts_in_order_then_the_oldest_lines_never_below_ten():
    sizes = {(): 100, ("months",): 90, ("months", "weeks"): 80, BUDGET_CUTS: 70}

    def measure(cuts, n):
        return sizes[cuts] + n  # the instruction's characters and one per history line

    assert fit_budget(measure, 100, 60) == ((), 60)                       # 160 ≤ 200
    assert fit_budget(measure, 75, 60) == (("months",), 60)               # 150 ≤ 150
    assert fit_budget(measure, 67, 60) == (BUDGET_CUTS, 60)               # 130 ≤ 134
    assert fit_budget(measure, 45, 60) == (BUDGET_CUTS, 20)               # then the oldest lines: 70 + 20 ≤ 90
    assert fit_budget(measure, 1, 60) == (BUDGET_CUTS, 10)                # never fewer than ten


def test_the_backups_prompt_reads_every_line_and_fits_its_budget(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    agent = her(tmp_path, monkeypatch)
    for i in range(80):
        agent.private_line(f"рядок {i:02d} " + "слово " * 40, ms(17) + i, "telegram", f"tg:{i}")
    agent._closed.add(("Ich", agent.private_history[-1][1]))
    agent.fallback_context = 4000
    prompt, lines = asyncio.run(agent._backup_private_prompt("БРИФ"))
    assert 10 <= len(lines) < 60 and lines[-1] == agent.private_history[-1]   # the closed line too
    assert len(prompt) + sum(len(f"{s}: {t}") + 1 for s, t in lines) <= 4000 * 2 or len(lines) == 10
    assert "the prompt fitted" in caplog.text and "Канон." in prompt and SECRET not in caplog.text


def test_geminis_history_is_the_last_lines_open_to_it_the_backups_every_line(tmp_path, monkeypatch):
    """v5.15 (the owner, 2026-10-30) — after a long talk through the backup, Gemini still gets the last `HISTORY_N`
    lines open to it (from the archive), never a closed one; the backup's history is the last lines of every mark."""
    agent = her(tmp_path, monkeypatch)
    agent.history_n = 4
    for i in range(3):
        agent.private_line(f"відкритий {i}", ms(16, i), "telegram", f"tg:o{i}")
    for i in range(4):
        agent.private_line(f"через backup {i}", ms(17, i), "telegram", f"tg:b{i}")
        agent.mark_unanswered("window", [(f"tg:b{i}", f"через backup {i}")])
    assert [t for _, t in agent.private_history] == [f"через backup {i}" for i in range(4)]  # the backup's view
    assert [t for _, t in agent.gemini_history()] == ["відкритий 0", "відкритий 1", "відкритий 2"]
    assert agent.closed_in_history() == 4
