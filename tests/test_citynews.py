"""v5.11 — Lviv's news: Zaxid.net's feed parsed, kept for the day and refreshed, each item rolled once, at most one
woven an hour and CITY_NEWS_MAX a day, in one of five ways, under the real-person and tragedy rules. The fetch and
Gemini are mocked; nothing reaches the network."""

import asyncio
import json
import os
import stat

import pytest

from agents.citynews import (
    LVIV_BOOST,
    NEWS_RULES,
    WAYS,
    Item,
    day_items,
    load,
    news_ask,
    parse_feed,
    pick_way,
    roll_news,
)
from agents.events import parse_day
from tests.test_events import EventLLM, at, person, tick

FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:dc="http://purl.org/dc/elements/1.1/" version="2.0">
  <channel>
    <title>ZAXID.NET - Всі новини</title>
    <item>
      <title>У Львові відкрили новий трамвайний маршрут</title>
      <link>https://zaxid.net/tram_n1</link>
      <description>[CDATA[&lt;img align='left' src='https://zaxid.net/x.png'&gt;На Сихів поїде &lt;b&gt;новий&lt;/b&gt; трамвай]]&gt;</description>
      <dc:date>2026-10-27T08:10:00Z</dc:date>
    </item>
    <item>
      <title>Уряд ухвалив нове рішення</title>
      <link>https://zaxid.net/gov_n2</link>
      <description>[CDATA[&lt;img src='x'&gt;Уряд ухвалив нове рішення]]&gt;</description>
      <dc:date>2026-10-27T09:00:00Z</dc:date>
    </item>
    <item>
      <title>Новина з датою RFC</title>
      <link>https://zaxid.net/rfc_n3</link>
      <pubDate>Mon, 26 Oct 2026 22:30:00 +0000</pubDate>
    </item>
    <item><title>Без посилання</title><dc:date>2026-10-27T09:00:00Z</dc:date></item>
    <item><title>Не https</title><link>http://zaxid.net/n4</link><dc:date>2026-10-27T09:00:00Z</dc:date></item>
    <item><title>Без дати</title><link>https://zaxid.net/n5</link></item>
  </channel>
</rss>"""


def item(n, title="Новина", when="2026-10-27T08:00:00+00:00"):
    return Item(title, f"https://zaxid.net/n{n}", "", when)


# --- the feed ----------------------------------------------------------------------------------------------------
def test_the_feed_parses_titles_links_summaries_and_dates():
    items = parse_feed(FEED)
    assert [i.link for i in items] == ["https://zaxid.net/tram_n1", "https://zaxid.net/gov_n2", "https://zaxid.net/rfc_n3"]
    assert items[0].summary == "На Сихів поїде новий трамвай" and "<" not in items[0].summary
    assert items[1].summary == ""                                    # a description that repeats the title
    assert items[0].published == "2026-10-27T08:10:00+00:00" and items[2].published == "2026-10-26T22:30:00+00:00"


@pytest.mark.parametrize("bad", [
    '<?xml version="1.0"?><!DOCTYPE rss [<!ENTITY x "y">]><rss><channel/></rss>',
    "<rss><channel><item>",
    "не xml",
])
def test_a_doctype_or_a_broken_document_is_refused(bad):
    with pytest.raises(ValueError):
        parse_feed(bad)


def test_the_days_items_in_local_time():
    items = parse_feed(FEED)
    day = at("2026-10-27 12:00").date()
    # 22:30 UTC on the 26th is 00:30 in Kyiv on the 27th
    assert [i.link for i in day_items(items + items, day, "Europe/Kyiv")] == [
        "https://zaxid.net/rfc_n3", "https://zaxid.net/tram_n1", "https://zaxid.net/gov_n2"]


# --- the roll ----------------------------------------------------------------------------------------------------
def test_each_item_rolls_once_until_a_hit():
    items = [item(1), item(2), item(3)]
    now = at("2026-10-27 14:00")
    seq = iter([0.5, 0.001, 0.0])
    rolled, hit = roll_news(items, set(), 0, 0.01, 2, now, lambda: next(seq))
    assert rolled == ["https://zaxid.net/n1", "https://zaxid.net/n2"] and hit == items[1]  # one an hour
    rolled, hit = roll_news(items, {"https://zaxid.net/n1", "https://zaxid.net/n2"}, 1, 0.01, 2, now, lambda: 0.5)
    assert rolled == ["https://zaxid.net/n3"] and hit is None


def test_the_caps_p_zero_and_an_item_from_the_future():
    items = [item(1), item(2, when="2026-10-27T20:00:00+00:00")]
    now = at("2026-10-27 14:00")
    assert roll_news(items, set(), 2, 1.0, 2, now, lambda: 0.0) == ([], None)          # the day's cap
    assert roll_news(items, set(), 0, 0.0, 2, now, lambda: 0.0) == ([], None)          # p = 0
    assert roll_news(items, set(), 0, 0.01, 2, now, lambda: 0.5) == (["https://zaxid.net/n1"], None)                                         # not yet published: later


def test_an_item_about_lviv_rolls_at_five_times_p():
    now = at("2026-10-27 14:00")
    p = 0.01
    lviv, other = item(1, "У Львові перекрили вулицю"), item(2, "Новина з Києва")
    assert roll_news([lviv], set(), 0, p, 2, now, lambda: p * LVIV_BOOST - 0.001)[1] == lviv
    assert roll_news([other], set(), 0, p, 2, now, lambda: p * LVIV_BOOST - 0.001)[1] is None


def test_the_ways_and_the_ask():
    assert {pick_way(lambda x=x: x) for x in (0.0, 0.2, 0.4, 0.6, 0.8, 0.999)} == set(WAYS)
    ask = news_ask(Item("Трамвай на Сихів", "https://zaxid.net/n1", "Новий маршрут", "x"), "heard")
    assert "«Трамвай на Сихів» — Новий маршрут" in ask and WAYS["heard"] in ask and NEWS_RULES in ask
    assert "https://" not in ask


# --- the agent ---------------------------------------------------------------------------------------------------
class Feed:
    def __init__(self, items=None, fail=False):
        self.items, self.fail, self.calls = items if items is not None else parse_feed(FEED), fail, 0

    async def __call__(self):
        self.calls += 1
        if self.fail:
            raise OSError("down")
        return self.items


def news_person(tmp_path, llm, when, feed, rolls, monkeypatch, p="0.01", cap="2"):
    monkeypatch.setenv("CITY_NEWS_P", p)
    monkeypatch.setenv("CITY_NEWS_MAX", cap)
    agent = person(tmp_path, llm, when, rolls=rolls)
    agent.citynews_fetch = feed
    return agent


def test_a_woven_item_is_her_event_with_a_hidden_link(tmp_path, monkeypatch):
    llm = EventLLM("Я їхала на роботу новим трамваєм і роздивлялася Сихів.")
    feed = Feed()
    # the event roll misses (0.99); the first item hits (0.0); the way: «there» (0.0)
    agent = news_person(tmp_path, llm, "2026-10-27 14:00", feed, (0.99, 0.0, 0.0), monkeypatch)
    tick(agent, "2026-10-27 14:00")
    events = agent.day_events(at("2026-10-27 14:00").date())
    assert [(e.kind, e.source, e.link) for e in events] == [("there", "news", "https://zaxid.net/rfc_n3")]
    assert "Новина з датою RFC" in llm.calls[0][1] and NEWS_RULES in llm.calls[0][1]
    assert "https://" not in llm.calls[0][1]
    path = tmp_path / "kira.citynews.json"
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600 and json.loads(path.read_text())["day"] == "2026-10-27"
    later = news_person(tmp_path, EventLLM(), "2026-10-27 16:00", feed, (0.99, 0.5, 0.5), monkeypatch)
    tick(later, "2026-10-27 16:00")
    seen = later.llm.calls
    assert seen == [] and feed.calls == 1                       # kept for three hours, reused after a restart


def test_one_fetch_kept_three_hours_then_merged(tmp_path, monkeypatch):
    feed = Feed([item(1)])
    agent = news_person(tmp_path, EventLLM(), "2026-10-27 10:00", feed, (0.99,) * 20, monkeypatch)
    tick(agent, "2026-10-27 10:00")
    tick(agent, "2026-10-27 12:00")
    assert feed.calls == 1
    feed.items = [item(2, when="2026-10-27T10:30:00+00:00")]
    tick(agent, "2026-10-27 13:30")
    assert feed.calls == 2
    assert [i.link for i in load(tmp_path / "kira.citynews.json")[2]] == ["https://zaxid.net/n1", "https://zaxid.net/n2"]
    rolled = parse_day(agent._read_raw(agent.events_file(at("2026-10-27 13:30").date()))).news
    assert rolled == {"https://zaxid.net/n1", "https://zaxid.net/n2"}  # each item rolled once


def test_a_failed_fetch_means_no_news_and_the_event_roll_goes_on(tmp_path, monkeypatch, caplog):
    llm = EventLLM()
    feed = Feed(fail=True)
    agent = news_person(tmp_path, llm, "2026-10-27 10:00", feed, (0.0, 0.0), monkeypatch)
    tick(agent, "2026-10-27 10:00")
    events = agent.day_events(at("2026-10-27 10:00").date())
    assert [e.source for e in events] == ["rolled"] and feed.calls == 1
    assert "fetch failed (OSError)" in caplog.text
    agent.clock = lambda: int(at("2026-10-27 10:59").timestamp() * 1000)
    assert asyncio.run(agent.ensure_citynews(at("2026-10-27 10:59"))) == [] and feed.calls == 1  # not before an hour
    agent.clock = lambda: int(at("2026-10-27 11:00").timestamp() * 1000)
    asyncio.run(agent.ensure_citynews(at("2026-10-27 11:00")))
    assert feed.calls == 2


def test_at_most_cap_a_day_and_p_zero_weaves_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("EVENT_P", "0")                           # only the news here
    items = [item(n, when="2026-10-27T06:00:00+00:00") for n in range(1, 6)]
    agent = news_person(tmp_path, EventLLM(), "2026-10-27 10:00", Feed(items), (0.5, 0.0, 0.0) * 10, monkeypatch,
                        cap="1")
    for hour in ("10:00", "11:00", "12:00"):
        tick(agent, f"2026-10-27 {hour}")
    assert [e.source for e in agent.day_events(at("2026-10-27 10:00").date())] == ["news"]
    zero = news_person(tmp_path / "z", EventLLM(), "2026-10-27 10:00", Feed(items), (0.5, 0.0) * 10, monkeypatch,
                       p="0")
    tick(zero, "2026-10-27 10:00")
    assert zero.day_events(at("2026-10-27 10:00").date()) == [] and zero.citynews_fetch.calls == 0


def test_a_woven_item_naming_the_room_is_dropped(tmp_path, monkeypatch):
    llm = EventLLM("Бруно розповів мені про трамвай.")
    agent = news_person(tmp_path, llm, "2026-10-27 14:00", Feed(), (0.99, 0.0, 0.0), monkeypatch)
    tick(agent, "2026-10-27 14:00")
    assert agent.day_events(at("2026-10-27 14:00").date()) == [] and len(llm.calls) == 2


def test_the_settings():
    from agents.settings import validate

    assert validate("CITY_NEWS_P", "0.03") == ("0.03", None) and validate("CITY_NEWS_P", "2")[0] is None
    assert validate("CITY_NEWS_MAX", "2") == ("2", None) and validate("CITY_NEWS_MAX", "9")[0] is None


def test_the_day_file_never_carries_the_feed_text_into_a_prompt(tmp_path, monkeypatch):
    llm = EventLLM("Я їхала новим трамваєм.", "Подзвонила мама.")
    agent = news_person(tmp_path, llm, "2026-10-27 14:00", Feed(), (0.99, 0.0, 0.0, 0.0, 0.0), monkeypatch)
    tick(agent, "2026-10-27 14:00")
    tick(agent, "2026-10-27 15:00")                               # the next event reads the last ones
    assert "[14:00] Я їхала новим трамваєм." in llm.calls[-1][1] and "zaxid.net" not in llm.calls[-1][1]

