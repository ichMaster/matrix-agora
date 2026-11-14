"""v7.6 (AGORA-263) — the two memories in the numbers: her agent tags the lines her memory shapes with its mode (an old
line reads `layered`); Analytics · Prompts «By memory» by agent and mode — her answers, their mean prompt, the share
from a cache, the cost an answer with the mode's own calls and her cache in it, the call time, her own recall; the
panel's Talk shows her day's digest and the gists, and her settings the switch (made-up lines only)."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from agents.lumi import Digest, save_digest
from agents.settings import BY_NAME, concerns
from agents.usage import (
    MEMORY_KINDS,
    PriceBook,
    analyze_detail,
    memory_tagged,
    parse_lines,
    parse_model_prices,
)
from panel.memory import talk_digest_view
from tests.test_lumi_memory import lumi
from tests.test_settings import ROOM

KYIV = ZoneInfo("Europe/Kyiv")


def test_only_the_lines_her_memory_shapes_carry_its_mode():
    assert memory_tagged({"kind": "private"}, "lumi") == {"kind": "private", "memory_mode": "lumi"}
    assert memory_tagged({"kind": "reply"}, "lumi") == {"kind": "reply"}           # Agora: her memory there is none
    assert memory_tagged({"kind": "cache"}, None) == {"kind": "cache"}
    assert {"private_recall", "talk_digest", "talk_gist", "memory_gist", "cache"} <= MEMORY_KINDS


def test_her_agent_tags_her_lines_with_the_mode_of_the_moment(tmp_path, monkeypatch):
    agent = lumi(tmp_path, monkeypatch)
    agent.record_usage("private", "gemini-3.1-pro-preview", None, True)
    agent.record_usage("reply", "gemini-3.1-pro-preview", None, True)
    monkeypatch.delenv("MEMORY_MODE")
    agent.record_usage("private", "gemini-3.1-pro-preview", None, True)
    records, bad = parse_lines(agent.usage_file.read_text(encoding="utf-8").splitlines())
    assert bad == 0 and [r["memory_mode"] for r in records] == ["lumi", None, "layered"]


def line(kind, mode, prompt=20_000, cached=0, out=500, latency=9_000, calls=None, minute=0, agent="kira"):
    return {"ts": f"2026-11-14T18:{minute:02d}:00+02:00", "agent": agent, "kind": kind,
            "model": "gemini-3.1-pro-preview" if kind not in ("talk_digest", "talk_gist", "memory_gist")
            else "gemini-2.5-flash-lite", "prompt_tokens": prompt, "output_tokens": out, "total_tokens": prompt + out,
            "ok": True, "engine": "gemini", "billing": "api", "cache_read_tokens": cached, "latency_ms": latency,
            "tool_calls": calls, **({"memory_mode": mode} if mode else {})}


def test_by_memory_compares_the_modes_by_agent_with_the_modes_own_calls_in_its_cost():
    records = [line("private", None, 30_000, 10_000, latency=14_000),                 # an old line: `layered`
               line("private", "layered", 30_000, 10_000, latency=12_000, minute=1),
               line("private", "lumi", 20_000, 15_000, latency=8_000, calls=1, minute=2),
               line("private_recall", "lumi", 19_000, 15_000, latency=3_000, minute=2),
               line("private_nudge", "lumi", 20_000, 15_000, latency=10_000, calls=0, minute=3),
               line("talk_digest", "lumi", 4_000, 0, 200, minute=4),
               line("reply", None, 25_000, minute=5)]                                   # Agora: not hers here
    prices, _ = parse_model_prices("gemini-3.1-pro-preview=2/12/0.2/4.5,gemini-2.5-flash-lite=0.1/0.4")
    detail = analyze_detail(records, [], date(2026, 11, 14), date(2026, 11, 14), "kira",
                            datetime(2026, 11, 14, 20, 0, tzinfo=KYIV), PriceBook(0.3, 2.5, prices))
    by = {m["mode"]: m for m in detail["prompts"]["memory"]}
    layered, lumi_ = by["layered"], by["lumi"]
    assert (layered["answers"], layered["prompt_mean"]) == (2, 30_000)
    assert layered["time_median"] in (12_000, 13_000, 14_000)                         # the analytics' own median
    assert layered["cached_share"] == round(20_000 / 60_000, 4) and layered["tool_calls_per_answer"] == 0
    assert (lumi_["answers"], lumi_["prompt_mean"], lumi_["rounds"], lumi_["background"]) == (2, 20_000, 1, 1)
    assert lumi_["cached_share"] == round(45_000 / 59_000, 4) and lumi_["tool_calls_per_answer"] == 0.5
    # two answers and a round on Gemini (fresh at $2, cached at $0.20, the output at $12), the digest on Flash-Lite
    lumi_cost = ((5_000 + 4_000 + 5_000) * 2 + 45_000 * 0.2 + 3 * 500 * 12) / 1e6 + (4_000 * 0.1 + 200 * 0.4) / 1e6
    assert abs(lumi_["cost_per_answer"] - round(lumi_cost / 2, 6)) < 1e-6
    assert set(by) == {"layered", "lumi"}


def test_the_panel_shows_her_days_digest_and_her_settings_the_switch(tmp_path):
    assert talk_digest_view(tmp_path, "kira") == {"day": "", "text": "", "previous_day": "", "previous_text": ""}
    save_digest(tmp_path / "kira.digest.json", Digest("2026-11-14", 5, "Про зорі.", "2026-11-13", "Про небо."))
    assert talk_digest_view(tmp_path, "kira") == {"day": "2026-11-14", "text": "Про зорі.",
                                                  "previous_day": "2026-11-13", "previous_text": "Про небо."}
    mode = BY_NAME["MEMORY_MODE"]
    assert mode.group == "switches" and mode.choices == ("layered", "lumi") and mode.default == "layered"
    assert {n for n, m in ROOM.items() if concerns(mode, m)} == {n for n, m in ROOM.items() if m.can("private")}
