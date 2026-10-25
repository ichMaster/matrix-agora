"""v5.8 — facts about the owner (`facts`): the store, the prompt block, the marker line, the session-end extraction,
the one-shot Noos import; facts only in her private prompt (Gemini mocked; the clock injected; files in a temp dir)."""

import asyncio
import io
import json
import logging
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agents.agent import Agent
from agents.config import AgentConfig
from agents.facts import (
    EXTRACT_SYSTEM,
    FACTS_TITLE,
    REMEMBER_SKILL,
    Fact,
    add_fact,
    fact_path,
    facts_section,
    load_facts,
    parse_extraction,
    parse_fact,
    read_noos,
    remove_fact,
    replace_fact,
    run_import,
    set_pin,
    split_marker,
)
from agents.logic import BANNED_RE
from agents.roster import RosterError, parse_member
from tests.test_archive import EmbedLLM
from tests.test_private_runtime import AGORA, DM, KIRA, OWNER, SECRET, ms

TODAY = "2026-10-25"


# --- the store -------------------------------------------------------------------------------------------------------
def test_a_fact_is_kept_once_privately_under_a_slug(tmp_path):
    folder = tmp_path / "kira.facts"
    fid = add_fact(folder, "  Ich веган уже чотири роки ", 1, "asked", TODAY, 100, 240)
    assert fid == "ich-веган-уже-чотири-роки"
    path = folder / f"{fid}.md"
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert path.read_text() == f"---\npin: 1\nadded: {TODAY}\nsource: asked\n---\nIch веган уже чотири роки\n"
    assert add_fact(folder, "ich ВЕГАН уже чотири роки", 2, "private", TODAY, 100, 240) is None   # known
    assert add_fact(folder, "я" * 241, 1, "asked", TODAY, 100, 240) is None                        # too long
    assert add_fact(folder, "   ", 1, "asked", TODAY, 100, 240) is None
    assert add_fact(folder, "Ich любить гори", 1, "asked", TODAY, 1, 240) is None                  # the store is full
    assert add_fact(folder, "Ich веган уже чотири роки!", 1, "asked", TODAY, 100, 240) == f"{fid}-2"


def test_replace_pin_and_remove_stay_inside_the_folder(tmp_path):
    folder = tmp_path / "kira.facts"
    fid = add_fact(folder, "Ich живе у Львові", 2, "private", "2026-10-01", 100, 240)
    assert replace_fact(folder, fid, "Ich переїхав до Києва", TODAY, 240) is True
    assert set_pin(folder, fid, 1) is True and set_pin(folder, fid, 5) is False
    assert load_facts(folder) == [Fact(fid, 1, TODAY, "private", "Ich переїхав до Києва")]
    (tmp_path / "secret.md").write_text("---\npin: 1\n---\nчуже")
    for bad in ("../secret", "a/b", "", "x" * 70, "unknown"):
        assert fact_path(folder, bad) is None and remove_fact(folder, bad) is False
    assert remove_fact(folder, fid) is True and load_facts(folder) == []
    assert (tmp_path / "secret.md").exists()


def test_noos_files_parse_too():
    raw = "---\npin: 2\ntags: food\nadded: 2026-10-22\n---\nВеган, без алкоголю.\n"
    assert parse_fact("побут", raw) == Fact("побут", 2, "2026-10-22", "noos", "Веган, без алкоголю.")
    assert parse_fact("x", "no header") is None and parse_fact("x", "---\npin: 9\n---\n  ") is None


def test_the_prompt_block_pins_first_within_the_limits():
    facts = [Fact("a", 2, "2026-10-01", "noos", "друге"), Fact("b", 1, "2026-10-02", "noos", "перше"),
             Fact("c", 0, "2026-10-01", "noos", "лише для пошуку"), Fact("d", 1, "2026-10-01", "noos", "я" * 300)]
    out = facts_section(facts, 3, 240)
    assert out.startswith(FACTS_TITLE)
    lines = out.split("\n")[1:]
    assert lines[0].startswith("- " + "я" * 200) and lines[0].endswith("…") and len(lines[0]) == 242
    assert lines[1:] == ["- перше", "- друге"] and "лише для пошуку" not in out
    assert facts_section(facts, 0, 240) is None and facts_section([], 25, 240) is None


# --- the marker --------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("raw", "clean", "facts"), [
    ("Добре, запам'ятала!\nЗАПАМ'ЯТАЙ: Ich народився в березні", "Добре, запам'ятала!", ["Ich народився в березні"]),
    ("Звісно.\n\nЗапам’ятай: «Ich не їсть цукру»\nзапамятай: Ich любить джаз", "Звісно.",
     ["Ich не їсть цукру", "Ich любить джаз"]),
    ("Просто рядок без нічого.", "Просто рядок без нічого.", []),
    ("**ЗАПАМ'ЯТАЙ:** Ich має кота", "", ["Ich має кота"]),
    ("Я тобі кажу: запам'ятай це місце", "Я тобі кажу: запам'ятай це місце", []),   # words, not the marker line
])
def test_split_marker(raw, clean, facts):
    assert split_marker(raw) == (clean, facts)


# --- the extraction's answer ------------------------------------------------------------------------------------
def test_parse_extraction_keeps_only_valid_items():
    raw = "```json\n" + json.dumps({"add": [{"text": "Ich любить гори", "pin": 1}, {"text": "я" * 300, "pin": 1},
                                            {"text": "pin 0 тут не можна", "pin": 0}, {"pin": 2}],
                                    "replace": [{"id": "known", "text": "нове"}, {"id": "nope", "text": "x"}]}) + "\n```"
    assert parse_extraction(raw, {"known"}, 240) == ([("Ich любить гори", 1)], [("known", "нове")])
    assert parse_extraction("не JSON", set(), 240) is None and parse_extraction('{"add": 5}', set(), 240) is None
    assert parse_extraction('{"add": [], "replace": []}', set(), 240) == ([], [])


# --- the agent -----------------------------------------------------------------------------------------------------
class FactsLLM(EmbedLLM):
    def __init__(self, reply="Привіт, сонце.", extraction='{"add": [], "replace": []}'):
        super().__init__()
        self.text, self.extraction = reply, extraction

    async def generate(self, transcript, system_instruction, max_output_tokens=400, kind="reply"):
        self.kinds.append(kind)
        self.calls.append((transcript, system_instruction))
        return self.extraction if kind == "facts" else self.text


def kira(tmp_path, monkeypatch, llm=None):
    monkeypatch.setenv("TIMEZONE", "Europe/Kyiv")
    caps = frozenset({"canon", "summary", "voice", "world", "private", "recall", "facts"})
    cfg = AgentConfig(name="Кіра", user_id=KIRA, canon="Канон.", homeserver="http://hs", room_id=AGORA,
                      owner=OWNER, password="pw", capabilities=caps)
    agent = Agent(cfg, llm=llm or FactsLLM())
    agent.private_file = tmp_path / "kira.private.json"
    agent.private_room = DM
    agent.client = SimpleNamespace(room_send=AsyncMock(), room_typing=AsyncMock(), rooms={}, invited_rooms={})
    agent.started, agent.started_ms = True, ms(8)
    agent.clock = lambda: ms(18)
    agent._spawn = lambda coro: coro.close()
    agent.voice_reply_p = 0.0
    return agent



def sent(agent):
    return [c.kwargs["content"]["body"] for c in agent.client.room_send.await_args_list]


def test_asked_to_remember_she_keeps_it_and_the_marker_is_never_sent(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    agent = kira(tmp_path, monkeypatch, FactsLLM(reply=f"Запам'ятала, обіцяю.\nЗАПАМ'ЯТАЙ: Ich боїться висоти {SECRET}"))
    agent.private_history = [("Ich", "Запам'ятай: я боюся висоти")]
    asyncio.run(agent.private_reply())
    assert sent(agent) == ["Запам'ятала, обіцяю."]
    facts = load_facts(agent.facts_dir)
    assert [(f.pin, f.source, f.text) for f in facts] == [(1, "asked", f"Ich боїться висоти {SECRET}")]
    assert agent.private_history[-1] == ("Кіра", "Запам'ятала, обіцяю.")
    assert REMEMBER_SKILL in agent.llm.calls[-1][1]
    assert "facts: kept one (asked)" in caplog.text and SECRET not in caplog.text


def test_a_marker_in_agora_is_stripped_too(tmp_path, monkeypatch):
    agent = kira(tmp_path, monkeypatch, FactsLLM(reply="Так!\nЗАПАМ'ЯТАЙ: Ich любить джаз"))
    text = asyncio.run(agent._compose(agent.build_prompt()))
    assert text == "Так!" and [f.text for f in load_facts(agent.facts_dir)] == ["Ich любить джаз"]
    only = kira(tmp_path / "o", monkeypatch, FactsLLM(reply="ЗАПАМ'ЯТАЙ: Ich любить чай"))
    only.facts_dir = tmp_path / "o.facts"
    assert asyncio.run(only._compose(only.build_prompt())) is None              # nothing left to say: silence


def test_facts_reach_only_her_private_prompt_and_only_a_private_recall(tmp_path, monkeypatch):
    agent = kira(tmp_path, monkeypatch)
    add_fact(agent.facts_dir, f"Ich веган {SECRET}", 1, "noos", TODAY, 100, 240)
    add_fact(agent.facts_dir, "Ich колись грав у театрі", 0, "noos", TODAY, 100, 240)
    private = agent.build_prompt(private="НАОДИНЦІ", facts=agent.facts_now())
    assert FACTS_TITLE in private and SECRET in private and "грав у театрі" not in private  # pin 0: search only
    assert FACTS_TITLE not in agent.build_prompt() and SECRET not in agent.build_prompt()
    assert asyncio.run(agent.recall_section("театрі", ("agora",), set())) is None
    assert "грав у театрі" in asyncio.run(agent.recall_section("театрі", ("agora", "private", "facts"), set()))


def test_a_deleted_fact_is_gone_from_the_next_answer(tmp_path, monkeypatch):
    agent = kira(tmp_path, monkeypatch)
    fid = add_fact(agent.facts_dir, "Ich любить гори", 1, "asked", TODAY, 100, 240)
    assert "любить гори" in agent.facts_now()
    remove_fact(agent.facts_dir, fid)                                          # the panel deletes it
    assert agent.facts_now() is None
    assert agent.archive.db.execute("SELECT COUNT(*) FROM lines WHERE place = 'facts'").fetchone()[0] == 0


def test_the_session_end_extraction_adds_and_replaces(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    agent = kira(tmp_path, monkeypatch)
    old = add_fact(agent.facts_dir, "Ich живе у Львові", 2, "private", "2026-10-01", 100, 240)
    agent.llm.extraction = json.dumps({"add": [{"text": "Ich вчить японську", "pin": 2}],
                                       "replace": [{"id": old, "text": "Ich переїхав до Києва"}]})
    asyncio.run(agent.extract_facts([("Ich (наодинці)", f"Я тепер у Києві і вчу японську {SECRET}"),
                                     ("Кіра (наодинці)", "Оце так!")]))
    texts = sorted(f.text for f in load_facts(agent.facts_dir))
    assert texts == ["Ich вчить японську", "Ich переїхав до Києва"]
    system, contents = agent.llm.calls[-1][1], agent.llm.calls[-1][0]
    assert f"{old}: Ich живе у Львові" in contents and agent.llm.kinds[-1] == "facts"
    assert not BANNED_RE.search(system) and "facts: 1 added, 1 replaced" in caplog.text and SECRET not in caplog.text


def test_an_invalid_extraction_or_a_session_without_him_changes_nothing(tmp_path, monkeypatch):
    agent = kira(tmp_path, monkeypatch, FactsLLM(extraction="вибач, не можу"))
    asyncio.run(agent.extract_facts([("Ich", "привіт")]))
    assert load_facts(agent.facts_dir) == []
    calls = len(agent.llm.calls)
    asyncio.run(agent.extract_facts([("Ада", "привіт"), ("Бруно", "привіт")]))
    assert len(agent.llm.calls) == calls                                     # no call at all


def test_the_capability_needs_the_private_chat():
    assert parse_member("kira", {"name": "Кіра", "user_id": KIRA,
                                 "capabilities": {"private": True, "facts": True}}, "kira.toml").can("facts")
    with pytest.raises(RosterError, match="'facts' needs 'private' on the same member"):
        parse_member("kira", {"name": "Кіра", "user_id": KIRA, "capabilities": {"facts": True}}, "kira.toml")


def test_her_lines_about_facts_never_say_what_she_is():
    assert not BANNED_RE.search(REMEMBER_SKILL) and not BANNED_RE.search(EXTRACT_SYSTEM)


# --- the import from Noos ------------------------------------------------------------------------------------------
def noos(tmp_path):
    src = tmp_path / "noos"
    (src / "facts").mkdir(parents=True)
    (src / "import" / "lumi").mkdir(parents=True)
    (src / "facts" / "побут.md").write_text("---\npin: 2\ntags: x\nadded: 2026-10-22\n---\nВеган, без алкоголю.\n")
    (src / "facts" / "сервер.md").write_text("---\npin: 1\n---\nНа сервері працює стек.\n")
    (src / "import" / "lumi" / "README.md").write_text("як імпортувати")
    (src / "import" / "lumi" / "core.md").write_text("# Особа\n- народився навесні")
    return src


class ImportLLM:
    def __init__(self, answer):
        self.answer, self.calls = answer, []

    async def generate(self, contents, system, max_output_tokens=400, kind="reply"):
        self.calls.append((contents, system, kind))
        return self.answer


ANSWER = json.dumps({"facts": [{"text": "Ich веган і не п'є алкоголю", "pin": 2},
                               {"text": "Ich народився навесні", "pin": 1},
                               {"text": "Ich веган і не п'є алкоголю", "pin": 2}]})


def test_the_import_reads_noos_files_and_extracts_without_readmes(tmp_path):
    facts, extracts = read_noos(noos(tmp_path))
    assert sorted(f.text for f in facts) == ["Веган, без алкоголю.", "На сервері працює стек."]
    assert extracts == ["# Особа\n- народився навесні"]


def test_a_dry_run_prints_and_writes_nothing(tmp_path):
    llm, out = ImportLLM(ANSWER), io.StringIO()
    folder = tmp_path / "kira.facts"
    assert asyncio.run(run_import(noos(tmp_path), folder, llm, TODAY, 100, 240, True, out)) == 2
    assert "[pin 1] Ich народився навесні" in out.getvalue() and "would keep 2 facts" in out.getvalue()
    assert load_facts(folder) == []
    contents, system, kind = llm.calls[0]
    assert kind == "facts" and "Веган, без алкоголю." in contents and "народився навесні" in contents
    assert "Noos" in system and "ботів" in system                             # the filter is asked for


def test_the_import_writes_once_as_noos(tmp_path):
    folder, src = tmp_path / "kira.facts", noos(tmp_path)
    assert asyncio.run(run_import(src, folder, ImportLLM(ANSWER), TODAY, 100, 240, False, io.StringIO())) == 2
    assert sorted((f.source, f.pin) for f in load_facts(folder)) == [("noos", 1), ("noos", 2)]
    llm, out = ImportLLM(ANSWER), io.StringIO()
    assert asyncio.run(run_import(src, folder, llm, TODAY, 100, 240, False, out)) == 0   # a second run: nothing
    assert llm.calls == [] and "already imported: 2 facts" in out.getvalue()


def test_an_invalid_import_answer_writes_nothing(tmp_path):
    folder, out = tmp_path / "kira.facts", io.StringIO()
    assert asyncio.run(run_import(noos(tmp_path), folder, ImportLLM("ні"), TODAY, 100, 240, False, out)) == 0
    assert load_facts(folder) == [] and "no valid answer" in out.getvalue()
