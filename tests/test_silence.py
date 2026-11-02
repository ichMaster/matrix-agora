"""v5.22 (the owner, 2026-11-02: «я не хочу щоб було просто тиша у відповідь, тоді пиши що вона пропустила і вирішила
мовчати, бо не зрозуміло чи вона взагалі працює») — her answer to him in Telegram that comes to nothing is one ⚙️ line
why, never a bare silence; never in her history; writing first stays silent (a fake bot; no network)."""

import asyncio

from agents.llm import LAST_BLOCK
from agents.private import silence_line
from tests.test_private_runtime import KindLLM, ms
from tests.test_telegram_runtime import kira, run_batch, texts_sent, tg

BLOCK = ("prompt", "prohibited_content", None)


def test_the_line_names_why():
    assert silence_line("Кіра", None, "model passed", "gemini", False) == (
        "⚙️ Кіра пропустила відповідь: вирішила мовчати (PASS)")
    assert silence_line("Кіра", BLOCK, None, "gemini", False) == (
        "⚙️ Кіра пропустила відповідь: блок gemini (prompt prohibited_content), backup вимкнено")
    assert silence_line("Кіра", ("answer", "safety", "HARM_CATEGORY_X"), None, "backup", True).endswith(
        "блок gemini (answer safety HARM_CATEGORY_X), backup не відповів")
    assert silence_line("Кіра", BLOCK, None, "gemini", True).endswith("блок gemini (prompt prohibited_content)")
    assert silence_line("Кіра", None, "only voice tags", "gemini", True).endswith("у відповіді були лише теги голосу")
    assert silence_line("Кіра", None, None, "backup", True).endswith(": backup не відповів")
    assert silence_line("Кіра", None, None, "gemini", False).endswith(": gemini нічого не повернув")


class Blocks(KindLLM):
    """Gemini blocks her private prompt."""

    async def generate(self, transcript, system_instruction, max_output_tokens=400, kind="reply"):
        if kind == "private":
            LAST_BLOCK.set(BLOCK)
            return None
        return await super().generate(transcript, system_instruction, max_output_tokens, kind)


def test_her_pass_to_him_is_said_and_kept_nowhere(tmp_path, monkeypatch):
    agent = kira(tmp_path, monkeypatch, llm=KindLLM("PASS"))
    run_batch(agent, tg(1, "привіт", at=ms(17, 30)))
    assert texts_sent(agent) == ["⚙️ Кіра пропустила відповідь: вирішила мовчати (PASS)"]
    assert not any("⚙️" in t for _, t in agent.private_history) and agent.telegram.send_voice.await_count == 0


def test_a_block_with_the_backup_off_is_said(tmp_path, monkeypatch):
    agent = kira(tmp_path, monkeypatch, llm=Blocks())
    run_batch(agent, tg(1, "привіт", at=ms(17, 30)))
    assert texts_sent(agent) == [silence_line("Кіра", BLOCK, None, "gemini", False)]


def test_a_failed_answer_is_said_and_writing_first_stays_silent(tmp_path, monkeypatch):
    agent = kira(tmp_path, monkeypatch, llm=KindLLM("PASS"))
    asyncio.run(agent.private_reply(nudge=True, channel="telegram"))
    assert texts_sent(agent) == []                                       # he asked nothing: no line

    async def fails(*args, **kwargs):
        raise RuntimeError("down")
    agent._private_text = fails
    run_batch(agent, tg(1, "привіт", at=ms(17, 30)))
    assert texts_sent(agent) == ["⚙️ Кіра пропустила відповідь: помилка (RuntimeError)"]
