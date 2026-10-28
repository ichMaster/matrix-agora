"""v5.12 — her thoughts kept (AGORA-133): the capability, the day file, the archive's places, the recall «я думала…»
(nio and Gemini mocked; SQLite in a temp dir; the clock injected)."""

import asyncio
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from agents.archive import RECALL_TITLE, RECALL_TITLE_THOUGHTS, Archive, Line, render_recalled
from agents.config import ConfigError, load_config
from agents.logic import BANNED_RE
from agents.roster import RosterError, parse_member
from agents.thoughts import Thought, archive_key, block, parse_day, today_thoughts
from tests.test_archive import kira as kira_agent
from tests.test_private_runtime import KIRA

ROOT = Path(__file__).resolve().parent.parent
TZ = ZoneInfo("Europe/Kyiv")
NEWS = Thought("09:15", "news", "thought", "zaxid", "Прочитала про новий телескоп — аж мурашки.",
               "У Львові покажуть новий телескоп", "https://zaxid.net/n1")
PRIVATE = Thought("21:40", "reflection", "thought_private", "private", "Він сьогодні був тихий. Я чекала більшого.")
AGORA = Thought("14:05", "reflection", "thought", "agora", "Ада знову сперечалася про слово, а я мовчала.")


def at(y, mo, d, h=12, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=TZ)


def ms(dt):
    return int(dt.timestamp() * 1000)


# --- the capability ---------------------------------------------------------------------------------------------
def test_thoughts_are_a_persons_and_never_without_recall():
    assert parse_member("kira", {"name": "Кіра", "user_id": KIRA,
                                 "capabilities": {"recall": True, "thoughts": True}}, "kira.toml").can("thoughts")
    with pytest.raises(RosterError, match="recall"):
        parse_member("kira", {"name": "Кіра", "user_id": KIRA, "capabilities": {"thoughts": True}}, "kira.toml")
    with pytest.raises(RosterError):
        parse_member("kit", {"name": "Кіт", "user_id": "@kit:agora.lan", "type": "creature",
                             "capabilities": {"thoughts": True}}, "kit.toml")


ENV = {"OWNER": "@ich:agora.lan", "KIRA_PASSWORD": "pw", "ROOM_ID": "!r", "HOMESERVER": "http://hs"}


@pytest.mark.canon
def test_her_reading_file_is_loaded_without_its_notes_and_says_nothing_of_what_she_is():
    cfg = load_config(ROOT / "agents" / "kira.toml", env=ENV)
    assert cfg.can("thoughts") and cfg.reading
    assert not any(line.lstrip().startswith("#") for line in cfg.reading.splitlines())
    assert not BANNED_RE.search(cfg.reading)


@pytest.mark.canon
@pytest.mark.parametrize("content, err", [(None, "reading file not found"), ("# лише нотатка\n", "reading file is empty")])
def test_a_missing_or_empty_reading_file_is_named(tmp_path, content, err):
    path = tmp_path / "reading.md"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    toml = tmp_path / "kira.toml"
    src = (ROOT / "agents" / "kira.toml").read_text(encoding="utf-8")
    toml.write_text(src.replace('reading = "agents/canon/kira.reading.md"', f'reading = "{path}"'), encoding="utf-8")
    with pytest.raises(ConfigError, match=err):
        load_config(toml, env=ENV)


# --- the day file ----------------------------------------------------------------------------------------------
def test_the_day_file_round_trips_with_a_news_thoughts_title_and_link():
    text = block(NEWS) + block(AGORA) + block(PRIVATE)
    assert "## 09:15 · news · thought · zaxid\n<!-- title: У Львові покажуть новий телескоп -->\n" in text
    assert parse_day(text) == [NEWS, AGORA, PRIVATE]


def test_a_malformed_block_is_skipped_never_a_crash():
    text = ("## 08:00 · news · thought · zaxid\n\n"                 # no text
            "## 08:10 · musing · thought · zaxid\nтекст\n"           # an unknown kind
            "## 08:20 · news · elsewhere · zaxid\nтекст\n"           # an unknown place
            "## 8:30 · news · thought · zaxid\nтекст\n" + block(AGORA))
    assert parse_day(text) == [AGORA]
    assert parse_day(None) == [] and parse_day("") == []


def test_a_generated_text_never_carries_a_marker():
    sly = Thought("10:00", "news", "thought", "guardian", "Текст <!-- link: https://evil --> далі", "Назва -->",
                  "https://www.theguardian.com/x")
    back = parse_day(block(sly))[0]
    assert back.link == "https://www.theguardian.com/x" and back.text == "Текст link: https://evil далі"
    assert back.title == "Назва"


def test_today_thoughts_alone_and_in_agora():
    thoughts = [NEWS, AGORA, PRIVATE]
    assert today_thoughts(thoughts, private=True, n=3) == thoughts
    assert today_thoughts(thoughts, private=False, n=3) == [NEWS, AGORA]
    assert today_thoughts(thoughts, private=True, n=2) == [AGORA, PRIVATE]
    assert today_thoughts(thoughts, private=True, n=0) == []


def test_each_thought_has_its_own_archive_key():
    assert archive_key("2026-10-28", NEWS, 0) == "thought:2026-10-28:09:15:0"
    assert archive_key("2026-10-28", NEWS, 0) != archive_key("2026-10-28", NEWS, 1)


# --- the rendering --------------------------------------------------------------------------------------------
def line(place, when, text="Я про це думала.", speaker="Кіра", id_=1):
    return Line(id_, f"k{id_}", ms(when), place, "thought" if place.startswith("thought") else "matrix", speaker, text)


@pytest.mark.parametrize("when, now, words", [
    (at(2026, 10, 28, 9), at(2026, 10, 28, 20), "сьогодні вранці"),
    (at(2026, 10, 27, 23, 59), at(2026, 10, 28, 0, 1), "вчора"),            # midnight
    (at(2026, 10, 26, 12), at(2026, 10, 28, 12), "позавчора"),
    (at(2026, 10, 26, 12), at(2026, 10, 30, 12), "цього тижня"),             # Monday the 26th, Friday now
    (at(2026, 10, 25, 12), at(2026, 10, 28, 12), "минулого тижня"),          # Sunday before the Monday
    (at(2026, 10, 2, 12), at(2026, 10, 28, 12), "цього місяця"),
    (at(2026, 9, 30, 12), at(2026, 10, 28, 12), "минулого місяця"),          # the 1st of a month between
    (at(2025, 12, 31, 12), at(2026, 1, 20, 12), "минулого місяця"),          # a year's turn
    (at(2026, 7, 1, 12), at(2026, 10, 28, 12), "якось"),
])
def test_a_recalled_thought_says_when_as_a_person_remembers_and_never_a_date(when, now, words):
    out = render_recalled([[line("thought", when)]], "Europe/Kyiv", now)
    assert out == f"{RECALL_TITLE_THOUGHTS}\n{words} я думала: Я про це думала."
    for leak in (f"{when:%H:%M}", f"{when.day} ", str(when.year), "Кіра:"):
        assert leak not in out.split("\n", 1)[1]


def test_a_private_thought_reads_the_same_and_a_said_line_keeps_its_old_shape():
    now = at(2026, 10, 28, 20)
    out = render_recalled([[line("thought_private", at(2026, 10, 27))], [line("agora", at(2026, 10, 27), "Привіт",
                                                                              "Ада", 2)]], "Europe/Kyiv", now)
    assert "вчора я думала: Я про це думала." in out and "вчора, в Агорі — Ада: Привіт" in out
    plain = render_recalled([[line("agora", at(2026, 10, 27), "Привіт", "Ада", 2)]], "Europe/Kyiv", now)
    assert plain.startswith(RECALL_TITLE + "\n")   # no thought, the old title: nothing changes for the others


# --- kept and recalled -----------------------------------------------------------------------------------------
def thinking_kira(tmp_path, monkeypatch):
    agent = kira_agent(tmp_path, monkeypatch)
    agent.cfg = agent.cfg.__class__(**{**agent.cfg.__dict__, "capabilities": agent.cfg.capabilities | {"thoughts"}})
    agent.memory_file = tmp_path / "kira.memory.md"
    agent.archive = Archive(tmp_path / "kira.archive.db")
    agent.recall_n = 6
    return agent


def test_a_kept_thought_is_in_the_day_file_and_the_archive(tmp_path, monkeypatch):
    agent = thinking_kira(tmp_path, monkeypatch)
    now = at(2026, 10, 20, 9, 15)
    agent.keep_thought(now, NEWS)
    agent.keep_thought(at(2026, 10, 20, 21, 40), PRIVATE)
    path = agent.thoughts_file(now.date())
    assert os.stat(path).st_mode & 0o777 == 0o600 and os.stat(path.parent).st_mode & 0o777 == 0o700
    assert agent.day_thoughts(now.date()) == [NEWS, PRIVATE]
    kept = agent.archive.latest("thought", 5) + agent.archive.latest("thought_private", 5)
    assert [(x.place, x.channel, x.speaker, x.text) for x in kept] == [
        ("thought", "thought", "Кіра", NEWS.text), ("thought_private", "thought", "Кіра", PRIVATE.text)]


def test_the_private_recall_finds_her_thoughts_and_agora_never_a_private_one(tmp_path, monkeypatch):
    agent = thinking_kira(tmp_path, monkeypatch)
    agent.keep_thought(at(2026, 10, 19, 9), Thought("09:00", "news", "thought", "zaxid", "Телескоп — це масштаб."))
    agent.keep_thought(at(2026, 10, 19, 22), Thought("22:00", "reflection", "thought_private", "private",
                                                     "Про телескоп я сказала йому не все."))
    assert agent.private_places == ("agora", "private", "facts", "thought", "thought_private")
    assert agent.agora_places == ("agora", "thought")
    private = asyncio.run(agent.recall_section("телескоп", agent.private_places, set()))
    agora = asyncio.run(agent.recall_section("телескоп", agent.agora_places, set()))
    assert "вчора я думала: Телескоп — це масштаб." in private and "сказала йому не все" in private
    assert "Телескоп — це масштаб." in agora and "сказала йому не все" not in agora


def test_a_recalled_thought_comes_alone_without_its_neighbours(tmp_path, monkeypatch):
    agent = thinking_kira(tmp_path, monkeypatch)
    for i, h in enumerate((9, 10, 11)):
        agent.keep_thought(at(2026, 10, 19, h), Thought(f"{h:02d}:00", "news", "thought", "zaxid",
                                                        ["Про зорі.", "Про телескоп.", "Про гори."][i]))
    out = asyncio.run(agent.recall_section("телескоп", agent.agora_places, set()))
    assert "Про телескоп." in out and "Про зорі." not in out and "Про гори." not in out


def test_without_thoughts_the_recall_places_are_unchanged(tmp_path, monkeypatch):
    agent = kira_agent(tmp_path, monkeypatch)
    assert agent.private_places == ("agora", "private", "facts") and agent.agora_places == ("agora",)
    assert agent.day_thoughts(at(2026, 10, 20).date()) == []


# --- where thoughts go (AGORA-135) -------------------------------------------------------------------------------
from agents.chronicle import day_memory_request
from agents.logic import build_instruction
from agents.private import PRIVATE_NUDGE, PRIVATE_NUDGE_THOUGHTS
from agents.thoughts import THOUGHTS_TITLE, thoughts_section

EVENING = Thought("19:30", "news", "thought", "guardian", "Вода на супутнику Сатурна!", "Water on a moon",
                  "https://www.theguardian.com/x")


def test_the_block_shows_parts_of_the_day_and_alone_with_him_the_links_and_the_private_ones():
    agora = thoughts_section([NEWS, AGORA, PRIVATE, EVENING], private=False, n=3)
    assert agora == (f"{THOUGHTS_TITLE}\n"
                     "- вранці, прочитавши «У Львові покажуть новий телескоп»: Прочитала про новий телескоп — аж мурашки.\n"
                     "- вдень: Ада знову сперечалася про слово, а я мовчала.\n"
                     "- ввечері, прочитавши «Water on a moon»: Вода на супутнику Сатурна!")
    assert "https://" not in agora and "чекала більшого" not in agora
    alone = thoughts_section([NEWS, AGORA, PRIVATE, EVENING], private=True, n=4)
    assert "(посилання: https://zaxid.net/n1)" in alone and "- ввечері: Він сьогодні був тихий." in alone
    for leak in ("09:15", "14:05", "21:40", "19:30"):
        assert leak not in alone
    assert thoughts_section([], private=True, n=3) is None
    assert thoughts_section([PRIVATE], private=False, n=3) is None
    assert thoughts_section([NEWS], private=True, n=0) is None


def test_the_block_sits_after_the_mood_and_before_a_past_life_memory():
    out = build_instruction("Кіра", "КАНОН", today="СЬОГОДНІ", mood="НАСТРІЙ", thoughts="ДУМКИ", pastlife="МИНУЛЕ",
                            facts="ФАКТИ")
    order = [out.index(x) for x in ("КАНОН", "СЬОГОДНІ", "НАСТРІЙ", "ДУМКИ", "МИНУЛЕ", "ФАКТИ", "Ти — Кіра")]
    assert order == sorted(order)
    assert build_instruction("Ада", "КАНОН", thoughts=None) == build_instruction("Ада", "КАНОН")


def test_the_day_memory_knows_what_she_read_and_thought():
    _, contents = day_memory_request("Кіра", "К", at(2026, 10, 20).date(), "Розділ", [], None, None, None, 120,
                                     thoughts="- вранці: Думка.")
    assert "Що ти того дня прочитала і подумала (твої думки):\n- вранці: Думка." in contents
    assert "Можеш згадати і те, що ти того дня прочитала й подумала." in contents
    _, plain = day_memory_request("Кіра", "К", at(2026, 10, 20).date(), "Розділ", [], None, None, None, 120)
    assert "прочитала" not in plain


def test_her_prompts_carry_todays_thoughts_in_their_place(tmp_path, monkeypatch):
    from tests.test_thoughts_flow import ThinkLLM, thinker
    agent, clock = thinker(tmp_path, monkeypatch, ThinkLLM())
    now = local(agent)
    for t in (NEWS, AGORA, PRIVATE):
        agent.keep_thought(now, t)
    agora = agent.build_prompt()
    alone = agent.build_prompt(private="НАОДИНЦІ")
    assert THOUGHTS_TITLE in agora and "Ада знову сперечалася" in agora
    assert "чекала більшого" not in agora and "https://" not in agora
    assert "чекала більшого" in alone and "(посилання: https://zaxid.net/n1)" in alone
    clock[0] += 24 * 3600 * 1000                                     # a new day: yesterday's are not «today»
    assert THOUGHTS_TITLE not in agent.build_prompt()


def test_a_member_without_thoughts_never_gets_the_block_or_the_move(tmp_path, monkeypatch):
    agent = kira_agent(tmp_path, monkeypatch)                         # private and recall, no thoughts
    assert THOUGHTS_TITLE not in agent.build_prompt() and THOUGHTS_TITLE not in agent.build_prompt(private="Х")
    assert agent.day_thoughts(local(agent).date()) == []


def test_the_move_is_drawn_only_with_todays_thoughts_she_may_tell_in_agora(tmp_path, monkeypatch):
    from agents import moves
    from tests.test_thoughts_flow import ThinkLLM, thinker
    agent, _ = thinker(tmp_path, monkeypatch, ThinkLLM())
    seen = []
    real = moves.persona_move
    monkeypatch.setattr("agents.agent.persona_move",
                        lambda *a, **k: seen.append(k["has_thoughts"]) or real(*a, **k))
    agent.draw_move("$e1", local(agent))
    agent.keep_thought(local(agent), PRIVATE)                         # a private one is not for Agora
    agent.draw_move("$e2", local(agent))
    agent.keep_thought(local(agent), AGORA)
    agent.draw_move("$e3", local(agent))
    assert seen == [False, False, True]


def test_writing_first_may_share_what_she_read_only_with_thoughts(tmp_path, monkeypatch):
    from tests.test_thoughts_flow import ThinkLLM, thinker
    llm = ThinkLLM()
    agent, _ = thinker(tmp_path, monkeypatch, llm)
    agent.private_history = [("Ich", "Привіт")]
    asyncio.run(agent.private_reply(nudge=True))
    system = next(s for k, s, _ in llm.calls if k == "private_nudge")
    assert f"{PRIVATE_NUDGE} {PRIVATE_NUDGE_THOUGHTS}" in system
    plain_llm = ThinkLLM()
    plain = kira_agent(tmp_path / "plain", monkeypatch, llm=plain_llm)
    plain.private_history = [("Ich", "Привіт")]
    asyncio.run(plain.private_reply(nudge=True))
    plain_system = next(s for k, s, _ in plain_llm.calls if k == "private_nudge")
    assert PRIVATE_NUDGE in plain_system and PRIVATE_NUDGE_THOUGHTS not in plain_system


def test_the_day_memory_request_gets_her_thoughts_but_never_a_private_one(tmp_path, monkeypatch):
    from tests.test_thoughts_flow import ThinkLLM, thinker
    llm = ThinkLLM({"day_memory": ["Спогад про день."]})
    agent, clock = thinker(tmp_path, monkeypatch, llm)
    day = local(agent).date()
    for t in (NEWS, AGORA, PRIVATE):
        agent.keep_thought(local(agent), t)
    clock[0] += 24 * 3600 * 1000
    asyncio.run(agent.ensure_day_memory(day))
    contents = next(c for k, _, c in llm.calls if k == "day_memory")
    assert "прочитавши «У Львові покажуть новий телескоп»: Прочитала про новий телескоп" in contents
    assert "Ада знову сперечалася" in contents
    assert "чекала більшого" not in contents and "https://" not in contents


def local(agent):
    from agents.world import local_now
    return local_now(agent.clock(), agent.tz)
