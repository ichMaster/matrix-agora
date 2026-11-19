"""v9.2.1 (the owner, 2026-11-19: «Кіра дивно поводиться в Агорі, виглядає що вона одне то саме по колу пише») — a
reply never says again what was already said: a part of it copying 8 consecutive words of her own line in her window
or of a line she recalls is dropped; nothing left — composed once more, then silence (nio and Gemini mocked; the clock
injected; SQLite in a temp dir; made-up lines only)."""

import asyncio
import logging

from agents.logic import REPEAT_WORDS, drop_repeats
from tests.test_archive import kira
from tests.test_private_runtime import AGORA, ms

GREETING = "привіт усім! я тут, сонце вже майже сідає, а ви все ще не спите!"
OLD = "бруно, ну от чесно, хіба це не цікавіше шукати музику всесвіту в тиші серед ночі?"
NEW = "Ада, а ти коли востаннє дивилася на Місяць у бінокль?"


# --- the pure part ----------------------------------------------------------------------------------------------------
def test_a_stitched_reply_keeps_only_what_is_new():
    text, dropped = drop_repeats(f"{GREETING}\n\n{OLD}\n\n{NEW}", [GREETING, f"щось інше\n\n{OLD}"])
    assert (text, dropped) == (NEW, 2)


def test_nothing_repeated_is_the_reply_as_it_was():
    reply = f"{GREETING}\n\n{NEW}"
    assert drop_repeats(reply, [OLD]) == (reply, 0)
    assert drop_repeats(reply, []) == (reply, 0)


def test_all_of_it_said_before_is_none():
    assert drop_repeats(f"{GREETING}\n{OLD}", [OLD, GREETING]) == (None, 2)


def test_fewer_words_in_a_row_are_no_repeat():
    short = " ".join(GREETING.split()[:REPEAT_WORDS - 1])           # 7 words of the greeting
    assert drop_repeats(f"{short} — і все.", [GREETING]) == (f"{short} — і все.", 0)
    assert drop_repeats("Мрррр.", ["Мрррр."]) == ("Мрррр.", 0)      # the cat's purr is never a repeat


def test_voice_tags_are_never_words_and_a_line_break_alone_is_a_part():
    tagged = "привіт усім! [laughs] я тут, сонце вже майже сідає, а ви все ще не спите!"
    assert drop_repeats(f"{tagged}\n{NEW}", [GREETING]) == (NEW, 1)
    assert drop_repeats(f"{tagged}\n[sighs]", [GREETING]) == (None, 1)  # only a tag is left: nothing of hers


def test_the_breaks_between_the_kept_parts_stay_as_they_were():
    reply = f"{NEW}\n\n{OLD}\nА ще: я сьогодні бачила Юпітер.\n\nДобраніч."
    assert drop_repeats(reply, [OLD]) == (f"{NEW}\nА ще: я сьогодні бачила Юпітер.\n\nДобраніч.", 1)


# --- the agent --------------------------------------------------------------------------------------------------------
class SeqLLM:
    """Replies in order; embeds nothing (the recall is by words)."""

    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    async def generate(self, transcript, system_instruction, max_output_tokens=400, kind="reply"):
        self.calls.append(kind)
        return self.replies.pop(0) if self.replies else None

    async def embed(self, texts, task="RETRIEVAL_DOCUMENT", kind="embed"):
        return None


def agent_with(tmp_path, monkeypatch, *replies):
    agent = kira(tmp_path, monkeypatch, llm=SeqLLM(*replies))
    agent.archive.append("$old", ms(9), "agora", "matrix", "Кіра", f"{GREETING}\n\n{OLD}")  # a day she spoke before
    agent.archive.append("$old2", ms(9, 1), "agora", "matrix", "Бруно", "Музика всесвіту? Тиша і є музика.")
    agent.history = [("Кіра", f"Ой, {NEW}"), ("Ich", "Кіро, а як там тиша і музика всесвіту, бруно?")]
    agent.history_ts = [ms(17), ms(17, 50)]
    agent.last_owner = ("$o", "Кіро, а як там тиша і музика всесвіту, бруно?")
    agent._texts = {}
    return agent


def sent(agent):
    return [c.kwargs["content"]["body"] for c in agent.client.room_send.await_args_list]


def test_her_reply_stitched_from_what_she_recalls_is_sent_without_it(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    fresh = "А тиша для мене — це коли телескоп гуде, а я чекаю на хмари."
    agent = agent_with(tmp_path, monkeypatch, f"{GREETING}\n\n{OLD}\n\n{fresh}")
    assert asyncio.run(agent.reply(AGORA)) is True
    assert sent(agent) == [fresh]
    assert "repeat: 2 parts dropped" in caplog.text and GREETING not in caplog.text and OLD not in caplog.text


def test_all_of_it_said_before_is_composed_once_more(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    fresh = "Тиша — це коли чути власне серце."
    agent = agent_with(tmp_path, monkeypatch, f"Ой, {NEW}", fresh)                  # her own window's line, again
    assert asyncio.run(agent.reply(AGORA)) is True
    assert sent(agent) == [fresh] and agent.llm.calls == ["reply", "reply"]
    assert "repeat: composing once more" in caplog.text


def test_twice_all_said_before_is_silence(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    agent = agent_with(tmp_path, monkeypatch, f"Ой, {NEW}", f"{GREETING}\n{OLD}")
    assert asyncio.run(agent.reply(AGORA)) is False
    agent.client.room_send.assert_not_awaited()
    assert agent.llm.calls == ["reply", "reply"] and "silent: only what it already said" in caplog.text


def test_what_others_said_in_her_window_is_no_repeat_of_hers(tmp_path, monkeypatch):
    agent = agent_with(tmp_path, monkeypatch, "Кіро, а як там тиша і музика всесвіту, бруно? Ось і я питаю.")
    agent.archive = None                                                            # no recall: her window alone
    assert asyncio.run(agent.reply(AGORA)) is True                                  # his words are not hers
    assert agent.llm.calls == ["reply"]


def test_a_recalled_thought_or_fact_is_never_counted_as_said(tmp_path, monkeypatch):
    agent = kira(tmp_path, monkeypatch, llm=SeqLLM())
    agent.archive.append("$t", ms(9), "thought", "matrix", "Кіра", "Тиша серед ночі — це музика всесвіту для мене.")
    agent.archive.append("$a", ms(9, 5), "agora", "matrix", "Ада", "Музика всесвіту — красиво сказано, Кіро.")
    said: list[str] = []
    section = asyncio.run(agent.recall_section("музика всесвіту", ("agora", "thought"), set(), said=said))
    assert section and "я думала" in section
    assert said == ["Музика всесвіту — красиво сказано, Кіро."]
