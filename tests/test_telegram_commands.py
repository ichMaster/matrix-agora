"""v5.14 — the owner's Telegram commands for her route: `/status`, `/auto`, `/gemini`, `/backup` and the list; a service
line, never voiced, never a trace in her talk (a fake bot; no network)."""

import asyncio
import logging

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
    assert len(sent) == 1 and sent[0].startswith("⚙️ Маршрут — авто: Gemini") and "з 10" in sent[0]
    assert not spawned and agent.telegram.send_voice.await_count == 0          # never her answer, never voiced
    assert untouched(agent) == before
    assert "telegram: command status" in caplog.text and str(OWNER_TG) not in caplog.text


def test_the_pins_and_auto(tmp_path, monkeypatch):
    agent = with_backup(kira(tmp_path, monkeypatch))
    agent.route_file.parent.mkdir(parents=True, exist_ok=True)
    run_batch(agent, tg(1, "/backup", at=ms(17, 30)))
    assert load_route(agent.route_file).pin == "backup" and "закріплено: резерв" in texts_sent(agent)[-1]
    run_batch(agent, tg(2, "/gemini", at=ms(17, 31)))
    assert load_route(agent.route_file).pin == "gemini"
    run_batch(agent, tg(3, "/auto", at=ms(17, 32)))
    assert load_route(agent.route_file).pin == "auto" and "авто: Gemini" in texts_sent(agent)[-1]


def test_an_unknown_command_gets_the_list(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    agent = with_backup(kira(tmp_path, monkeypatch))
    run_batch(agent, tg(1, "/start", at=ms(17, 30)))
    assert all(f"/{name}" in texts_sent(agent)[-1] for name, _ in COMMANDS)
    assert "telegram: command unknown" in caplog.text


def test_without_the_backup_a_pin_says_so(tmp_path, monkeypatch):
    agent = kira(tmp_path, monkeypatch)
    run_batch(agent, tg(1, "/backup", at=ms(17, 30)))
    assert "Резерв вимкнено" in texts_sent(agent)[-1] and not agent.route_file.exists()


def test_a_strangers_command_and_one_from_before_the_start_are_ignored(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    agent = with_backup(kira(tmp_path, monkeypatch))
    run_batch(agent, tg(1, "/backup", sender=STRANGER, at=ms(17, 30)), tg(2, "/backup", at=ms(7)))
    assert texts_sent(agent) == [] and not agent.route_file.exists()
    assert "ignored: stranger" in caplog.text and "ignored: command" in caplog.text


def test_the_status_text():
    now = 1_761_670_000_000
    r = Route(blocks=(now - 600_000, now - 7_200_000), window_until_ms=now + 120_000, day="2026-10-28",
              answers={"gemini": 4, "backup": 2})
    text = status_text(r, now, TZ, "2026-10-28", now - 10_000_000, 10, 3, 1)
    assert "авто: резерв до" in text and "за годину 1, сьогодні 2 з 10" in text
    assert "чекають на суддю 3, цензуровані 1" in text and "через Gemini 4, через резерв 2" in text
    pinned = status_text(Route(pin="backup", pinned_at_ms=now), now, TZ, "2026-10-29", now, 10, 0, 0)
    assert "закріплено: резерв" in pinned and "через Gemini 0, через резерв 0" in pinned


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
    assert [c["command"] for c in body["commands"]] == ["status", "auto", "gemini", "backup"]


def test_a_saved_window_shows_in_status(tmp_path, monkeypatch):
    agent = with_backup(kira(tmp_path, monkeypatch))
    agent.route_file.parent.mkdir(parents=True, exist_ok=True)
    save_route(agent.route_file, Route(window_until_ms=ms(18, 5)))
    run_batch(agent, tg(1, "/status", at=ms(17, 30)))
    assert "авто: резерв до 18:05" in texts_sent(agent)[-1]
