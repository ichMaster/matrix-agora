"""v5.24 (AGORA-212) — the scan in Кіра's agent: her private prompt to Gemini checked by a fake filter that blocks only
what holds a made-up word `LIMIT` times — a run of lines that blocks together, no line alone —, the hours of that run
softened one step at a time until the prompt passes, nothing closed; after a prompt-stage block the scan starts by
itself once she answered; `/scan` in her Telegram chat (nio, Gemini and the bot faked; made-up lines only)."""

import asyncio
import logging

from agents.archive import Archive
from agents.llm import LAST_BLOCK
from agents.logic import SOFT_LINE
from agents.route import Route, load_route, save_route
from agents.scan import STRICT_MAX
from agents.talk import TALK_GENTLE
from agents.telegram import COMMANDS
from tests.test_archive import EmbedLLM, kira
from tests.test_private_runtime import ms
from tests.test_telegram_runtime import kira as telegram_kira
from tests.test_telegram_runtime import texts_sent

MARK = "гроза-212"   # the made-up word the fake filter counts
LIMIT = 3            # a prompt holding it this many times blocks


class Filter(EmbedLLM):
    """Gemini 3.1 Pro: `probe` blocks a prompt (instruction and history) holding `MARK` `LIMIT` times; her summary of
    an hour (`think`) at strictness 0, 1, 2 still holds it `soft_marks[strict]` times; `down`: every check fails.
    `blocks`: her next answers blocked at `stage`."""

    reply_model = "gemini-3.1-pro-preview"

    def __init__(self, soft_marks=(1, 0, 0), down=False, blocks=0, stage="prompt"):
        super().__init__()
        self.soft_marks, self.down, self.blocks, self.stage = soft_marks, down, blocks, stage
        self.probed, self.thought = [], []

    async def think(self, contents, system_instruction, model="", max_output_tokens=0, kind="", level=None):
        strict = next(i for i, g in enumerate(TALK_GENTLE) if g in system_instruction)
        self.thought.append((kind, strict))
        return " ".join(["Пам'ятаю тепло."] + [MARK] * self.soft_marks[strict])

    async def probe(self, transcript, system_instruction, kind="probe"):
        self.probed.append(kind)
        return None if self.down else (transcript + (system_instruction or "")).count(MARK) >= LIMIT

    async def generate(self, transcript, system_instruction, max_output_tokens=400, kind="reply"):
        if self.blocks and kind in ("private", "private_nudge"):
            self.blocks -= 1
            LAST_BLOCK.set((self.stage, "prohibited_content", None))
            return None
        return await super().generate(transcript, system_instruction, max_output_tokens, kind)


RUN = [(13, 10, "Ich", f"{MARK} раз"), (13, 20, "Кіра", "Ну таке."), (14, 10, "Кіра", f"{MARK} два"),
       (15, 10, "Ich", f"{MARK} три"), (16, 5, "Кіра", "Вечір тихий."), (17, 5, "Ich", "Як ти?"),
       (17, 6, "Кіра", "Добре.")]


def scanning(tmp_path, monkeypatch, llm=None, lines=RUN, agent=None):
    agent = agent or kira(tmp_path, monkeypatch, llm or Filter())
    agent.cfg = agent.cfg.__class__(**{**agent.cfg.__dict__, "capabilities": agent.cfg.capabilities | {"talk"}})
    agent.talk_words = {"hour": 60, "day": 150}
    agent.private_history_hours, agent.private_history_min = 24, 20
    agent.scan_calls_max, agent.scan_auto_hour_max = 40, 3
    for i, (h, m, who, text) in enumerate(lines):
        agent.archive.append(f"tg:{i}", ms(h, m), "private", "telegram", who, text)
    return agent


def shown(agent):
    return "\n".join(f"{who}: {t}" if who else t for _, (who, t) in agent.gemini_history_shown())


def marks(agent):
    return dict(agent.archive.db.execute("SELECT key, mark FROM lines WHERE place = 'private'").fetchall())


def test_scan_is_a_command():
    assert ("scan", "Знайти й пом'якшити години, що блокують gemini") in COMMANDS


def test_a_prompt_that_passes_changes_nothing(tmp_path, monkeypatch):
    agent = scanning(tmp_path, monkeypatch, lines=RUN[1:])          # the word twice: under the limit
    assert asyncio.run(agent.scan_once()) == "⚙️ Промпт проходить — нічого не треба (перевірок: 1)"
    assert agent.archive.soft_rows() == [] and agent.llm.probed == ["scan_check"]


def test_the_hours_that_block_together_go_stricter_step_by_step_until_it_passes_and_nothing_closes(
        tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    agent = scanning(tmp_path, monkeypatch)
    answer = asyncio.run(agent.scan_once())
    assert answer.startswith("⚙️ Пом'якшено: 13:00–14:00 — суворіший підсумок; 14:00–15:00 — суворіший підсумок; "
                             "15:00–16:00 — суворіший підсумок. Промпт проходить — далі gemini (перевірок: ")
    rows = agent.archive.soft_rows()
    assert [(r.start_ms, r.end_ms, r.strict) for r in rows] == [(ms(h), ms(h + 1), 1) for h in (13, 14, 15)]
    assert [s for _, s in agent.llm.thought] == [0, 0, 0, 1, 1, 1]  # the gentle summaries first, then stricter
    assert set(marks(agent).values()) == {"gemini"}                    # nothing closed
    history = shown(agent)
    assert MARK not in history and history.count(SOFT_LINE.format(text="Пам'ятаю тепло.")) == 3
    assert "Кіра: Вечір тихий." in history and history.endswith("Ich: Як ти?\nКіра: Добре.")  # the rest word for word
    assert set(agent.llm.probed) == {"scan_check"} and len(agent.llm.probed) <= agent.scan_calls_max
    assert MARK not in caplog.text and "тепло" not in caplog.text and "scan: softened after" in caplog.text


def test_an_hour_with_its_own_summary_starts_from_it(tmp_path, monkeypatch):
    agent = scanning(tmp_path, monkeypatch)
    for h in (13, 14, 15):
        agent.archive.talk_put("hour", ms(h), ms(h + 1), "Ми говорили про погоду.", 1, 0, 0, ms(h + 1))
    assert asyncio.run(agent.scan_once()).startswith("⚙️ Пом'якшено: 13:00–14:00 — підсумок")
    assert agent.llm.thought == [] and {r.text for r in agent.archive.soft_rows()} == {"Ми говорили про погоду."}


def test_the_strictest_step_is_to_leave_the_hour_out(tmp_path, monkeypatch):
    agent = scanning(tmp_path, monkeypatch, Filter(soft_marks=(3, 3, 3)))
    assert "— без підсумку" in asyncio.run(agent.scan_once())
    assert {r.strict for r in agent.archive.soft_rows()} == {STRICT_MAX}
    assert MARK not in shown(agent) and "раз" not in shown(agent)


def test_his_line_still_waiting_is_in_every_check_and_never_softened(tmp_path, monkeypatch):
    lines = [(13, 10, "Ich", f"{MARK} раз"), (13, 20, "Кіра", "Ну таке."), (14, 10, "Кіра", f"{MARK} два"),
             (17, 30, "Ich", f"{MARK} знову")]
    agent = scanning(tmp_path, monkeypatch, Filter(soft_marks=(0, 0, 0)), lines)
    agent._unanswered = [("tg:3", f"{MARK} знову")]
    assert asyncio.run(agent.scan_once()).startswith("⚙️ Пом'якшено: 13:00–14:00 — підсумок; 14:00–15:00 — підсумок.")
    assert shown(agent).endswith(f"Ich: {MARK} знову")                 # his line, word for word


def test_when_his_waiting_line_blocks_alone_nothing_is_softened(tmp_path, monkeypatch):
    agent = scanning(tmp_path, monkeypatch, lines=[(13, 10, "Ich", "Привіт"), (17, 30, "Ich", f"{MARK} {MARK} {MARK}")])
    agent._unanswered = [("tg:1", f"{MARK} {MARK} {MARK}")]
    assert asyncio.run(agent.scan_once()).startswith("⚙️ Блокує повідомлення, на яке вона ще не відповіла")
    assert agent.archive.soft_rows() == []


def test_when_only_the_rest_of_the_prompt_blocks_the_hours_are_left_as_they_are(tmp_path, monkeypatch):
    agent = scanning(tmp_path, monkeypatch, lines=RUN[1:])

    async def prompt(brief):
        return f"Канон.\n\n{MARK} {MARK} {MARK}"
    agent._gemini_private_prompt = prompt
    assert asyncio.run(agent.scan_once()).startswith("⚙️ Блокує не розмова, а решта промпту")
    assert agent.archive.soft_rows() == [] and agent.llm.thought == []


def test_a_failed_check_changes_nothing(tmp_path, monkeypatch):
    agent = scanning(tmp_path, monkeypatch, Filter(down=True))
    assert asyncio.run(agent.scan_once()) == "⚙️ Gemini не відповів на перевірку: нічого не змінено (перевірок: 1)"
    assert agent.archive.soft_rows() == []


def test_past_its_checks_the_scan_changes_nothing(tmp_path, monkeypatch):
    agent = scanning(tmp_path, monkeypatch)
    agent.scan_calls_max = 3
    assert asyncio.run(agent.scan_once()) == "⚙️ Перевірок забагато: нічого не змінено (перевірок: 3)"
    assert agent.archive.soft_rows() == [] and agent.llm.probed == ["scan_check"] * 3


def test_a_softened_span_is_out_of_her_recall_topics_and_style_line(tmp_path, monkeypatch):
    agent = scanning(tmp_path, monkeypatch)
    asyncio.run(agent.scan_once())
    hidden = agent._soft_hidden()
    assert {t for _, t in hidden} == {f"{MARK} раз", "Ну таке.", f"{MARK} два", f"{MARK} три"}
    agent.topics_lines = 20
    asked = []

    async def generate(transcript, system_instruction, max_output_tokens=400, kind="reply"):
        asked.append(transcript)
        return '{"topics": []}'
    agent.llm.generate = generate
    asyncio.run(agent.ensure_topics())
    assert asked and MARK not in asked[0] and "Вечір тихий." in asked[0]


def test_a_prompt_block_closes_nothing_and_the_scan_starts_once_she_answered(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    agent = scanning(tmp_path, monkeypatch, Filter(blocks=1))
    spawned = []
    agent._spawn = spawned.append
    agent.private_line("Ну що?", ms(17, 50), "telegram", "tg:new")
    asyncio.run(agent.private_reply())                                  # blocked: no backup here, silence
    assert marks(agent)["tg:new"] == "gemini"                           # his line stays open
    scans = [c for c in spawned if c.__qualname__ == "Agent._scan_run"]
    assert len(scans) == 1
    asyncio.run(scans[0])
    assert agent.archive.soft_rows() and not agent._scan_running
    for coro in spawned:
        if coro is not scans[0]:
            coro.close()


def test_an_answer_stage_block_still_closes_his_line_and_starts_no_scan(tmp_path, monkeypatch):
    agent = scanning(tmp_path, monkeypatch, Filter(blocks=1, stage="answer"), lines=RUN[1:])
    spawned = []
    agent._spawn = spawned.append
    agent.private_line("Ну що?", ms(17, 50), "telegram", "tg:new")
    asyncio.run(agent.private_reply())
    assert marks(agent)["tg:new"] == "blocked"
    assert not [c for c in spawned if c.__qualname__ == "Agent._scan_run"]
    for coro in spawned:
        coro.close()


def test_the_scans_after_a_block_are_capped_by_the_hour_and_never_two_at_once(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    agent = scanning(tmp_path, monkeypatch, lines=RUN[1:])
    spawned = []
    agent._spawn = spawned.append
    agent.scan_auto_hour_max = 1
    agent.auto_scan()
    agent.auto_scan()                                                    # one is running
    for coro in spawned:
        asyncio.run(coro)
    agent.auto_scan()                                                    # the hour's one is spent
    assert len(spawned) == 1 and "not started after the block (running)" in caplog.text
    assert "not started after the block (the hour's cap)" in caplog.text
    agent.clock = lambda: ms(19, 1)
    agent.auto_scan()
    agent.scan_auto_hour_max = 0
    agent.auto_scan()
    assert len(spawned) == 2 and "not started after the block (off)" in caplog.text
    spawned[1].close()


def test_a_scan_that_makes_it_pass_ends_the_backups_window_but_never_a_pin(tmp_path, monkeypatch):
    agent = scanning(tmp_path, monkeypatch)
    agent.cfg = agent.cfg.__class__(**{**agent.cfg.__dict__, "capabilities": agent.cfg.capabilities | {"fallback"}})
    save_route(agent.route_file, Route(window_until_ms=ms(18, 5), blocks=(ms(17, 59),)))
    asyncio.run(agent.scan_once())
    route = load_route(agent.route_file)
    assert route.window_until_ms is None and route.blocks == (ms(17, 59),)
    save_route(agent.route_file, Route(pin="backup", window_until_ms=None))
    agent.archive.db.execute("DELETE FROM soft")
    asyncio.run(agent.scan_once())
    assert load_route(agent.route_file).pin == "backup"


def test_a_scan_that_finds_the_prompt_passing_ends_the_backups_window_too(tmp_path, monkeypatch):
    # 2026-11-05 20:13: his blocked lines were closed by then, the prompt passed, and the backup kept the window
    agent = scanning(tmp_path, monkeypatch, lines=RUN[1:])
    agent.cfg = agent.cfg.__class__(**{**agent.cfg.__dict__, "capabilities": agent.cfg.capabilities | {"fallback"}})
    save_route(agent.route_file, Route(window_until_ms=ms(18, 5)))
    assert asyncio.run(agent.scan_once()).startswith("⚙️ Промпт проходить")
    assert load_route(agent.route_file).window_until_ms is None


def test_scan_in_telegram_answers_at_once_and_sends_the_result_and_yes_is_gone(tmp_path, monkeypatch):
    agent = telegram_kira(tmp_path, monkeypatch, llm=Filter())
    agent.archive = Archive(tmp_path / "kira.archive.db")
    scanning(tmp_path, monkeypatch, agent=agent)
    spawned = []
    agent._spawn = spawned.append
    asyncio.run(agent.telegram_command("/scan"))
    assert texts_sent(agent) == ["⚙️ Сканую…"]
    asyncio.run(agent.telegram_command("/scan"))
    assert texts_sent(agent)[-1] == "⚙️ Сканування вже йде"
    asyncio.run(spawned[0])
    assert texts_sent(agent)[-1].startswith("⚙️ Пом'якшено: ")
    asyncio.run(agent.telegram_command("/scan yes"))
    assert texts_sent(agent)[-1] == "⚙️ /scan yes більше немає: сканування саме пом'якшує години й нічого не закриває"
    for coro in spawned[1:]:
        coro.close()
