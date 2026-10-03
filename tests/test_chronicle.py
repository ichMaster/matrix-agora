import asyncio
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from agents.agent import Agent
from agents.chronicle import (
    days_due,
    months_due,
    select_layers,
    shares_span,
    visible_deviations,
    weeks_due,
    years_due,
)
from agents.config import AgentConfig
from agents.life import parse_life
from tests.test_first_sync import FakeLLM

LIFE = parse_life(open("agents/canon/ada.life.md", encoding="utf-8").read())  # noqa: SIM115
CFG = AgentConfig(name="Ада", user_id="@ada:agora.lan", canon="Канон.", homeserver="http://hs",
                  room_id="!room", owner="@ich:agora.lan", password="pw", life=LIFE)
KYIV = ZoneInfo("Europe/Kyiv")


def ms(dt):
    return int(dt.timestamp() * 1000)


# --- pure ---
def test_verbatim_guard():
    story = "о дев'ятій флет-уайт із корицею в кав'ярні на Вірменській бариста Назар знає її замовлення"
    assert shares_span("Зранку о дев'ятій флет-уайт із корицею в кав'ярні на Вірменській, як завжди", story)
    assert not shares_span("Зранку кава на Вірменській, Назар намалював листок", story)


def test_deviation_tags_become_visible_for_generators():
    assert visible_deviations("- Жовква <!-- mutation: spontaneous -->") == "- Жовква [відхилення]"


def test_days_due_respects_first_run_and_bound():
    today = date(2026, 10, 10)
    assert days_due(today, date(2026, 10, 8), set(), 7) == [date(2026, 10, 8), date(2026, 10, 9)]
    assert len(days_due(today, date(2020, 1, 1), set(), 7)) == 7
    assert days_due(today, date(2026, 10, 8), {date(2026, 10, 8)}, 7) == [date(2026, 10, 9)]


def test_weeks_months_years_due():
    today = date(2026, 11, 4)  # Wednesday
    days = {date(2026, 10, 27), date(2026, 10, 30), date(2026, 9, 15)}
    assert weeks_due(today, date(2026, 9, 1), set(), days) == [date(2026, 9, 14), date(2026, 10, 26)]
    assert weeks_due(today, date(2026, 10, 1), set(), days) == [date(2026, 10, 26)]  # before first run
    assert months_due(today, date(2026, 9, 1), set(), days) == [(2026, 9), (2026, 10)]
    assert months_due(today, date(2026, 9, 1), {(2026, 9)}, days) == [(2026, 10)]
    assert years_due(date(2028, 2, 1), date(2026, 9, 1), set(), {(2026, 9), (2027, 3)}) == [2026, 2027]


def test_layers_are_nested_oldest_first_without_gaps():
    today = date(2027, 10, 3)  # Sunday
    days = {today - timedelta(days=i) for i in range(1, 400)}
    weeks = {date(2027, 9, 27) - timedelta(days=7 * i) for i in range(60)}
    months = {(2026, m) for m in range(9, 13)} | {(2027, m) for m in range(1, 10)}
    years = {2026}
    layers = select_layers(today, 7, 4, 6, days, weeks, months, years)
    kinds = [k for k, _ in layers]
    assert kinds == ["year"] + ["month"] * 6 + ["week"] * 4 + ["day"] * 7
    day_keys = [k for kind, k in layers if kind == "day"]
    week_keys = [k for kind, k in layers if kind == "week"]
    month_keys = [k for kind, k in layers if kind == "month"]
    assert day_keys[0] == today - timedelta(days=7) and day_keys[-1] == today - timedelta(days=1)
    assert week_keys[-1] + timedelta(days=7) >= day_keys[0]  # no gap between weeks and days
    first_week = week_keys[0]
    last_month_end = date(month_keys[-1][0], month_keys[-1][1] % 12 + 1, 1) if month_keys[-1][1] < 12 \
        else date(month_keys[-1][0] + 1, 1, 1)
    assert last_month_end >= first_week  # no gap between months and weeks


# --- the agent ---
class SeqLLM(FakeLLM):
    def __init__(self, *texts):
        super().__init__()
        self.texts = list(texts)

    async def generate(self, transcript, system_instruction, max_output_tokens=400, kind="reply"):
        self.calls.append((transcript, system_instruction))
        return self.texts.pop(0) if self.texts else "- пункт"


def make(tmp_path, llm, now):
    agent = Agent(CFG, llm=llm)
    agent.client = SimpleNamespace(room_send=AsyncMock(), room_typing=AsyncMock())
    agent.memory_file = tmp_path / "ada.memory.md"
    agent.clock = lambda: ms(now)
    agent.rng = lambda: 0.99  # no mutations
    return agent


def test_day_memory_is_regenerated_once_when_it_copies_the_story(tmp_path):
    from agents.life import current_chapter
    copied = current_chapter(LIFE, date(2026, 10, 2)).body[:400]
    agent = make(tmp_path, SeqLLM(copied, "Свіжий спогад із новими деталями."), datetime(2026, 10, 3, 9, tzinfo=KYIV))
    assert asyncio.run(agent.ensure_day_memory(date(2026, 10, 2))) is True
    assert agent._memory_path("day", date(2026, 10, 2)).read_text(encoding="utf-8").strip() == \
        "Свіжий спогад із новими деталями."


def test_day_memory_is_never_rewritten(tmp_path):
    agent = make(tmp_path, SeqLLM("нове"), datetime(2026, 10, 3, 9, tzinfo=KYIV))
    p = agent._memory_path("day", date(2026, 10, 2))
    p.parent.mkdir(parents=True)
    p.write_text("старе\n", encoding="utf-8")
    asyncio.run(agent.ensure_day_memory(date(2026, 10, 2)))
    assert p.read_text(encoding="utf-8") == "старе\n"


def test_world_tick_catches_up_from_first_run_then_plans(tmp_path):
    now = datetime(2026, 10, 3, 9, tzinfo=KYIV)
    agent = make(tmp_path, SeqLLM("спогад 1", "спогад 2"), now)
    (tmp_path / "ada.first_run.txt").write_text("2026-10-01\n", encoding="utf-8")
    asyncio.run(agent.world_tick(force=True))
    assert agent._dates_in("days") == {date(2026, 10, 1), date(2026, 10, 2)}  # never before first run
    assert all(p.exists() for p in agent.plan_paths(now.date()).values())


def test_world_tick_failure_backs_off(tmp_path):
    class Down(FakeLLM):
        async def generate(self, *a, **k):
            self.calls.append(a)

    llm = Down()
    now = datetime(2026, 10, 3, 9, tzinfo=KYIV)
    agent = make(tmp_path, llm, now)
    (tmp_path / "ada.first_run.txt").write_text("2026-10-01\n", encoding="utf-8")
    asyncio.run(agent.world_tick(force=True))
    n = len(llm.calls)
    asyncio.run(agent.world_tick(force=True))  # inside the cooldown → no new calls
    assert len(llm.calls) == n and agent._gen_retry_ms > ms(now)


def test_memories_section_layers_and_labels(tmp_path):
    now = datetime(2026, 10, 3, 9, tzinfo=KYIV)
    agent = make(tmp_path, SeqLLM(), now)
    for d in (date(2026, 10, 2), date(2026, 10, 1)):
        p = agent._memory_path("day", d)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"день {d.day}", encoding="utf-8")
    w = agent._memory_path("week", date(2026, 9, 14))
    w.parent.mkdir(parents=True)
    w.write_text("тиждень", encoding="utf-8")
    section = agent.memories_section(now)
    assert section.index("тиждень 14–20 вересня: тиждень") < section.index("позавчора, четвер, 1 жовтня: день 1")
    assert section.index("позавчора") < section.index("вчора, п'ятниця, 2 жовтня: день 2")


def test_today_block_hourly_and_reset_at_midnight(tmp_path):
    llm = SeqLLM("Сьогодні вже: кава. Ще сьогодні: ринок.", "Сьогодні вже: кава і ринок. Ще сьогодні: хліб.")
    t1 = datetime(2026, 10, 3, 9, 5, tzinfo=KYIV)
    agent = make(tmp_path, llm, t1)
    asyncio.run(agent.ensure_today(t1))
    asyncio.run(agent.ensure_today(t1.replace(minute=50)))  # same hour → cached
    assert len(llm.calls) == 1
    asyncio.run(agent.ensure_today(t1.replace(hour=10)))     # next hour → refreshed
    assert len(llm.calls) == 2
    assert "хліб" in agent.today_section(t1.replace(hour=10))
    assert agent.today_section(datetime(2026, 10, 4, 0, 30, tzinfo=KYIV)) is None  # midnight reset
