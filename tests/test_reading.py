"""v5.12 — what Кіра reads: Zaxid.net's full text, the Guardian's sections, the items she has seen (AGORA-132)."""

import asyncio
import logging
import os
import urllib.parse
from datetime import date

import pytest

from agents import citynews
from agents.guardian import search_url
from agents.reading import (
    ARTICLE_MAX_CHARS,
    SEEN_KEEP_MS,
    Item,
    ReadingState,
    Sources,
    article_body,
    fresh,
    from_citynews,
    load_state,
    parse_sections,
    save_state,
    zaxid_link_ok,
)

PAGE = """<html><head>
<script type="application/ld+json">{"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": []}</script>
<script type="application/ld+json">
{"@context": "https://schema.org", "@type": "NewsArticle", "headline": "Заголовок",
 "articleBody": "У Львові   відкрили\\nновий &laquo;планетарій&raquo;. <b>Перший</b> показ — у суботу."}
</script></head><body><p>не це</p></body></html>"""


def params(url):
    return dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))


def run(coro):
    return asyncio.run(coro)


# --- Zaxid.net's full text --------------------------------------------------------------------------------------
def test_the_article_body_comes_from_the_pages_json_ld():
    assert article_body(PAGE) == "У Львові відкрили новий «планетарій». Перший показ — у суботу."


def test_a_body_inside_a_graph_or_a_list_is_found():
    graph = '<script type="application/ld+json">{"@graph": [{"@type": "WebPage"}, {"articleBody": "Текст"}]}</script>'
    listed = "<script type='application/ld+json'>[{\"articleBody\": \"Інший\"}]</script>"
    assert article_body(graph) == "Текст" and article_body(listed) == "Інший"


def test_a_page_without_a_body_or_with_a_broken_block_gives_none():
    assert article_body("<html><p>текст</p></html>") is None
    assert article_body('<script type="application/ld+json">{"@type": "NewsArticle"}</script>') is None
    assert article_body('<script type="application/ld+json">{broken</script>') is None
    assert article_body(None) is None
    broken_then_good = ('<script type="application/ld+json">{broken</script>'
                        '<script type="application/ld+json">{"articleBody": "Є"}</script>')
    assert article_body(broken_then_good) == "Є"


def test_the_body_is_cut_at_its_cap():
    long = '<script type="application/ld+json">{"articleBody": "' + "а" * (ARTICLE_MAX_CHARS + 50) + '"}</script>'
    assert len(article_body(long)) == ARTICLE_MAX_CHARS


def test_only_an_https_page_on_zaxid_net_is_fetched():
    assert zaxid_link_ok("https://zaxid.net/news/n1612345")
    assert zaxid_link_ok("https://www.zaxid.net/x")
    assert not zaxid_link_ok("http://zaxid.net/x")
    assert not zaxid_link_ok("https://zaxid.net.evil.com/x")
    assert not zaxid_link_ok("https://evil.com/zaxid.net")
    assert not zaxid_link_ok("")


def test_a_refused_link_is_never_fetched():
    fetched = []

    async def text(url):
        fetched.append(url)
        return PAGE

    src = Sources("", fetch_text=text)
    item = Item("zaxid", "http://zaxid.net/x", "T", "", "http://zaxid.net/x", "2026-10-28T08:00:00+00:00")
    assert run(src.full_text(item)) is None and fetched == []
    ok = Item("zaxid", "https://zaxid.net/x", "T", "", "https://zaxid.net/x", "2026-10-28T08:00:00+00:00")
    assert run(src.full_text(ok)).startswith("У Львові") and fetched == ["https://zaxid.net/x"]


def test_the_kept_feed_items_become_hers_to_read():
    kept = [citynews.Item("Новина", "https://zaxid.net/n1", "опис", "2026-10-28T06:00:00+00:00")]
    assert from_citynews(kept) == [Item("zaxid", "https://zaxid.net/n1", "Новина", "опис", "https://zaxid.net/n1",
                                        "2026-10-28T06:00:00+00:00")]


# --- the Guardian ---------------------------------------------------------------------------------------------
def hit(cid, title="A title", url=None):
    return {"id": cid, "webTitle": title, "webUrl": url or f"https://www.theguardian.com/{cid}",
            "webPublicationDate": "2026-10-28T07:00:00Z", "sectionName": "Science",
            "fields": {"trailText": "<p>Trail</p>"}}


def test_an_empty_query_sends_no_q_and_a_query_is_unchanged():
    p = params(search_url("K", "", "science", 1, date(2026, 10, 28)))
    assert "q" not in p and p["section"] == "science" and p["from-date"] == "2026-10-27"
    assert params(search_url("K", " cats ", None, 3, date(2026, 10, 28)))["q"] == "cats"   # Claude's tool


def test_the_sections_are_read_and_their_items_kept_once():
    urls = []

    async def fetch(url):
        urls.append(params(url)["section"])
        if "science" in url:
            return {"response": {"results": [hit("science/2026/oct/28/a"), hit("science/2026/oct/28/b")]}}
        return {"response": {"results": [hit("science/2026/oct/28/a"), hit("world/2026/oct/28/c", url="http://x")]}}

    items = run(Sources("K", fetch_json=fetch).guardian(["science", "world"], date(2026, 10, 28)))
    assert urls == ["science", "world"]
    assert [i.id for i in items] == ["science/2026/oct/28/a", "science/2026/oct/28/b"]   # once; http dropped
    assert items[0].source == "guardian" and items[0].summary == "Trail" and items[0].published == "2026-10-28"


def test_without_a_key_the_guardian_is_skipped_and_logged_once(caplog):
    async def fetch(url):
        raise AssertionError("never called")

    src = Sources("", fetch_json=fetch)
    with caplog.at_level(logging.INFO, logger="agent.reading"):
        assert run(src.guardian(["science"], date(2026, 10, 28))) == []
        assert run(src.guardian(["science"], date(2026, 10, 28))) == []
    assert sum("GUARDIAN_API_KEY" in r.getMessage() for r in caplog.records) == 1


def test_a_failed_section_is_logged_by_its_type_and_never_the_key(caplog):
    async def fetch(url):
        raise RuntimeError(f"boom {url}")

    with caplog.at_level(logging.WARNING, logger="agent.reading"):
        assert run(Sources("SECRETKEY", fetch_json=fetch).guardian(["science"], date(2026, 10, 28))) == []
    assert "RuntimeError" in caplog.text and "SECRETKEY" not in caplog.text


def test_a_guardian_pick_is_read_by_its_content_id():
    async def fetch(url):
        assert "/science/2026/oct/28/a?" in url and "bodyText" in url
        return {"response": {"content": {"webTitle": "T", "webUrl": "https://www.theguardian.com/x",
                                         "fields": {"bodyText": "Body text."}}}}

    item = Item("guardian", "science/2026/oct/28/a", "T", "", "https://www.theguardian.com/x", "2026-10-28")
    assert run(Sources("K", fetch_json=fetch).full_text(item)) == "Body text."
    assert run(Sources("", fetch_json=fetch).full_text(item)) is None   # no key, no read


def test_a_failed_read_is_none(caplog):
    async def text(url):
        raise OSError("down")

    item = Item("zaxid", "https://zaxid.net/x", "T", "", "https://zaxid.net/x", "")
    with caplog.at_level(logging.WARNING, logger="agent.reading"):
        assert run(Sources("", fetch_text=text).full_text(item)) is None
    assert "OSError" in caplog.text


def test_the_sections_setting_drops_a_malformed_id():
    assert parse_sections("science, world,../admin,Science,world") == ["science", "world"]
    assert parse_sections(None) == ["science", "world", "environment", "technology", "culture"]
    assert parse_sections("") == []


# --- the items she has seen -----------------------------------------------------------------------------------
def test_a_seen_item_is_never_fresh_again():
    a = Item("zaxid", "https://zaxid.net/a", "A", "", "https://zaxid.net/a", "")
    b = Item("guardian", "world/x", "B", "", "https://www.theguardian.com/b", "")
    assert fresh([a, b, a], {}) == [a, b]
    assert fresh([a, b], {"https://zaxid.net/a": 1}) == [b]


def test_the_state_round_trips_private_and_atomic(tmp_path):
    path = tmp_path / "kira.reading.json"
    now = 10 * SEEN_KEEP_MS
    st = ReadingState({"old": now - SEEN_KEEP_MS - 1, "new": now - 5}, now - 100, {"private": now - 50})
    save_state(path, st, now)
    assert os.stat(path).st_mode & 0o777 == 0o600 and not path.with_suffix(".json.tmp").exists()
    back = load_state(path)
    assert back.seen == {"new": now - 5} and back.last_reading_ms == now - 100 and back.reflected == {"private": now - 50}
    assert "old" not in path.read_text()


@pytest.mark.parametrize("raw", ["", "{broken", "[]", '{"seen": 5}'])
def test_a_missing_or_corrupt_state_is_a_fresh_start(tmp_path, raw):
    path = tmp_path / "kira.reading.json"
    assert load_state(path) == ReadingState()
    path.write_text(raw)
    assert load_state(path) == ReadingState()



# --- the schedule and the requests (AGORA-134) -------------------------------------------------------------------
from agents.logic import BANNED_RE
from agents.reading import (
    SHOWN_PER_SOURCE,
    parse_picks,
    pick_request,
    reading_due,
    reflect_due,
    reflection_request,
    shown,
    split_reflection,
    thought_request,
)


@pytest.mark.parametrize("text, picks", [
    ("2, 1", [1, 0]), ("3", [2]), ("0", []), ("", []), (None, []), ("1, 1, 2", [0, 1]),
    ("1, 2, 3", [0, 1]),                     # the cap
    ("7, 2", [1]),                           # out of range
    ("Мені цікаве друге", []),               # words: garbage, no pick
    ("2.", [1]), ("1; 3", [0, 2]),
])
def test_parse_picks(text, picks):
    assert parse_picks(text, 4, 2) == picks


def test_the_schedule():
    assert reading_due(10_000, 0, 10_000, True) and not reading_due(9_999, 0, 10_000, True)
    assert not reading_due(10_000, 0, 10_000, False)            # outside her reading hours
    assert reflect_due(3_600_000, 0, 3_600_000) and not reflect_due(3_599_999, 0, 3_600_000)


def test_a_reading_shows_the_freshest_of_each_source_lviv_first():
    z = [Item("zaxid", f"z{i}", f"Z{i}", "", "https://zaxid.net/x", "") for i in range(30)]
    g = [Item("guardian", f"g{i}", f"G{i}", "", "https://www.theguardian.com/x", "") for i in range(30)]
    out = shown(z, g)
    assert len(out) == 2 * SHOWN_PER_SOURCE and out[0].id == "z10" and out[SHOWN_PER_SOURCE].id == "g0"


def test_the_requests_say_who_she_is_and_never_what_she_is_not():
    item = Item("guardian", "x/y", "Water on a moon", "A find", "https://www.theguardian.com/x", "")
    sysp, contents = pick_request("Кіра", "КАНОН", "ЧИТАЄ", "Легкий день.", ["Стара думка."], [item], 2)
    assert "КАНОН" in sysp and "ЧИТАЄ" in sysp and "Настрій дня: Легкий день." in sysp and "Стара думка." in sysp
    assert contents == "1. [The Guardian] Water on a moon — A find"
    syst, body = thought_request("Кіра", "КАНОН", None, "ЗГАДКА", item, "BODY")
    assert "ЗГАДКА" in syst and "лише на факти зі статті" in syst and "не шукала" in syst
    assert body == "Заголовок: Water on a moon\n\nBODY"
    sysr, lines = reflection_request("Кіра", "КАНОН", None, [], "agora", [("Ада", "Привіт"), ("Кіра", "Хай")])
    assert "в Агорі" in sysr and "ні слів, ні вчинків Ich чи інших" in sysr and lines == "Ада: Привіт\nКіра: Хай"
    assert "наодинці" in reflection_request("Кіра", "К", None, [], "private", [])[0]
    for s in (sysp, syst, sysr):
        assert not BANNED_RE.search(s)


def test_a_reflection_is_at_most_two_thoughts_a_line_each():
    assert split_reflection("- Перша думка.\n\n2) Друга.\nТретя.") == ["Перша думка.", "Друга."]
    assert split_reflection("") == [] and split_reflection(None) == []
