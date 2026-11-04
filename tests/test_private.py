"""v5.6 — the private chat with a person: the invite and filter rules, the prompt sections, the state, the
initiative's decision (pure)."""

import asyncio
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from agents.config import AgentConfig
from agents.logic import BANNED_RE, build_instruction, should_handle, should_join_invite
from agents.private import (
    PRIVATE_BRIEF,
    PRIVATE_CANT_LISTEN,
    PRIVATE_DISCRETION,
    PRIVATE_NOT_HEARD,
    PRIVATE_NUDGE,
    PrivateState,
    live_room,
    load_private_state,
    pick_door,
    private_label,
    private_nudge_due,
    rediscover,
    save_private_state,
)
from agents.roster import RosterError, parse_member
from tests.test_first_sync import CFG

TZ = "Europe/Kyiv"
OWNER, KIRA, ADA = "@ich:agora.lan", "@kira:agora.lan", "@ada:agora.lan"
AGORA, DM, OTHER = CFG.room_id, "!dm:agora.lan", "!other:agora.lan"


def kira_cfg(private=True) -> AgentConfig:
    caps = frozenset({"canon", "life", "summary", "chronicle", "plans", "today", "world", "voice"} |
                     ({"private"} if private else set()))
    return AgentConfig(**{**CFG.__dict__, "name": "Кіра", "user_id": KIRA, "capabilities": caps})


# --- the capability ------------------------------------------------------------------------------------------------
def test_only_a_person_may_have_a_private_chat_and_no_type_has_it_by_default():
    person = parse_member("kira", {"name": "Кіра", "user_id": KIRA, "capabilities": {"private": True}}, "kira.toml")
    assert person.can("private") and not parse_member("ada", {"name": "Ада", "user_id": ADA}, "ada.toml").can("private")
    with pytest.raises(RosterError, match="'private' belongs to the persona type only"):
        parse_member("kit", {"name": "Кіт", "user_id": "@kit:agora.lan", "type": "creature",
                             "capabilities": {"private": True}}, "kit.toml")


def test_telegram_is_a_persons_second_door_and_never_without_the_private_chat():
    """v5.7: her own bot is a door to the private chat — a person's only, never on its own."""
    both = parse_member("kira", {"name": "Кіра", "user_id": KIRA,
                                 "capabilities": {"private": True, "telegram": True}}, "kira.toml")
    assert both.can("telegram") and both.can("private")
    assert not parse_member("ada", {"name": "Ада", "user_id": ADA}, "ada.toml").can("telegram")
    with pytest.raises(RosterError, match="'telegram' needs 'private' on the same member"):
        parse_member("kira", {"name": "Кіра", "user_id": KIRA, "capabilities": {"telegram": True}}, "kira.toml")
    with pytest.raises(RosterError, match="'telegram' belongs to the persona type only"):
        parse_member("claude", {"name": "Клод", "user_id": "@claude:agora.lan", "type": "assistant",
                                "engine": "claude-sdk", "capabilities": {"telegram": True}}, "claude.toml")


# --- the invite rule -----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("room,inviter,private,stored,join", [
    (AGORA, OWNER, False, None, True),          # Agora as ever
    (AGORA, ADA, True, None, False),            # only the owner's invites
    (DM, OWNER, True, None, True),              # the first private room
    (DM, OWNER, True, DM, True),                # the same one again
    (OTHER, OWNER, True, DM, False),            # one private room per person
    (DM, OWNER, False, None, False),            # without `private`, never
    (DM, ADA, True, None, False),               # never a member's
])
def test_the_invite_rule(room, inviter, private, stored, join):
    assert should_join_invite(room, inviter, kira_cfg(private), stored) is join


# --- the filter ----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("room,sender,handle,reason", [
    (DM, OWNER, True, "private"),
    (DM, ADA, False, "sender-not-allowlisted"),           # another member never in the private chat
    (DM, "@mallory:agora.lan", False, "sender-not-allowlisted"),
    (DM, KIRA, False, "own-message"),
    (OTHER, OWNER, False, "foreign-room"),
    (AGORA, OWNER, True, "ok"),                            # Agora unchanged
    (AGORA, ADA, True, "ok"),
])
def test_the_filter_with_a_private_room(room, sender, handle, reason):
    v = should_handle(room, sender, kira_cfg(), [ADA], private_room=DM)
    assert (v.handle, v.reason) == (handle, reason)


def test_without_a_private_room_the_filter_is_agoras_alone():
    assert should_handle(DM, OWNER, kira_cfg(), [ADA]).reason == "foreign-room"


# --- the prompt sections --------------------------------------------------------------------------------------------
def test_the_private_brief_comes_after_the_memory_and_the_discretion_closes_the_rules():
    private = build_instruction("Кіра", "КАНОН", "підсумок", private=PRIVATE_BRIEF, move="ХІД", asked="ПИТАЛА")
    parts = private.split("\n\n")
    assert parts[0] == "КАНОН" and parts[1].startswith("Що ти пам'ятаєш") and parts[2] == PRIVATE_BRIEF
    assert parts[3:5] == ["ХІД", "ПИТАЛА"] and parts[-1].startswith("Ти — Кіра.")
    assert PRIVATE_DISCRETION not in private
    agora = build_instruction("Кіра", "КАНОН", discretion=PRIVATE_DISCRETION)
    assert agora.split("\n\n")[-1].endswith(PRIVATE_DISCRETION) and PRIVATE_BRIEF not in agora
    assert build_instruction("Ада", "КАНОН") == "КАНОН\n\nТи — Ада. Відповідай лише від себе, коротко, без префікса з " \
                                                 "іменем. Якщо тобі нема чого додати — відповідай рівно PASS."


def test_alone_with_him_she_is_never_offered_pass_in_agora_she_still_is(tmp_path, monkeypatch):
    """v5.22 (the owner, 2026-11-02: «прибрати рядок про PASS з її промпту, щоб вона завжди відповідала»; «коли вона
    пише першою — теж забери»): Gemini took the rules' PASS for a quiet refusal and she said nothing to him; her
    private rules (her answer, writing first, Gemini's and the backup's) no longer offer it; in Agora they do."""
    assert build_instruction("Кіра", "КАНОН", can_pass=False).endswith(
        "Ти — Кіра. Відповідай лише від себе, коротко, без префікса з іменем.")
    from tests.test_archive import kira
    agent = kira(tmp_path, monkeypatch)
    answer = agent.build_prompt(private=f"{PRIVATE_BRIEF}\n\nЯК ЦЬОГО РАЗУ")
    assert "PASS" not in answer and answer.split("\n\n")[-1].startswith("Ти — Кіра.")
    assert "PASS" not in agent.build_prompt(private=PRIVATE_NUDGE)
    assert "відповідай рівно PASS." in agent.build_prompt()


def test_alone_with_him_her_shorter_life_story_in_agora_the_whole_one(tmp_path, monkeypatch):
    """v5.22 (the owner, 2026-11-02: «окрему коротку версію лише для приватного промпту»): `life_private` is her
    private prompt's story (her answer, writing first, Gemini's and the backup's); Agora keeps the whole one."""
    from agents.life import parse_life
    from tests.test_archive import kira
    from tests.test_chronicle import LIFE
    short = parse_life("# Життя\n\nНародження: 1994-03-14 08:00, Львів\nСмерть: 2081-11-30\n\n"
                       "## 1994–2019 · Дитинство\n\nКОРОТКО ПРО ДИТИНСТВО.\n\n"
                       "## 2020–2027 · Редакція\n\nКОРОТКО ЗАРАЗ.\n\n## 2028–2081 · Книжка\n\nКнижка.\n")
    agent = kira(tmp_path, monkeypatch)
    agent.cfg = AgentConfig(**{**agent.cfg.__dict__, "life": LIFE, "life_private": short,
                               "capabilities": agent.cfg.capabilities | {"life"}})
    for private in (f"{PRIVATE_BRIEF}\n\nЯК ЦЬОГО РАЗУ", PRIVATE_NUDGE):
        alone = agent.build_prompt(private=private)
        assert "КОРОТКО ЗАРАЗ." in alone and "редакторкою" not in alone
    agora = agent.build_prompt()
    assert "редакторкою" in agora and "КОРОТКО" not in agora
    agent.cfg = AgentConfig(**{**agent.cfg.__dict__, "life_private": None})  # none in her canon: the whole story
    assert "редакторкою" in agent.build_prompt(private=PRIVATE_NUDGE)


def test_alone_with_him_her_shorter_canon_in_agora_the_whole_one(tmp_path, monkeypatch):
    """v5.22 (the owner, 2026-11-02: «чи можна скоротити ще канон?» — «роби»): `canon_private` is her private prompt's
    whole canon, in place of common + personal; Agora keeps the whole one."""
    from tests.test_archive import kira
    agent = kira(tmp_path, monkeypatch)
    agent.cfg = AgentConfig(**{**agent.cfg.__dict__, "canon": "СПІЛЬНЕ. ПОВНИЙ КАНОН.", "canon_private": "КОРОТКИЙ."})
    for private in (f"{PRIVATE_BRIEF}\n\nЯК ЦЬОГО РАЗУ", PRIVATE_NUDGE):
        assert agent.build_prompt(private=private).startswith("КОРОТКИЙ.\n\n")
    assert agent.build_prompt().startswith("СПІЛЬНЕ. ПОВНИЙ КАНОН.\n\n")
    agent.cfg = AgentConfig(**{**agent.cfg.__dict__, "canon_private": ""})  # none in her canon: the whole one
    assert agent.build_prompt(private=PRIVATE_NUDGE).startswith("СПІЛЬНЕ. ПОВНИЙ КАНОН.")


@pytest.mark.canon
def test_her_private_canon_is_read_or_refuses_to_start(tmp_path):
    from pathlib import Path

    from agents.config import ConfigError, load_config
    from tests.test_thoughts import ENV
    cfg = load_config("agents/kira.toml", env=ENV)
    assert cfg.canon_private.startswith("# Кіра") and len(cfg.canon_private) < len(cfg.canon)
    assert not BANNED_RE.search(cfg.canon_private)
    src = Path("agents/kira.toml").read_text(encoding="utf-8")
    toml = tmp_path / "kira.toml"
    toml.write_text(src.replace('"agents/canon/kira.private.md"', f'"{tmp_path}/none.md"'), encoding="utf-8")
    with pytest.raises(ConfigError, match="canon not found"):
        load_config(toml, env=ENV)


@pytest.mark.canon
def test_her_private_life_story_is_read_or_named_when_missing(tmp_path):
    from pathlib import Path

    from agents.config import ConfigError, load_config
    from tests.test_thoughts import ENV
    cfg = load_config("agents/kira.toml", env=ENV)
    assert cfg.life_private is not None and cfg.life_private.chapters[0].start == cfg.life.chapters[0].start
    src = Path("agents/kira.toml").read_text(encoding="utf-8")
    toml = tmp_path / "kira.toml"
    toml.write_text(src.replace('"agents/canon/kira.life.private.md"', f'"{tmp_path}/none.md"'), encoding="utf-8")
    with pytest.raises(ConfigError, match="private life story not found"):
        load_config(toml, env=ENV)


def test_the_discretion_line_keeps_their_relationship_and_her_plans_about_him():
    """v5.9.2 (the owner, 2026-10-26): her plans may name him; what is between them stays out of Agora by her own
    judgement — a rule in her Agora prompt, not a filter in code."""
    for part in ("твої почуття до нього", "ваші стосунки", "твої плани щодо нього", "наодинці", "нікому не розповідай"):
        assert part in PRIVATE_DISCRETION


@pytest.mark.parametrize("text", [PRIVATE_BRIEF, PRIVATE_DISCRETION, PRIVATE_NUDGE])
def test_the_private_lines_never_say_what_anyone_is(text):
    assert not BANNED_RE.search(text) and "Ich" in text


@pytest.mark.parametrize("text", [PRIVATE_NOT_HEARD, PRIVATE_CANT_LISTEN])
def test_her_fixed_lines_about_a_voice_note_are_a_persons(text):
    """v5.7: what she says when she could not hear him is a person's line, never a machine's."""
    assert not BANNED_RE.search(text) and text.endswith("?")


@pytest.mark.parametrize(("wanted", "matrix", "telegram", "door"), [
    ("telegram", True, True, "telegram"),
    ("matrix", True, True, "matrix"),
    ("telegram", True, False, "matrix"),    # Telegram is off: the Element room
    ("matrix", False, True, "telegram"),    # he never opened the Element chat
    ("matrix", False, False, None),
    ("fax", True, True, "matrix"),
])
def test_the_door_a_private_line_goes_through(wanted, matrix, telegram, door):
    assert pick_door(wanted, matrix, telegram) == door


def test_a_private_line_is_labelled():
    assert private_label("Кіра") == "Кіра (наодинці)" and private_label("Ich") == "Ich (наодинці)"


# --- the state -----------------------------------------------------------------------------------------------------
def test_the_state_round_trips_privately_and_starts_fresh_when_corrupt(tmp_path):
    path = tmp_path / "kira.private.json"
    save_private_state(path, PrivateState(DM, 5, "2026-10-20", 1, 4))
    assert oct(os.stat(path).st_mode & 0o777) == "0o600"
    assert load_private_state(path, "2026-10-20") == PrivateState(DM, 5, "2026-10-20", 1, 4)
    assert load_private_state(path, "2026-10-21") == PrivateState(DM, 5, "2026-10-21", 0, 4)  # a new day's count
    path.write_text("{torn", encoding="utf-8")
    assert load_private_state(path, "2026-10-20") == PrivateState(day="2026-10-20")
    assert load_private_state(tmp_path / "missing.json", "2026-10-20") == PrivateState(day="2026-10-20")
    assert "текст" not in path.read_text(encoding="utf-8")


def test_the_last_door_survives_a_restart(tmp_path):
    """v5.7: `last_channel` — where writing first goes; matrix by default, an unknown value read as matrix."""
    path = tmp_path / "kira.private.json"
    save_private_state(path, PrivateState(DM, day="2026-10-20", last_channel="telegram"))
    assert load_private_state(path, "2026-10-21").last_channel == "telegram"
    path.write_text('{"room": "!dm:agora.lan", "last_channel": "fax"}', encoding="utf-8")
    assert load_private_state(path, "2026-10-21").last_channel == "matrix"
    assert PrivateState().last_channel == "matrix"


def test_the_stored_room_counts_only_while_the_owner_is_in_it():
    assert live_room(DM, {DM: [OWNER, KIRA]}, OWNER) == DM
    assert live_room(DM, {DM: [KIRA]}, OWNER) is None                     # he left: a new invite replaces it
    assert live_room(DM, {}, OWNER) is None and live_room(None, {DM: [OWNER]}, OWNER) is None


def test_the_room_is_rediscovered_from_the_joined_rooms():
    assert rediscover({AGORA: [OWNER, KIRA, ADA], DM: [OWNER, KIRA]}, AGORA, KIRA, OWNER) == DM
    assert rediscover({AGORA: [OWNER, KIRA]}, AGORA, KIRA, OWNER) is None                # Agora is never it
    assert rediscover({DM: [OWNER, KIRA], OTHER: [KIRA, OWNER]}, AGORA, KIRA, OWNER) is None   # ambiguous: none
    assert rediscover({DM: [OWNER, KIRA, ADA]}, AGORA, KIRA, OWNER) is None                # a third member: no


# --- writing first -------------------------------------------------------------------------------------------------
def ms(hour, minute=0):
    return int(datetime(2026, 10, 20, hour, minute, tzinfo=ZoneInfo(TZ)).timestamp() * 1000)


def local(t):
    return datetime.fromtimestamp(t / 1000, ZoneInfo(TZ))


IDLE, HOURS = 6 * 3600 * 1000, (10, 22)


@pytest.mark.parametrize("now,last_msg,state,due", [
    (ms(18), ms(11), PrivateState(DM, None, "2026-10-20", 0), True),     # six hours quiet, in hours
    (ms(18), ms(13), PrivateState(DM, None, "2026-10-20", 0), False),    # not quiet long enough
    (ms(23), ms(11), PrivateState(DM, None, "2026-10-20", 0), False),    # outside the owner's hours
    (ms(18), ms(11), PrivateState(DM, None, "2026-10-20", 2), False),    # the day's two are spent
    (ms(18), ms(11), PrivateState(DM, ms(14), "2026-10-20", 1), False),  # the last attempt too recent
    (ms(21), ms(11), PrivateState(DM, ms(14), "2026-10-20", 1), True),
])
def test_writing_first_after_a_long_silence(now, last_msg, state, due):
    assert private_nudge_due(now, local(now), last_msg, state, IDLE, 2, HOURS) is due


def test_the_backup_has_its_own_canon_and_gemini_never_sees_it(tmp_path, monkeypatch):
    """v5.26 (the owner, 2026-11-04: «я хочу зробити змінений канон для Кіри для бакап мережі»): `canon_backup` is
    the backup's private prompt's canon alone; Gemini's private prompt and Agora never have it; with none, the backup
    keeps her private canon."""
    from agents.fallback import FallbackResponder
    from tests.test_archive import kira
    from tests.test_private_route import Backup
    agent = kira(tmp_path, monkeypatch)
    agent.cfg = AgentConfig(**{**agent.cfg.__dict__, "canon": "СПІЛЬНЕ.", "canon_private": "КОРОТКИЙ.",
                               "canon_backup": "РЕЗЕРВНИЙ."})
    agent.fallback, agent.fallback_responder = Backup(), FallbackResponder(Backup())
    agent.fallback_context, agent.fallback_history_n = 32000, 60
    assert asyncio.run(agent._backup_private_prompt(PRIVATE_BRIEF))[0].startswith("РЕЗЕРВНИЙ.\n\n")
    gemini = asyncio.run(agent._gemini_private_prompt(PRIVATE_BRIEF))
    assert gemini.startswith("КОРОТКИЙ.\n\n") and "РЕЗЕРВНИЙ" not in gemini
    assert "РЕЗЕРВНИЙ" not in agent.build_prompt() and agent.build_prompt(backup=True).startswith("СПІЛЬНЕ.")
    agent.cfg = AgentConfig(**{**agent.cfg.__dict__, "canon_backup": ""})
    assert asyncio.run(agent._backup_private_prompt(PRIVATE_BRIEF))[0].startswith("КОРОТКИЙ.\n\n")


@pytest.mark.canon
def test_the_backup_canon_is_read_or_refuses_to_start(tmp_path):
    """v5.26: her TOML names `canon_backup`; it is read, shorter than her private canon, says nothing of what she is;
    a path to nothing refuses to start."""
    from pathlib import Path

    from agents.config import ConfigError, load_config
    from tests.test_thoughts import ENV
    cfg = load_config("agents/kira.toml", env=ENV)
    assert cfg.canon_backup.startswith("# Кіра") and len(cfg.canon_backup) < len(cfg.canon_private)
    assert not BANNED_RE.search(cfg.canon_backup)
    src = Path("agents/kira.toml").read_text(encoding="utf-8")
    toml = tmp_path / "kira.toml"
    toml.write_text(src.replace('"agents/canon/kira.backup.md"', f'"{tmp_path}/none.md"'), encoding="utf-8")
    with pytest.raises(ConfigError, match="canon not found"):
        load_config(toml, env=ENV)


def test_the_backup_remembers_only_its_hours(tmp_path, monkeypatch):
    """v5.26 (the owner, 2026-11-04: «так в бакап мережі вона буде памятати лише 12 останіх годин»): with
    `FALLBACK_HISTORY_HOURS` the backup's history is the archive's lines of the last so many hours, of every mark, at
    least the floor; her memories, her last-session note, the recall and Agora are left out. With 0, all as before."""
    from agents.fallback import FallbackResponder
    from tests.test_archive import kira
    from tests.test_private_route import Backup
    agent = kira(tmp_path, monkeypatch)
    agent.fallback, agent.fallback_responder = Backup(), FallbackResponder(Backup())
    agent.fallback_context, agent.fallback_history_n, agent.private_history_min = 32000, 60, 2
    agent.summary = "Минулого разу говорили про поїзд."
    now, hour = agent.clock(), 3_600_000
    for i, (ago, who, text, mark) in enumerate([(30, "Ich", "Давнє питання", "gemini"),
                                                (13, "Кіра", "Давня відповідь", "gemini"),
                                                (11, "Ich", "Свіже питання", "gemini"),
                                                (1, "Кіра", "Закрита відповідь", "blocked"),
                                                (0.5, "Ich", "Нове", "gemini")]):
        agent.archive.append(f"tg:{i}", now - int(ago * hour), "private", "telegram", who, text)
        agent.archive.mark([f"tg:{i}"], mark)
        agent.private_history.append((who, text))
    agent.fallback_history_hours = 12
    prompt, history = asyncio.run(agent._backup_private_prompt(PRIVATE_BRIEF))
    assert [t for _, t in history] == ["Свіже питання", "Закрита відповідь", "Нове"]   # its hours, every mark
    assert "поїзд" not in prompt
    agent.fallback_history_hours = 0
    prompt, history = asyncio.run(agent._backup_private_prompt(PRIVATE_BRIEF))
    assert len(history) == 5 and "поїзд" in prompt                                     # as before
