"""Token accounting: the usage line, parsing, aggregation and the report
(ARCHITECTURE §Token accounting). Pure functions; no texts ever."""

from __future__ import annotations

import calendar
import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

KINDS = ("reply", "summary", "plan", "day_memory", "digest", "today", "mood",
         "digest_voice", "ask", "tts",  # v5.1: Hermes's digest and answers (Gemini Pro), his voice (ElevenLabs)
         "stt",                         # v5.2: his hearing (Deepgram)
         "private", "private_nudge",    # v5.6: a person's private chat — an answer, a line written first
         "embed",                       # v5.8: the archive's embeddings (`recall`)
         "facts",                       # v5.8: the facts' extraction and the Noos import (`facts`)
         "event",                       # v5.11: an event of her life, written by one call (`events`)
         "reading", "thought", "reflection",  # v5.12: her pick, a thought on what she read, a reflection (`thoughts`)
         "judge",                             # v5.15: the judge rating her backup's talk (OpenRouter)
         "probe",                             # v5.16: Gemini asked whether it blocks a part of a blocked prompt
         "photo",                             # v5.17: Google's image model, her photo in Telegram
         "video", "video_note")               # v5.18: her clip (Omni Flash) and her кружечок (Fabric 1.0 on fal)
# v4.4 — how a call is paid: `api` (Gemini, priced), `subscription` (Claude on the Max plan; v5.1 also the ElevenLabs
# plan's credits), `external` (Lumi's own)
BILLING = ("api", "subscription", "external")


def _count(usage: Any, field: str) -> int | None:
    value = getattr(usage, field, None) if usage is not None else None
    return int(value) if isinstance(value, int) else None


def _output(usage: Any) -> int | None:
    """The answer plus the thinking (v5.1): Gemini bills the thoughts as output."""
    answer, thoughts = _count(usage, "candidates_token_count"), _count(usage, "thoughts_token_count")
    if answer is None and thoughts is None:
        return None
    return (answer or 0) + (thoughts or 0)


def usage_line(ts_iso: str, agent: str, kind: str, model: str, usage: Any, ok: bool,
               blocked: str | None = None) -> dict:
    """One record per Gemini call (v2 since v4.4: engine, billing, cache tokens; v3 since v5.1: `characters`, null
    here, and the thinking counted in the output; v5 since v5.13: `blocked`, the stage of a safety block — `prompt`
    or `answer` — or null). Missing metadata → nulls. Never any text."""
    return {
        "ts": ts_iso,
        "agent": agent,
        "kind": kind,
        "model": model,
        "prompt_tokens": _count(usage, "prompt_token_count"),
        "output_tokens": _output(usage),
        "total_tokens": _count(usage, "total_token_count"),
        "ok": bool(ok),
        "engine": "gemini",
        "billing": "api",
        "cache_read_tokens": _count(usage, "cached_content_token_count"),
        "cache_write_tokens": None,
        "reported_cost_usd": None,
        "characters": None,
        "audio_ms": None,
        "blocked": blocked,
        "video_ms": None,  # v6 (v5.18): a video's length, on a `video_note` line only
    }


def tts_usage_line(ts_iso: str, agent: str, model: str, characters: int, ok: bool) -> dict:
    """v5.1 — one record per text-to-speech call (ElevenLabs): counted in characters, paid from the plan's credits
    (`subscription`, never priced); no tokens. Never any text."""
    return {
        "ts": ts_iso, "agent": agent, "kind": "tts", "model": model,
        "prompt_tokens": None, "output_tokens": None, "total_tokens": None, "ok": bool(ok),
        "engine": "elevenlabs", "billing": "subscription",
        "cache_read_tokens": None, "cache_write_tokens": None, "reported_cost_usd": None,
        "characters": int(characters),
        "audio_ms": None,
        "blocked": None,  # v5.13: one line shape — only a Gemini call is ever blocked
        "video_ms": None,
    }


def fallback_usage_line(ts_iso: str, agent: str, kind: str, model: str, ok: bool) -> dict:
    """v5.14 — one record per call of Кіра's backup model (GLM-4.6 on NovelAI): the subscription pays it, so it is
    never priced, and the stream reports no token counts. Never any text."""
    return {
        "ts": ts_iso, "agent": agent, "kind": kind, "model": model,
        "prompt_tokens": None, "output_tokens": None, "total_tokens": None, "ok": bool(ok),
        "engine": "novelai", "billing": "subscription",
        "cache_read_tokens": None, "cache_write_tokens": None, "reported_cost_usd": None,
        "characters": None, "audio_ms": None, "blocked": None, "video_ms": None,
    }


def judge_usage_line(ts_iso: str, agent: str, model: str, prompt_tokens: int | None, output_tokens: int | None,
                     ok: bool, reported_cost: float | None = None) -> dict:
    """v5.15 — one record per call of the judge (Gemma 4 31B on OpenRouter, `agents/judge.py`): the kind `judge`,
    paid per token (`api`, priced by `PRICE_MODELS` under the model's id); OpenRouter's own cost of the call, when it
    sends one, kept beside it. Never any text."""
    total = prompt_tokens + output_tokens if prompt_tokens is not None and output_tokens is not None else None
    return {
        "ts": ts_iso, "agent": agent, "kind": "judge", "model": model,
        "prompt_tokens": prompt_tokens, "output_tokens": output_tokens, "total_tokens": total, "ok": bool(ok),
        "engine": "openrouter", "billing": "api",
        "cache_read_tokens": None, "cache_write_tokens": None, "reported_cost_usd": reported_cost,
        "characters": None, "audio_ms": None, "blocked": None, "video_ms": None,
    }


def stt_usage_line(ts_iso: str, agent: str, model: str, audio_ms: int | None, ok: bool) -> dict:
    """v5.2 — one record per speech-to-text call (Deepgram): counted by the audio's length (usage line v4,
    `audio_ms`), paid from the plan's credits (`subscription`, never priced); no tokens. Never any text."""
    return {
        "ts": ts_iso, "agent": agent, "kind": "stt", "model": model,
        "prompt_tokens": None, "output_tokens": None, "total_tokens": None, "ok": bool(ok),
        "engine": "deepgram", "billing": "subscription",
        "cache_read_tokens": None, "cache_write_tokens": None, "reported_cost_usd": None,
        "characters": None, "audio_ms": int(audio_ms) if isinstance(audio_ms, int) else None,
        "blocked": None, "video_ms": None,
    }


def video_note_usage_line(ts_iso: str, agent: str, model: str, video_ms: int | None, ok: bool,
                          blocked: str | None = None) -> dict:
    """v5.18 — one record per call of her кружечок's model on fal (`agents/video.py`): paid per second of
    video (`api`, priced by `PRICE_SECONDS` under the model's id), counted by the video's length (usage line v6,
    `video_ms`); no tokens. Never any text."""
    return {
        "ts": ts_iso, "agent": agent, "kind": "video_note", "model": model,
        "prompt_tokens": None, "output_tokens": None, "total_tokens": None, "ok": bool(ok),
        "engine": "fal", "billing": "api",
        "cache_read_tokens": None, "cache_write_tokens": None, "reported_cost_usd": None,
        "characters": None, "audio_ms": None, "blocked": blocked,
        "video_ms": int(video_ms) if isinstance(video_ms, int) and not isinstance(video_ms, bool) else None,
    }


def _int(d: dict, key: str) -> int | None:
    value = d.get(key) if isinstance(d, dict) else None
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def sdk_usage_line(ts_iso: str, agent: str, kind: str, model: str, usage: dict | None, ok: bool,
                   reported_cost: float | None = None) -> dict:
    """v4.4 — one record per Claude Agent SDK call: always `claude-sdk` / `subscription` (the Max plan, never an API
    key); the SDK's `total_cost_usd` is a client-side estimate, kept as reported and never billed."""
    usage = usage or {}
    fresh, output = _int(usage, "input_tokens"), _int(usage, "output_tokens")
    cache_read, cache_write = _int(usage, "cache_read_input_tokens"), _int(usage, "cache_creation_input_tokens")
    # the whole prompt, as Gemini's count includes its cache (review #12); the cache parts stay in their columns
    prompt = fresh + (cache_read or 0) + (cache_write or 0) if fresh is not None else None
    total = prompt + output if prompt is not None and output is not None else None
    cost = float(reported_cost) if isinstance(reported_cost, int | float) and not isinstance(reported_cost, bool) else None
    return {
        "ts": ts_iso, "agent": agent, "kind": kind, "model": model,
        "prompt_tokens": prompt, "output_tokens": output, "total_tokens": total, "ok": bool(ok),
        "engine": "claude-sdk", "billing": "subscription",
        "cache_read_tokens": cache_read,
        "cache_write_tokens": cache_write,
        "reported_cost_usd": cost,
        "characters": None,
        "audio_ms": None,
        "blocked": None,
        "video_ms": None,
    }


COUNT_FIELDS = ("prompt_tokens", "output_tokens", "total_tokens", "cache_read_tokens", "cache_write_tokens",
                "characters", "audio_ms", "video_ms")


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
            and rec.get("billing", "api") in BILLING and isinstance(rec.get("engine", "gemini"), str)
            and isinstance(rec.get("blocked") or "", str))  # v5.13: missing or null on an older line


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
    characters: int = 0     # v5.1: text-to-speech characters (ElevenLabs)
    blocked: int = 0        # v5.13: calls Gemini's safety filter blocked
    video_ms: int = 0       # v5.18: the videos' length (fal's кружечки)
    audio_ms: int = 0       # v5.19: the audio heard (Deepgram), for the analytics
    by_model: dict[str, list[int]] = field(default_factory=dict)  # v5.1: the `api` tokens per model, for its price
    ms_by_model: dict[str, int] = field(default_factory=dict)     # v5.18: the `api` video ms per model, for its price

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
        self.characters += other.characters
        self.blocked += other.blocked
        self.video_ms += other.video_ms
        self.audio_ms += other.audio_ms
        for model, ms in other.ms_by_model.items():
            self.ms_by_model[model] = self.ms_by_model.get(model, 0) + ms
        for model, (p, o) in other.by_model.items():
            mine = self.by_model.setdefault(model, [0, 0])
            mine[0] += p
            mine[1] += o


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
        kind = str(r.get("kind", "?"))
        if _engine(r) == "novelai":  # v5.14: her backup's answers are a row of their own, named by the model
            kind = f"{kind} ({r.get('model') or 'backup'})"
        _add_line(rows[(day, str(r.get("agent", "?")), kind)], r)
    return dict(sorted(rows.items()))


def _engine(r: dict) -> str:
    return str(r.get("engine", "gemini"))  # a v1 line is Gemini's


def _add_line(row: Row, r: dict) -> None:
    """One usage line into a row: its counts, and its `api` tokens and video ms by model, for the price."""
    billing = str(r.get("billing", "api"))
    row.engine, row.billing = _merge(row.engine, _engine(r)), _merge(row.billing, billing)
    row.calls += 1
    row.failed += 0 if r.get("ok") else 1
    row.prompt += r.get("prompt_tokens") or 0
    row.output += r.get("output_tokens") or 0
    row.total += r.get("total_tokens") or 0
    row.characters += r.get("characters") or 0
    row.blocked += 1 if r.get("blocked") else 0  # v5.13
    row.video_ms += r.get("video_ms") or 0       # v5.18
    row.audio_ms += r.get("audio_ms") or 0       # v5.19
    if billing == "api" and r.get("video_ms"):
        model = str(r.get("model", ""))
        row.ms_by_model[model] = row.ms_by_model.get(model, 0) + r["video_ms"]
    if billing == "api":
        p, o = r.get("prompt_tokens") or 0, r.get("output_tokens") or 0
        row.priced_prompt += p
        row.priced_output += o
        mine = row.by_model.setdefault(str(r.get("model", "")), [0, 0])
        mine[0] += p
        mine[1] += o


Prices = dict[str, tuple[float, float]]


def parse_model_prices(spec: str | None) -> tuple[Prices, list[str]]:
    """v5.1 — `PRICE_MODELS`: comma-separated `model=in/out` (USD per 1M tokens), e.g.
    `gemini-3.1-pro-preview=2/12`. Returns the prices and the malformed entries (to warn about, never fatal)."""
    prices: Prices = {}
    bad: list[str] = []
    for entry in (spec or "").split(","):
        entry = entry.strip()
        if not entry:
            continue
        model, _, pair = entry.partition("=")
        p_in, _, p_out = pair.partition("/")
        try:
            values = float(p_in), float(p_out)
        except ValueError:
            bad.append(entry)
            continue
        if not model.strip() or not all(math.isfinite(v) and v >= 0 for v in values):
            bad.append(entry)
            continue
        prices[model.strip()] = values
    return prices, bad


SecondPrices = dict[str, float]


def parse_second_prices(spec: str | None) -> tuple[SecondPrices, list[str]]:
    """v5.18 — `PRICE_SECONDS`: comma-separated `model=usd` (USD per second of video), e.g.
    `veed/fabric-1.0=0.08`. Returns the prices and the malformed entries (to warn about,
    never fatal)."""
    prices: SecondPrices = {}
    bad: list[str] = []
    for entry in (spec or "").split(","):
        entry = entry.strip()
        if not entry:
            continue
        model, _, value = entry.partition("=")
        try:
            price = float(value)
        except ValueError:
            bad.append(entry)
            continue
        if not model.strip() or not math.isfinite(price) or price < 0:
            bad.append(entry)
            continue
        prices[model.strip()] = price
    return prices, bad


def cost(row: Row, price_in: float | None, price_out: float | None, models: Prices | None = None,
         seconds: SecondPrices | None = None) -> float | None:
    """The price of a row's `api` tokens: a model listed in `models` (v5.1, `PRICE_MODELS`) by its own pair, the rest
    by the PRICE_* pair (Gemini Flash's). A row with no `api` part — Claude on the subscription, the ElevenLabs
    credits, Lumi's own — has no cost, never $0 (v4.4); api tokens with no price known → None. v5.18: a row's `api`
    video seconds are priced by `seconds` (`PRICE_SECONDS`) under their model — one with no price → None."""
    if row.billing and row.billing != "api" and not (row.priced_prompt or row.priced_output or row.ms_by_model):
        return None
    total = 0.0
    if row.ms_by_model:
        for model, ms in row.ms_by_model.items():
            price = (seconds or {}).get(model)
            if price is None:
                return None
            total += ms / 1000 * price
        if not (row.priced_prompt or row.priced_output):
            return total
    models = models or {}
    listed_in, listed_out = 0, 0
    for model, (p, o) in row.by_model.items():
        pair = models.get(model)
        if pair:
            total += p / 1e6 * pair[0] + o / 1e6 * pair[1]
            listed_in, listed_out = listed_in + p, listed_out + o
    rest_in, rest_out = row.priced_prompt - listed_in, row.priced_output - listed_out
    if rest_in or rest_out or not (listed_in or listed_out):
        if price_in is None or price_out is None:
            return None
        total += rest_in / 1e6 * price_in + rest_out / 1e6 * price_out
    return total


def month_chars(records: list[dict], agent: str, month: str) -> int:
    """v5.1 — the text-to-speech characters `agent` used in `month` (`YYYY-MM`): its ok `tts` lines. The usage file
    is the one record; Hermes's monthly cap reads this."""
    return sum(r.get("characters") or 0 for r in records
               if r.get("agent") == agent and r.get("kind") == "tts" and r.get("ok") and str(r["ts"])[:7] == month)


def render(rows: dict[tuple[str, str, str], Row], price_in: float | None, price_out: float | None,
           markdown: bool = False, models: Prices | None = None, seconds: SecondPrices | None = None) -> str:
    if not rows:
        return "no data"
    with_cost = price_in is not None and price_out is not None or bool(models) or bool(seconds)
    with_chars = any(r.characters for r in rows.values())  # v5.1: text to speech counts characters
    with_video = any(r.video_ms for r in rows.values())    # v5.18: her кружечки count seconds
    prices = (price_in, price_out)
    head = ["day", "agent", "kind", "calls", "failed", "input", "output", "total"] \
        + (["chars"] if with_chars else []) + (["video s"] if with_video else []) + ["billing"] \
        + (["cost $"] if with_cost else [])  # v4.4: billing — only `api` rows carry a cost
    body = []

    def line(cells: list[str], r: Row) -> None:
        body.append(cells + ([str(r.characters)] if with_chars else []) + ([_secs(r.video_ms)] if with_video else [])
                    + [r.billing or "api"] + ([_usd(r, prices, models, seconds)] if with_cost else []))

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


_cost = cost  # the daily report's own `cost` closes over its prices


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


def _secs(ms: int) -> str:
    return f"{ms / 1000:,.0f}"


def _usd(row: Row, prices: tuple[float | None, float | None], models: Prices | None = None,
         seconds: SecondPrices | None = None) -> str:
    c = cost(row, *prices, models, seconds)
    return "—" if c is None else f"{c:.4f}"


def _prices_line(price_in: float | None, price_out: float | None, models: Prices | None,
                 seconds: SecondPrices | None = None) -> str:
    """The report's price line: the pairs that are set (v5.1 review #5 — a model's own pair alone is not "no
    prices", and the models without one show «—», never $0); v5.18: the per-second prices."""
    parts = [f"${price_in:.2f} input / ${price_out:.2f} output per 1M tokens"] \
        if price_in is not None and price_out is not None else []
    parts += [f"{m} ${a:g} / ${b:g}" for m, (a, b) in sorted((models or {}).items())]
    parts += [f"{m} ${p:g} per second" for m, p in sorted((seconds or {}).items())]
    if not parts:
        return "No prices set (`PRICE_INPUT_PER_1M` / `PRICE_OUTPUT_PER_1M`) — tokens only."
    rest = "" if price_in is not None and price_out is not None else \
        " Other models have no price (`PRICE_INPUT_PER_1M` / `PRICE_OUTPUT_PER_1M`): a cost that includes them is —."
    return "Prices: " + "; ".join(parts) + "." + rest


def _per(c: float | None, divisor: float, digits: int) -> str:
    """A cost divided (an average, a projection), or «—» when it cannot be known — never a made-up $0."""
    return "—" if c is None else f"${c / divisor:.{digits}f}"


def _cost_change(now: float | None, before: float | None) -> str:
    return "—" if now is None or before is None else _change(now, before)


def _change(now: float, before: float) -> str:
    if not before:
        return "—"
    return f"{(now - before) / before * 100:+.0f}%"


def daily_report(records: list[dict], now: datetime, price_in: float | None = None,
                 price_out: float | None = None, models: Prices | None = None,
                 seconds: SecondPrices | None = None) -> str:
    """The daily markdown report for the local `now`: yesterday in detail, the day before for comparison,
    the last 7 complete days, the month of yesterday so far (+ a projection), and today so far."""
    prices = (price_in, price_out)
    priced = price_in is not None and price_out is not None or bool(models) or bool(seconds)
    today = now.date()
    yday = today - timedelta(days=1)
    usd = ["cost $"] if priced else []
    chars = ["chars"] if any(r.get("characters") for r in records) else []  # v5.1: text to speech
    video = ["video s"] if any(r.get("video_ms") for r in records) else []  # v5.18: her кружечки

    def cost(r: Row) -> float | None:  # every price the report knows
        return _cost(r, *prices, models, seconds)

    def money(r: Row) -> list[str]:
        return [_usd(r, prices, models, seconds)] if priced else []

    def spoken(r: Row) -> list[str]:
        return ([_n(r.characters)] if chars else []) + ([_secs(r.video_ms)] if video else [])

    def stats_row(label: str, r: Row) -> list[str]:
        return [label, _n(r.calls), _n(r.failed), _n(r.prompt), _n(r.output), _n(r.total)] + spoken(r) + money(r)

    head = ["", "calls", "failed", "input", "output", "total"] + chars + video + usd
    out = [f"# Token usage — {today.isoformat()}",
           "",
           f"Generated {now.strftime('%Y-%m-%d %H:%M')} ({now.tzname() or 'local'}). "
           + _prices_line(price_in, price_out, models, seconds),
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
                + (f", cost {_cost_change(cost(y), cost(before))}"
                   if priced else "") + ".", ""]
        k_head = ["kind", "calls", "share of tokens", "avg input / call", "avg output / call", "failed"] + usd
        k_body = [[k, _n(r.calls), f"{(r.total / y.total * 100 if y.total else 0):.0f}%",
                   _n(r.prompt / r.calls), _n(r.output / r.calls), _n(r.failed)] + money(r)
                  for k, r in sorted(rollup(y_rows, 2).items(), key=lambda kv: -kv[1].total)]
        out += ["### By kind", "", table(k_head, k_body, markdown=True), ""]
        out += ["### By agent × kind", "", render(y_rows, price_in, price_out, markdown=True, models=models,
                                                  seconds=seconds), ""]

    # the last 7 complete days
    first = yday - timedelta(days=6)
    week_rows = aggregate(records, first, yday)
    by_day = rollup(week_rows, 0)
    w = _total(week_rows)
    days = [first + timedelta(days=i) for i in range(7)]
    d_body = [stats_row(d.isoformat(), by_day.get(d.isoformat(), Row())) for d in days]
    out += [f"## Last 7 days — {first.isoformat()} … {yday.isoformat()}", "",
            table(["day", "calls", "failed", "input", "output", "total"] + chars + video + usd,
                  d_body + [stats_row("**total**", w)], markdown=True), "",
            f"Daily average: {_n(w.calls / 7)} calls, {_n(w.total / 7)} tokens"
            + (f", {_per(cost(w), 7, 4)}" if priced else "") + "."
            + (f" Busiest day: {max(by_day.items(), key=lambda kv: kv[1].total)[0]}." if by_day else ""), ""]

    # the month of yesterday, so far
    m_first = yday.replace(day=1)
    m = _total(aggregate(records, m_first, yday))
    m_days = calendar.monthrange(yday.year, yday.month)[1]
    out += [f"## Month so far — {m_first.strftime('%Y-%m')} (days 1–{yday.day} of {m_days})", "",
            f"{_n(m.calls)} calls · {_n(m.failed)} failed · {_n(m.total)} tokens "
            f"({_n(m.prompt)} input, {_n(m.output)} output)"
            + (f" · {_per(cost(m), 1, 4)} · projected month "
               f"{_per(cost(m), yday.day / m_days, 2)}"
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


# --- the analytics (v5.19): one period and one agent (or all), by service, model, kind, day and agent ---
@dataclass(frozen=True)
class PriceBook:
    """Every price the analytics knows: the default pair, `PRICE_MODELS`, `PRICE_SECONDS` and, v5.19,
    `PRICE_SUBSCRIPTIONS` (a service's monthly fee)."""
    price_in: float | None = None
    price_out: float | None = None
    models: Prices = field(default_factory=dict)
    seconds: SecondPrices = field(default_factory=dict)
    subscriptions: dict[str, float] = field(default_factory=dict)

    @property
    def priced(self) -> bool:
        return self.price_in is not None and self.price_out is not None or bool(self.models) or bool(self.seconds)


def parse_subscription_prices(spec: str | None) -> tuple[dict[str, float], list[str]]:
    """v5.19 — `PRICE_SUBSCRIPTIONS`: comma-separated `service=usd_per_month`, keyed by the usage line's `engine`
    (`elevenlabs=99,novelai=25`); the same `name=usd` shape as `PRICE_SECONDS`. Returns the prices and the malformed
    entries (to warn about, never fatal)."""
    return parse_second_prices(spec)


Atom = tuple[str, str, str, str, str]  # (day, agent, service, model, kind): one model, so one exact price


def _atoms(records: list[dict], since: date, until: date) -> dict[Atom, Row]:
    atoms: dict[Atom, Row] = defaultdict(Row)
    for r in records:
        day = str(r["ts"])[:10]
        if not since.isoformat() <= day <= until.isoformat():
            continue
        _add_line(atoms[(day, str(r.get("agent", "?")), _engine(r), str(r.get("model") or "?"),
                         str(r.get("kind", "?")))], r)
    return atoms


def _atom_cost(row: Row, prices: PriceBook) -> float | None:
    """One atom's cost: a subscription's is None, never $0 (v4.4); an `api` atom with nothing billable (a failed
    call without counts) is $0; an `api` model with no price is None — named in `unpriced`."""
    if row.billing == "api" and not (row.priced_prompt or row.priced_output or row.ms_by_model):
        return 0.0
    return cost(row, prices.price_in, prices.price_out, prices.models, prices.seconds)


@dataclass
class _Sum:
    """A sum of atoms: their counts, the cost of the priced ones, and whether an unpriced `api` atom is in it."""
    row: Row = field(default_factory=Row)
    cost: float = 0.0
    priced: bool = False
    complete: bool = True

    def add(self, row: Row, c: float | None) -> None:
        self.row.add(row)
        if c is not None:
            self.cost, self.priced = self.cost + c, True
        elif row.billing != "subscription":
            self.complete = False

    def totals(self) -> dict:
        r = self.row
        return {"calls": r.calls, "failed": r.failed, "blocked": r.blocked, "input": r.prompt, "output": r.output,
                "tokens": r.total, "characters": r.characters, "audio_s": round(r.audio_ms / 1000, 1),
                "video_s": round(r.video_ms / 1000, 1), "billing": r.billing or "api",
                "cost": round(self.cost, 6) if self.priced else None, "complete": self.complete}

    def brief(self) -> dict:
        return {"cost": round(self.cost, 6) if self.priced else None, "calls": self.row.calls,
                "tokens": self.row.total}


def _group(atoms: dict[Atom, Row], costs: dict[Atom, float | None], key) -> dict:
    out: dict = defaultdict(_Sum)
    for atom, row in atoms.items():
        out[key(atom)].add(row, costs[atom])
    return out


def _days(since: date, until: date) -> list[str]:
    return [(since + timedelta(days=i)).isoformat() for i in range((until - since).days + 1)]


def _rank(item: tuple) -> tuple:
    s = item[1]
    return (-(s.cost if s.priced else -1.0), -s.row.calls, item[0])


def trend(daily: list[float]) -> dict:
    """The daily cost's least-squares slope (as $ a week) and its direction: flat under 5 % of the mean a day, or
    with fewer than 3 days that cost anything (pure)."""
    n = len(daily)
    if n < 2:
        return {"slope_per_week": 0.0, "direction": "flat"}
    mean_x, mean_y = (n - 1) / 2, sum(daily) / n
    sxx = sum((x - mean_x) ** 2 for x in range(n))
    slope = sum((x - mean_x) * (y - mean_y) for x, y in enumerate(daily)) / sxx
    flat = sum(1 for y in daily if y > 0) < 3 or not mean_y or abs(slope) < 0.05 * mean_y
    return {"slope_per_week": round(slope * 7, 6),
            "direction": "flat" if flat else "rising" if slope > 0 else "falling"}


def analyze(records: list[dict], since: date, until: date, agent: str | None = None,
            prices: PriceBook | None = None) -> dict:
    """v5.19 — the analytics for [since, until] (local days, inclusive) and one agent, or all (None): the totals and
    the previous period's of the same length, by service (`engine`) and its models, by kind, day by day (the cost by
    service, its 7-day moving average and running total) with the trend, by agent, the subscriptions' fees prorated
    by day, the unpriced models and the atomic rows. Pure, over plain data; the days are given, no clock inside."""
    prices = prices or PriceBook()
    n = (until - since).days + 1
    p_until, p_since = since - timedelta(days=1), since - timedelta(days=n)
    lines = [r for r in records if agent is None or r.get("agent") == agent]
    first_line = min((str(r["ts"])[:10] for r in lines), default=None)
    window = _atoms(lines, min(p_since, since - timedelta(days=6)), until)
    costs = {a: _atom_cost(row, prices) for a, row in window.items()}
    days, p_days = _days(since, until), _days(p_since, p_until)
    now = {a: r for a, r in window.items() if since.isoformat() <= a[0]}
    before = {a: r for a, r in window.items() if p_since.isoformat() <= a[0] <= p_until.isoformat()}

    total, prev = _group(now, costs, lambda a: "")[""], _group(before, costs, lambda a: "")[""]
    by_day_cost = {d: s.cost for d, s in _group(window, costs, lambda a: a[0]).items()}
    prev_by = {name: _group(before, costs, key) for name, key in
               (("service", lambda a: a[2]), ("kind", lambda a: a[4]), ("agent", lambda a: a[1]))}

    services = []
    for svc, s in sorted(_group(now, costs, lambda a: a[2]).items(), key=_rank):
        mine = {a: r for a, r in now.items() if a[2] == svc}
        per_day = {d: (x.cost, x.row.calls) for d, x in _group(mine, costs, lambda a: a[0]).items()}
        models = [{"model": m, **x.totals(), "previous": _group({a: r for a, r in before.items() if a[2] == svc
                                                                  and a[3] == m}, costs, lambda a: "")[""].brief()}
                  for m, x in sorted(_group(mine, costs, lambda a: a[3]).items(), key=_rank)]
        services.append({"service": svc, **s.totals(), "previous": prev_by["service"][svc].brief(),
                         "series": {"cost": [round(per_day.get(d, (0.0, 0))[0], 6) for d in days],
                                    "calls": [per_day.get(d, (0.0, 0))[1] for d in days]},
                         "models": models})

    t_cost = total.cost if total.priced else None
    kinds = [{"kind": k, **s.totals(), "previous": prev_by["kind"][k].brief(),
              "share": round(s.cost / t_cost, 4) if s.priced and t_cost else None}
             for k, s in sorted(_group(now, costs, lambda a: a[4]).items(), key=_rank)]

    day_groups = {name: _group(now, costs, key) for name, key in
                  (("day", lambda a: a[0]), ("svc", lambda a: (a[0], a[2])))}
    day_series, running = [], 0.0
    for i, d in enumerate(days):
        s = day_groups["day"][d]
        running += s.cost
        start = max(since - timedelta(days=6) + timedelta(days=i), date.fromisoformat(first_line or d))
        window_days = _days(start, date.fromisoformat(d))
        avg = sum(by_day_cost.get(w, 0.0) for w in window_days) / max(1, len(window_days))
        mine = {svc: x for (day, svc), x in day_groups["svc"].items() if day == d}
        day_series.append({"day": d, "cost": round(s.cost, 6), "calls": s.row.calls, "tokens": s.row.total,
                           "cost_by_service": {svc: round(x.cost, 6) for svc, x in mine.items() if x.priced},
                           "calls_by_service": {svc: x.row.calls for svc, x in mine.items()},
                           "tokens_by_service": {svc: x.row.total for svc, x in mine.items()},
                           "cost_avg7": round(avg, 6), "cost_cumulative": round(running, 6)})
    p_running, previous_cumulative = 0.0, []
    for d in p_days:
        p_running += by_day_cost.get(d, 0.0)
        previous_cumulative.append(round(p_running, 6))

    agents = [] if agent is not None else [
        {"agent": a, **s.totals(), "previous": prev_by["agent"][a].brief(),
         "services": [svc for svc, _ in sorted(_group({k: r for k, r in now.items() if k[1] == a}, costs,
                                                      lambda x: x[2]).items(), key=_rank)]}
        for a, s in sorted(_group(now, costs, lambda a: a[1]).items(), key=_rank)]
    subscriptions = [] if agent is not None else [
        {"service": svc, "monthly": fee,
         "period_cost": round(sum(fee / calendar.monthrange(int(d[:4]), int(d[5:7]))[1] for d in days), 6)}
        for svc, fee in sorted(prices.subscriptions.items())]

    per_day = t_cost / n if t_cost is not None else None
    return {
        "since": since.isoformat(), "until": until.isoformat(), "days": n, "agent": agent,
        "total": {**total.totals(), "cost_per_day": round(per_day, 6) if per_day is not None else None},
        "previous": {"since": p_since.isoformat(), "until": p_until.isoformat(), **prev.totals()},
        "services": services, "kinds": kinds, "day_series": day_series,
        "previous_cumulative": previous_cumulative,
        "trend": {**trend([x["cost"] for x in day_series]),
                  "month_at_rate": round(per_day * 30, 6) if per_day is not None else None},
        "agents": agents, "subscriptions": subscriptions,
        "unpriced": sorted({a[3] for a, r in now.items() if costs[a] is None and r.billing != "subscription"}),
        "rows": [{"day": a[0], "agent": a[1], "service": a[2], "model": a[3], "kind": a[4], **{
            k: v for k, v in _Sum(r, costs[a] or 0.0, costs[a] is not None).totals().items() if k != "complete"}}
                 for a, r in sorted(now.items())],
    }
