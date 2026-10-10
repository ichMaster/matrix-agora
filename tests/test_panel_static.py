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


def test_the_page_follows_capabilities():
    """v4.1: tabs, the today field, the summary wording and the busy label need their capability; `it` is a
    pronoun; with every capability on (Ada, Bruno) the page is unchanged."""
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    assert 'const TAB_CAP = {session: "summary", memory: "chronicle", plans: "plans", today: "today", mood: "mood"};' in js
    assert 'PRONOUN = {she: "She", he: "He", it: "It"}' in js
    assert "agentTabs(a)" in js and 'dr.tab = "log"' in js
    assert 'can(a, "today") ?' in js                                   # the card's Today field
    assert 'summary ? `${subject} will write a session summary' in js    # stop wording
    assert 'Boolean(agent) && can(agent, "summary")' in js               # "writing summary" busy label
    assert "Forget last session" in js and 'session: "summary"' in js   # Forget lives in the session tab



def test_the_mood_tab_and_the_n_agent_chart():
    """v4.2: a `mood` agent gets the Mood tab and a mood line on its card; the token chart stacks every agent."""
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    css = (STATIC_DIR / "panel.css").read_text(encoding="utf-8")
    assert '["mood", "Mood"]' in js and 'mood: "mood"' in js and "moodTabHtml(mem)" in js
    assert 'can(a, "mood") ?' in js and "Mood of the day" in js
    assert 'const SERIES = ["a", "b", "c", "d", "e"]' in js and "agents.slice(0, 2)" not in js and "names[1]" not in js
    assert ".bars .c" in css and ".legend .e" in css


def test_the_full_reading_stays_open_across_re_renders():
    """Review #10: every poll re-renders the drawer, and the Mood tab's <details> folded shut each time."""
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    assert "openDetails: {}" in js
    assert 'data-keep="mood:${esc(mem.mood.date)}" ${S.openDetails[`mood:${mem.mood.date}`] ? "open" : ""}' in js
    assert 'document.addEventListener("toggle"' in js and "S.openDetails[key] = e.target.open" in js


def test_the_creature_card_shows_his_past_life_line():
    """v4.3: «93 theses · last nudge 14:05 · 2 today» on the card and the Mood tab — only with the capabilities."""
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    assert 'can(a, "pastlife") || can(a, "nudge") ? `<div class="muted" style="font-size:12px">${pastLifeLine(mem)}' in js
    assert "function pastLifeLine(mem)" in js and "${past}<div class=\"meta-line\">" in js
    assert 'return esc(parts.join(" · "));' in js


def test_another_days_nudge_shows_its_date():
    """v4.3 review #10: «last nudge 21:40 · 0 today» three days later read as today's."""
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    assert 'last.toDateString() !== new Date().toDateString()' in js
    assert '`${last.toLocaleDateString("en-US", {month: "short", day: "numeric"})}, ${time}`' in js


def test_claudes_card_and_the_billing_column():
    """v4.4: the subscription lines on Claude's card; the token table shows billing and never formats a missing
    cost (a subscription row has none)."""
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    assert '${a.engine === "claude-sdk" ? `<div style="display:flex;flex-direction:column;gap:3px"><div class="label">Subscription</div>${claudeLines(mem)}' in js
    assert "function claudeLines(mem)" in js and "OAuth ✓ (no API key)" in js
    assert '(muted && r.status === "rejected") ? "err" : muted ? "warn" : r.status ? "ok" : "unknown"' in js
    assert "<th>billing</th>" in js and 'r.cost == null ? "—" : r.cost.toFixed(4)' in js
    assert "r.cost.toFixed(4)}</td>` : \"\"}</tr>`;" not in js.replace('r.cost == null ? "—" : r.cost.toFixed(4)', "")
