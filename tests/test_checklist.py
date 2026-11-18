"""v9.2 — her checklist (the owner, 2026-11-18: «має бути чекліст що вже виконалось а що ні»; «щоб вона могла позначити
це виконано чи ні, бо зараз вона читає це в переписці і думає що подія виконана хоча такого не було»): the append-only
log folded into the list, «time passed» derived, the section, a past day plan's outcomes (pure, clock injected;
made-up items only)."""

import json
import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from agents.checklist import (
    add_entry,
    append,
    fold,
    load,
    mark_entry,
    mark_problem,
    next_id,
    parse_due,
    plan_outcomes,
    section_lines,
    state_of,
)
from agents.roster import RosterError, parse_member

KYIV = ZoneInfo("Europe/Kyiv")
NOW = datetime(2026, 11, 19, 14, 20, tzinfo=KYIV)  # a Thursday


def at(*a):
    return datetime(*a, tzinfo=KYIV)


# --- AGORA-282: the log and the fold --------------------------------------------------------------------------------
def test_the_log_is_appended_private_and_folded_into_the_list(tmp_path):
    path = tmp_path / "kira.checklist.jsonl"
    log = [add_entry(1, "сходити в кіно", at(2026, 11, 18, 21), who="Ich", ich=True, due="2026-11-20T19:00",
                     source="line:abc"),
           add_entry(2, "подзвонити мамі", at(2026, 11, 18, 21, 5), due="2026-11-18")]
    append(path, log)
    append(path, [mark_entry(2, "done", at(2026, 11, 19, 9)), mark_entry(1, "moved", at(2026, 11, 19, 10),
                                                                          due="2026-11-21T18:00")])
    assert oct(os.stat(path).st_mode & 0o777) == "0o600"
    entries, corrupt = load(path)
    assert corrupt == 0 and [e["op"] for e in entries] == ["add", "add", "mark", "mark"]
    items = fold(entries)
    assert [(x.id, x.status, x.due) for x in items] == [(1, "moved", "2026-11-21T18:00"), (2, "done", "2026-11-18")]
    assert items[0].ich and items[0].who == "Ich" and next_id(entries) == 3
    with path.open("a", encoding="utf-8") as f:
        f.write("not json\n" + json.dumps({"op": "mark", "id": 9, "status": "done"}) + "\n")
    entries, corrupt = load(path)
    assert corrupt == 1 and fold(entries) == items                                  # an unknown number changes nothing
    assert load(tmp_path / "немає.jsonl") == ([], 0)


def test_a_mark_that_cannot_be_made_is_said_in_words():
    items = fold([add_entry(1, "кіно", NOW), add_entry(2, "лекція", NOW), mark_entry(2, "done", NOW)])
    assert mark_problem(items, 1, "done") is None and mark_problem(items, 1, "moved", "2026-11-21") is None
    assert "№7" in mark_problem(items, 7, "done")
    assert "зроблено" in mark_problem(items, 1, "кудись")
    assert "нова дата" in mark_problem(items, 1, "moved")
    assert "уже позначена" in mark_problem(items, 2, "missed")
    assert "номер" in mark_problem(items, "1", "done") and "номер" in mark_problem(items, True, "done")


def test_her_date_and_time_read_as_a_due_or_none():
    assert parse_due("2026-11-20", "19:00") == "2026-11-20T19:00"
    assert parse_due("2026-11-20", "9:05") == "2026-11-20T09:05"
    assert parse_due("2026-11-20", "25:00") == "2026-11-20" and parse_due("2026-11-20") == "2026-11-20"
    assert parse_due("завтра") is None and parse_due(None) is None


def test_time_passed_with_no_mark_reads_overdue():
    items = fold([add_entry(1, "кіно", at(2026, 11, 18), due="2026-11-19T14:00"),
                  add_entry(2, "лекція", at(2026, 11, 18), due="2026-11-19"),
                  add_entry(3, "зустріч", at(2026, 11, 18), due="2026-11-18"),
                  add_entry(4, "без часу", at(2026, 11, 18))])
    assert [state_of(x, NOW) for x in items] == ["overdue", "planned", "overdue", "planned"]
    assert state_of(items[1], at(2026, 11, 20, 0, 0)) == "overdue"                   # a day's due — after that day
    assert state_of(items[0], at(2026, 11, 19, 13, 59)) == "planned"


# --- the section ---------------------------------------------------------------------------------------------------
def test_the_section_open_first_then_the_closed_ones_by_days_and_cap_and_agora_without_him():
    entries = [add_entry(1, "сходити в кіно", at(2026, 11, 18, 21), who="Ich", ich=True, due="2026-11-20T19:00"),
               add_entry(2, "подзвонити мамі", at(2026, 11, 18, 21), due="2026-11-18"),
               add_entry(3, "дочитати статтю", at(2026, 11, 10)),
               add_entry(4, "старе", at(2026, 11, 1), due="2026-11-02"),
               mark_entry(4, "done", at(2026, 11, 3)),
               add_entry(5, "купити квіти", at(2026, 11, 17), due="2026-11-18"),
               mark_entry(5, "missed", at(2026, 11, 19, 9))]
    items = fold(entries)
    lines = section_lines(items, NOW, True, 7, 20)
    assert lines == [
        "№2 [час минув — не знаєш, чи це було] подзвонити мамі — вчора (18.11)",
        "№1 [заплановано] сходити в кіно (з Ich) — завтра (20.11, 19:00)",
        "№3 [заплановано] дочитати статтю — без дати, записано тиждень тому (10.11)",
        "№5 [не відбулося] купити квіти — вчора (18.11)",
    ]                                                                              # №4 closed 16 days ago: gone
    assert section_lines(items, NOW, True, 7, 2) == lines[:2]                      # the cap keeps the open ones first
    agora = section_lines(items, NOW, False, 7, 20)
    assert all("Ich" not in x for x in agora) and len(agora) == 3                  # never an item about him in Agora
    assert section_lines([], NOW, True, 7, 20) == []


# --- her life's day plan --------------------------------------------------------------------------------------------
def test_a_past_day_plans_outcomes_by_their_hidden_tags():
    text = ("- лекція о 10:00\n- кава з Олею <!-- mutation: postponed -->\n- спортзал <!-- mutation: cancelled -->\n"
            "- нова ідея <!-- mutation: whim -->\n")
    entries = plan_outcomes(text, date(2026, 11, 18), 7, NOW)
    items = fold(entries)
    assert [(x.id, x.what, x.status, x.by, x.plan_day) for x in items] == [
        (7, "лекція о 10:00", "done", "plan", "2026-11-18"), (8, "кава з Олею", "moved", "plan", "2026-11-18"),
        (9, "спортзал", "cancelled", "plan", "2026-11-18"), (10, "нова ідея", "done", "plan", "2026-11-18")]
    assert "mutation" not in json.dumps(entries, ensure_ascii=False)
    assert all(state_of(x, NOW) != "overdue" for x in items)                        # an outcome is never open
    assert "№8 [перенесено] кава з Олею (з твого плану на день) — вчора (18.11)" in section_lines(items, NOW, True, 7, 20)


# --- the capability -------------------------------------------------------------------------------------------------
def test_the_checklist_is_a_persons_and_needs_her_private_chat():
    member = parse_member("kira", {"name": "Кіра", "user_id": "@kira:agora.lan",
                                   "capabilities": {"private": True, "checklist": True}})
    assert member.can("checklist")
    with pytest.raises(RosterError, match="'checklist' needs 'private'"):
        parse_member("kira", {"name": "Кіра", "user_id": "@kira:agora.lan", "capabilities": {"checklist": True}})
    with pytest.raises(RosterError, match="persona type only"):
        parse_member("kit", {"name": "Кіт", "user_id": "@kit:agora.lan", "type": "creature",
                             "capabilities": {"checklist": True}})
