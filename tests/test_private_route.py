"""v5.14, v5.21 — her private answer through the route: Gemini; a block or a refusal makes the exchange `blocked` and
the backup answers for 5 minutes (an hour after more than 10 blocks in an hour), marked with its end; in the backup
mode Gemini is never asked; after it his next message goes straight to Gemini; `/backup` by hand; the backup's prompt
and budget; and nothing of the backup's talk reaches Gemini (nio, Gemini and NovelAI mocked; an injected clock)."""

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

    def __init__(self, blocks=0, block=("refusal", "виконати цей запит", None)):
        super().__init__()
        self.text, self.blocks, self.block, self.transcripts = "Від Gemini.", blocks, block, []

    async def generate(self, transcript, system_instruction, max_output_tokens=400, kind="reply"):
        self.transcripts.append(transcript)
        if self.blocks:
            self.blocks -= 1
            LAST_BLOCK.set(self.block)
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
    agent.fallback_window_s, agent.fallback_hour_max, agent.fallback_lock_s = 300, 10, 3600
    agent.fallback_context, agent.fallback_history_n = 32000, 60
    agent.marks_sent = []
    for door in ("send_line", "send_telegram"):                            # the mark above her words, as sent
        sent = getattr(agent, door)

        async def keep(*args, _sent=sent, **kwargs):
            agent.marks_sent.append(kwargs.get("mark"))
            return await _sent(*args, **kwargs)

        setattr(agent, door, keep)
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
    assert agent.marks_sent == [None]


def test_a_refusal_makes_the_exchange_blocked_and_the_backup_answers_for_five_minutes_marked_with_its_end(
        tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    agent = her(tmp_path, monkeypatch, Gemini(blocks=1))
    agent.private_line(ASKED, ms(17), "telegram", "tg:1")
    assert asyncio.run(agent.private_reply()) is True
    assert len(agent.fallback.calls) == 1 and ASKED in agent.fallback.calls[0]["transcript"]
    r = load_route(agent.route_file)
    assert r.window_until_ms == ms(18, 5) and r.answers == {"gemini": 0, "backup": 1} and len(r.blocks) == 1
    assert set(marks(agent).values()) == {"blocked"}                       # his line and hers, for good
    assert agent.marks_sent == ["⚙️ backup до 18:05"]                        # her clock reads 18:00
    assert agent.gemini_history() == [] and len(agent.private_history) == 2
    assert agent.session == []                                             # the summary is Gemini's
    assert "answered (telegram) by the backup" in caplog.text or "answered by the backup" in caplog.text
    assert SECRET not in caplog.text and "Від резерву" not in caplog.text


def test_an_answer_stage_block_is_tried_once_more_on_gemini_and_twice_takes_the_same_path(tmp_path, monkeypatch,
                                                                                          caplog):
    # v5.24 (AGORA-213, the owner, 2026-11-05): Gemini blocking what it wrote — the same prompt mostly passes again
    caplog.set_level(logging.INFO)
    gemini = Gemini(blocks=1, block=("answer", "prohibited_content", None))
    agent = her(tmp_path, monkeypatch, gemini)
    agent.private_line(ASKED, ms(17), "telegram", "tg:1")
    assert asyncio.run(agent.private_reply()) is True
    assert agent.fallback.calls == [] and agent.private_history[-1] == ("Кіра", "Від Gemini.")
    assert set(marks(agent).values()) == {"gemini"} and load_route(agent.route_file).window_until_ms is None
    assert len(gemini.transcripts) == 2 and "her answer blocked — once more on gemini" in caplog.text
    gemini.blocks = 2
    agent.private_line("і ще", ms(17, 1), "telegram", "tg:2")
    assert asyncio.run(agent.private_reply()) is True
    assert len(gemini.transcripts) == 4 and len(agent.fallback.calls) == 1        # two tries, then the backup
    assert marks(agent)["tg:2"] == "blocked" and load_route(agent.route_file).window_until_ms == ms(18, 5)
    gemini.blocks, gemini.block = 1, ("prompt", "prohibited_content", None)        # a prompt block: never again
    at(agent, 18, 10)
    agent.private_line("а тепер", ms(18, 10), "telegram", "tg:3")
    asyncio.run(agent.private_reply())
    assert len(gemini.transcripts) == 5


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


def test_in_the_backup_mode_gemini_is_never_asked_his_lines_stay_open_hers_are_blocked_then_gemini_directly(
        tmp_path, monkeypatch):
    # v5.24 (AGORA-212, the owner: «не закривати нічого»): the window after a block closes only the backup's own lines
    gemini = Gemini()
    agent = her(tmp_path, monkeypatch, gemini)
    save_route(agent.route_file, Route(window_until_ms=ms(18, 5)))
    agent.private_line(ASKED, ms(17, 59), "telegram", "tg:1")
    embedded = len(gemini.embedded)
    assert asyncio.run(agent.private_reply()) is True
    assert gemini.transcripts == [] and len(gemini.embedded) == embedded   # no answer, no recall embedding
    got = marks(agent)
    assert got["tg:1"] == "gemini" and sorted(got.values()) == ["blocked", "gemini"]   # his open, hers closed
    at(agent, 18, 6)                                                       # after the window
    agent.private_line("Добре, а тепер про погоду", ms(18, 6), "telegram", "tg:2")
    assert asyncio.run(agent.private_reply()) is True
    assert len(agent.fallback.calls) == 1                                   # straight to Gemini, no backup beside it
    assert ASKED in gemini.transcripts[-1] and "Від резерву" not in gemini.transcripts[-1]
    assert "Добре, а тепер про погоду" in gemini.transcripts[-1]
    assert load_route(agent.route_file).window_until_ms is None            # Gemini's again
    assert agent.private_history[-1] == ("Кіра", "Від Gemini.")


def test_after_the_window_a_block_opens_the_next(tmp_path, monkeypatch):
    agent = her(tmp_path, monkeypatch, Gemini(blocks=1))
    save_route(agent.route_file, Route(window_until_ms=ms(17, 50)))
    agent.private_line(ASKED, ms(17, 59), "telegram", "tg:1")
    assert asyncio.run(agent.private_reply()) is True
    assert len(agent.fallback.calls) == 1 and agent.private_history[-1][1].endswith("Від резерву, сонце.")
    assert load_route(agent.route_file).window_until_ms == ms(18, 5)
    assert marks(agent)["tg:1"] == "blocked"


def test_more_than_ten_blocks_in_an_hour_give_the_backup_an_hour(tmp_path, monkeypatch):
    agent = her(tmp_path, monkeypatch, Gemini(blocks=1))
    save_route(agent.route_file, Route(blocks=tuple(ms(17, m) for m in range(0, 50, 5))))  # ten in the last hour
    at(agent, 17, 55)
    agent.private_line(ASKED, ms(17, 55), "telegram", "tg:1")
    assert asyncio.run(agent.private_reply()) is True
    assert load_route(agent.route_file).window_until_ms == ms(18, 55)
    assert agent.marks_sent == ["⚙️ backup до 18:55"]


def test_backup_by_hand_holds_and_an_old_gemini_pin_is_the_rules(tmp_path, monkeypatch):
    agent = her(tmp_path, monkeypatch)
    save_route(agent.route_file, Route(pin="backup"))
    agent.private_line("Привіт", ms(17), "telegram", "tg:1")
    asyncio.run(agent.private_reply())
    assert len(agent.fallback.calls) == 1 and agent.llm.transcripts == []
    assert agent.marks_sent == ["⚙️ backup · вручну"] and marks(agent)["tg:1"] == "blocked"
    old = her(tmp_path / "g", monkeypatch, Gemini(blocks=1))
    old.route_file.parent.mkdir(parents=True, exist_ok=True)
    old.route_file.write_text('{"pin": "gemini", "judged": {"rated": 3}, "pinned_blocks": [1]}', encoding="utf-8")
    old.private_line(ASKED, ms(17), "telegram", "tg:1")
    asyncio.run(old.private_reply())
    r = load_route(old.route_file)
    assert r.pin == "auto" and r.window_until_ms == ms(18, 5) and len(r.blocks) == 1   # v5.21's rules


def test_a_line_she_writes_first_in_the_backup_mode_is_blocked_and_marks_none_of_his(tmp_path, monkeypatch):
    agent = her(tmp_path, monkeypatch)
    agent.private_line("Добраніч", ms(1), "telegram", "tg:1")
    agent._unanswered = []
    save_route(agent.route_file, Route(window_until_ms=ms(18, 5)))
    assert asyncio.run(agent.private_reply(nudge=True)) is True
    assert agent.fallback.calls[0]["kind"] == "private_nudge"
    got = marks(agent)
    assert got["tg:1"] == "gemini" and sorted(got.values()) == ["blocked", "gemini"]


def test_a_dropped_backup_answer_is_silence_and_his_line_stays_as_the_mode_leaves_it(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    agent = her(tmp_path, monkeypatch, Gemini(), Backup("Привет! Это ты?"))
    save_route(agent.route_file, Route(window_until_ms=ms(18, 5)))
    agent.private_line(ASKED, ms(17, 59), "telegram", "tg:1")
    assert asyncio.run(agent.private_reply()) is False
    assert "backup: dropped (russian)" in caplog.text and marks(agent)["tg:1"] == "gemini"   # the window: open
    save_route(agent.route_file, Route(pin="backup", pinned_at_ms=ms(17)))
    agent.private_line("ще раз", ms(17, 59, ), "telegram", "tg:2")
    assert asyncio.run(agent.private_reply()) is False
    assert marks(agent)["tg:2"] == "blocked"                                     # his `/backup`: closed
    assert load_route(agent.route_file).answers == {"gemini": 0, "backup": 0}


def test_without_the_backup_a_refusal_is_v5_13s_silence_with_his_line_blocked(tmp_path, monkeypatch):
    agent = her(tmp_path, monkeypatch, Gemini(blocks=1))
    agent.fallback = agent.fallback_responder = None
    agent.private_line(ASKED, ms(17), "telegram", "tg:1")
    assert asyncio.run(agent.private_reply()) is False
    assert marks(agent)["tg:1"] == "blocked" and not agent.route_file.exists()


def test_the_panels_switch_off_is_silence_at_once_and_on_again_the_backup_answers(tmp_path, monkeypatch):
    """v5.22 (the owner, 2026-11-02: «зроби нормальний перемикач коли роутінг включений а коли ні»): with
    `FALLBACK_ROUTE` off in the panel a block is v5.13's silence — his line blocked, the backup never called, no
    route kept; switched on again, without a restart, the backup answers the next block."""
    from agents.settings import OVERRIDES_FILE, save_json
    agent = her(tmp_path, monkeypatch, Gemini(blocks=2))
    switch = agent.memory_file.parent / OVERRIDES_FILE
    save_json(switch, {"services": {}, "agents": {"kira": {"FALLBACK_ROUTE": "off"}}})
    assert agent.backup_open() is False
    agent.private_line(ASKED, ms(17), "telegram", "tg:1")
    assert asyncio.run(agent.private_reply()) is False
    assert marks(agent)["tg:1"] == "blocked" and agent.fallback.calls == [] and not agent.route_file.exists()
    save_json(switch, {"services": {}, "agents": {"kira": {"FALLBACK_ROUTE": "on"}}})
    agent.private_line(ASKED, ms(17, 1), "telegram", "tg:2")
    assert asyncio.run(agent.private_reply()) is True
    assert len(agent.fallback.calls) == 1 and marks(agent)["tg:2"] == "blocked"


def test_the_backup_never_keeps_a_fact_and_sends_the_rest(tmp_path, monkeypatch, caplog):
    """v5.21 (the owner, 2026-11-02): «ніколи» — a «ЗАПАМ'ЯТАЙ» from the backup is dropped, never kept or sent."""
    caplog.set_level(logging.INFO)
    agent = her(tmp_path, monkeypatch, Gemini(), Backup("Звісно. ЗАПАМ'ЯТАЙ: Ich любить грозу"))
    agent.facts_dir = tmp_path / "kira.facts"
    agent.facts_max, agent.fact_max_chars, agent.facts_in_prompt = 50, 240, 10
    save_route(agent.route_file, Route(window_until_ms=ms(18, 5)))
    agent.private_line("Запам'ятай, я люблю грозу", ms(17, 59), "telegram", "tg:1")
    assert asyncio.run(agent.private_reply()) is True
    assert agent.facts_now(gemini=False) is None and not (tmp_path / "kira.facts").exists()
    assert agent.private_history[-1] == ("Кіра", "Звісно.") and "facts: dropped (backup)" in caplog.text


def test_the_backups_prompt_holds_blocked_lines_only_as_history_never_in_its_recall_or_facts(tmp_path, monkeypatch):
    """v5.21: the backup reads `blocked` lines as its history (300 of every mark), its recall and facts are open
    ones only, by words (no embedding of its query), and an emptied line never shows."""
    from agents.facts import add_fact
    agent = her(tmp_path, monkeypatch)
    agent.facts_dir, agent.facts_in_prompt, agent.fact_max_chars = tmp_path / "kira.facts", 10, 240
    add_fact(agent.facts_dir, "Відкритий факт про грозу", 1, "private", "2026-11-01", 50, 240)
    add_fact(agent.facts_dir, "Закритий факт про грозу", 1, "asked", "2026-11-01", 50, 240, mark="blocked")
    agent.archive.append("tg:old", ms(9), "private", "telegram", "Ich", "давня гроза відкрита")
    agent.archive.append("tg:shut", ms(10), "private", "telegram", "Ich", "давня гроза закрита")
    agent.archive.mark(["tg:shut"], "blocked")
    agent.private_history = [("Ich", "свіжий закритий рядок"), ("Ich", ""), ("Ich", "а гроза?")]
    embedded = len(agent.llm.embedded)
    prompt, lines = asyncio.run(agent._backup_private_prompt("БРИФ"))
    assert lines == [("Ich", "свіжий закритий рядок"), ("Ich", "а гроза?")]           # history: every mark, none empty
    assert "Відкритий факт" in prompt and "Закритий факт" not in prompt
    assert "давня гроза відкрита" in prompt and "давня гроза закрита" not in prompt
    assert len(agent.llm.embedded) == embedded                                           # words only


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
    assert 10 <= len(lines) < 80 and lines[-1] == agent.private_history[-1]   # the closed line too
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


def test_geminis_transcript_says_when_the_talk_was_and_how_long_the_pause_lasted(tmp_path, monkeypatch):
    """The owner, 2026-11-01 — the days between were closed to Gemini, so Tuesday's «I'm off to Kyiv tomorrow» sat
    right before Saturday's lines and read as tonight's: her transcript now says when, and how long the pause was;
    the history's data stays lines only."""
    gemini = Gemini()
    agent = her(tmp_path, monkeypatch, gemini)
    day = 86_400_000
    agent.private_line("Я завтра їду до Києва", ms(22, 50), "telegram", "tg:w1")
    agent.private_line("Я вже вдома", ms(22, 27) + 4 * day, "telegram", "tg:s1")   # Tuesday → Saturday
    agent.clock = lambda: ms(22, 28) + 4 * day
    assert asyncio.run(agent.private_reply()) is True
    t = gemini.transcripts[-1]
    assert (t.index("— цього тижня: —") < t.index("Ich: Я завтра їду до Києва")
            < t.index("— через 3 дні, сьогодні ввечері: —") < t.index("Ich: Я вже вдома"))
    assert [s for s, _ in agent.gemini_history()] == ["Ich", "Ich", "Кіра"]           # her answer joined it
    assert [i for i, _ in agent.gemini_history_shown()][:4] == [None, "line:tg:w1", None, "line:tg:s1"]


def test_her_last_private_prompt_to_gemini_is_kept_whole_with_its_outcome(tmp_path, monkeypatch):
    """v5.20 (the owner, 2026-11-02: «в панелі просто виводь останній промпт») — after an answer and after a block,
    the prompt as sent and what came of it, replaced each time, 0600."""
    import json
    import os
    import stat
    gemini = Gemini()
    agent = her(tmp_path, monkeypatch, gemini)
    path = agent.memory_file.parent / "kira.prompt.json"
    agent.private_line("Привіт", ms(17), "telegram", "tg:1")
    asyncio.run(agent.private_reply())
    kept = json.loads(path.read_text(encoding="utf-8"))
    assert kept["outcome"] == "answered" and kept["block"] is None and kept["model"] == ""
    assert kept["system"].startswith("Канон.") and kept["transcript"].endswith("Ich: Привіт")
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    gemini.blocks, gemini.block = 1, ("prompt", "prohibited_content", None)
    agent.private_line("Як ти?", ms(17, 5), "telegram", "tg:2")
    asyncio.run(agent.private_reply())
    kept = json.loads(path.read_text(encoding="utf-8"))
    assert kept["outcome"] == "blocked" and kept["block"] == ["prompt", "prohibited_content", None]
    assert "Ich: Як ти?" in kept["transcript"]                            # the test's clock stands at 18:00
