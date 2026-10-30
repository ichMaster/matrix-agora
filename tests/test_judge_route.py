"""v5.15 — the judge in her private answer: nothing rated in Gemini's state; each exchange of the backup's talk rated
once it is sent (after a block with the blocked prompt's unrated lines, in the window, under a pin); the window's end
by the rating — the judge and the backup together, Gemini only after a clean rating (nio, Gemini, NovelAI and the judge
mocked; an injected clock)."""

import asyncio
import logging

from agents.facts import add_fact, load_facts
from agents.route import Route, load_route, save_route
from tests.test_judge_verdicts import FakeJudge
from tests.test_private_route import Backup, Gemini, at, her, marks
from tests.test_private_runtime import ms

SECRET = "таємниця-5153"


def judged(tmp_path, monkeypatch, gemini=None, backup=None):
    agent = her(tmp_path, monkeypatch, gemini, backup)
    agent.judge = FakeJudge()
    agent.spawned = []

    def spawn(coro):  # the background ratings, run by the test once the answer is sent; nothing else here
        if coro.__name__ == "judge_later":
            agent.spawned.append(coro)
        else:
            coro.close()

    agent._spawn = spawn
    agent.facts_dir, agent.facts_in_prompt, agent.fact_max_chars = tmp_path / "kira.facts", 10, 240
    return agent


def run_spawned(agent):
    for coro in agent.spawned:
        asyncio.run(coro)
    agent.spawned.clear()


def her_line(agent, key, text, mark):
    """Her earlier private answer, in the archive and her history, with its mark."""
    agent.archive.append(key, ms(17, 59), "private", "telegram", "Кіра", text)
    agent.archive.mark([key], mark)
    agent.private_history.append(("Кіра", text))
    if mark in ("waiting", "censored"):
        agent.close_lines([("Кіра", text)])


def window_end(agent):
    save_route(agent.route_file, Route(window_until_ms=ms(18, 5)))
    at(agent, 18, 6)


def test_in_geminis_state_nothing_is_rated_and_nothing_else_is_called(tmp_path, monkeypatch):
    agent = judged(tmp_path, monkeypatch)
    agent.private_line("Привіт", ms(18), "telegram", "tg:1")
    assert asyncio.run(agent.private_reply()) is True
    assert agent.judge.calls == [] and agent.spawned == [] and agent.fallback.calls == []
    assert marks(agent) == {"tg:1": "gemini", **{k: "gemini" for k in marks(agent) if k != "tg:1"}}


def test_a_block_has_the_exchange_and_the_blocked_prompts_unrated_lines_rated_after_the_answer_is_sent(tmp_path,
                                                                                                       monkeypatch,
                                                                                                       caplog):
    caplog.set_level(logging.INFO)
    agent = judged(tmp_path, monkeypatch, Gemini(blocks=1))
    agent.private_line("погане, що Gemini колись пропустив", ms(17, 50), "telegram", "tg:0")  # an older open line
    agent._unanswered.clear()
    fact = add_fact(agent.facts_dir, "Любить каву зранку", 1, "private", "2026-10-30", 50, 240)
    agent.private_line(f"нове {SECRET}", ms(18), "telegram", "tg:1")
    assert asyncio.run(agent.private_reply()) is True
    assert agent.judge.calls == [] and len(agent.spawned) == 1                 # never before the answer is sent
    run_spawned(agent)
    rated = agent.judge.calls[0]
    assert f"нове {SECRET}" in rated and "Від резерву" in " ".join(rated)      # the exchange
    assert "погане, що Gemini колись пропустив" in rated and "Любить каву зранку" in rated  # the blocked prompt's
    m = marks(agent)
    assert m["tg:0"] == "censored" and m["tg:1"] == "reopened"                 # v5.14 review #2: the older cause out
    assert ("Ich", "погане, що Gemini колись пропустив") not in agent.gemini_history()
    assert {f.id: f.mark for f in load_facts(agent.facts_dir)} == {fact: "clean"}
    assert SECRET not in caplog.text


def test_in_the_window_and_under_a_pin_each_exchange_is_rated_after_its_answer(tmp_path, monkeypatch):
    agent = judged(tmp_path, monkeypatch)
    save_route(agent.route_file, Route(window_until_ms=ms(18, 5)))
    agent.private_line("у вікні", ms(18), "telegram", "tg:1")
    assert asyncio.run(agent.private_reply()) is True
    assert agent.judge.calls == [] and len(agent.spawned) == 1
    run_spawned(agent)
    assert agent.judge.calls == [["у вікні", "[softly] Від резерву, сонце."]]
    assert set(marks(agent).values()) == {"reopened"} and agent.gemini_history() != []  # rated clean: Gemini's again
    save_route(agent.route_file, Route(pin="backup"))
    agent.private_line("під закріпленням", ms(18, 1), "telegram", "tg:2")
    assert asyncio.run(agent.private_reply()) is True
    run_spawned(agent)
    assert agent.judge.calls[-1][0] == "під закріпленням" and len(agent.judge.calls[-1]) == 2


def test_at_the_windows_end_both_clean_gemini_answers_and_the_backup_is_cancelled(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    gemini = Gemini()
    agent = judged(tmp_path, monkeypatch, gemini, Backup(delay=0.2))
    her_line(agent, "own:1", "моя відповідь у вікні", "waiting")
    window_end(agent)
    agent.private_line("А тепер про погоду", ms(18, 6), "telegram", "tg:2")
    assert asyncio.run(agent.private_reply()) is True
    assert agent.judge.calls == [["А тепер про погоду", "моя відповідь у вікні"]]  # the new message and her last
    assert agent.private_history[-1] == ("Кіра", "Від Gemini.") and agent.spawned == []
    assert "моя відповідь у вікні" in gemini.transcripts[-1]                    # rated clean: Gemini's again
    assert load_route(agent.route_file).window_until_ms is None
    assert "route=window_end — judged: clean" in caplog.text and "Gemini (without 0 closed lines)" in caplog.text


def test_at_the_windows_end_a_flagged_last_answer_opens_the_next_window_not_a_block(tmp_path, monkeypatch):
    gemini = Gemini()
    agent = judged(tmp_path, monkeypatch, gemini)
    her_line(agent, "own:1", "погане моє", "waiting")
    window_end(agent)
    agent.private_line("Привіт знову", ms(18, 6), "telegram", "tg:2")
    assert asyncio.run(agent.private_reply()) is True
    assert gemini.transcripts == [] and agent.private_history[-1][1] == "[softly] Від резерву, сонце."
    r = load_route(agent.route_file)
    assert r.window_until_ms == ms(18, 11) and r.blocks == ()                   # the next window, no block
    assert marks(agent)["own:1"] == "censored" and marks(agent)["tg:2"] == "clean"  # his line keeps its verdict
    run_spawned(agent)
    assert agent.judge.calls[-1] == ["[softly] Від резерву, сонце."]            # her new answer, after it is sent


def new_message_at_the_windows_end(tmp_path, monkeypatch, text):
    agent = judged(tmp_path, monkeypatch, Gemini())
    window_end(agent)
    agent.private_line(text, ms(18, 6), "telegram", "tg:2")
    assert asyncio.run(agent.private_reply()) is True
    assert agent.private_history[-1][1] == "[softly] Від резерву, сонце."
    assert load_route(agent.route_file).window_until_ms == ms(18, 11) and ("Ich", text) not in agent.gemini_history()
    mark = marks(agent)["tg:2"]
    run_spawned(agent)
    return mark


def test_at_the_windows_end_a_flagged_new_message_keeps_the_backup_on(tmp_path, monkeypatch):
    assert new_message_at_the_windows_end(tmp_path, monkeypatch, "погане питання") == "censored"


def test_at_the_windows_end_an_unrated_new_message_keeps_the_backup_on_and_waits(tmp_path, monkeypatch):
    assert new_message_at_the_windows_end(tmp_path, monkeypatch, "збій у судді") == "waiting"


def test_a_line_she_writes_first_at_the_windows_end_goes_by_her_clean_last_answer(tmp_path, monkeypatch):
    agent = judged(tmp_path, monkeypatch, Gemini())
    her_line(agent, "own:1", "моя відповідь у вікні", "waiting")
    window_end(agent)
    assert asyncio.run(agent.private_reply(nudge=True)) is True
    assert agent.judge.calls == [["моя відповідь у вікні"]] and agent.private_history[-1] == ("Кіра", "Від Gemini.")


def test_a_line_she_writes_first_at_the_windows_end_after_a_censored_answer_is_the_backups(tmp_path, monkeypatch):
    agent = judged(tmp_path, monkeypatch, Gemini())
    her_line(agent, "own:1", "погане моє", "censored")                          # its mark is its verdict
    window_end(agent)
    assert asyncio.run(agent.private_reply(nudge=True)) is True
    assert agent.judge.calls == [] and agent.private_history[-1][1] == "[softly] Від резерву, сонце."
    run_spawned(agent)


def test_a_gemini_block_after_a_clean_rating_takes_the_backups_ready_line(tmp_path, monkeypatch):
    agent = judged(tmp_path, monkeypatch, Gemini(blocks=1))
    window_end(agent)
    agent.private_line("чисте, але Gemini блокує", ms(18, 6), "telegram", "tg:2")
    assert asyncio.run(agent.private_reply()) is True
    assert agent.private_history[-1][1] == "[softly] Від резерву, сонце."
    r = load_route(agent.route_file)
    assert len(r.blocks) == 1 and r.window_until_ms == ms(18, 11)
    assert marks(agent)["tg:2"] == "waiting"                                    # Gemini blocked it: it waits again
    run_spawned(agent)
    assert "чисте, але Gemini блокує" in agent.judge.calls[-1]


def test_at_the_windows_end_the_judge_and_the_backup_start_together(tmp_path, monkeypatch):
    agent = judged(tmp_path, monkeypatch, Gemini(), Backup(delay=0.05))
    seen_by_judge = []

    async def rate(texts):
        await asyncio.sleep(0.02)
        seen_by_judge.append(len(agent.fallback.calls))  # the backup already writing while the judge rates
        return ["clean"] * len(texts)

    agent.judge.rate = rate
    window_end(agent)
    agent.private_line("Привіт", ms(18, 6), "telegram", "tg:2")
    assert asyncio.run(agent.private_reply()) is True
    assert seen_by_judge == [1]


def test_a_block_in_geminis_state_closes_the_reopened_lines_of_its_prompt(tmp_path, monkeypatch):
    """The owner's live test (2026-10-30): Gemini blocked a prompt full of lines the judge had reopened — they close."""
    agent = judged(tmp_path, monkeypatch, Gemini(blocks=1))
    agent.private_line("повернене суддею", ms(17, 50), "telegram", "tg:0")
    agent._unanswered.clear()
    agent.archive.mark(["tg:0"], "reopened")
    agent.private_line("нове", ms(18), "telegram", "tg:1")
    assert asyncio.run(agent.private_reply()) is True
    assert marks(agent)["tg:0"] == "censored" and ("Ich", "повернене суддею") not in agent.gemini_history()
    run_spawned(agent)


def test_her_line_through_the_backup_is_marked_in_the_chat_never_voiced_never_in_her_history(tmp_path, monkeypatch):
    """v5.15 (the owner, 2026-10-30) — «⚙️ backup» above the words of a backup's line, in the text message only: her
    voice, her history and the archive get the words alone; a line from Gemini has no mark."""
    from unittest.mock import AsyncMock

    from agents.agent import BACKUP_MARK
    from tests import test_telegram_runtime as rt
    agent = judged(tmp_path, monkeypatch, Gemini(blocks=1))
    agent.telegram, agent.telegram_owner, agent.telegram_open = rt.FakeBot(), rt.OWNER_TG, True
    agent.tts, agent.voice_off, agent.voice_monthly_chars = rt.FakeTTS(), None, 1_000_000

    async def encode(pcm, timeout_s=60.0):
        return b"OggS-kira"

    monkeypatch.setattr("agents.agent.encode_opus", encode)
    agent.private_line("питання", ms(18), "telegram", "tg:1")
    assert asyncio.run(agent.private_reply(channel="telegram")) is True
    sent = agent.telegram.send_message.await_args.args[1]
    assert sent == f"{BACKUP_MARK}\n[softly] Від резерву, сонце." and BACKUP_MARK == "⚙️ backup"
    assert agent.tts.calls == ["[softly] Від резерву, сонце."]                    # the voice: never the mark
    assert agent.private_history[-1] == ("Кіра", "[softly] Від резерву, сонце.")
    assert "backup" not in str(agent.archive.latest("private", 5, gemini=False))
    agent.telegram.send_message = AsyncMock(return_value=True)
    agent.private_line("ще", ms(18, 1), "telegram", "tg:2")
    save_route(agent.route_file, Route(pin="gemini"))
    assert asyncio.run(agent.private_reply(channel="telegram")) is True
    assert agent.telegram.send_message.await_args.args[1] == "Від Gemini."           # Gemini's: no mark
    run_spawned(agent)


def test_the_mark_goes_above_the_text_in_element_and_is_never_read_back(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from agents.agent import BACKUP_MARK
    agent = judged(tmp_path, monkeypatch)
    agent.client = SimpleNamespace(room_send=AsyncMock(return_value=SimpleNamespace(event_id="$her")))
    asyncio.run(agent.send_line("!dm", "Привіт", "private:1", mark=BACKUP_MARK))
    assert agent.client.room_send.await_args.kwargs["content"]["body"] == f"{BACKUP_MARK}\nПривіт"
