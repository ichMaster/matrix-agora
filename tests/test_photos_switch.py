"""v6.5 (AGORA-235) — the owner's switch of her photos: `/photos fal|google` in her Telegram, for a person with
`photos_fal` only; kept in `state/<name>.photos.json` across a restart; under `fal` her photo goes through the request
and Seedream, a video's frame stays on Google (a fake bot, fake makers; no network; made-up lines)."""

import asyncio
import logging
import os
import stat
from datetime import date

import pytest

from agents.falphoto import load_photo_route, save_photo_route
from agents.photo import Made, Shot
from agents.telegram import COMMANDS, TelegramBot, command_help, commands_for
from tests.test_photo_route import Maker
from tests.test_telegram_runtime import OWNER_TG, TOKEN, kira, ms, run_batch, texts_sent, tg


class FalMaker:
    """Seedream on fal: one `Made` for every shot; keeps each shot and its request."""

    def __init__(self, made=None):
        self.made, self.calls = made or Made(b"FAL-JPEG", "image/jpeg", "ok"), []

    async def make(self, shot, prompt):
        self.calls.append((shot, prompt))
        return self.made


def switchable(agent, fal=True):
    agent.cfg = agent.cfg.__class__(**{**agent.cfg.__dict__,
                                       "capabilities": agent.cfg.capabilities | {"photos", "photos_fal"}})
    agent.photos, agent.photo_day_max = Maker(), 40
    agent.fal_photos = FalMaker() if fal else None
    agent.photo_birth, agent.photo_look = date(2004, 11, 1), "Light grey eyes."
    return agent


def test_the_route_file_defaults_to_google_and_is_private(tmp_path):
    path = tmp_path / "ustyna.photos.json"
    assert load_photo_route(path) == "google"
    path.write_text("{not json")
    assert load_photo_route(path) == "google"
    save_photo_route(path, "fal")
    assert load_photo_route(path) == "fal" and stat.S_IMODE(os.stat(path).st_mode) == 0o600
    with pytest.raises(ValueError):
        save_photo_route(path, "pulid")


def test_photos_fal_and_google_and_the_bare_command_answer_one_service_line(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    agent = switchable(kira(tmp_path, monkeypatch))
    run_batch(agent, tg(1, "/photos", at=ms(17, 30)))
    assert texts_sent(agent)[-1] == "⚙️ Фото: google"
    run_batch(agent, tg(2, "/photos fal", at=ms(17, 31)))
    assert texts_sent(agent)[-1] == "⚙️ Фото: fal (Seedream, фільтр вимкнено)"
    assert load_photo_route(agent.photo_route_file) == "fal" and agent.photo_route() == "fal"
    run_batch(agent, tg(3, "/photos google", at=ms(17, 32)))
    assert texts_sent(agent)[-1] == "⚙️ Фото: google" and agent.photo_route() == "google"
    assert agent.telegram.send_voice.await_count == 0 and "telegram: command photos" in caplog.text


def test_the_switch_survives_a_restart(tmp_path, monkeypatch):
    agent = switchable(kira(tmp_path, monkeypatch))
    run_batch(agent, tg(1, "/photos fal", at=ms(17, 30)))
    again = switchable(kira(tmp_path, monkeypatch))                     # a new agent over the same state
    assert again.photo_route_file == agent.photo_route_file and again.photo_route() == "fal"


def test_closed_without_photos_fal_and_fal_refused_without_its_maker(tmp_path, monkeypatch):
    agent = kira(tmp_path, monkeypatch)
    run_batch(agent, tg(1, "/photos fal", at=ms(17, 30)))
    assert texts_sent(agent)[-1] == "⚙️ Перемикач фото закритий"
    assert not agent.photo_route_file.exists()
    agent = switchable(kira(tmp_path, monkeypatch), fal=False)
    run_batch(agent, tg(2, "/photos fal", at=ms(17, 31)))
    assert texts_sent(agent)[-1] == "⚙️ fal недоступний: фото лишаються в google" and agent.photo_route() == "google"
    save_photo_route(agent.photo_route_file, "fal")                     # saved before the key went: still google
    assert agent.photo_route() == "google"


def test_the_menu_holds_photos_only_for_a_person_with_the_switch(monkeypatch):
    assert commands_for(False) == COMMANDS and "photos" not in [n for n, _ in COMMANDS]
    assert commands_for(True)[-1] == ("photos", "Фото: google чи fal") and "/photos" in command_help(commands_for(True))
    bot, calls = TelegramBot(TOKEN), []

    async def call(method, timeout_s, json_body=None, data=None):
        calls.append(json_body)
        from agents.telegram import Reply
        return Reply(True, True)

    monkeypatch.setattr(bot, "_call", call)
    asyncio.run(bot.set_commands(OWNER_TG, commands_for(True)))
    assert [c["command"] for c in calls[0]["commands"]][-1] == "photos"


def test_under_fal_a_photo_goes_through_the_request_and_seedream_and_a_frame_stays_on_google(tmp_path, monkeypatch):
    agent = switchable(kira(tmp_path, monkeypatch))
    agent.fallback = None                                                # the template
    save_photo_route(agent.photo_route_file, "fal")
    made = asyncio.run(agent._make_photo(Shot("selfie", "я з чаєм біля вікна")))
    assert made.image == b"FAL-JPEG" and agent.photos.shots == []
    shot, prompt = agent.fal_photos.calls[0]
    assert shot.kind == "selfie" and "She is an adult woman, 2" in prompt and "я з чаєм" in prompt  # her age that day
    asyncio.run(agent._make_photo(Shot("selfie", "кружечок"), "1:1", "a frame line", "frame"))
    assert agent.photos.kinds == ["frame"] and len(agent.fal_photos.calls) == 1   # Omni Flash is Google's
    save_photo_route(agent.photo_route_file, "google")
    asyncio.run(agent._make_photo(Shot("photo", "чашка на підвіконні")))
    assert agent.photos.kinds == ["frame", "photo"] and len(agent.fal_photos.calls) == 1


def test_the_caps_and_the_door_are_the_same_on_both_routes(tmp_path, monkeypatch):
    agent = switchable(kira(tmp_path, monkeypatch))
    save_photo_route(agent.photo_route_file, "fal")
    assert agent._photo_closed("telegram") is None and agent._photo_closed("matrix") == "element"
    agent.photo_day_max = 0
    assert agent._photo_closed("telegram") == "off"
