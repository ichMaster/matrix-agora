"""v5.8 — the archive (`recall`): the SQLite store with its word and meaning searches, the pure fusion and pick, and
the agent's appends, embedding ticks, first fill and private seed (nio and Gemini mocked; SQLite in a temp dir)."""

import asyncio
import logging
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import numpy as np
import pytest

from agents.agent import Agent
from agents.archive import Archive, Line, cosine_top, fuse, pick_recall, words_query
from agents.config import AgentConfig
from agents.roster import RosterError, parse_member
from tests.test_private_runtime import AGORA, DM, KIRA, OWNER, SECRET, KindLLM, ms, text


@pytest.fixture
def arc(tmp_path):
    a = Archive(tmp_path / "kira.archive.db")
    yield a
    a.close()


# --- the store -------------------------------------------------------------------------------------------------------
def test_the_file_is_private_and_a_line_is_kept_once(arc, tmp_path):
    assert os.stat(tmp_path / "kira.archive.db").st_mode & 0o777 == 0o600
    assert arc.append("$1", ms(10), "agora", "matrix", "Ада", "Зорі сьогодні яскраві") is True
    assert arc.append("$1", ms(10), "agora", "matrix", "Ада", "Зорі сьогодні яскраві") is False  # the same key
    assert arc.append("$2", ms(11), "agora", "matrix", "Ада", "   ") is False                     # nothing to keep
    assert arc.append("$3", ms(11), "elsewhere", "matrix", "Ада", "текст") is False                # an unknown place
    assert arc.counts() == (1, 0)


def test_the_word_search_finds_ukrainian_within_its_places(arc):
    arc.append("$a", ms(9), "agora", "matrix", "Бруно", "Їдемо на Тустань лазити по скелях")
    arc.append("$b", ms(10), "private", "telegram", "Ich", "Я мрію про Тустань восени")
    arc.append("$c", ms(11), "agora", "matrix", "Ада", "Переклад книжки про космос")
    assert set(arc.search_words("тустань", ["agora", "private"])) == {1, 2}
    assert arc.search_words("Тустань!", ["agora"]) == [1]                    # the place filter is the query's
    assert arc.search_words("на по", ["agora"]) == []                        # no word longer than 2 characters
    assert arc.search_words('"; DROP TABLE lines; --', ["agora"]) == []      # quoted, never FTS syntax


def test_embeddings_and_the_meaning_search(arc):
    for i, t in enumerate(["перше", "друге", "третє"]):
        arc.append(f"${i}", ms(9 + i), "agora", "matrix", "Ада", t)
    assert [i for i, _ in arc.unembedded(2)] == [1, 2]
    arc.set_embeddings([(1, [1.0, 0.0]), (2, [0.0, 1.0]), (3, [0.7, 0.7])])
    assert arc.unembedded(10) == [] and arc.counts() == (3, 3)
    ids, matrix = arc.vectors(["agora"])
    assert cosine_top([1.0, 0.1], ids, matrix, 2) == [1, 3]
    assert arc.vectors(["private"]) == ([], None) and cosine_top([1.0], [], None) == []


def test_around_and_latest_stay_in_their_place(arc):
    arc.append("$p1", ms(9), "private", "matrix", "Ich", "раз")
    arc.append("$a1", ms(10), "agora", "matrix", "Ада", "агора")
    arc.append("$p2", ms(11), "private", "telegram", "Кіра", "два")
    arc.append("$p3", ms(12), "private", "matrix", "Ich", "три")
    middle = arc.lines([3])[3]
    assert [line.text for line in arc.around(middle, 1)] == ["раз", "два", "три"]
    assert [line.text for line in arc.latest("private", 2)] == ["два", "три"]
    assert [line.text for line in arc.latest("agora", 5, since_ms=ms(11))] == []


# --- the pure parts ---------------------------------------------------------------------------------------------------
def test_words_query():
    assert words_query("Як там Тустань? Ми ж їздили!") == '"там" OR "Тустань" OR "їздили"'
    assert words_query("а б") is None and words_query("") is None


def test_reciprocal_rank_fusion_rewards_agreement():
    assert fuse([1, 2, 3], [3, 1, 4]) == [1, 3, 2, 4]
    assert fuse([], [5, 6]) == [5, 6] and fuse() == []


def test_the_pick_leaves_out_what_the_prompt_already_holds():
    lines = {i: Line(i, f"${i}", i, "agora", "matrix", "Ада", t) for i, t in enumerate(["а", "б", "в", "г"])}
    assert [line.text for line in pick_recall([0, 1, 2, 3, 9], lines, {("Ада", "б")}, 2)] == ["а", "в"]


# --- the capability ---------------------------------------------------------------------------------------------------
def test_recall_is_a_persons_capability():
    assert parse_member("kira", {"name": "Кіра", "user_id": KIRA, "capabilities": {"recall": True}},
                        "kira.toml").can("recall")
    with pytest.raises(RosterError, match="'recall' belongs to the persona type only"):
        parse_member("kit", {"name": "Кіт", "user_id": "@kit:agora.lan", "type": "creature",
                             "capabilities": {"recall": True}}, "kit.toml")


# --- the agent --------------------------------------------------------------------------------------------------------
class EmbedLLM(KindLLM):
    def __init__(self, fail=False):
        super().__init__()
        self.embedded, self.fail = [], fail

    async def embed(self, texts, task="RETRIEVAL_DOCUMENT", kind="embed"):
        self.embedded.append(list(texts))
        return None if self.fail else [[float(len(t)), 1.0] for t in texts]


def kira(tmp_path, monkeypatch, llm=None):
    monkeypatch.setenv("TIMEZONE", "Europe/Kyiv")
    caps = frozenset({"canon", "summary", "voice", "world", "private", "recall"})
    cfg = AgentConfig(name="Кіра", user_id=KIRA, canon="Канон.", homeserver="http://hs", room_id=AGORA,
                      owner=OWNER, password="pw", capabilities=caps)
    agent = Agent(cfg, llm=llm or EmbedLLM())
    agent.private_file = tmp_path / "kira.private.json"
    agent.private_room = DM
    agent.client = SimpleNamespace(room_send=AsyncMock(), room_typing=AsyncMock(), rooms={}, invited_rooms={})
    agent.started, agent.started_ms = True, ms(8)
    agent.clock = lambda: ms(18)
    agent._spawn = lambda coro: coro.close()
    agent.voice_reply_p = 0.0
    return agent


def test_every_agora_line_and_both_sides_of_the_private_chat_are_kept(tmp_path, monkeypatch, caplog):
    agent = kira(tmp_path, monkeypatch)
    asyncio.run(agent.on_message(SimpleNamespace(room_id=AGORA), text("@ada:agora.lan", "Привіт усім", ms(17), "$r1")))
    asyncio.run(agent.on_message(SimpleNamespace(room_id=AGORA), text("@ada:agora.lan", "Привіт усім", ms(17), "$r1")))
    asyncio.run(agent.on_message(SimpleNamespace(room_id=DM), text(OWNER, f"Тільки тобі {SECRET}", ms(17, 5), "$p1")))
    agent.private_line("з телеграму", ms(17, 6), "telegram", "tg:41")
    asyncio.run(agent.private_reply())
    rows = agent.archive.db.execute("SELECT key, place, channel, speaker, text FROM lines ORDER BY id").fetchall()
    assert rows[0] == ("$r1", "agora", "matrix", "Ада", "Привіт усім")          # kept once
    assert rows[1] == ("$p1", "private", "matrix", "Ich", f"Тільки тобі {SECRET}")
    assert rows[2] == ("tg:41", "private", "telegram", "Ich", "з телеграму")
    assert rows[3][1:] == ("private", "matrix", "Кіра", "Привіт, сонце.")  # her answer (no bot here: Element)
    assert len(rows) == 4 and SECRET not in caplog.text


def test_the_idle_tick_embeds_in_batches_and_a_failure_waits(tmp_path, monkeypatch):
    agent = kira(tmp_path, monkeypatch)
    for i in range(5):
        agent.archive.append(f"${i}", ms(9, i), "agora", "matrix", "Ада", "x" * (i + 1))
    assert asyncio.run(agent.embed_tick(batch=3)) == 3 and agent.archive.counts() == (5, 3)
    assert asyncio.run(agent.embed_tick(batch=3)) == 2 and agent.archive.counts() == (5, 5)
    assert asyncio.run(agent.embed_tick()) == 0
    failing = kira(tmp_path, monkeypatch, llm=EmbedLLM(fail=True))
    failing.archive = Archive(tmp_path / "other.archive.db")
    failing.archive.append("$z", ms(9), "agora", "matrix", "Ада", "текст")
    assert asyncio.run(failing.embed_tick()) == 0 and failing.archive.counts() == (1, 0)


def page(events, end):
    return SimpleNamespace(chunk=list(reversed(events)), end=end)


def test_the_first_fill_reads_agora_and_the_private_room_bounded(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    agent = kira(tmp_path, monkeypatch)
    monkeypatch.setattr("agents.agent.ARCHIVE_AGORA_LINES", 3)
    agora = [text("@ada:agora.lan", f"рядок {i}", ms(9, i), f"$a{i}") for i in range(5)]
    private = [text(OWNER, "наодинці", ms(10), "$p1"), text("@mallory:agora.lan", "чужий", ms(10, 1), "$p2"),
               text(KIRA, "я тут", ms(10, 2), "$p3")]

    async def messages(room, start, direction, limit):
        if room == AGORA:
            return page(agora[2:], "t2") if start == "s0" else page(agora[:2], "t3")
        return page(private, "end")

    agent.client.room_messages = messages
    asyncio.run(agent.archive_backfill("s0"))
    rows = agent.archive.db.execute("SELECT place, speaker, text FROM lines ORDER BY ts_ms").fetchall()
    assert [r[2] for r in rows if r[0] == "agora"] == ["рядок 2", "рядок 3", "рядок 4"]   # the last 3
    assert [(r[1], r[2]) for r in rows if r[0] == "private"] == [("Ich", "наодинці"), ("Кіра", "я тут")]
    assert "archive: 3 Agora lines from the homeserver" in caplog.text


def test_the_private_history_at_start_comes_from_the_archive_both_doors(tmp_path, monkeypatch):
    """v5.7 review #5: Telegram lines survived only in the summary after a restart."""
    agent = kira(tmp_path, monkeypatch)
    agent.archive.append("$p1", ms(9), "private", "matrix", "Ich", "з Element")
    agent.archive.append("tg:1", ms(10), "private", "telegram", "Ich", "з телеграму")
    agent.archive.append("own:telegram:1", ms(11), "private", "telegram", "Кіра", "відповідь")
    agent.private_history, agent.last_private_ms = [("Ich", "з Element")], ms(9)
    agent.seed_private_from_archive()
    assert agent.private_history == [("Ich", "з Element"), ("Ich", "з телеграму"), ("Кіра", "відповідь")]
    assert agent.last_private_ms == ms(11)


def test_an_agent_without_recall_keeps_no_archive(tmp_path, monkeypatch):
    monkeypatch.setenv("TIMEZONE", "Europe/Kyiv")
    cfg = AgentConfig(name="Ада", user_id="@ada:agora.lan", canon="К.", homeserver="http://hs", room_id=AGORA,
                      owner=OWNER, password="pw")
    agent = Agent(cfg, llm=KindLLM())
    assert agent.archive is None and asyncio.run(agent.embed_tick()) == 0
    assert not list(tmp_path.glob("*.archive.db"))


def test_the_vectors_are_float32(arc):
    arc.append("$1", ms(9), "agora", "matrix", "Ада", "текст")
    arc.set_embeddings([(1, [0.25, 0.5])])
    ids, matrix = arc.vectors(["agora"])
    assert ids == [1] and matrix.dtype == np.float32 and matrix.shape == (1, 2)


# --- the embedding call (google-genai mocked) -------------------------------------------------------------------------
@pytest.mark.parametrize(("embeddings", "fail", "out", "ok"), [
    ([[0.1, 0.2], [0.3, 0.4]], None, [[0.1, 0.2], [0.3, 0.4]], True),
    ([[0.1, 0.2]], None, None, False),                       # a short answer is none
    (None, RuntimeError("quota"), None, False),
])
def test_the_embedding_call(monkeypatch, caplog, embeddings, fail, out, ok):
    from agents import llm as llm_mod
    seen = {}

    async def embed_content(model, contents, config):
        seen.update(model=model, contents=contents, config=config)
        if fail:
            raise fail
        return SimpleNamespace(embeddings=[SimpleNamespace(values=v) for v in embeddings], metadata=None)

    models = SimpleNamespace(embed_content=embed_content)
    monkeypatch.setattr(llm_mod.genai, "Client", lambda: SimpleNamespace(aio=SimpleNamespace(models=models)))
    usage = []
    client = llm_mod.GeminiClient(sink=lambda kind, model, meta, good: usage.append((kind, model, good)))
    assert asyncio.run(client.embed([f"рядок {SECRET}", "інший"], task="RETRIEVAL_QUERY")) == out
    assert seen["model"] == "gemini-embedding-001" and seen["config"].output_dimensionality == 768
    assert seen["config"].task_type == "RETRIEVAL_QUERY" and usage == [("embed", "gemini-embedding-001", ok)]
    assert SECRET not in caplog.text
    assert asyncio.run(client.embed([])) == []
