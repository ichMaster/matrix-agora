"""v4.7 (the owner, 2026-10-11): Claude's folder in the panel — list, read, download, upload, delete — and nothing
outside it."""
import os

import pytest
from fastapi.testclient import TestClient

from panel.app import create_app
from panel.files import MAX_UPLOAD, FilesError, safe_path
from panel.health import Prober
from panel.registry import Registry
from tests.test_panel_actions import AUTH, TOKEN, make


@pytest.fixture
def box(tmp_path):
    folder = tmp_path / "claude-workspace"
    folder.mkdir()
    (folder / "notes").mkdir()
    (folder / "notes" / "day.md").write_text("Нотатка дня", encoding="utf-8")
    (folder / "blob.bin").write_bytes(b"\xff\xfe\x00\x01")
    (folder / ".hidden").write_text("x", encoding="utf-8")
    outside = tmp_path / "state"
    outside.mkdir()
    (outside / "ada.json").write_text('{"access_token": "secret"}', encoding="utf-8")
    os.symlink(outside, folder / "escape")
    os.symlink(outside / "ada.json", folder / "notes" / "token.json")
    sup, *_ = make()
    reg = Registry()
    client = TestClient(create_app(token=TOKEN, registry=reg, docker_reader=sup.reader, prober=Prober(reg),
                                   state_dir=outside, background=False, supervisor=sup, files_dir=folder))
    return client, folder


def test_the_list_shows_his_files_and_skips_hidden_and_links(box):
    client, _ = box
    files = client.get("/api/agents/claude/files", headers=AUTH).json()["files"]
    assert {f["path"] for f in files} == {"notes/day.md", "blob.bin"}
    assert all({"path", "size", "modified"} <= set(f) for f in files)


def test_read_a_text_file_download_any_and_a_binary_is_download_only(box):
    client, _ = box
    assert client.get("/api/agents/claude/files/notes/day.md", headers=AUTH).json()["text"] == "Нотатка дня"
    assert client.get("/api/agents/claude/files/blob.bin", headers=AUTH).status_code == 415
    r = client.get("/api/agents/claude/files/blob.bin?download=1", headers=AUTH)
    assert r.status_code == 200 and r.content == b"\xff\xfe\x00\x01" and "attachment" in r.headers["content-disposition"]


def test_upload_needs_overwrite_to_replace_creates_folders_and_is_capped(box):
    client, folder = box
    assert client.put("/api/agents/claude/files/for-claude/brief.txt", headers=AUTH, content=b"read me").json() == \
        {"path": "for-claude/brief.txt", "size": 7, "replaced": False}
    assert (folder / "for-claude" / "brief.txt").read_bytes() == b"read me"
    assert client.put("/api/agents/claude/files/for-claude/brief.txt", headers=AUTH, content=b"v2").status_code == 409
    assert client.put("/api/agents/claude/files/for-claude/brief.txt?overwrite=1", headers=AUTH,
                      content=b"v2").json()["replaced"] is True
    assert client.put("/api/agents/claude/files/big.bin", headers=AUTH,
                      content=b"x" * (MAX_UPLOAD + 1)).status_code == 413
    assert not (folder / "big.bin").exists()


def test_delete_a_file(box):
    client, folder = box
    assert client.delete("/api/agents/claude/files/notes/day.md", headers=AUTH).json()["deleted"] is True
    assert not (folder / "notes" / "day.md").exists()
    assert client.delete("/api/agents/claude/files/notes/day.md", headers=AUTH).status_code == 404


@pytest.mark.parametrize("path", ["../state/ada.json", "notes/../../state/ada.json", "escape/ada.json",
                                  "notes/token.json", ".hidden", "notes/.x", "~/x", " notes/day.md"])
def test_nothing_outside_his_folder_is_reached(box, path):
    client, folder = box
    url = f"/api/agents/claude/files/{path}"
    for r in (client.get(url, headers=AUTH), client.get(url + "?download=1", headers=AUTH),
              client.put(url, headers=AUTH, content=b"x"), client.delete(url, headers=AUTH)):
        assert r.status_code in (400, 404, 405), (path, r.status_code)  # 405: «..» normalized onto another route
        assert "secret" not in r.text
    assert (folder.parent / "state" / "ada.json").read_text(encoding="utf-8") == '{"access_token": "secret"}'


def test_the_guard_itself(tmp_path):
    for bad in ("", "/etc/passwd", "a//b", "a\\\\b", "a\x00b", "..", "a/./b"):
        with pytest.raises(FilesError):
            safe_path(tmp_path, bad)
    assert safe_path(tmp_path, "a/b.md") == tmp_path.resolve() / "a" / "b.md"


def test_only_claude_has_a_folder_and_the_token_is_needed(box):
    client, _ = box
    assert client.get("/api/agents/ada/files", headers=AUTH).status_code == 404
    assert client.get("/api/agents/kit/files/notes/day.md", headers=AUTH).status_code == 404
    assert client.get("/api/agents/claude/files").status_code == 401
    assert client.put("/api/agents/claude/files/x.md", content=b"x").status_code == 401
    r = client.delete("/api/agents/claude/files/notes/day.md", headers={**AUTH, "origin": "http://evil.example"})
    assert r.status_code == 403
