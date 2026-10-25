"""v5.9 (AGORA-121) — the panel shows what a Gemini speaker runs on: its answers' and background models, its voice,
and Кіра's emotion palette; never the voice id or the palette's text; an unreadable file is null, never a 500."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from panel.app import create_app
from panel.docker_read import DockerReader
from panel.health import Prober
from panel.memory import models_view
from panel.registry import Registry

TOKEN = "t" * 32
AUTH = {"Authorization": f"Bearer {TOKEN}"}
ROOT = Path(__file__).resolve().parent.parent


def settings(**values):
    return json.dumps({k: {"value": v, "source": "env"} for k, v in values.items()})


@pytest.fixture
def state(tmp_path):
    s = tmp_path / "state"
    s.mkdir()
    (s / "kira.settings.json").write_text(settings(
        GEMINI_MODEL="gemini-2.5-flash", GEMINI_REPLY_MODEL="gemini-3.1-pro-preview", GEMINI_THINKING_LEVEL="low",
        ELEVENLABS_MODEL="eleven_v4_turbo", VOICE_STABILITY="0.3", VOICE_SPEED="1.0", VOICE_ID="KiraVoiceSecret12345"))
    (s / "ada.settings.json").write_text(settings(GEMINI_MODEL="gemini-2.5-flash", GEMINI_REPLY_MODEL="",
                                                  ELEVENLABS_MODEL="eleven_turbo_v2_5", VOICE_STABILITY="0.5"))
    return s


@pytest.fixture
def client(state):
    reg = Registry()
    return TestClient(create_app(token=TOKEN, registry=reg, docker_reader=DockerReader(client_factory=lambda: None),
                                 prober=Prober(reg), state_dir=state, background=False))


def test_kiras_card_shows_her_models_her_voice_and_her_palette(client):
    m = client.get("/api/agents/kira/memory", headers=AUTH).json()["models"]
    assert (m["answers"], m["background"], m["thinking"]) == ("gemini-3.1-pro-preview", "gemini-2.5-flash", "low")
    assert m["voice"] == {"model": "eleven_v4_turbo", "stability": "0.3", "speed": "1.0"}
    assert m["emotion"]["performed"] is True and "[laughs]" in m["emotion"]["tags"] and len(m["emotion"]["tags"]) == 10
    raw = json.dumps(m)
    assert "KiraVoiceSecret" not in raw and "Здебільшого" not in raw            # no voice id, no palette text


def test_a_plain_speaker_has_one_model_and_no_palette(client):
    m = client.get("/api/agents/ada/memory", headers=AUTH).json()["models"]
    assert (m["answers"], m["background"], m["thinking"]) == ("gemini-2.5-flash", "gemini-2.5-flash", None)
    assert m["voice"]["model"] == "eleven_turbo_v2_5" and m["emotion"] is None


def test_claude_and_hermes_have_no_models_view(client):
    assert client.get("/api/agents/claude/memory", headers=AUTH).json()["models"] is None
    assert client.get("/api/agents/hermes/memory", headers=AUTH).json()["models"] is None


def test_an_unreadable_settings_file_is_null(state):
    (state / "kira.settings.json").write_text("{torn")
    assert models_view(state, "kira") is None
    assert models_view(state, "nobody") is None


def test_a_palette_on_a_model_that_reads_tags_aloud_says_so(state):
    (state / "kira.settings.json").write_text(settings(GEMINI_MODEL="gemini-2.5-flash",
                                                       ELEVENLABS_MODEL="eleven_turbo_v2_5"))
    m = models_view(state, "kira", ROOT / "agents" / "canon" / "kira.voice.md")
    assert m["emotion"]["performed"] is False and m["emotion"]["tags"]


def test_the_registry_carries_the_palette_path():
    assert Registry().agents["kira"].voice_spec == "agents/canon/kira.voice.md"
    assert Registry().agents["ada"].voice_spec == ""
