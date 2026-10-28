"""v5.13 — the owner's message a block or a refusal answered is marked censored in her archive and never reaches
Gemini again: not her history, not the session, not a reader of the archive (nio and Gemini mocked)."""

import asyncio
import logging
from types import SimpleNamespace

from agents.llm import LAST_BLOCK
from agents.private import private_label
from tests.test_archive import EmbedLLM, kira
from tests.test_private_runtime import DM, OWNER, SECRET, ms, text

CENSORED = f"запит, на який Gemini відмовив {SECRET}"


class BlockLLM(EmbedLLM):
    """Gemini, refusing the next `blocks` answers (as `GeminiClient` does: `LAST_BLOCK` set, None returned)."""

    def __init__(self, blocks=1, stage="refusal"):
        super().__init__()
        self.blocks, self.stage, self.transcripts = blocks, stage, []

    async def generate(self, transcript, system_instruction, max_output_tokens=400, kind="reply"):
        self.transcripts.append(transcript)
        if self.blocks:
            self.blocks -= 1
            LAST_BLOCK.set((self.stage, "виконати цей запит", None))
            return None
        return await super().generate(transcript, system_instruction, max_output_tokens, kind)


def marks(agent):
    return dict(agent.archive.db.execute("SELECT key, mark FROM lines WHERE place = 'private'").fetchall())


def test_a_refused_answer_marks_his_unanswered_lines_and_they_never_reach_gemini_again(tmp_path, monkeypatch, caplog):
    llm = BlockLLM()
    agent = kira(tmp_path, monkeypatch, llm)
    caplog.set_level(logging.INFO)
    agent.private_line("Привіт!", ms(17), "telegram", "tg:1")
    asyncio.run(agent.private_reply())                                # refused
    assert agent._unanswered == [] and marks(agent)["tg:1"] == "censored"
    assert agent.private_history == [] and not agent.session

    llm2 = BlockLLM(blocks=0)
    agent.llm = agent.responder.llm = llm2
    agent.private_line("Привіт ще раз", ms(17, 1), "telegram", "tg:2")
    asyncio.run(agent.private_reply())
    assert "Привіт!" not in llm2.transcripts[-1] and "Привіт ще раз" in llm2.transcripts[-1]
    assert agent._unanswered == [] and marks(agent)["tg:2"] == "gemini"
    assert "1 line(s) marked censored after a refusal" in caplog.text and "Привіт!" not in caplog.text


def test_only_the_lines_since_her_last_answer_are_marked_and_the_session_loses_them(tmp_path, monkeypatch):
    llm = BlockLLM(blocks=0)
    agent = kira(tmp_path, monkeypatch, llm)
    agent.private_line("Як ти?", ms(16), "telegram", "tg:1")
    asyncio.run(agent.private_reply())                               # answered: kept, «gemini»
    llm.blocks = 1
    asyncio.run(agent.on_message(SimpleNamespace(room_id=DM), text(OWNER, CENSORED, ms(17), "$p1")))
    agent.private_line("і ще одне", ms(17, 1), "telegram", "tg:2")
    assert len(agent.session) == 4                                   # both his lines are in the session
    asyncio.run(agent.private_reply())
    got = marks(agent)
    assert (got["tg:1"], got["$p1"], got["tg:2"]) == ("gemini", "censored", "censored")
    assert [v for k, v in got.items() if k not in ("tg:1", "$p1", "tg:2")] == ["gemini"]  # her answer
    assert [t for s, t in agent.private_history] == ["Як ти?", "Привіт, сонце."]
    assert agent.session == [(private_label("Ich"), "Як ти?"), (private_label("Кіра"), "Привіт, сонце.")]
    assert [line.text for line in agent.archive.latest("private", 10)] == ["Як ти?", "Привіт, сонце."]
    assert agent.archive.search_words(SECRET, ("private",)) == []
    assert all(CENSORED not in t for _, t in agent.archive.unembedded(10))


def test_a_block_on_a_line_she_writes_first_marks_nothing(tmp_path, monkeypatch):
    agent = kira(tmp_path, monkeypatch, BlockLLM(blocks=1, stage="prompt"))
    agent.private_line("Добраніч", ms(1), "telegram", "tg:1")
    agent._unanswered = ["tg:1"]
    asyncio.run(agent.private_reply(nudge=True))
    assert marks(agent)["tg:1"] == "gemini" and agent._unanswered == ["tg:1"]


def test_silence_without_a_block_marks_nothing(tmp_path, monkeypatch):
    llm = BlockLLM(blocks=0)
    llm.text = "PASS"  # she has nothing to add: silence, not a block
    agent = kira(tmp_path, monkeypatch, llm)
    agent.private_line("Ок", ms(17), "telegram", "tg:1")
    asyncio.run(agent.private_reply())
    assert marks(agent)["tg:1"] == "gemini" and agent.private_history == [("Ich", "Ок")]
