"""Token accounting: the usage line, parsing, aggregation and the report
(ARCHITECTURE §Token accounting). Pure functions; no texts ever."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any

KINDS = ("reply", "summary", "plan", "day_memory", "digest", "today")


def _count(usage: Any, field: str) -> int | None:
    value = getattr(usage, field, None) if usage is not None else None
    return int(value) if isinstance(value, int) else None


def usage_line(ts_iso: str, agent: str, kind: str, model: str, usage: Any, ok: bool) -> dict:
    """One record per Gemini call. Missing metadata → nulls. Never any text."""
    return {
        "ts": ts_iso,
        "agent": agent,
        "kind": kind,
        "model": model,
        "prompt_tokens": _count(usage, "prompt_token_count"),
        "output_tokens": _count(usage, "candidates_token_count"),
        "total_tokens": _count(usage, "total_token_count"),
        "ok": bool(ok),
    }


def parse_lines(lines: list[str]) -> tuple[list[dict], int]:
    """(records, corrupt_count) — a corrupt line is skipped, never fatal."""
    out, bad = [], 0
    for line in lines:
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
            date.fromisoformat(str(rec["ts"])[:10])
            out.append(rec)
        except (ValueError, KeyError, TypeError):
            bad += 1
    return out, bad


@dataclass
class Row:
    calls: int = 0
    failed: int = 0
    prompt: int = 0
    output: int = 0
    total: int = 0


def aggregate(records: list[dict], since: date | None = None) -> dict[tuple[str, str, str], Row]:
    """By (day, agent, kind). Null counts add nothing."""
    rows: dict[tuple[str, str, str], Row] = defaultdict(Row)
    for r in records:
        day = str(r["ts"])[:10]
        if since and date.fromisoformat(day) < since:
            continue
        row = rows[(day, str(r.get("agent", "?")), str(r.get("kind", "?")))]
        row.calls += 1
        row.failed += 0 if r.get("ok") else 1
        row.prompt += r.get("prompt_tokens") or 0
        row.output += r.get("output_tokens") or 0
        row.total += r.get("total_tokens") or 0
    return dict(sorted(rows.items()))


def cost(row: Row, price_in: float | None, price_out: float | None) -> float | None:
    if price_in is None or price_out is None:
        return None
    return row.prompt / 1e6 * price_in + row.output / 1e6 * price_out


def render(rows: dict[tuple[str, str, str], Row], price_in: float | None, price_out: float | None,
           markdown: bool = False) -> str:
    if not rows:
        return "no data"
    with_cost = price_in is not None and price_out is not None
    head = ["day", "agent", "kind", "calls", "failed", "input", "output", "total"] + (["cost $"] if with_cost else [])
    body = []

    def line(cells: list[str]) -> None:
        body.append(cells)

    per_agent: dict[str, Row] = defaultdict(Row)
    overall = Row()
    for (day, agent, kind), r in rows.items():
        line([day, agent, kind, str(r.calls), str(r.failed), str(r.prompt), str(r.output), str(r.total)]
             + ([f"{cost(r, price_in, price_out):.4f}"] if with_cost else []))
        for acc in (per_agent[agent], overall):
            acc.calls += r.calls
            acc.failed += r.failed
            acc.prompt += r.prompt
            acc.output += r.output
            acc.total += r.total
    for agent, r in sorted(per_agent.items()):
        line(["TOTAL", agent, "", str(r.calls), str(r.failed), str(r.prompt), str(r.output), str(r.total)]
             + ([f"{cost(r, price_in, price_out):.4f}"] if with_cost else []))
    line(["TOTAL", "all", "", str(overall.calls), str(overall.failed), str(overall.prompt), str(overall.output),
          str(overall.total)] + ([f"{cost(overall, price_in, price_out):.4f}"] if with_cost else []))
    if markdown:
        out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
        out += ["| " + " | ".join(c) + " |" for c in body]
        return "\n".join(out)
    widths = [max(len(head[i]), *(len(c[i]) for c in body)) for i in range(len(head))]
    fmt = "  ".join(f"{{:{'<' if i < 3 else '>'}{w}}}" for i, w in enumerate(widths))
    return "\n".join([fmt.format(*head)] + [fmt.format(*c) for c in body])
