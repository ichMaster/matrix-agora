"""The page (v3.3): served without the token, holds no data, makes no outside request."""

import re
from pathlib import Path

from fastapi.testclient import TestClient

from panel.app import STATIC_DIR, create_app

TOKEN = "t" * 32
FILES = ["index.html", "app.js", "icons.js", "panel.css"]


def client():
    return TestClient(create_app(token=TOKEN, background=False))


def test_the_page_and_its_assets_are_served_without_the_token():
    c = client()
    page = c.get("/")
    assert page.status_code == 200 and "<title>Agora · panel</title>" in page.text
    for name in FILES:
        assert c.get(f"/{name}").status_code == 200, name
    assert c.get("/api/health").status_code == 401  # the data stays gated


def test_no_outside_requests_and_a_strict_policy():
    for name in FILES:
        # the SVG namespace is an identifier, never fetched
        text = (STATIC_DIR / name).read_text(encoding="utf-8").replace("http://www.w3.org/2000/svg", "")
        assert not re.search(r"https?://|//cdn|@import|googleapis|unpkg", text), name
    csp = client().get("/").headers["content-security-policy"]
    assert "default-src 'self'" in csp and "script-src 'self'" in csp and "connect-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp


def test_the_script_talks_only_to_the_panel_api():
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    targets = re.findall(r"\b(?:api|post)\(\s*[`\"']([^`\"']+)", js)
    assert targets and all(t.startswith("/api/") for t in targets)
    assert js.count("fetch(") == 2  # api() reads, post() acts — both always with the token
    assert js.count("Authorization: `Bearer ${S.token}`") == 2


def test_no_secret_is_baked_into_the_page():
    for name in ("index.html", "app.js", "panel.css"):  # icons.js is only SVG path data
        text = (STATIC_DIR / name).read_text(encoding="utf-8")
        assert "PANEL_TOKEN" not in text and not re.search(r"[A-Za-z0-9_-]{32,}", text), name


def test_the_only_state_change_is_post_and_the_dialogs_say_what_happens():
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    assert js.count('method: "POST"') == 1 and "async function post(path)" in js  # one helper changes state
    assert not re.search(r"method:\s*[\"'](PUT|DELETE|PATCH)", js)
    for text in ("will write a session summary — up to 30 seconds.", "The current session will end with a summary.",
                 "The summary will be deleted; day memories stay. Stopped agents only.",
                 "Agents will keep reconnecting until it is back.", "Agents will reconnect briefly.",
                 "Creates the container and starts it", "creating container…", "v3.4 · control"):
        assert text in js, text
    assert 'if (action === "start") perform(' in js  # start runs without a confirmation; the rest ask first


def test_static_files_are_the_handoff_stylesheet_plus_additions():
    css = (STATIC_DIR / "panel.css").read_text(encoding="utf-8")
    handoff = Path("specification/design/design_handoff_agora_panel/agora-panel.css").read_text(encoding="utf-8")
    assert css.startswith(handoff)
