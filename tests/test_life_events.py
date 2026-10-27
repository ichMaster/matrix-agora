"""v5.11 — a chapter's dated events (`### Події`): parsed, cut out of the body, and selected by date."""

from datetime import date
from pathlib import Path

import pytest

from agents.life import LifeError, current_chapter, events_due, known_ahead, life_section, parse_life

STORY = """Народження: 2002-12-02 20:40, Донецьк
Смерть: 2089-08-12

## 2002–2023 · Минуле

Дитинство і навчання.

## 2024–2027 · Зараз

Робота в планетарії, звичайний тиждень.

### Події
- 2026-11-03 · known · Дедлайн статті про змінні зорі.
- 2026-10-29 · surprise · Подзвонила стара подруга з Единбурга.

- 2027-02-14 · known · Прем'єра нової програми під куполом.

### Люди

Мама, брат, подруги.

## 2028–2040 · Далі

Майбутнє, якого вона не знає.
"""
TODAY = date(2026, 10, 27)


def story(text: str = STORY):
    return parse_life(text)


def test_the_list_is_parsed_and_cut_out_of_the_body():
    cur = current_chapter(story(), TODAY)
    assert [(e.date, e.kind) for e in cur.events] == [
        (date(2026, 10, 29), "surprise"), (date(2026, 11, 3), "known"), (date(2027, 2, 14), "known")]
    assert cur.events[1].text == "Дедлайн статті про змінні зорі."
    assert "Події" not in cur.body and "Дедлайн" not in cur.body and "подруга з Единбурга" not in cur.body
    assert "Робота в планетарії" in cur.body and "### Люди" in cur.body and "Мама, брат" in cur.body


def test_a_story_without_the_list_is_unchanged():
    plain = STORY.split("### Події")[0] + "### Люди\n\nМама, брат, подруги.\n\n## 2028–2040 · Далі\n\nМайбутнє.\n"
    cur = current_chapter(story(plain), TODAY)
    assert cur.events == () and cur.body == "Робота в планетарії, звичайний тиждень.\n\n### Люди\n\nМама, брат, подруги."


def test_the_list_last_in_a_chapter():
    text = STORY.replace("### Люди\n\nМама, брат, подруги.\n\n", "")
    cur = current_chapter(story(text), TODAY)
    assert len(cur.events) == 3 and cur.body == "Робота в планетарії, звичайний тиждень."


@pytest.mark.parametrize("day", [date(2026, 10, 27), date(2026, 10, 28), date(2026, 10, 29), date(2026, 11, 3),
                                 date(2027, 2, 14), date(2027, 6, 1)])
def test_no_section_ever_shows_an_event(day):
    section = life_section(story(), day)
    for e in current_chapter(story(), TODAY).events:
        assert e.text not in section, (day, e.text)
    assert "Події" not in section


def test_events_due_on_their_date_only():
    s = story()
    assert events_due(s, date(2026, 10, 28)) == []
    assert [e.kind for e in events_due(s, date(2026, 10, 29))] == ["surprise"]
    assert [e.kind for e in events_due(s, date(2026, 11, 3))] == ["known"]
    assert events_due(s, date(2026, 11, 4)) == []


def test_known_ahead_never_a_surprise_and_at_the_edges():
    s = story()
    assert [e.date for e in known_ahead(s, TODAY, date(2026, 11, 3))] == [date(2026, 11, 3)]
    assert known_ahead(s, TODAY, date(2026, 11, 2)) == []                       # `until` is inclusive, not beyond
    assert known_ahead(s, date(2026, 11, 3), date(2026, 12, 31)) == []          # today itself is not ahead
    assert all(e.kind == "known" for e in known_ahead(s, date(2026, 1, 1), date(2027, 12, 31)))
    assert len(known_ahead(s, date(2026, 1, 1), date(2027, 12, 31))) == 2


@pytest.mark.parametrize("line, why", [
    ("- 2026-11-03 known Дедлайн.", "not '- YYYY-MM-DD"),
    ("Дедлайн статті.", "not '- YYYY-MM-DD"),
    ("- 2026-11-03 · maybe · Дедлайн.", "unknown event kind"),
    ("- 2026-02-30 · known · Дедлайн.", "bad event date"),
    ("- 2029-01-05 · known · Дедлайн.", "outside the chapter"),
])
def test_a_bad_line_stops_the_story(line, why):
    text = STORY.replace("- 2026-11-03 · known · Дедлайн статті про змінні зорі.", line)
    with pytest.raises(LifeError, match=why):
        parse_life(text)


@pytest.mark.canon
def test_her_real_story_parses_with_its_list():
    s = parse_life(Path("agents/canon/kira.life.md").read_text(encoding="utf-8"))
    cur = current_chapter(s, TODAY)
    assert cur.events, "her current chapter carries the dated list"
    assert {e.kind for e in cur.events} == {"known", "surprise"}
    assert all(e.text not in life_section(s, TODAY) for e in cur.events)
