"""Claude's folder in the panel (v4.7; the owner, 2026-10-11): list, read, download, upload, delete.

The folder is `claude-workspace` on the host — `/workspace` for Claude, `/claude-workspace` for the panel. Every
path from a request goes through `safe_path`: relative only, no `..`, no leading `/` or `~`, no NUL, no
surrounding whitespace, no hidden (`.`-prefixed) name, no symlink, and its `realpath` inside the folder. Reads are
capped (text ≤ 256 KB, a binary file is download-only), uploads ≤ 5 MB, and a replace needs `overwrite`. The log
names the action and the path, never a file's content.
"""

from __future__ import annotations

import contextlib
import logging
import os
import secrets
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger("panel.files")

MAX_READ = 256 * 1024
MAX_UPLOAD = 5 * 1024 * 1024
MAX_LIST = 2000


class FilesError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


def safe_path(root: Path, rel: str) -> Path:
    """The file `rel` names inside `root`, or a refusal (400) — the one gate for every request path."""
    if not isinstance(rel, str) or not rel or rel != rel.strip() or "\x00" in rel or "\\" in rel:
        raise FilesError(400, "not a path in the folder")
    if rel.startswith(("/", "~")):
        raise FilesError(400, "not a path in the folder")
    parts = rel.split("/")
    if any(p in ("", ".", "..") or p.startswith(".") for p in parts):
        raise FilesError(400, "not a path in the folder")
    base = Path(os.path.realpath(root))
    target = base.joinpath(*parts)
    walk = base
    for p in parts:  # no symlink anywhere on the way, even one that points inside
        walk = walk / p
        if walk.is_symlink():
            raise FilesError(400, "a link, not a file")
    real = Path(os.path.realpath(target))
    if real != base and base not in real.parents:
        raise FilesError(400, "not a path in the folder")
    return target


def list_files(root: Path) -> list[dict]:
    """Every regular file, recursive, newest first: relative path, size, modified (ISO, UTC). Hidden names and links
    are skipped."""
    base = Path(os.path.realpath(root))
    if not base.is_dir():
        return []
    out = []
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and not os.path.islink(os.path.join(dirpath, d))]
        for name in filenames:
            path = Path(dirpath) / name
            if name.startswith(".") or path.is_symlink() or not path.is_file():
                continue
            st = path.stat()
            out.append({"path": path.relative_to(base).as_posix(), "size": st.st_size,
                        "modified": datetime.fromtimestamp(st.st_mtime, UTC).isoformat(timespec="seconds")})
    # newest first over everything, then the cap (v4.7 review #7: the old break left the outer walk running)
    return sorted(out, key=lambda f: f["modified"], reverse=True)[:MAX_LIST]


def read_text(root: Path, rel: str) -> dict:
    path = safe_path(root, rel)
    if not path.is_file():
        raise FilesError(404, "no such file")
    size = path.stat().st_size
    if size > MAX_READ:
        raise FilesError(413, "too large to show — download it")
    try:
        text = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        raise FilesError(415, "not text — download it") from None
    return {"path": rel, "size": size, "text": text}


def file_for_download(root: Path, rel: str) -> Path:
    path = safe_path(root, rel)
    if not path.is_file():
        raise FilesError(404, "no such file")
    return path


def write_file(root: Path, rel: str, data: bytes, overwrite: bool) -> dict:
    path = safe_path(root, rel)
    if len(data) > MAX_UPLOAD:
        raise FilesError(413, "larger than 5 MB")
    if path.is_dir():
        raise FilesError(409, "a folder has this name")
    existed = path.exists()
    if existed and not overwrite:
        raise FilesError(409, "exists — replace it?")
    tmp = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        safe_path(root, rel)  # the folders just made are real folders inside — check again before writing
        # a short hidden name (never listed): a long file name stays under the name limit (v4.7 review #6)
        tmp = path.parent / f".upload-{secrets.token_hex(6)}"
        tmp.write_bytes(data)
        os.replace(tmp, path)
        tmp = None
    except OSError as exc:
        raise FilesError(400, f"cannot write it ({type(exc).__name__})") from None
    finally:
        if tmp is not None:
            with contextlib.suppress(OSError):
                tmp.unlink()
    log.info("files: %s %s (%d bytes)", "replaced" if existed else "uploaded", rel, len(data))
    return {"path": rel, "size": len(data), "replaced": existed}


def delete_file(root: Path, rel: str) -> dict:
    path = safe_path(root, rel)
    if not path.is_file():
        raise FilesError(404, "no such file")
    path.unlink()
    log.info("files: deleted %s", rel)
    return {"path": rel, "deleted": True}
