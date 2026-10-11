"""v4.5 review #6 (the owner, 2026-10-11): Claude's news comes from The Guardian Open Platform — two in-process tools
over an injectable fetch; the key never in a log or a tool result."""
import asyncio
import json
import logging
import urllib.parse
from datetime import date

from agents.guardian import Guardian, article, plain, read_url, results, search_url

PAYLOAD = {"response": {"status": "ok", "results": [
    {"id": "science/2026/oct/11/stars", "webTitle": "Stars &amp; cats", "webUrl": "https://www.theguardian.com/s",
     "webPublicationDate": "2026-10-11T08:00:00Z", "sectionName": "Science",
     "fields": {"trailText": "<p>A <strong>new</strong> study</p>"}},
]}}


def params(url):
    return dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))


def test_the_search_url_asks_for_the_newest_within_the_days_and_bounds_them():
    p = params(search_url("K", " cats ", "science", 3, date(2026, 10, 11)))
    assert p["q"] == "cats" and p["order-by"] == "newest" and p["from-date"] == "2026-10-08"
    assert p["section"] == "science" and p["page-size"] == "8" and p["api-key"] == "K"
    assert params(search_url("K", "x", None, 99, date(2026, 10, 11)))["from-date"] == "2026-09-27"   # ≤ 14 days
    assert "section" not in params(search_url("K", "x", "../admin", 3, date(2026, 10, 11)))


def test_results_and_articles_are_plain_text():
    assert results(PAYLOAD) == [{"id": "science/2026/oct/11/stars", "title": "Stars & cats",
                                 "url": "https://www.theguardian.com/s", "date": "2026-10-11", "section": "Science",
                                 "trail": "A new study"}]
    assert results({}) == [] and results({"response": {"results": ["x"]}}) == []
    item = article({"response": {"content": {"webTitle": "T", "webUrl": "u", "webPublicationDate": "2026-10-11",
                                             "fields": {"bodyText": "a " * 4000}}}}, max_chars=10)
    assert item["text"] == "a a a a a " and plain("<b>x</b>&nbsp;y") == "x y"


def test_read_takes_a_content_id_never_a_url():
    assert read_url("K", "world/2026/oct/11/some-title").startswith("https://content.guardianapis.com/world/")
    for bad in ("https://evil.example/x", "../x", "world", "", "world/../../x"):
        assert read_url("K", bad) is None


def test_the_tools_answer_and_fail_without_the_key(caplog):
    seen = []

    async def fetch(url):
        seen.append(url)
        return PAYLOAD

    g = Guardian("SECRET-KEY", fetch=fetch, today=lambda: date(2026, 10, 11))
    out = asyncio.run(g.search({"query": "stars"}))
    assert json.loads(out["content"][0]["text"])[0]["title"] == "Stars & cats" and "is_error" not in out
    assert "SECRET-KEY" in seen[0] and "SECRET-KEY" not in out["content"][0]["text"]
    assert asyncio.run(g.search({"query": " "}))["is_error"]
    assert asyncio.run(g.read({"id": "https://x"}))["is_error"]

    async def boom(url):
        raise RuntimeError(f"failed {url}")                       # an error's text carries the URL — and the key

    caplog.set_level(logging.WARNING)
    bad = Guardian("SECRET-KEY", fetch=boom)
    for out in (asyncio.run(bad.search({"query": "x"})), asyncio.run(bad.read({"id": "a/b"}))):
        assert out["is_error"] and "SECRET-KEY" not in out["content"][0]["text"]
    assert "SECRET-KEY" not in caplog.text and "RuntimeError" in caplog.text
