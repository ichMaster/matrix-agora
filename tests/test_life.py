from datetime import date
from pathlib import Path

import pytest

from agents.life import LifeError, current_chapter, life_section, next_chapter, parse_life

ADA = parse_life(Path("agents/canon/ada.life.md").read_text(encoding="utf-8"))
BRUNO = parse_life(Path("agents/canon/bruno.life.md").read_text(encoding="utf-8"))
TODAY = date(2026, 10, 3)


def test_headers_parse():
    assert ADA.birth == date(1994, 2, 7) and ADA.birth_time == "05:40" and ADA.birth_place == "Львів"
    assert BRUNO.birth == date(1990, 12, 4) and BRUNO.birth_time == "23:15"
    assert ADA.death.year == 2079 and BRUNO.death.year == 2072


def test_current_and_next_chapter():
    assert current_chapter(ADA, TODAY).start == 2024
    assert next_chapter(ADA, TODAY).start == 2028
    assert current_chapter(BRUNO, TODAY).start == 2024


def test_year_boundaries_move_the_story():
    assert current_chapter(ADA, date(2027, 12, 31)).start == 2024
    assert current_chapter(ADA, date(2028, 1, 1)).start == 2028


@pytest.mark.parametrize("story", [ADA, BRUNO])
def test_visibility_never_the_future_never_death(story):
    section = life_section(story, TODAY)
    assert "Смерть" not in section and str(story.death.year) not in section
    for ch in story.chapters:
        if ch.start > TODAY.year:
            assert ch.opening not in section, ch.title
            assert ch.title not in section
    assert "Твоє життя досі" in section
    assert current_chapter(story, TODAY).body in section


def test_future_people_never_leak():
    assert "Маркіян" not in life_section(ADA, TODAY)      # Ada's future partner
    assert "Данило" not in life_section(BRUNO, TODAY)     # Bruno's future son


def test_malformed_stories_are_rejected():
    with pytest.raises(LifeError):
        parse_life("## 2000–2001 · x\ntext")  # no header
    bad = "Народження: 1990-01-01, X\nСмерть: 2050-01-01\n## 1990–2000 · a\nx\n\n## 1999–2005 · b\ny"
    with pytest.raises(LifeError, match="overlap"):
        parse_life(bad)


def test_the_cats_life_story_never_shows_his_death():
    """v4.2: the cat's human life is past chapters, his rebirth opens the current one (2005–2027), and the hidden
    end (2038-01-19) sits in a future chapter — the prompt never sees 2038."""
    from datetime import date
    from pathlib import Path

    from agents.life import current_chapter, life_section, parse_life
    story = parse_life(Path("agents/canon/kit.life.md").read_text(encoding="utf-8"))
    assert story.birth == date(1965, 9, 13) and story.death == date(2038, 1, 19)
    assert (current_chapter(story, date(2026, 10, 10)).start, current_chapter(story, date(2026, 10, 10)).end) == (2005, 2027)
    section = life_section(story, date(2026, 10, 10))
    assert "2038" not in section and "2028" not in section and "Шістнадцятого квітня 2005" in section


@pytest.mark.parametrize("name", ["ada", "bruno", "kit"])
def test_no_year_of_life_ever_shows_the_death_year(name):
    """Review #5: the current chapter used to print its end year — for the last chapter, the death year (the cat's
    hidden 2028–2038 chapter turns current on 2028-01-01). Every year up to the death is checked: the header never
    carries it, and for the cat nothing in the section does. (Ada's and Bruno's last chapters narrate their deaths
    in the body — from 2066, a canon edit deferred in the v4.2 review.)"""
    from pathlib import Path
    story = parse_life(Path(f"agents/canon/{name}.life.md").read_text(encoding="utf-8"))
    for year in range(2026, story.death.year + 1):
        section = life_section(story, date(year, 6, 1))
        cur = current_chapter(story, date(year, 6, 1))
        header = f"Зараз (з {cur.start} · {cur.title}):"
        assert header in section and str(story.death.year) not in header and "(зараз)" not in section, year
        if name == "kit":
            assert str(story.death.year) not in section and "Смерть" not in section, year
