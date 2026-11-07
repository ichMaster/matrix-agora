"""v6.2 — two companions side by side: a second persona with every one of Кіра's capabilities (her TOML's) runs beside
her, and nothing of one reaches the other — her state files, archive, facts, talk, photos and videos, route, usage,
Telegram state and selfie are her own, and a command or a cap of one never reads or writes the other's (nio, Gemini,
the image model, Telegram and the archive's embeddings mocked; made-up lines only)."""

import asyncio
import tomllib
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agents import agent as agent_mod
from agents.config import AgentConfig
from agents.llm import GeminiClient
from agents.roster import load_roster, parse_member
from agents.telegram import TelegramState, load_telegram_state, save_telegram_state
from tests.test_archive import EmbedLLM
from tests.test_private_runtime import OWNER, ms

ROOT = Path(__file__).resolve().parents[1]
KIRAS = parse_member("kira", tomllib.loads((ROOT / "agents" / "kira.toml").read_text(encoding="utf-8"))).capabilities
NATALS = {"kira": "Народження: 09.03.2003, 04:10, Донецьк.", "ustyna": "Народження: 01.11.2004, 23:00, Львів."}
NAMES = {"kira": "Кіра", "ustyna": "Устина"}
ROSTER = load_roster("agora", ROOT / "simulations.toml", ROOT / "agents")


class Embeds(EmbedLLM, GeminiClient):
    """The archive's embeddings as `EmbedLLM` gives them, and a `GeminiClient`, so her photo maker is built."""

    def __init__(self, sink=None):
        EmbedLLM.__init__(self)


def companion(localpart):
    cfg = AgentConfig(name=NAMES[localpart], user_id=f"@{localpart}:agora.lan", canon="Канон.", homeserver="http://hs",
                      room_id="!agora", owner=OWNER, password="pw", capabilities=KIRAS, natal=NATALS[localpart])
    agent = agent_mod.Agent(cfg, llm=Embeds(), roster=ROSTER)
    agent.client = SimpleNamespace(room_send=AsyncMock(), room_typing=AsyncMock(), rooms={}, invited_rooms={})
    agent.started, agent.started_ms, agent.clock = True, ms(8), lambda: ms(18)
    agent._spawn = lambda coro: coro.close()
    return agent


@pytest.fixture
def pair(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TIMEZONE", "Europe/Kyiv")
    for name in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_OWNER_ID", "FAL_KEY", "NOVELAI_API_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    (tmp_path / "state").mkdir()
    built = []
    monkeypatch.setattr(agent_mod, "photo_maker", lambda *a: built.append(a) or SimpleNamespace(args=a))
    monkeypatch.setattr(agent_mod, "load_faces", lambda folder: [(f"{folder.name[:-5]}.png", b"x", "image/png")])
    monkeypatch.setattr(agent_mod, "load_look", lambda path: f"look of {path.name}")
    monkeypatch.setattr(agent_mod, "clip_maker", lambda *a: object())                  # Omni: no client here
    agents = {name: companion(name) for name in ("kira", "ustyna")}
    yield agents, built
    for agent in agents.values():
        if agent.archive is not None:
            agent.archive.close()


def test_kiras_capabilities_are_every_one_a_second_companion_gets():
    assert {"private", "telegram", "recall", "facts", "photos", "videos", "fallback", "talk", "mood"} <= KIRAS


def test_every_state_file_of_one_is_her_own(pair):
    agents, _ = pair
    paths = {}
    for name, agent in agents.items():
        mine = [agent.cfg.state_file, agent.cfg.memory_file, agent.private_file, agent.telegram_file, agent.facts_dir,
                agent.route_file, agent.usage_file, agent.answers_file, agent._dir("photos"), agent._dir("videos"),
                agent._dir("days"), Path(agent.archive.path)]
        paths[name] = set(mine)
        assert all(p.name.startswith(f"{name}.") for p in paths[name]), name
    assert not paths["kira"] & paths["ustyna"]


def test_each_selfie_is_its_persons_own_main_face_age_and_look(pair):
    _, built = pair
    by_face = {a[4]: a for a in built}
    assert set(by_face) == {"kira.png", "ustyna.png"}
    assert by_face["kira.png"][5] == date(2003, 3, 9) and by_face["kira.png"][6] == "look of kira.look.md"
    assert by_face["ustyna.png"][5] == date(2004, 11, 1) and by_face["ustyna.png"][6] == "look of ustyna.look.md"
    assert [f[0] for f in by_face["ustyna.png"][2]] == ["ustyna.png"]                  # her own face folder


def test_a_cap_of_one_counts_her_own_photos_and_videos_alone(pair):
    agents, _ = pair
    kira, ustyna = agents["kira"], agents["ustyna"]
    day = agent_mod.local_now(kira.clock(), kira.tz).date().isoformat()
    for kind in ("photos", "videos"):
        folder = kira._dir(kind) / day
        folder.mkdir(parents=True)
        (folder / "120000.jpg").write_bytes(b"x")
    assert kira.photos_today() == 1 and ustyna.photos_today() == 0


def test_her_archive_and_a_command_on_it_are_hers_alone(pair):
    agents, _ = pair
    kira, ustyna = agents["kira"], agents["ustyna"]
    for agent in (kira, ustyna):
        agent._archive(f"$h-{agent.cfg.localpart}", ms(17), "private", "matrix", "Ich", "привіт")
        agent._archive(f"$s-{agent.cfg.localpart}", ms(17, 1), "private", "matrix", agent.cfg.name, "привіт і тобі")
    answer = ustyna.unblock_answer()                                                   # her /unblock
    assert answer.startswith("⚙️ Закрито для gemini")

    def marks(agent):
        return dict(agent.archive.db.execute("SELECT mark, COUNT(*) FROM lines GROUP BY mark").fetchall())

    assert marks(ustyna).get("blocked") == 2
    assert "blocked" not in marks(kira) and sum(marks(kira).values()) == 2              # Кіра's lines untouched


def test_her_telegram_state_is_her_own(pair):
    agents, _ = pair
    kira, ustyna = agents["kira"], agents["ustyna"]
    save_telegram_state(kira.telegram_file, TelegramState(offset=41, seen_ms=ms(17)))
    assert load_telegram_state(ustyna.telegram_file).offset != 41
    assert load_telegram_state(kira.telegram_file).offset == 41


def test_the_panel_lists_both_with_their_capabilities(tmp_path):
    from panel.registry import Registry
    sims = tmp_path / "simulations.toml"
    sims.write_text((ROOT / "simulations.toml").read_text(encoding="utf-8").replace('"kira", "kit"', '"kira", "ustyna", "kit"'),
                    encoding="utf-8")
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    kira_toml = (ROOT / "agents" / "kira.toml").read_text(encoding="utf-8")
    (agents_dir / "kira.toml").write_text(kira_toml, encoding="utf-8")
    (agents_dir / "ustyna.toml").write_text(
        kira_toml.replace('name = "Кіра"', 'name = "Устина"', 1).replace("@kira:agora.lan", "@ustyna:agora.lan")
        .replace('"kira"]', '"ustyna"]').replace('name_forms = ["кіра", "кіри", "кірі", "кіру", "кірою", "кіро", ',
                                                  'name_forms = ["устина", "устини", "устині", "устину", "устиною", '),
        encoding="utf-8")
    found = Registry(sims, agents_dir).agents
    assert {"kira", "ustyna"} <= set(found)
    for name in ("kira", "ustyna"):
        assert {"private", "talk", "facts", "photos", "videos"} <= set(found[name].capabilities), name
