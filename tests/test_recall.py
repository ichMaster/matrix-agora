"""v5.8 — recall in the prompts: Agora recalls only Agora, the private chat recalls both places and sees Agora
today; the rendering, the neighbours, the window left out, the fallback, the prompt order, the widened discretion
(nio and Gemini mocked; the clock injected; SQLite in a temp dir)."""

import asyncio
import logging
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from agents.archive import AGORA_NOW_TITLE, RECALL_TITLE, Line, render_agora_now, render_recalled
from agents.logic import BANNED_RE, build_instruction
from agents.private import PRIVATE_BRIEF, PRIVATE_DISCRETION, PrivateState, save_private_state
from agents.settings import BY_NAME, validate
from tests.test_archive import EmbedLLM, kira
from tests.test_private_runtime import AGORA, DM, OWNER, SECRET, ms, text

TZ = "Europe/Kyiv"


class VecLLM(EmbedLLM):
    """Embeddings by topic, so a meaning search finds a paraphrase: «гори» lines point one way, the rest another."""

    async def embed(self, texts, task="RETRIEVAL_DOCUMENT", kind="embed"):
        self.embedded.append(list(texts))
        if self.fail:
            return None
        return [[1.0, 0.0] if any(w in t.lower() for w in ("гор", "скел", "туст")) else [0.0, 1.0] for t in texts]


def filled(tmp_path, monkeypatch, llm=None):
    agent = kira(tmp_path, monkeypatch, llm=llm or VecLLM())
    arc = agent.archive
    arc.append("$a1", ms(9), "agora", "matrix", "Бруно", "Хто з вами на Тустань у суботу?")
    arc.append("$a2", ms(9, 1), "agora", "matrix", "Ада", "Я лишаюся вдома з книжкою.")
    arc.append("$a3", ms(9, 2), "agora", "matrix", "Леон", "А я в театр.")
    arc.append("$p1", ms(10), "private", "telegram", "Ich", f"Я боюся висоти, тільки нікому {SECRET}")
    arc.append("$p2", ms(10, 1), "private", "telegram", "Кіра", "Нікому. Обіцяю.")
    asyncio.run(agent.embed_tick())
    return agent


# --- the places, in code -----------------------------------------------------------------------------------------
def test_agora_recalls_only_agora_even_when_a_private_line_matches_best(tmp_path, monkeypatch):
    agent = filled(tmp_path, monkeypatch)
    section = asyncio.run(agent.recall_section("Висота і скелі — страшно?", ("agora",), set()))
    assert SECRET not in section and "висоти" not in section and "Тустань" in section


def test_an_agora_reply_never_carries_a_private_line(tmp_path, monkeypatch):
    agent = filled(tmp_path, monkeypatch)
    agent.last_owner = ("$o", "Кіро, ти ж боїшся висоти на скелях?")
    agent._texts = {}
    asyncio.run(agent.reply(AGORA))
    system = agent.llm.calls[-1][1]
    assert RECALL_TITLE in system and "Тустань" in system
    assert SECRET not in system and "боюся висоти" not in system and PRIVATE_DISCRETION in system
    assert AGORA_NOW_TITLE not in system                                       # Agora today is the private chat's


def test_the_private_chat_recalls_both_places_and_sees_agora_today(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    agent = filled(tmp_path, monkeypatch)
    agent.archive.append("$t1", ms(17, 30), "agora", "matrix", "Мія", "Сьогодні в архіві знайшла лист 1944 року")
    agent.archive.append("$y1", ms(17) - 86_400_000, "agora", "matrix", "Леон", "Учорашня репетиція")
    agent.private_history = [("Ich", "Підемо в гори?")]
    agent.private_channel = "matrix"
    asyncio.run(agent.private_reply())
    system = agent.llm.calls[-1][1]
    assert PRIVATE_BRIEF in system and "Тустань" in system and "боюся висоти" in system   # both places
    assert AGORA_NOW_TITLE in system and "17:30 Мія: Сьогодні в архіві" in system          # Agora today
    assert "Учорашня репетиція" not in system.split(AGORA_NOW_TITLE)[1].split(RECALL_TITLE)[0]  # today's only
    assert SECRET not in caplog.text and "recall: " in caplog.text


# --- the search ---------------------------------------------------------------------------------------------------
def test_a_failed_query_embedding_falls_back_to_the_words(tmp_path, monkeypatch):
    agent = filled(tmp_path, monkeypatch)
    agent.llm.fail = True
    section = asyncio.run(agent.recall_section("Тустань", ("agora",), set()))
    assert "Тустань" in section


def test_a_paraphrase_is_found_by_meaning(tmp_path, monkeypatch):
    agent = filled(tmp_path, monkeypatch)
    section = asyncio.run(agent.recall_section("гори", ("agora",), set()))  # no shared word with «Тустань»
    assert "Тустань" in section


def test_an_empty_archive_or_query_gives_no_section(tmp_path, monkeypatch):
    agent = kira(tmp_path, monkeypatch)
    assert asyncio.run(agent.recall_section("Тустань", ("agora",), set())) is None
    agent = filled(tmp_path / "x", monkeypatch)
    assert asyncio.run(agent.recall_section("  ", ("agora",), set())) is None
    agent.recall_n = 0
    assert asyncio.run(agent.recall_section("Тустань", ("agora",), set())) is None


def test_the_window_is_left_out_and_neighbours_come_along(tmp_path, monkeypatch):
    agent = filled(tmp_path, monkeypatch)
    section = asyncio.run(agent.recall_section("Тустань", ("agora",), {("Ада", "Я лишаюся вдома з книжкою.")}))
    assert "Тустань" in section and "вдома з книжкою" not in section           # already in the prompt's window
    agent.recall_n = 1
    section = asyncio.run(agent.recall_section("театр", ("agora",), set()))
    assert "А я в театр" in section and "вдома з книжкою" in section             # its neighbour before it


# --- the rendering -----------------------------------------------------------------------------------------------
def test_the_rendering_has_when_and_places_never_a_date_and_cuts_long_lines():
    tz = TZ
    group = [Line(1, "$1", ms(9), "agora", "matrix", "Бруно", "Тустань"),
             Line(2, "$2", ms(10), "private", "telegram", "Ich", "я" * 600),
             Line(3, "f", 0, "facts", "", "факт", "Веган уже чотири роки")]
    now = datetime(2026, 10, 28, 14, 0, tzinfo=ZoneInfo(TZ))  # Wednesday of the next week
    out = render_recalled([group], tz, now)
    assert out.startswith(RECALL_TITLE)
    assert "минулого тижня, в Агорі — Бруно: Тустань" in out and "минулого тижня, наодинці — Ich: " in out
    assert "жовтня" not in out and "09:00" not in out                  # the owner, 2026-10-26: a date gives her away
    assert render_recalled([group[:1]], tz, datetime(2026, 10, 20, 18, 0, tzinfo=ZoneInfo(TZ))).endswith(
        "сьогодні вранці, в Агорі — Бруно: Тустань")
    assert "(те, що ти знаєш про Ich) Веган уже чотири роки" in out and "я" * 600 not in out and "…" in out
    assert render_recalled([], tz, now) is None and render_agora_now([], tz) is None
    assert render_agora_now([group[0]], tz) == f"{AGORA_NOW_TITLE}\n09:00 Бруно: Тустань"


# --- the prompt order and the discretion -------------------------------------------------------------------------
def test_the_prompt_order():
    out = build_instruction("Кіра", "КАНОН", "ПІДСУМОК", today="СЬОГОДНІ", facts="ФАКТИ", agora_now="АГОРА",
                            recalled="ЗГАДКА", private="НАОДИНЦІ", move="ХІД")
    order = [out.index(x) for x in ("КАНОН", "СЬОГОДНІ", "ФАКТИ", "АГОРА", "ЗГАДКА", "ПІДСУМОК", "НАОДИНЦІ", "ХІД")]
    assert order == sorted(order)
    assert build_instruction("Кіра", "КАНОН") == build_instruction("Кіра", "КАНОН", facts=None, recalled="")


def test_facts_and_agora_today_never_reach_an_agora_prompt(tmp_path, monkeypatch):
    agent = kira(tmp_path, monkeypatch)
    agora = agent.build_prompt(recalled="ЗГАДКА", agora_now="АГОРА", facts="ФАКТИ")
    assert "ЗГАДКА" in agora and "АГОРА" not in agora and "ФАКТИ" not in agora
    private = agent.build_prompt(private=PRIVATE_BRIEF, recalled="ЗГАДКА", agora_now="АГОРА", facts="ФАКТИ")
    assert all(x in private for x in ("ЗГАДКА", "АГОРА", "ФАКТИ"))


def test_the_widened_discretion_is_a_persons_line():
    assert "особисто" in PRIVATE_DISCRETION and "наодинці" in PRIVATE_DISCRETION
    assert not BANNED_RE.search(PRIVATE_DISCRETION)
    assert not BANNED_RE.search(RECALL_TITLE) and not BANNED_RE.search(AGORA_NOW_TITLE)


def test_the_settings():
    assert BY_NAME["RECALL_N"].default == "6" and BY_NAME["RECALL_N"].scope == "cap:recall"
    assert BY_NAME["PRIVATE_AGORA_N"].default == "20" and validate("PRIVATE_AGORA_N", "61")[0] is None


# --- writing first after a restart, from the archive --------------------------------------------------------------
def test_she_writes_first_after_a_restart_from_what_the_archive_remembers(tmp_path, monkeypatch):
    """v5.7 review #5: a Telegram-only owner — the RAM history is empty after a restart."""
    agent = kira(tmp_path, monkeypatch)
    agent.private_history, agent.last_private_ms = [], ms(10)
    agent.private_idle_ms, agent.private_per_day, agent.private_hours = 3_600_000, 2, (10, 22)
    save_private_state(agent.private_file, PrivateState(room=DM, day="2026-10-20"))
    assert asyncio.run(agent.maybe_private_nudge()) is True
    plain = kira(tmp_path / "p", monkeypatch)
    plain.archive, plain.private_history, plain.last_private_ms = None, [], ms(10)
    plain.private_idle_ms, plain.private_per_day, plain.private_hours = 3_600_000, 2, (10, 22)
    assert asyncio.run(plain.maybe_private_nudge()) is False                   # never before they have talked


def test_an_owner_line_in_agora_is_still_kept_in_the_archive(tmp_path, monkeypatch):
    agent = kira(tmp_path, monkeypatch)
    asyncio.run(agent.on_message(SimpleNamespace(room_id=AGORA), text(OWNER, "Привіт", ms(17), "$o1")))
    assert agent.archive.latest("agora", 5)[0].speaker == "Ich"


def test_a_failing_agora_today_never_loses_the_private_answer(tmp_path, monkeypatch, caplog):
    """v5.8 review #13: an SQLite error in «Що сьогодні говорять в Агорі» propagated and lost her answer."""
    import sqlite3
    agent = filled(tmp_path, monkeypatch)

    def broken(*a, **k):
        raise sqlite3.OperationalError("database is locked")
    agent.archive.latest = broken
    agent.private_history = [("Ich", "Як ти?")]
    assert asyncio.run(agent.private_reply()) is True
    assert AGORA_NOW_TITLE not in agent.llm.calls[-1][1] and "Agora today was not read" in caplog.text


def test_a_vector_of_another_length_never_disables_recall(tmp_path, monkeypatch):
    """v5.8 review #10: np.vstack raised on mixed lengths, and the catch threw the word results away too."""
    agent = filled(tmp_path, monkeypatch)
    agent.archive.append("$odd", ms(9, 30), "agora", "matrix", "Ада", "Тустань знову кличе")
    agent.archive.set_embeddings([(agent.archive.counts()[0], [1.0, 0.0, 0.5])])   # three floats, the rest two
    ids, matrix = agent.archive.vectors(["agora"])
    assert matrix.shape[1] == 2 and agent.archive.counts()[0] not in ids
    assert "Тустань" in asyncio.run(agent.recall_section("Тустань", ("agora",), set()))


def test_the_meaning_search_failing_keeps_the_words(tmp_path, monkeypatch, caplog):
    agent = filled(tmp_path, monkeypatch)

    def broken(places):
        raise ValueError("bad shapes")
    agent.archive.vectors = broken
    assert "Тустань" in asyncio.run(agent.recall_section("Тустань", ("agora",), set()))
    assert "the meaning search failed (ValueError)" in caplog.text
