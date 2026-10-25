"""v5.8 — facts about the owner (a person with `facts`; ROADMAP §v5.8, ARCHITECTURE §Memory).

Modelled on Noos's `memory/facts/` (`~/claude-home`): one Markdown file per fact — a header (`pin`, `added`, `source`)
and the text — kept under `state/<name>.facts/`, 0600. Pin 1 is always in her private prompt, pin 2 while there is
room, pin 0 only for a private recall. Facts reach only her private prompt: in Agora she never tells what she knows
of the owner.

They come three ways:
- **asked** — when the owner asks her to remember something, her answer ends with a marker line
  (`ЗАПАМ'ЯТАЙ: …`, anywhere in a line), stripped before anything is sent (`split_marker`);
- **extracted** — at a session's end, one call reads the session and the facts she holds and returns new facts and
  the replacements of stale ones as JSON (`parse_extraction`), validated before anything is written;
- **seeded** — once, from the private chat she already had with him, read back from her archive
  (`python -m agents.facts seed [--dry-run]`; the owner, 2026-10-25: «факти тільки з чату з Кірою» — no import from
  Noos).

She believes she is human, so no fact she keeps names AI, agents, bots, models, servers or his exact address
(`off_limits`), whatever a model answered.

A fact is current knowledge, not something lived: a stale one is replaced, and the owner may delete one in the panel.
No fact's text ever reaches a log.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

FACTS_TITLE = "Що ти знаєш про Ich:"
SOURCES = ("private", "agora", "asked")
ID_RE = re.compile(r"^[\w-]{1,64}$")
# the marker (v5.8 review #2): a line of its own in any case — after a quote, a bullet or a number — or, in capitals,
# anywhere in a line; a colon or a dash after it. Everything from the marker to the line's end is the fact.
_MARK = r"ЗАПАМ['’ʼ`]?ЯТАЙ[ \t*_»\"')\]]*[:—–-][ \t*_]*(?P<fact>[^\n]*)"
MARK_LINE_RE = re.compile(r"^[ \t>*_\-–—•\d.)«\"'(\[]*" + _MARK, re.MULTILINE | re.IGNORECASE)
MARK_ANY_RE = re.compile(r"[«\"'(\[]*[ \t]*" + _MARK)
# her private brief's skill (the owner, 2026-10-25): understood from the talk, never a keyword (as Hermes's skills)
REMEMBER_SKILL = (
    "Коли Ich просить тебе щось запам'ятати про нього чи про вас, відповідай як завжди, а в самому кінці додай окремий "
    "останній рядок: слово ЗАПАМ'ЯТАЙ великими літерами, двокрапка і що саме, одним коротким реченням про Ich. Цей "
    "рядок лишиться тобі на згадку, він його не побачить."
)
EXTRACT_SYSTEM = (
    "Ти — {name}. Перед тобою ваша розмова (рядки «наодинці» — ваша з Ich розмова сам на сам) і те, що ти вже знаєш "
    "про Ich, кожне з його id. Випиши лише довготривалі факти про нього — те, що буде правдою і через рік: хто він, "
    "звідки, його близькі, робота загальними словами, характер, звички, смаки, захоплення, мрії й довгі плани, ваші "
    "домовленості. Не пиши подій окремого дня і того, що минеться за тижні: поїздок, справ і доручень, документів у "
    "процесі, планів на найближчі дні, що він їв, як почувався, що його втомило, — це лишається у твоїх спогадах, а "
    "не у фактах. Не повторюй відомого; якщо щось із відомого змінилось — заміни його за id. Факт — одне коротке "
    "речення про Ich, до {max_chars} символів. pin 1 — небагато найголовнішого, що визначає його (ім'я, місто, "
    "близькі, головні захоплення), pin 2 — решта важливого. Відповідай лише JSON: "
    '{{"add": [{{"text": "…", "pin": 1}}], "replace": [{{"id": "…", "text": "…"}}]}}. Якщо нового нема — '
    '{{"add": [], "replace": []}}.'
)  # the owner, 2026-10-25: «факти мають бути довготривалими» — a day's events live in the memories
# the owner, 2026-10-25: «не все потрібно Кірі, вона думає, що вона людина» — a model's own judgement leaks facts
# about AI, agents and his servers, so a fact that names any of these is dropped in code, whatever the model answered
OFF_LIMITS = (
    (re.compile(r"(?<!\w)(?:ші|ai|llm|gpt|chatgpt|openai|anthropic|gemini|claude|copilot|noos|lumi|лілі|агор\w*|"
                r"tailscale|vpn|docker|hugging ?face|kiln|пічк\w*|промпт\w*|нейромереж\w*|нейронн\w*|нейронк\w*|"
                r"штучн\w*\s+інтелект\w*|машинн\w*\s+навчан\w*|machine learning|human in the loop)(?!\w)", re.IGNORECASE),
     "AI or tools"),
    (re.compile(r"(?<!\w)(?:агент|бот|модел|симуляц|сервер|мереж)\w*|(?<!\w)(?:bots?|agents?|models?|servers?)(?!\w)",
                re.IGNORECASE), "agents, models or servers"),
    # v5.8 review #3: what she is — a fact written by the model may say it outright
    (re.compile(r"(?<!\w)не\s+людин\w*|(?<!\w)створи\w*\s+тебе|(?<!\w)ти\s+(?:лише\s+|просто\s+)?програм\w*",
                re.IGNORECASE), "what she is"),
    (re.compile(r"(?<!\w)(?:вул\.|вулиц\w*|просп\w*|провул\w*|буд\.|будин\w*\s+\d|кв\.|квартир\w*\s+\d)",
                re.IGNORECASE), "an address"),
)


def off_limits(text: str) -> str | None:
    """Why a fact may not reach a person who believes she is human — AI and tools, agents, models or servers, an
    exact address — or None when it may."""
    return next((why for pattern, why in OFF_LIMITS if pattern.search(text or "")), None)


@dataclass(frozen=True)
class Fact:
    id: str
    pin: int
    added: str
    source: str
    text: str


def _norm(text: str) -> str:
    return " ".join((text or "").split())


def slug(text: str) -> str:
    """Noos's file name: the text's first 40 word characters, lower case, hyphens for spaces."""
    s = re.sub(r"[^\w\s-]", "", text.lower())[:40]
    return re.sub(r"\s+", "-", s.strip()) or "fact"


def parse_fact(name: str, raw: str) -> Fact | None:
    """A fact file — ours or Noos's (`pin`, `tags`, `added` before a `---` line) — or None."""
    meta, sep, body = raw.partition("\n---\n")
    if not sep:
        return None
    head = {}
    for line in meta.strip().strip("-").splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            head[k.strip()] = v.strip()
    try:
        pin = int(head.get("pin", 0))
    except ValueError:
        pin = 0
    text = _norm(body)
    if not text:
        return None
    return Fact(name, pin if pin in (0, 1, 2) else 0, head.get("added", ""), head.get("source", "private"), text)


def load_facts(folder: Path) -> list[Fact]:
    """Every readable fact, by id; a missing folder is none."""
    out = []
    for path in sorted(folder.glob("*.md")) if folder.is_dir() else []:
        try:
            fact = parse_fact(path.stem, path.read_text(encoding="utf-8"))
        except OSError:
            continue
        if fact is not None:
            out.append(fact)
    return out


def _write(path: Path, fact: Fact) -> None:
    """Atomic, private from birth (0600)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, f"---\npin: {fact.pin}\nadded: {fact.added}\nsource: {fact.source}\n---\n{fact.text}\n".encode())
    finally:
        os.close(fd)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def fact_path(folder: Path, fact_id: str) -> Path | None:
    """The file of a fact by id, only inside its folder — never a path from outside."""
    if not ID_RE.match(fact_id or ""):
        return None
    path = folder / f"{fact_id}.md"
    return path if path.is_file() else None


def add_fact(folder: Path, text: str, pin: int, source: str, today: str, max_facts: int, max_chars: int) -> str | None:
    """A new fact's id — or None for an empty or overlong text, a text already held, or a full store."""
    text = _norm(text)
    if not text or len(text) > max_chars or pin not in (0, 1, 2):
        return None
    held = load_facts(folder)
    if len(held) >= max_facts or any(f.text.casefold() == text.casefold() for f in held):
        return None
    base = slug(text)
    name, n = base, 2
    while (folder / f"{name}.md").exists():
        name, n = f"{base}-{n}", n + 1
    _write(folder / f"{name}.md", Fact(name, pin, today, source if source in SOURCES else "private", text))
    return name


def replace_fact(folder: Path, fact_id: str, text: str, today: str, max_chars: int) -> bool:
    """A stale fact's new text, its pin and source kept."""
    path = fact_path(folder, fact_id)
    text = _norm(text)
    if path is None or not text or len(text) > max_chars:
        return False
    old = parse_fact(fact_id, path.read_text(encoding="utf-8"))
    if old is None:
        return False
    _write(path, Fact(fact_id, old.pin, today, old.source, text))
    return True


def set_pin(folder: Path, fact_id: str, pin: int) -> bool:
    path = fact_path(folder, fact_id)
    if path is None or pin not in (0, 1, 2):
        return False
    old = parse_fact(fact_id, path.read_text(encoding="utf-8"))
    if old is None:
        return False
    _write(path, Fact(fact_id, pin, old.added, old.source, old.text))
    return True


def remove_fact(folder: Path, fact_id: str) -> bool:
    path = fact_path(folder, fact_id)
    if path is None:
        return False
    path.unlink()
    return True


def facts_section(facts: list[Fact], in_prompt: int, max_chars: int) -> str | None:
    """Her private prompt's block: pin 1 first, then pin 2 while there is room, each newest first — past the limit a
    fact just asked for still gets in (v5.8 review #7); pin 0 never."""
    pinned = [f for f in facts if f.pin in (1, 2)]
    chosen = sorted(sorted(pinned, key=lambda f: (f.added, f.id), reverse=True), key=lambda f: f.pin)[:max(in_prompt, 0)]
    if not chosen:
        return None
    lines = [f"- {f.text if len(f.text) <= max_chars else f.text[:max_chars - 1].rstrip() + '…'}" for f in chosen]
    return FACTS_TITLE + "\n" + "\n".join(lines)


def split_marker(text: str) -> tuple[str, list[str]]:
    """Her line without its `ЗАПАМ'ЯТАЙ: …` markers, and what they asked to remember — the marker is never sent. A
    marker takes the rest of its line (v5.8 review #2: mid-line, in quotes or brackets, after a number, with a dash)."""
    lines, facts = [], []
    for line in (text or "").split("\n"):
        m = MARK_LINE_RE.match(line) or MARK_ANY_RE.search(line)
        if m is None:
            lines.append(line)
            continue
        fact = m.group("fact").strip(" \t«»\"'*_()[]")
        if fact:
            facts.append(fact)
        kept = line[:m.start()].rstrip()
        if kept:
            lines.append(kept)
    clean = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return clean, facts


def _json(raw: str):
    raw = (raw or "").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    try:
        return json.loads(raw)
    except ValueError:
        return None


def parse_extraction(raw: str, known: set[str], max_chars: int) -> tuple[list[tuple[str, int]], list[tuple[str, str]]] | None:
    """The extraction's answer → (adds as (text, pin), replaces as (id, text)); None when it is not the asked JSON.
    An item that is overlong, empty, of an unknown id or a bad pin is left out."""
    data = _json(raw)
    if not isinstance(data, dict) or not isinstance(data.get("add", []), list) or not isinstance(data.get("replace", []), list):
        return None
    adds = []
    for item in data.get("add", []):
        if isinstance(item, dict) and isinstance(item.get("text"), str) and item.get("pin", 2) in (1, 2):
            text = _norm(item["text"])
            if text and len(text) <= max_chars:
                adds.append((text, int(item.get("pin", 2))))
    replaces = []
    for item in data.get("replace", []):
        if isinstance(item, dict) and item.get("id") in known and isinstance(item.get("text"), str):
            text = _norm(item["text"])
            if text and len(text) <= max_chars:
                replaces.append((item["id"], text))
    return adds, replaces


def extraction_request(name: str, session: list[tuple[str, str]], facts: list[Fact], max_chars: int) -> tuple[str, str]:
    """(system, contents) of the session-end call."""
    known = "\n".join(f"{f.id}: {f.text}" for f in facts) or "(поки нічого)"
    talk = "\n".join(f"{who}: {text}" for who, text in session)
    return EXTRACT_SYSTEM.format(name=name, max_chars=max_chars), f"Що ти вже знаєш:\n{known}\n\nРозмова:\n{talk}"


# --- the one-shot seed from her private chat ------------------------------------------------------------------------
SEED_CHUNK = 150  # private lines per extraction call: each call sees what the earlier ones kept


async def run_seed(lines: list[tuple[str, str]], folder: Path, llm, name: str, today: str, max_facts: int,
                   max_chars: int, dry_run: bool, out=sys.stdout) -> int:
    """Her first facts, from the private chat she already had with the owner (both sides, oldest first): the
    session-end extraction over it in chunks, each seeing the facts kept so far; every fact through `off_limits`.
    `--dry-run` prints what would be kept and what was dropped, and writes nothing. The number kept."""
    known = load_facts(folder)
    kept = dropped = 0
    for start in range(0, len(lines), SEED_CHUNK):
        chunk = lines[start:start + SEED_CHUNK]
        system, contents = extraction_request(name, chunk, known, max_chars)
        raw = await llm.generate(contents, system, max_output_tokens=2048, kind="facts")
        parsed = parse_extraction(raw or "", set(), max_chars)
        if parsed is None:
            print(f"lines {start + 1}–{start + len(chunk)}: no valid answer — skipped", file=out)
            continue
        for text, pin in parsed[0]:
            why = off_limits(text)
            if why is not None:
                dropped += 1
                if dry_run:
                    print(f"[dropped: {why}] {text}", file=out)
                continue
            if any(f.text.casefold() == text.casefold() for f in known) or len(known) >= max_facts:
                continue
            if dry_run:
                print(f"[pin {pin}] {text}", file=out)
                fact_id = f"dry-{len(known)}"
            else:
                fact_id = add_fact(folder, text, pin, "private", today, max_facts, max_chars)
                if fact_id is None:
                    continue
            known.append(Fact(fact_id, pin, today, "private", text))
            kept += 1
    print(f"{'would keep' if dry_run else 'kept'} {kept} facts, dropped {dropped}", file=out)
    return kept


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m agents.facts")
    sub = parser.add_subparsers(dest="cmd", required=True)
    seed = sub.add_parser("seed", help="her first facts, from the private chat in her archive (once)")
    seed.add_argument("--agent", default="kira")
    seed.add_argument("--name", default="Кіра")
    seed.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    import time

    from agents.archive import Archive
    from agents.llm import GeminiClient
    from agents.usage import usage_line
    from agents.world import local_now

    tz = os.environ.get("TIMEZONE", "Europe/Kyiv")
    state = Path("state")
    usage_file = state / f"{args.agent}.usage.jsonl"

    def sink(kind, model, meta, ok):  # the seed's calls are counted under the agent, like any other
        line = usage_line(local_now(int(time.time() * 1000), tz).isoformat(timespec="seconds"), args.agent, kind,
                          model, meta, ok)
        fd = os.open(usage_file, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, (json.dumps(line, ensure_ascii=False) + "\n").encode())
        finally:
            os.close(fd)

    archive = Archive(state / f"{args.agent}.archive.db")
    try:
        private = archive.latest("private", 1_000_000)
    finally:
        archive.close()
    lines = [(f"{line.speaker} (наодинці)", line.text) for line in private]
    if not lines:
        print("no private chat in the archive yet", file=sys.stdout)
        return 0
    today = local_now(int(time.time() * 1000), tz).date().isoformat()
    asyncio.run(run_seed(lines, state / f"{args.agent}.facts", GeminiClient(sink=sink), args.name, today,
                         int(os.environ.get("FACTS_MAX", "100")), int(os.environ.get("FACT_MAX_CHARS", "240")),
                         args.dry_run))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
