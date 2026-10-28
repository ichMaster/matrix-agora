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
        return self.db.execute("SELECT id, text FROM lines WHERE emb IS NULL ORDER BY id LIMIT ?", (limit,)).fetchall()

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

    def search_words(self, query: str, places: Iterable[str], limit: int = CANDIDATES) -> list[int]:
        """BM25 over FTS5 within `places`, the best first; no usable word → nothing."""
        match = words_query(query)
        places = tuple(places)
        if match is None or not places:
            return []
        marks = ",".join("?" * len(places))
        try:
            return [r[0] for r in self.db.execute(
                f"SELECT l.id FROM fts JOIN lines l ON l.id = fts.rowid WHERE fts MATCH ? AND l.place IN ({marks}) "
                "ORDER BY bm25(fts) LIMIT ?", (match, *places, limit))]
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
        rows = self.db.execute("SELECT id, place, emb FROM lines WHERE emb IS NOT NULL").fetchall()
        if rows:
            size = Counter(len(r[2]) for r in rows).most_common(1)[0][0]
            rows = [r for r in rows if len(r[2]) == size and size % 4 == 0]
        if not rows:
            return [], np.array([], dtype=object), np.zeros((0, 0), dtype="float32")
        matrix = _normalised(np.vstack([np.frombuffer(r[2], dtype="float32") for r in rows]))
        return [r[0] for r in rows], np.array([r[1] for r in rows], dtype=object), matrix

    def lines(self, ids: Iterable[int]) -> dict[int, Line]:
        ids = list(ids)
        if not ids:
            return {}
        rows = self.db.execute(f"SELECT id, key, ts_ms, place, channel, speaker, text FROM lines WHERE id IN "
                               f"({','.join('?' * len(ids))})", ids).fetchall()
        return {r[0]: Line(*r) for r in rows}

    def around(self, line: Line, n: int = 1) -> list[Line]:
        """The line with its `n` neighbours before and after, in its own place, oldest first."""
        cols = "id, key, ts_ms, place, channel, speaker, text"
        before = self.db.execute(f"SELECT {cols} FROM lines WHERE place = ? AND (ts_ms, id) < (?, ?) "
                                 "ORDER BY ts_ms DESC, id DESC LIMIT ?", (line.place, line.ts_ms, line.id, n)).fetchall()
        after = self.db.execute(f"SELECT {cols} FROM lines WHERE place = ? AND (ts_ms, id) > (?, ?) "
                                "ORDER BY ts_ms, id LIMIT ?", (line.place, line.ts_ms, line.id, n)).fetchall()
        return [Line(*r) for r in reversed(before)] + [line] + [Line(*r) for r in after]

    def sync_facts(self, facts: Iterable[tuple[str, str]], ts_ms: int) -> None:
        """The `facts` place mirrors her facts (id, text): few and edited often, so replaced whole each time they
        change (Noos's reindexing) — their embeddings follow on the next ticks."""
        self._cache = None  # their rows go: the vectors are read again at the next recall
        with self.db:
            for row_id, text in self.db.execute("SELECT id, text FROM lines WHERE place = 'facts'").fetchall():
                self.db.execute("INSERT INTO fts(fts, rowid, text) VALUES ('delete', ?, ?)", (row_id, text))
            self.db.execute("DELETE FROM lines WHERE place = 'facts'")
            for fact_id, text in facts:
                cur = self.db.execute(
                    "INSERT INTO lines(key, ts_ms, place, channel, speaker, text) VALUES (?,?,?,?,?,?)",
                    (f"fact:{fact_id}", int(ts_ms), "facts", "", "факт", text))
                self.db.execute("INSERT INTO fts(rowid, text) VALUES (?,?)", (cur.lastrowid, text))

    def latest(self, place: str, limit: int, since_ms: int | None = None) -> list[Line]:
        """The last `limit` lines of a place (from `since_ms` on), oldest first."""
        rows = self.db.execute(
            "SELECT id, key, ts_ms, place, channel, speaker, text FROM lines WHERE place = ? AND ts_ms >= ? "
            "ORDER BY ts_ms DESC, id DESC LIMIT ?", (place, since_ms or 0, limit)).fetchall()
        return [Line(*r) for r in reversed(rows)]
