"""v5.14 — the owner's Telegram commands for her route: `/status`, `/auto`, `/gemini`, `/backup` and the list; a service
line, never voiced, never a trace in her talk (a fake bot; no network)."""

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from agents.route import Route, load_route, save_route, status_text
from agents.telegram import COMMANDS, TelegramBot, command_of
from tests.test_telegram_runtime import OWNER_TG, STRANGER, TOKEN, kira, ms, run_batch, texts_sent, tg

TZ = "Europe/Kyiv"


def with_backup(agent):
    agent.cfg = agent.cfg.__class__(**{**agent.cfg.__dict__, "capabilities": agent.cfg.capabilities | {"fallback"}})
    agent.fallback_responder = object()  # on: the commands may pin
    return agent


def untouched(agent):
    return (agent.private_history, agent.session, agent._unanswered, agent.last_private_ms)


def test_command_names():
    assert [command_of(t) for t in ("/status", "/Status@ich_kira_bot", "/backup now", "/", "")] == [
        "status", "status", "backup", "", ""]


def test_status_answers_with_one_service_line_and_leaves_no_trace(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    agent = with_backup(kira(tmp_path, monkeypatch))
    before = tuple(list(x) if isinstance(x, list) else x for x in untouched(agent))
    spawned = run_batch(agent, tg(1, "/status", at=ms(17, 30)))
    sent = texts_sent(agent)
    assert len(sent) == 1 and sent[0].startswith("⚙️ Маршрут — auto: gemini") and "з 10" in sent[0]
    assert not spawned and agent.telegram.send_voice.await_count == 0          # never her answer, never voiced
    assert untouched(agent) == before
    assert "telegram: command status" in caplog.text and str(OWNER_TG) not in caplog.text


def test_the_pins_and_auto(tmp_path, monkeypatch):
    agent = with_backup(kira(tmp_path, monkeypatch))
    agent.route_file.parent.mkdir(parents=True, exist_ok=True)
    run_batch(agent, tg(1, "/backup", at=ms(17, 30)))
    assert load_route(agent.route_file).pin == "backup"
    assert "Маршрут — backup (закріплено о 18:00; скасувати: /auto)" in texts_sent(agent)[-1]
    assert "резерв" not in texts_sent(agent)[-1]
    run_batch(agent, tg(2, "/gemini", at=ms(17, 31)))
    assert load_route(agent.route_file).pin == "gemini"
    run_batch(agent, tg(3, "/auto", at=ms(17, 32)))
    assert load_route(agent.route_file).pin == "auto" and "auto: gemini" in texts_sent(agent)[-1]


def test_an_unknown_command_gets_the_list(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    agent = with_backup(kira(tmp_path, monkeypatch))
    run_batch(agent, tg(1, "/start", at=ms(17, 30)))
    assert all(f"/{name}" in texts_sent(agent)[-1] for name, _ in COMMANDS)
    assert "telegram: command unknown" in caplog.text


def test_without_the_backup_a_pin_says_so(tmp_path, monkeypatch):
    agent = kira(tmp_path, monkeypatch)
    run_batch(agent, tg(1, "/backup", at=ms(17, 30)))
    assert "Backup вимкнено" in texts_sent(agent)[-1] and not agent.route_file.exists()


def test_a_strangers_command_and_one_from_before_the_start_are_ignored(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    agent = with_backup(kira(tmp_path, monkeypatch))
    run_batch(agent, tg(1, "/backup", sender=STRANGER, at=ms(17, 30)), tg(2, "/backup", at=ms(7)))
    assert texts_sent(agent) == [] and not agent.route_file.exists()
    assert "ignored: stranger" in caplog.text and "ignored: command" in caplog.text


def test_the_status_text():
    now = 1_761_670_000_000
    window = status_text(Route(window_until_ms=now + 120_000), now, TZ, 10, 3, 1, {"gemini": 4, "backup": 2}, 1, 2)
    assert "auto: backup до" in window and "за годину 1, сьогодні 2 з 10" in window
    assert "чекають на суддю 3, цензуровані 1" in window and "через gemini 4, через backup 2" in window
    pinned = status_text(Route(pin="backup", pinned_at_ms=now), now, TZ, 10, 0, 0, {"gemini": 0, "backup": 0}, 0, 0)
    assert "Маршрут — backup (закріплено о" in pinned and "скасувати: /auto" in pinned and "резерв" not in pinned
    assert pinned.endswith("Суддя: вимкнено")                                         # v5.15: no judge
    judged = status_text(Route(), now, TZ, 10, 4, 1, {"gemini": 0, "backup": 0}, 0, 0, {"rated": 25, "flagged": 3})
    assert judged.endswith("Суддя: оцінено сьогодні 25, позначено 3, чекають 4")


def test_status_shows_the_judges_day(tmp_path, monkeypatch):
    """v5.15 — `/status` with the judge on: today's ratings from the route file, the waiting lines from the archive."""
    from agents.route import Route, day_bounds, save_route
    from tests.test_judge_verdicts import FakeJudge
    agent = with_talk(tmp_path, monkeypatch)
    agent.judge = FakeJudge()
    today = day_bounds(agent.clock(), agent.tz)[0]
    save_route(agent.route_file, Route(day=today, judged={"rated": 7, "flagged": 2}))
    assert agent.status_answer().endswith("Суддя: оцінено сьогодні 7, позначено 2, чекають 2")
    agent.judge = None
    assert "Суддя: вимкнено" in agent.status_answer()


def test_the_days_counts_come_from_her_usage_lines_the_whole_day():
    """The owner's live test: «через Gemini 0» after a day of Gemini's answers — the counts are the day's, not the
    route file's since the deploy."""
    from agents.route import day_counts
    from agents.usage import fallback_usage_line, usage_line
    lines = [usage_line("2026-10-28T09:00:00+02:00", "kira", "private", "gemini-3.1-pro-preview", None, True),
             usage_line("2026-10-28T20:21:00+02:00", "kira", "private", "gemini-3.1-pro-preview", None, False,
                        "refusal"),
             usage_line("2026-10-28T20:50:00+02:00", "kira", "private_nudge", "gemini-3.1-pro-preview", None, False,
                        "prompt"),
             usage_line("2026-10-28T20:55:00+02:00", "kira", "summary", "gemini-2.5-flash", None, True),  # not an answer
             usage_line("2026-10-28T21:00:00+02:00", "kira", "private", "gemini-3.1-pro-preview", None, False),
             fallback_usage_line("2026-10-28T21:25:00+02:00", "kira", "private", "glm-4-6", True),
             usage_line("2026-10-27T21:00:00+02:00", "kira", "private", "gemini-3.1-pro-preview", None, True)]
    now = int(datetime(2026, 10, 28, 21, 30, tzinfo=ZoneInfo(TZ)).timestamp() * 1000)
    assert day_counts(lines, "2026-10-28", now) == ({"gemini": 1, "backup": 1}, 1, 2)


def test_the_command_list_is_set_for_the_owners_chat_only(monkeypatch):
    bot, calls = TelegramBot(TOKEN), []

    async def call(method, timeout_s, json_body=None, data=None):
        calls.append((method, json_body))
        from agents.telegram import Reply
        return Reply(True, True)

    monkeypatch.setattr(bot, "_call", call)
    assert asyncio.run(bot.set_commands(OWNER_TG)) is True
    method, body = calls[0]
    assert method == "setMyCommands" and body["scope"] == {"type": "chat", "chat_id": OWNER_TG}
    assert [c["command"] for c in body["commands"]] == ["status", "auto", "gemini", "backup", "purge"]


def test_a_saved_window_shows_in_status(tmp_path, monkeypatch):
    agent = with_backup(kira(tmp_path, monkeypatch))
    agent.route_file.parent.mkdir(parents=True, exist_ok=True)
    save_route(agent.route_file, Route(window_until_ms=ms(18, 5)))
    run_batch(agent, tg(1, "/status", at=ms(17, 30)))
    assert "auto: backup до 18:05" in texts_sent(agent)[-1]


# --- /purge: the backup's talk deleted, at the owner's word, after a confirmation ----------------------------------------
def with_talk(tmp_path, monkeypatch):
    from agents.archive import Archive
    from agents.facts import add_fact
    agent = with_backup(kira(tmp_path, monkeypatch))
    agent.archive = Archive(tmp_path / "kira.archive.db")
    agent.facts_dir, agent.facts_in_prompt, agent.fact_max_chars = tmp_path / "kira.facts", 10, 240
    for key, speaker, text, mark in (("tg:1", "Ich", "відкритий рядок", "gemini"), ("tg:2", "Ich", "закритий рядок", "waiting"),
                                     ("own:1", "Кіра", "відповідь backup", "waiting"),
                                     ("tg:3", "Ich", "давня відмова", "censored")):
        agent.archive.append(key, ms(17), "private", "telegram", speaker, text)
        agent.archive.mark([key], mark)
        agent.private_history.append((speaker, text))
        if mark != "gemini":
            agent._closed.add((speaker, text))
    add_fact(agent.facts_dir, "Відкритий факт", 1, "private", "2026-10-30", 50, 240)
    add_fact(agent.facts_dir, "Факт від backup", 1, "asked", "2026-10-30", 50, 240, mark="waiting")
    return agent


def test_purge_asks_first_then_deletes_only_the_backups_talk(tmp_path, monkeypatch, caplog):
    from agents.facts import load_facts
    caplog.set_level(logging.INFO)
    agent = with_talk(tmp_path, monkeypatch)
    run_batch(agent, tg(1, "/purge", at=ms(17, 30)))
    assert "3 рядків і 1 фактів" in texts_sent(agent)[-1] and "/purge yes" in texts_sent(agent)[-1]
    assert agent.archive.closed_count() == 3                              # nothing gone yet
    run_batch(agent, tg(2, "/purge yes", at=ms(17, 31)))
    assert "Видалено розмову через backup: 3 рядків, 1 фактів" in texts_sent(agent)[-1]
    assert agent.archive.closed_count() == 0 and agent.archive.counts()[0] == 2  # the open line and the open fact
    assert [f.text for f in load_facts(agent.facts_dir)] == ["Відкритий факт"]
    assert agent.private_history == [("Ich", "відкритий рядок")] and agent._closed == set()
    assert agent.archive.search_words("закритий", ("private",), gemini=False) == []  # out of the word index too
    assert "закритий" not in caplog.text and "purge: the backup's talk deleted (3 lines, 1 facts)" in caplog.text


def test_purge_yes_without_asking_or_too_late_only_asks(tmp_path, monkeypatch):
    agent = with_talk(tmp_path, monkeypatch)
    run_batch(agent, tg(1, "/purge yes", at=ms(17, 30)))                  # never asked: it asks now
    assert "Не скасувати" in texts_sent(agent)[-1] or "не скасувати" in texts_sent(agent)[-1]
    assert agent.archive.closed_count() == 3
    agent.clock = lambda: ms(18, 3)                                        # more than two minutes later
    run_batch(agent, tg(2, "/purge yes", at=ms(18, 3)))
    assert agent.archive.closed_count() == 3 and "/purge yes" in texts_sent(agent)[-1]
