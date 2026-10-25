"""v5.8 — facts about the owner (a person with `facts`; ROADMAP §v5.8, ARCHITECTURE §Memory).

Modelled on Noos's `memory/facts/` (`~/claude-home`): one Markdown file per fact — a header (`pin`, `added`, `source`)
and the text — kept under `state/<name>.facts/`, 0600. Pin 1 is always in her private prompt, pin 2 while there is
room, pin 0 only for a private recall. Facts reach only her private prompt: in Agora she never tells what she knows
of the owner.

They come three ways:
- **asked** — when the owner asks her to remember something, her answer ends with a marker line
  (`ЗАПАМ'ЯТАЙ: …`), stripped before anything is sent (`split_marker`);
- **extracted** — at a session's end, one call reads the session and the facts she holds and returns new facts and
  the replacements of stale ones as JSON (`parse_extraction`), validated before anything is written;
- **imported** — once, from Noos (`python -m agents.facts import <dir> [--dry-run]`), filtered to the owner as a
  person: nothing about servers, tokens, agents, bots or simulations, so no fact tells a persona what she is.

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
SOURCES = ("private", "agora", "asked", "noos")
ID_RE = re.compile(r"^[\w-]{1,64}$")
MARK_RE = re.compile(r"^[ \t>*_-]*ЗАПАМ['’ʼ`]?ЯТАЙ[ \t*_]*:[ \t*_]*(.*?)[ \t*_]*$", re.MULTILINE | re.IGNORECASE)
# her private brief's skill (the owner, 2026-10-25): understood from the talk, never a keyword (as Hermes's skills)
REMEMBER_SKILL = (
    "Коли Ich просить тебе щось запам'ятати про нього чи про вас, відповідай як завжди, а в самому кінці додай окремий "
    "рядок: «ЗАПАМ'ЯТАЙ: <що саме, одним коротким реченням про Ich>». Цей рядок лишиться тобі на згадку, він його "
    "не побачить."
)
EXTRACT_SYSTEM = (
    "Ти — {name}. Перед тобою ваша щойно завершена розмова (рядки «наодинці» — ваша з Ich розмова сам на сам) і те, "
    "що ти вже знаєш про Ich, кожне з його id. Випиши нові довготривалі факти про нього: хто він, його життя, близькі, "
    "робота, звички, смаки, мрії, плани, ваші домовленості. Не повторюй відомого; якщо щось із відомого змінилось — "
    "заміни його за id. Не пиши дрібниць дня і того, що він сказав мимохідь. Факт — одне коротке речення про Ich, "
    "до {max_chars} символів. pin 1 — головне про нього, pin 2 — важливе. Відповідай лише JSON: "
    '{{"add": [{{"text": "…", "pin": 1}}], "replace": [{{"id": "…", "text": "…"}}]}}. Якщо нового нема — '
    '{{"add": [], "replace": []}}.'
)
IMPORT_SYSTEM = (
    "Перед тобою записи про одну людину — у розмовах її звуть Ich. Склади з них короткі факти про Ich як про людину: "
    "його життя, сім'я і близькі, дитинство, робота загальними словами (професія, галузь), інтереси, книжки і кіно, "
    "духовність, характер, цінності, побут, звички. Не бери нічого про сервери, програми, токени, паролі, дозволи, "
    "налаштування, а також про агентів, ботів, моделі, симуляції, чати з ними і їхні імена (Агора, Ада, Бруно, Кіра, "
    "Кіт, Клод, Гермес, Леон, Мія, Ірма, Лілі, Lumi, Noos) — такі записи пропусти повністю. Кожен факт — одне "
    "речення про Ich, до {max_chars} символів, без повторів. pin 1 — хто він і найголовніше (не більше 20), pin 2 — "
    "важливе, pin 0 — решта. Щонайбільше {limit} фактів. Відповідай лише JSON: "
    '{{"facts": [{{"text": "…", "pin": 1}}]}}.'
)


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
    return Fact(name, pin if pin in (0, 1, 2) else 0, head.get("added", ""), head.get("source", "noos"), text)


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
    """Her private prompt's block: pin 1 first, then pin 2 while there is room, each oldest first; pin 0 never."""
    chosen = sorted((f for f in facts if f.pin in (1, 2)), key=lambda f: (f.pin, f.added, f.id))[:max(in_prompt, 0)]
    if not chosen:
        return None
    lines = [f"- {f.text if len(f.text) <= max_chars else f.text[:max_chars - 1].rstrip() + '…'}" for f in chosen]
    return FACTS_TITLE + "\n" + "\n".join(lines)


def split_marker(text: str) -> tuple[str, list[str]]:
    """Her line without its `ЗАПАМ'ЯТАЙ: …` lines, and what they asked to remember — the marker is never sent."""
    facts = [m.group(1).strip(" «»\"'") for m in MARK_RE.finditer(text or "")]
    clean = MARK_RE.sub("", text or "")
    clean = re.sub(r"\n{3,}", "\n\n", clean).strip()
    return clean, [f for f in facts if f]


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


# --- the one-shot import from Noos -----------------------------------------------------------------------------------
def read_noos(folder: Path) -> tuple[list[Fact], list[str]]:
    """Noos's facts (`facts/*.md`) and its imported extracts (`import/*/*.md`, README left out)."""
    facts = load_facts(folder / "facts")
    extracts = []
    for path in sorted((folder / "import").glob("*/*.md")) if (folder / "import").is_dir() else []:
        if path.name.lower() != "readme.md":
            extracts.append(path.read_text(encoding="utf-8"))
    return facts, extracts


def import_request(facts: list[Fact], extracts: list[str], max_chars: int, limit: int) -> tuple[str, str]:
    notes = "\n".join(f"[pin {f.pin}] {f.text}" for f in facts)
    contents = f"Нотатки (з важливістю):\n{notes}\n\n" + "\n\n".join(f"Витяг:\n{e}" for e in extracts)
    return IMPORT_SYSTEM.format(max_chars=max_chars, limit=limit), contents


def parse_import(raw: str, max_chars: int, limit: int) -> list[tuple[str, int]] | None:
    data = _json(raw)
    if not isinstance(data, dict) or not isinstance(data.get("facts"), list):
        return None
    out, seen = [], set()
    for item in data["facts"]:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str) or item.get("pin", 2) not in (0, 1, 2):
            continue
        text = _norm(item["text"])
        if text and len(text) <= max_chars and text.casefold() not in seen:
            seen.add(text.casefold())
            out.append((text, int(item.get("pin", 2))))
    return out[:limit]


async def run_import(source: Path, folder: Path, llm, today: str, max_facts: int, max_chars: int,
                     dry_run: bool, out=sys.stdout) -> int:
    """Noos's facts and extracts → her facts, `source: noos`; once only — a store that holds any is left as it is.
    `--dry-run` prints what would be kept and writes nothing. The number written (or that would be)."""
    held = load_facts(folder)
    if any(f.source == "noos" for f in held):
        print(f"already imported: {sum(f.source == 'noos' for f in held)} facts from Noos — nothing done", file=out)
        return 0
    facts, extracts = read_noos(source)
    if not facts and not extracts:
        print("nothing to import", file=out)
        return 0
    limit = max(max_facts - len(held), 0)
    system, contents = import_request(facts, extracts, max_chars, limit)
    raw = await llm.generate(contents, system, max_output_tokens=8192, kind="facts")
    kept = parse_import(raw or "", max_chars, limit)
    if kept is None:
        print("the import failed: no valid answer", file=out)
        return 0
    written = 0
    for text, pin in kept:
        if dry_run:
            print(f"[pin {pin}] {text}", file=out)
            written += 1
        elif add_fact(folder, text, pin, "noos", today, max_facts, max_chars):
            written += 1
    print(f"{'would keep' if dry_run else 'kept'} {written} facts", file=out)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m agents.facts")
    sub = parser.add_subparsers(dest="cmd", required=True)
    imp = sub.add_parser("import", help="the one-shot import of Noos's facts")
    imp.add_argument("source", type=Path)
    imp.add_argument("--agent", default="kira")
    imp.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    from agents.llm import GeminiClient
    from agents.usage import usage_line
    from agents.world import local_now

    tz = os.environ.get("TIMEZONE", "Europe/Kyiv")
    state = Path("state")
    usage_file = state / f"{args.agent}.usage.jsonl"

    def sink(kind, model, meta, ok):  # the import's call is counted under the agent, like any other
        line = usage_line(local_now(int(time.time() * 1000), tz).isoformat(timespec="seconds"), args.agent, kind,
                          model, meta, ok)
        fd = os.open(usage_file, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, (json.dumps(line, ensure_ascii=False) + "\n").encode())
        finally:
            os.close(fd)

    import time
    today = local_now(int(time.time() * 1000), tz).date().isoformat()
    asyncio.run(run_import(args.source, state / f"{args.agent}.facts", GeminiClient(sink=sink), today,
                           int(os.environ.get("FACTS_MAX", "100")), int(os.environ.get("FACT_MAX_CHARS", "240")),
                           args.dry_run))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
