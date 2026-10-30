"""v5.8 — the archive: every line a person with `recall` sees, searchable by words and by meaning (ROADMAP §v5.8,
ARCHITECTURE §Memory).

Modelled on Noos's `memory/sessions.db` (`~/claude-home`): SQLite with an FTS5 index over the text (BM25) and, per
line, an embedding (here Gemini's `gemini-embedding-001`, added later in batches by the idle watcher); a recall merges
the two ranked lists by reciprocal rank fusion, so both a literal match and a paraphrase are found.

`state/<name>.archive.db` holds texts, so it is created 0600, stays in `state/`, and is read by no other agent. It is
append-only and never pruned; a line's `key` (the Matrix event id, `tg:<update_id>`, or the agent's own) makes a
second append of it a no-op. The fusion and the pick are pure; only the class touches the file.
"""

from __future__ import annotations

import os
import re
import sqlite3
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

from agents.world import ago, local_now

# facts (v5.8, `facts`): searchable by a private recall only; v5.12 (`thoughts`): her thoughts — `thought` (on what
# she read, on Agora) recalled anywhere, `thought_private` (on the private chat) alone with the owner only
PLACES = ("agora", "private", "facts", "thought", "thought_private")
THOUGHT_PLACES = ("thought", "thought_private")
RRF_K = 60       # Noos's reciprocal rank fusion constant
CANDIDATES = 50  # each ranked list's length before the fusion
_WORD_RE = re.compile(r"\w+", re.UNICODE)
LINE_MAX_CHARS = 400  # a recalled line is cut here: the gist, not a long news item in full
PLACE_LABEL = {"agora": "в Агорі", "private": "наодинці"}
# the prompt sections (ARCHITECTURE §Prompt assembly) — her memory, never told as what is said now
RECALL_TITLE = "Тобі згадується з давніших розмов (це пам'ять, а не те, що кажуть зараз):"
RECALL_TITLE_THOUGHTS = "Тобі згадується з давніших розмов і твоїх думок (це пам'ять, а не те, що кажуть зараз):"
AGORA_NOW_TITLE = "Що сьогодні говорять в Агорі:"
# v5.13 — a line's mark: `gemini` (passed through Gemini, clean by default — every line before v5.13), v5.14
# `waiting` (a line of the backup's talk, or one a block or a refusal answered: closed to Gemini until v5.15's judge
# rates it) and `censored` (the judge's verdict, for good); v5.15 adds `clean` (the judge rated it clean: Gemini's
# again, embedded at the next tick) and `reopened` (the owner's live test, 2026-10-30: a line of the backup's talk the
# judge rated clean — open to Gemini until a Gemini block on a prompt that holds it censors it; Gemma does not predict
# Gemini's prohibited-content filter). Gemini's readers never return a line whose mark is in `GEMINI_CLOSED`, and it is
# never embedded; the backup's readers (`gemini=False`) return every one. `/purge` deletes `BACKUP_MARKS`.
MARKS = ("gemini", "waiting", "censored", "clean", "reopened")
GEMINI_CLOSED = ("censored", "waiting")
BACKUP_MARKS = ("waiting", "censored", "reopened")  # the backup's talk, whatever the judge said
_OPEN = f"mark NOT IN ({','.join(repr(m) for m in GEMINI_CLOSED)})"
_COLS = "id, key, ts_ms, place, channel, speaker, text, mark"
SCHEMA_VERSION = 1  # v5.14: v5.13's `censored` lines (Gemini's verdict alone) became `waiting` once (review #3)


def _open_to(gemini: bool, alias: str = "") -> str:
    """The SQL condition on a line's mark for a reader: Gemini's skips the closed ones, the backup's reads all."""
    return f"{alias}{_OPEN}" if gemini else "1 = 1"

SCHEMA = """
CREATE TABLE IF NOT EXISTS lines (
    id INTEGER PRIMARY KEY, key TEXT UNIQUE NOT NULL, ts_ms INTEGER NOT NULL, place TEXT NOT NULL,
    channel TEXT NOT NULL, speaker TEXT NOT NULL, text TEXT NOT NULL, emb BLOB);
CREATE INDEX IF NOT EXISTS lines_place_ts ON lines (place, ts_ms);
CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(text, content='lines', content_rowid='id', tokenize='unicode61');
"""


@dataclass(frozen=True)
class Line:
    id: int
    key: str
    ts_ms: int
    place: str
    channel: str
    speaker: str
    text: str
    mark: str = "gemini"  # v5.13


def words_query(text: str) -> str | None:
    """An FTS5 query from free text: its words longer than 2 characters, each quoted, joined with OR (Noos's);
    None when no word is left."""
    words = [w for w in _WORD_RE.findall(text or "") if len(w) > 2]
    return " OR ".join(f'"{w}"' for w in dict.fromkeys(words)) or None


def fuse(*ranked: list[int], k: int = RRF_K) -> list[int]:
    """Reciprocal rank fusion: every list adds 1 / (k + rank) to its ids; the best first (ties by first seen)."""
    score: dict[int, float] = {}
    for ids in ranked:
        for rank, i in enumerate(ids):
            score[i] = score.get(i, 0.0) + 1.0 / (k + rank)
    return sorted(score, key=lambda i: -score[i])


def _normalised(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.where(norms == 0, 1.0, norms)


def cosine_top(query: list[float] | np.ndarray, ids: list[int], matrix: np.ndarray | None, n: int = CANDIDATES) -> list[int]:
    """The `n` ids whose vectors are closest to the query's by cosine."""
    if matrix is None or not ids:
        return []
    q = np.asarray(query, dtype="float32")
    sims = matrix @ q / (np.linalg.norm(matrix, axis=1) * np.linalg.norm(q) + 1e-9)
    return [ids[j] for j in np.argsort(-sims)[:n]]


def pick_recall(ranked: list[int], lines: dict[int, Line], exclude: set[tuple[str, str]], n: int) -> list[Line]:
    """The best `n` lines not already in the prompt's history window (`exclude`: its (speaker, text) pairs)."""
    out = []
    for i in ranked:
        line = lines.get(i)
        if line is None or (line.speaker, line.text) in exclude:
            continue
        out.append(line)
        if len(out) >= n:
            break
    return out


def _cut(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= LINE_MAX_CHARS else text[:LINE_MAX_CHARS - 1].rstrip() + "…"


def render_recalled(groups: list[list[Line]], tz, now: datetime) -> str | None:
    """The recall section: each recalled line with its neighbours, a group a paragraph, oldest first, each line
    with when it was, as a person remembers it, and its place («минулого тижня, в Агорі — Ада: …»; never a date —
    the owner, 2026-10-26); a fact as what she knows; v5.12: a thought as hers, «вчора я думала: …» — never said."""
    out, thought = [], False
    for group in groups:
        rows = []
        for line in group:
            if line.place == "facts":
                rows.append(f"(те, що ти знаєш про Ich) {_cut(line.text)}")
                continue
            when = ago(local_now(line.ts_ms, tz), now)
            if line.place in THOUGHT_PLACES:
                rows.append(f"{when} я думала: {_cut(line.text)}")
                thought = True
                continue
            rows.append(f"{when}, {PLACE_LABEL.get(line.place, line.place)} — {line.speaker}: {_cut(line.text)}")
        if rows:
            out.append("\n".join(rows))
    return (RECALL_TITLE_THOUGHTS if thought else RECALL_TITLE) + "\n" + "\n\n".join(out) if out else None


def render_agora_now(lines: list[Line], tz) -> str | None:
    """Agora's latest lines of today, for the private chat: «14:05 Ада: …»."""
    if not lines:
        return None
    rows = [f"{local_now(line.ts_ms, tz):%H:%M} {line.speaker}: {_cut(line.text)}" for line in lines]
    return AGORA_NOW_TITLE + "\n" + "\n".join(rows)


class Archive:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():  # private from birth: the owner's words are inside
            os.close(os.open(path, os.O_WRONLY | os.O_CREAT, 0o600))
        os.chmod(path, 0o600)
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)
        if "mark" not in {r[1] for r in self.db.execute("PRAGMA table_info(lines)")}:  # v5.13: migrated in place
            with self.db:
                self.db.execute("ALTER TABLE lines ADD COLUMN mark TEXT NOT NULL DEFAULT 'gemini'")
        if self.db.execute("PRAGMA user_version").fetchone()[0] < SCHEMA_VERSION:  # v5.14, once (v5.13 review #3)
            with self.db:
                self.db.execute("UPDATE lines SET mark = 'waiting' WHERE mark = 'censored'")
                self.db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        # v5.8 review #5: the embedded vectors, read once and kept normalised in memory — (ids, places, matrix) —
        # appended as lines are embedded; a recall never reads them all from the file again
        self._cache: tuple[list[int], np.ndarray, np.ndarray] | None = None

    def close(self) -> None:
        self.db.close()

    def append(self, key: str, ts_ms: int, place: str, channel: str, speaker: str, text: str) -> bool:
        """A line once: False for an empty text or a key already held."""
        if not text or not text.strip() or place not in PLACES:
            return False
        try:
            with self.db:
                cur = self.db.execute(
                    "INSERT INTO lines(key, ts_ms, place, channel, speaker, text) VALUES (?,?,?,?,?,?)",
                    (key, int(ts_ms), place, channel, speaker, text))
                self.db.execute("INSERT INTO fts(rowid, text) VALUES (?,?)", (cur.lastrowid, text))
        except sqlite3.IntegrityError:
            return False
        return True

    def counts(self) -> tuple[int, int]:
        """(lines, embedded)."""
        lines, embedded = self.db.execute("SELECT COUNT(*), COUNT(emb) FROM lines").fetchone()
        return int(lines), int(embedded)

    def unembedded(self, limit: int) -> list[tuple[int, str]]:
        return self.db.execute(f"SELECT id, text FROM lines WHERE emb IS NULL AND {_OPEN} ORDER BY id LIMIT ?",
                               (limit,)).fetchall()

    def mark(self, keys: Iterable[str], mark: str) -> int:
        """v5.14 — set these lines' mark; a mark closed to Gemini drops their vectors (they are never embedded again).
        How many."""
        keys = [k for k in keys if k]
        if not keys or mark not in MARKS:
            return 0
        closed = mark in GEMINI_CLOSED
        with self.db:
            cur = self.db.execute(f"UPDATE lines SET mark = ?{', emb = NULL' if closed else ''} WHERE key IN "
                                  f"({','.join('?' * len(keys))})", (mark, *keys))
        if closed:
            self._cache = None  # their vectors leave the matrix: read again at the next recall
        return cur.rowcount

    def unrated(self, place: str, limit: int) -> list[Line]:
        """v5.15 — the oldest `waiting` lines of a place, for the judge: the backup's talk not rated yet."""
        rows = self.db.execute(f"SELECT {_COLS} FROM lines WHERE place = ? AND mark = 'waiting' ORDER BY ts_ms, id "
                               "LIMIT ?", (place, max(int(limit), 0))).fetchall()
        return [Line(*r) for r in rows]

    def by_keys(self, keys: Iterable[str]) -> list[Line]:
        """v5.15 — these lines by key, every mark (the judge reads a blocked prompt's lines by them)."""
        keys = list(keys)
        if not keys:
            return []
        rows = self.db.execute(f"SELECT {_COLS} FROM lines WHERE key IN ({','.join('?' * len(keys))})",
                               keys).fetchall()
        return [Line(*r) for r in rows]

    def mark_counts(self, place: str) -> dict[str, int]:
        """v5.14 — how many lines of a place carry each mark."""
        return dict(self.db.execute("SELECT mark, COUNT(*) FROM lines WHERE place = ? GROUP BY mark", (place,)))

    def closed_count(self, place: str = "private") -> int:
        """v5.14 — how many lines of a place are the backup's talk (`BACKUP_MARKS`; v5.15 `reopened` too)."""
        marks = ",".join("?" * len(BACKUP_MARKS))
        return self.db.execute(f"SELECT COUNT(*) FROM lines WHERE place = ? AND mark IN ({marks})",
                               (place, *BACKUP_MARKS)).fetchone()[0]

    def purge_closed(self, place: str = "private") -> list[tuple[str, str]]:
        """v5.14, the owner's `/purge` — delete every line of a place that is the backup's talk (`BACKUP_MARKS`: what
        Gemini blocked or refused, what went through the backup, rated or not), with its word index: the one exception
        to «nothing lived is deleted». The (speaker, text) of the lines deleted, for her history."""
        marks = ",".join("?" * len(BACKUP_MARKS))
        with self.db:
            rows = self.db.execute(f"SELECT id, speaker, text FROM lines WHERE place = ? AND mark IN ({marks})",
                                   (place, *BACKUP_MARKS)).fetchall()
            for row_id, _, text in rows:
                self.db.execute("INSERT INTO fts(fts, rowid, text) VALUES ('delete', ?, ?)", (row_id, text))
            self.db.execute(f"DELETE FROM lines WHERE place = ? AND mark IN ({marks})", (place, *BACKUP_MARKS))
        self._cache = None
        return [(speaker, text) for _, speaker, text in rows]

    def censor(self, keys: Iterable[str]) -> int:
        """v5.13 — mark these lines `censored`: Gemini never reads them again. How many."""
        return self.mark(keys, "censored")

    def set_embeddings(self, pairs: Iterable[tuple[int, list[float]]]) -> None:
        pairs = [(i, np.asarray(v, dtype="float32")) for i, v in pairs]
        with self.db:
            self.db.executemany("UPDATE lines SET emb = ? WHERE id = ?", [(v.tobytes(), i) for i, v in pairs])
        if self._cache is None or not pairs:
            return
        ids, places, matrix = self._cache
        if any(v.shape[0] != matrix.shape[1] for _, v in pairs) and matrix.shape[0]:
            self._cache = None  # another length: the next recall reads the file again and keeps the common one
            return
        known = {i: n for n, i in enumerate(ids)}
        new = [(i, v) for i, v in pairs if i not in known]
        if any(i in known for i, _ in pairs):
            self._cache = None  # a vector replaced: read again
            return
        place_of = dict(self.db.execute(f"SELECT id, place FROM lines WHERE id IN ({','.join('?' * len(new))})",
                                        [i for i, _ in new]).fetchall()) if new else {}
        rows = [(i, v) for i, v in new if i in place_of]
        if not rows:
            return
        added = _normalised(np.vstack([v for _, v in rows]))
        self._cache = (ids + [i for i, _ in rows],
                       np.concatenate([places, np.array([place_of[i] for i, _ in rows], dtype=object)]),
                       added if not matrix.shape[0] else np.vstack([matrix, added]))

    def search_words(self, query: str, places: Iterable[str], limit: int = CANDIDATES,
                     gemini: bool = True) -> list[int]:
        """BM25 over FTS5 within `places`, the best first; no usable word → nothing. `gemini=False` (v5.14, the
        backup) reads the closed lines too."""
        match = words_query(query)
        places = tuple(places)
        if match is None or not places:
            return []
        marks = ",".join("?" * len(places))
        try:
            return [r[0] for r in self.db.execute(
                f"SELECT l.id FROM fts JOIN lines l ON l.id = fts.rowid WHERE fts MATCH ? AND l.place IN ({marks}) "
                f"AND {_open_to(gemini, 'l.')} ORDER BY bm25(fts) LIMIT ?", (match, *places, limit))]
        except sqlite3.OperationalError:
            return []

    def vectors(self, places: Iterable[str]) -> tuple[list[int], np.ndarray | None]:
        """The embedded lines of `places`: their ids and their vectors (normalised) as one matrix — only the vectors
        of the most common length, so one of another size never disables the search (v5.8 review #10). Read from the
        file once, then kept in memory (v5.8 review #5)."""
        places = tuple(places)
        if not places:
            return [], None
        if self._cache is None:
            self._cache = self._load_vectors()
        ids, where, matrix = self._cache
        if not ids:
            return [], None
        mask = np.isin(where, places)
        if not mask.any():
            return [], None
        return [i for i, keep in zip(ids, mask, strict=True) if keep], matrix[mask]

    def _load_vectors(self) -> tuple[list[int], np.ndarray, np.ndarray]:
        rows = self.db.execute(f"SELECT id, place, emb FROM lines WHERE emb IS NOT NULL AND {_OPEN}").fetchall()
        if rows:
            size = Counter(len(r[2]) for r in rows).most_common(1)[0][0]
            rows = [r for r in rows if len(r[2]) == size and size % 4 == 0]
        if not rows:
            return [], np.array([], dtype=object), np.zeros((0, 0), dtype="float32")
        matrix = _normalised(np.vstack([np.frombuffer(r[2], dtype="float32") for r in rows]))
        return [r[0] for r in rows], np.array([r[1] for r in rows], dtype=object), matrix

    def lines(self, ids: Iterable[int], gemini: bool = True) -> dict[int, Line]:
        ids = list(ids)
        if not ids:
            return {}
        rows = self.db.execute(f"SELECT {_COLS} FROM lines WHERE id IN "
                               f"({','.join('?' * len(ids))}) AND {_open_to(gemini)}", ids).fetchall()
        return {r[0]: Line(*r) for r in rows}

    def around(self, line: Line, n: int = 1, gemini: bool = True) -> list[Line]:
        """The line with its `n` neighbours before and after, in its own place, oldest first."""
        where = _open_to(gemini)
        before = self.db.execute(f"SELECT {_COLS} FROM lines WHERE place = ? AND (ts_ms, id) < (?, ?) AND {where} "
                                 "ORDER BY ts_ms DESC, id DESC LIMIT ?", (line.place, line.ts_ms, line.id, n)).fetchall()
        after = self.db.execute(f"SELECT {_COLS} FROM lines WHERE place = ? AND (ts_ms, id) > (?, ?) AND {where} "
                                "ORDER BY ts_ms, id LIMIT ?", (line.place, line.ts_ms, line.id, n)).fetchall()
        return [Line(*r) for r in reversed(before)] + [line] + [Line(*r) for r in after]

    def sync_facts(self, facts: Iterable[tuple], ts_ms: int) -> None:
        """The `facts` place mirrors her facts (id, text[, mark] — v5.14): few and edited often, so replaced whole each
        time they change (Noos's reindexing) — their embeddings follow on the next ticks (an open fact's only)."""
        self._cache = None  # their rows go: the vectors are read again at the next recall
        with self.db:
            for row_id, text in self.db.execute("SELECT id, text FROM lines WHERE place = 'facts'").fetchall():
                self.db.execute("INSERT INTO fts(fts, rowid, text) VALUES ('delete', ?, ?)", (row_id, text))
            self.db.execute("DELETE FROM lines WHERE place = 'facts'")
            for fact_id, text, *rest in facts:
                mark = rest[0] if rest and rest[0] in MARKS else "gemini"
                cur = self.db.execute(
                    "INSERT INTO lines(key, ts_ms, place, channel, speaker, text, mark) VALUES (?,?,?,?,?,?,?)",
                    (f"fact:{fact_id}", int(ts_ms), "facts", "", "факт", text, mark))
                self.db.execute("INSERT INTO fts(rowid, text) VALUES (?,?)", (cur.lastrowid, text))

    def latest(self, place: str, limit: int, since_ms: int | None = None, gemini: bool = True) -> list[Line]:
        """The last `limit` lines of a place (from `since_ms` on), oldest first; for Gemini never a closed one (v5.13),
        for the backup (`gemini=False`, v5.14) every one, each with its mark."""
        rows = self.db.execute(
            f"SELECT {_COLS} FROM lines WHERE place = ? AND ts_ms >= ? "
            f"AND {_open_to(gemini)} ORDER BY ts_ms DESC, id DESC LIMIT ?", (place, since_ms or 0, limit)).fetchall()
        return [Line(*r) for r in reversed(rows)]
