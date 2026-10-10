"""Token accounting: the usage line, parsing, aggregation and the report
(ARCHITECTURE §Token accounting). Pure functions; no texts ever."""

from __future__ import annotations

import calendar
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

KINDS = ("reply", "summary", "plan", "day_memory", "digest", "today", "mood")
# v4.4 — how a call is paid: `api` (Gemini, priced), `subscription` (Claude on the Max plan), `external` (Lumi's own)
BILLING = ("api", "subscription", "external")


def _count(usage: Any, field: str) -> int | None:
    value = getattr(usage, field, None) if usage is not None else None
    return int(value) if isinstance(value, int) else None


def usage_line(ts_iso: str, agent: str, kind: str, model: str, usage: Any, ok: bool) -> dict:
    """One record per Gemini call (v2 since v4.4: engine, billing, cache tokens). Missing metadata → nulls. Never any
    text."""
    return {
        "ts": ts_iso,
        "agent": agent,
        "kind": kind,
        "model": model,
        "prompt_tokens": _count(usage, "prompt_token_count"),
        "output_tokens": _count(usage, "candidates_token_count"),
        "total_tokens": _count(usage, "total_token_count"),
        "ok": bool(ok),
        "engine": "gemini",
        "billing": "api",
        "cache_read_tokens": _count(usage, "cached_content_token_count"),
        "cache_write_tokens": None,
        "reported_cost_usd": None,
    }


def _int(d: dict, key: str) -> int | None:
    value = d.get(key) if isinstance(d, dict) else None
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def sdk_usage_line(ts_iso: str, agent: str, kind: str, model: str, usage: dict | None, ok: bool,
                   reported_cost: float | None = None) -> dict:
    """v4.4 — one record per Claude Agent SDK call: always `claude-sdk` / `subscription` (the Max plan, never an API
    key); the SDK's `total_cost_usd` is a client-side estimate, kept as reported and never billed."""
    usage = usage or {}
    prompt, output = _int(usage, "input_tokens"), _int(usage, "output_tokens")
    total = prompt + output if prompt is not None and output is not None else None
    cost = float(reported_cost) if isinstance(reported_cost, int | float) and not isinstance(reported_cost, bool) else None
    return {
        "ts": ts_iso, "agent": agent, "kind": kind, "model": model,
        "prompt_tokens": prompt, "output_tokens": output, "total_tokens": total, "ok": bool(ok),
        "engine": "claude-sdk", "billing": "subscription",
        "cache_read_tokens": _int(usage, "cache_read_input_tokens"),
        "cache_write_tokens": _int(usage, "cache_creation_input_tokens"),
        "reported_cost_usd": cost,
    }


COUNT_FIELDS = ("prompt_tokens", "output_tokens", "total_tokens", "cache_read_tokens", "cache_write_tokens")


def _valid(rec: Any) -> bool:
    """The line's shape (code review #1): anything else is corrupt, never a crash later."""
    if not isinstance(rec, dict) or not isinstance(rec.get("ts"), str):
        return False
    try:
        date.fromisoformat(rec["ts"][:10])
    except ValueError:
        return False
    counts_ok = all(rec.get(f) is None or (isinstance(rec[f], int) and not isinstance(rec[f], bool))
                    for f in COUNT_FIELDS)
    return (counts_ok and isinstance(rec.get("ok"), bool)
            and isinstance(rec.get("agent"), str) and isinstance(rec.get("kind"), str)
            and rec.get("billing", "api") in BILLING and isinstance(rec.get("engine", "gemini"), str))


def parse_lines(lines: list[str]) -> tuple[list[dict], int]:
    """(records, corrupt_count) — a corrupt line is skipped, never fatal."""
    out, bad = [], 0
    for line in lines:
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            rec = None
        if _valid(rec):
            out.append(rec)
        else:
            bad += 1
    return out, bad


@dataclass
class Row:
    calls: int = 0
    failed: int = 0
    prompt: int = 0
    output: int = 0
    total: int = 0
    priced_prompt: int = 0  # v4.4: the tokens of `api` calls only — the only ones a price applies to
    priced_output: int = 0
    engine: str = ""        # the rows' engine and billing; "mixed" when a total spans several
    billing: str = ""

    def add(self, other: Row) -> None:
        self.calls += other.calls
        self.failed += other.failed
        self.prompt += other.prompt
        self.output += other.output
        self.total += other.total
        self.priced_prompt += other.priced_prompt
        self.priced_output += other.priced_output
        self.engine = _merge(self.engine, other.engine)
        self.billing = _merge(self.billing, other.billing)


def _merge(a: str, b: str) -> str:
    return b if not a else a if not b or a == b else "mixed"


def aggregate(records: list[dict], since: date | None = None,
              until: date | None = None) -> dict[tuple[str, str, str], Row]:
    """By (day, agent, kind), days in [since, until]. Null counts add nothing."""
    rows: dict[tuple[str, str, str], Row] = defaultdict(Row)
    for r in records:
        day = str(r["ts"])[:10]
        if (since and date.fromisoformat(day) < since) or (until and date.fromisoformat(day) > until):
            continue
        row = rows[(day, str(r.get("agent", "?")), str(r.get("kind", "?")))]
        engine, billing = str(r.get("engine", "gemini")), str(r.get("billing", "api"))  # a v1 line is Gemini's
        row.engine, row.billing = _merge(row.engine, engine), _merge(row.billing, billing)
        row.calls += 1
        row.failed += 0 if r.get("ok") else 1
        row.prompt += r.get("prompt_tokens") or 0
        row.output += r.get("output_tokens") or 0
        row.total += r.get("total_tokens") or 0
        if billing == "api":
            row.priced_prompt += r.get("prompt_tokens") or 0
            row.priced_output += r.get("output_tokens") or 0
    return dict(sorted(rows.items()))


def cost(row: Row, price_in: float | None, price_out: float | None) -> float | None:
    """The price of a row's `api` tokens (the PRICE_* pair is Gemini's); a row with no `api` part — Claude on the
    subscription, Lumi's own — has no cost, never $0 (v4.4)."""
    if price_in is None or price_out is None:
        return None
    if row.billing and row.billing != "api" and not (row.priced_prompt or row.priced_output):
        return None
    return row.priced_prompt / 1e6 * price_in + row.priced_output / 1e6 * price_out


def render(rows: dict[tuple[str, str, str], Row], price_in: float | None, price_out: float | None,
           markdown: bool = False) -> str:
    if not rows:
        return "no data"
    with_cost = price_in is not None and price_out is not None
    prices = (price_in, price_out)
    head = ["day", "agent", "kind", "calls", "failed", "input", "output", "total", "billing"] \
        + (["cost $"] if with_cost else [])  # v4.4: billing — only `api` rows carry a cost
    body = []

    def line(cells: list[str], r: Row) -> None:
        body.append(cells + [r.billing or "api"] + ([_usd(r, prices)] if with_cost else []))

    per_agent: dict[str, Row] = defaultdict(Row)
    overall = Row()
    for (day, agent, kind), r in rows.items():
        line([day, agent, kind, str(r.calls), str(r.failed), str(r.prompt), str(r.output), str(r.total)], r)
        per_agent[agent].add(r)
        overall.add(r)
    for agent, r in sorted(per_agent.items()):
        line(["TOTAL", agent, "", str(r.calls), str(r.failed), str(r.prompt), str(r.output), str(r.total)], r)
    line(["TOTAL", "all", "", str(overall.calls), str(overall.failed), str(overall.prompt), str(overall.output),
          str(overall.total)], overall)
    return table(head, body, markdown, left=3)


def table(head: list[str], body: list[list[str]], markdown: bool, left: int = 1) -> str:
    """A markdown table, or aligned plain columns (the first `left` columns left-aligned)."""
    if markdown:
        out = ["| " + " | ".join(head) + " |", "|" + "".join("---|" if i < left else "--:|" for i in range(len(head)))]
        out += ["| " + " | ".join(c) + " |" for c in body]
        return "\n".join(out)
    widths = [max(len(head[i]), *(len(c[i]) for c in body)) for i in range(len(head))]
    fmt = "  ".join(f"{{:{'<' if i < left else '>'}{w}}}" for i, w in enumerate(widths))
    return "\n".join([fmt.format(*head)] + [fmt.format(*c) for c in body])


# --- the daily report (v3.1.1) ---
def rollup(rows: dict[tuple[str, str, str], Row], by: int) -> dict[str, Row]:
    """Sum (day, agent, kind) rows by one key: 0 = day, 1 = agent, 2 = kind."""
    out: dict[str, Row] = defaultdict(Row)
    for key, r in rows.items():
        out[key[by]].add(r)
    return dict(sorted(out.items()))


def _total(rows: dict) -> Row:
    acc = Row()
    for r in rows.values():
        acc.add(r)
    return acc


def _n(x: float) -> str:
    return f"{round(x):,}"


def _usd(row: Row, prices: tuple[float | None, float | None]) -> str:
    c = cost(row, *prices)
    return "—" if c is None else f"{c:.4f}"


def _change(now: float, before: float) -> str:
    if not before:
        return "—"
    return f"{(now - before) / before * 100:+.0f}%"


def daily_report(records: list[dict], now: datetime, price_in: float | None = None,
                 price_out: float | None = None) -> str:
    """The daily markdown report for the local `now`: yesterday in detail, the day before for comparison,
    the last 7 complete days, the month of yesterday so far (+ a projection), and today so far."""
    prices = (price_in, price_out)
    priced = price_in is not None and price_out is not None
    today = now.date()
    yday = today - timedelta(days=1)
    usd = ["cost $"] if priced else []

    def money(r: Row) -> list[str]:
        return [_usd(r, prices)] if priced else []

    def stats_row(label: str, r: Row) -> list[str]:
        return [label, _n(r.calls), _n(r.failed), _n(r.prompt), _n(r.output), _n(r.total)] + money(r)

    head = ["", "calls", "failed", "input", "output", "total"] + usd
    out = [f"# Token usage — {today.isoformat()}",
           "",
           f"Generated {now.strftime('%Y-%m-%d %H:%M')} ({now.tzname() or 'local'}). "
           + (f"Prices: ${price_in:.2f} input / ${price_out:.2f} output per 1M tokens." if priced
              else "No prices set (`PRICE_INPUT_PER_1M` / `PRICE_OUTPUT_PER_1M`) — tokens only."),
           ""]

    # yesterday
    y_rows = aggregate(records, yday, yday)
    y, before = _total(y_rows), _total(aggregate(records, yday - timedelta(days=1), yday - timedelta(days=1)))
    out += [f"## Yesterday — {yday.isoformat()}", ""]
    if not y_rows:
        out += ["No Gemini calls.", ""]
    else:
        out += [table(head, [stats_row(a, r) for a, r in rollup(y_rows, 1).items()] + [stats_row("**all**", y)],
                      markdown=True), ""]
        out += [f"vs {(yday - timedelta(days=1)).isoformat()}: calls {_change(y.calls, before.calls)}, "
                f"tokens {_change(y.total, before.total)}"
                + (f", cost {_change(cost(y, *prices) or 0.0, cost(before, *prices) or 0.0)}"
                   if priced else "") + ".", ""]
        k_head = ["kind", "calls", "share of tokens", "avg input / call", "avg output / call", "failed"] + usd
        k_body = [[k, _n(r.calls), f"{(r.total / y.total * 100 if y.total else 0):.0f}%",
                   _n(r.prompt / r.calls), _n(r.output / r.calls), _n(r.failed)] + money(r)
                  for k, r in sorted(rollup(y_rows, 2).items(), key=lambda kv: -kv[1].total)]
        out += ["### By kind", "", table(k_head, k_body, markdown=True), ""]
        out += ["### By agent × kind", "", render(y_rows, price_in, price_out, markdown=True), ""]

    # the last 7 complete days
    first = yday - timedelta(days=6)
    week_rows = aggregate(records, first, yday)
    by_day = rollup(week_rows, 0)
    w = _total(week_rows)
    days = [first + timedelta(days=i) for i in range(7)]
    d_body = [stats_row(d.isoformat(), by_day.get(d.isoformat(), Row())) for d in days]
    out += [f"## Last 7 days — {first.isoformat()} … {yday.isoformat()}", "",
            table(["day", "calls", "failed", "input", "output", "total"] + usd,
                  d_body + [stats_row("**total**", w)], markdown=True), "",
            f"Daily average: {_n(w.calls / 7)} calls, {_n(w.total / 7)} tokens"
            + (f", ${(cost(w, *prices) or 0.0) / 7:.4f}" if priced else "") + "."
            + (f" Busiest day: {max(by_day.items(), key=lambda kv: kv[1].total)[0]}." if by_day else ""), ""]

    # the month of yesterday, so far
    m_first = yday.replace(day=1)
    m = _total(aggregate(records, m_first, yday))
    m_days = calendar.monthrange(yday.year, yday.month)[1]
    out += [f"## Month so far — {m_first.strftime('%Y-%m')} (days 1–{yday.day} of {m_days})", "",
            f"{_n(m.calls)} calls · {_n(m.failed)} failed · {_n(m.total)} tokens "
            f"({_n(m.prompt)} input, {_n(m.output)} output)"
            + (f" · ${cost(m, *prices) or 0.0:.4f} · projected month ${(cost(m, *prices) or 0.0) / yday.day * m_days:.2f}"
               if priced else "") + ".", ""]

    # today so far
    t_rows = aggregate(records, today, today)
    out += [f"## Today so far — until {now.strftime('%H:%M')}", ""]
    if not t_rows:
        out += ["No Gemini calls yet."]
    else:
        kinds = " · ".join(f"{k} {r.calls}" for k, r in sorted(rollup(t_rows, 2).items(), key=lambda kv: -kv[1].calls))
        out += [table(head, [stats_row(a, r) for a, r in rollup(t_rows, 1).items()]
                      + [stats_row("**all**", _total(t_rows))], markdown=True), "", f"Calls by kind: {kinds}."]
    return "\n".join(out) + "\n"
