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
    targets = re.findall(r"\b(?:api|post|put)\(\s*[`\"']([^`\"']+)", js)
    targets += re.findall(r"\bsend\(\"\w+\",\s*[`\"']([^`\"']+)", js)
    assert targets and all(t.startswith("/api/") for t in targets)
    assert js.count("fetch(") == 2  # api() reads, send() changes (v4.7: POST / PUT / DELETE) — both with the token
    assert js.count("Authorization: `Bearer ${S.token}`") == 2


def test_no_secret_is_baked_into_the_page():
    for name in ("index.html", "app.js", "panel.css"):  # icons.js is only SVG path data
        text = (STATIC_DIR / name).read_text(encoding="utf-8")
        assert "PANEL_TOKEN" not in text and not re.search(r"[A-Za-z0-9_-]{32,}", text), name


def test_the_only_state_change_is_post_and_the_dialogs_say_what_happens():
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    assert "async function send(method, path, payload, raw = false)" in js  # one helper changes state (v4.7)
    assert set(re.findall(r'send\("(\w+)"', js)) <= {"POST", "PUT", "DELETE"} and "PATCH" not in js
    assert 'const post = (path) => send("POST", path);' in js
    for text in ("will write a session summary — up to 30 seconds.", "The current session will end with a summary.",
                 "The summary will be deleted; day memories stay. Stopped agents only.",
                 "Agents will keep reconnecting until it is back.", "Agents will reconnect briefly.",
                 "Creates the container and starts it", "creating container…", "v4.7 · settings"):
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
    assert ('const TAB_CAP = {session: "summary", memory: "chronicle", plans: "plans", today: "today", mood: "mood", '
            'facts: "facts",\n                 voice: "voice", events: "events", thoughts: "thoughts"};') in js
    # v5.8 Facts, v5.9 Voice, v5.11 Events, v5.12 Thoughts need their capability
    assert 'rel="noopener noreferrer"' in js and "eventsTabHtml(a, mem)" in js
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


def test_a_person_with_a_mood_shows_it_under_today_with_the_weather():
    """v5.10: «Mood of the day» shows for every agent with `mood` — Кіра has «Today» too — and the Lviv weather beneath
    it on the card and in the Mood tab."""
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    assert '${can(a, "mood") ? `<div style="display:flex;flex-direction:column;gap:3px"><div class="label">Mood of the day</div>${moodLine(mem)}${weatherLine(mem)}</div>` : ""}' in js
    assert '!can(a, "today") && can(a, "mood")' not in js
    assert "function weatherLine(mem)" in js and "esc(mem.weather.line)" in js
    assert 'const weather = mem.weather ?' in js and "${esc(mem.mood.date)}</div>${weather}" in js


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
    assert '|| r.last_error || (muted && r.status === "rejected") ? "err"' in js and "last call failed:" in js
    assert "<th>billing</th>" in js and 'r.cost == null ? "—" : r.cost.toFixed(4)' in js
    assert "r.cost.toFixed(4)}</td>` : \"\"}</tr>`;" not in js.replace('r.cost == null ? "—" : r.cost.toFixed(4)', "")


def test_claudes_card_shows_his_news():
    """v4.5: the last news he brought (dated when not today) and today's count; nothing when `news` is null."""
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    assert "const n = mem.news, nAt = n?.last ? new Date(n.last) : null;" in js
    assert "`no news yet · ${Number(n.today)} today`" in js
    assert '${news ? `<div class="muted" style="font-size:12px">${esc(news)}</div>` : ""}' in js



def test_a_subscription_cost_is_never_shown_as_zero():
    """v4.4 review #13: the Tokens tab summed `r.cost || 0` and printed 0.0000 for Claude's rows, and a missing cost
    left a dangling « · »."""
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    assert "r.cost || 0" not in js and "if (r.cost != null) k.cost = (k.cost ?? 0) + r.cost;" in js
    assert 'byKind[k].cost == null ? "—" : byKind[k].cost.toFixed(4)' in js
    assert "const costSuffix = (n) => n == null ? \"\" : ` · ${fmtUsd(n)}`;" in js
    assert "` · ${fmtUsd(" not in js.replace("const costSuffix = (n) => n == null ? \"\" : ` · ${fmtUsd(n)}`;", "")


def test_the_settings_drawer_confirms_a_save_and_never_redraws_under_typing():
    """v4.7: the settings under their service (AGORA-078) — a sim's on its card, an agent's in its tab; Save asks
    which agents restart; the poll leaves typing alone."""
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    assert 'data-act="sim-settings"' in js and "async function openSimSettings(simId)" in js
    assert "`/api/simulations/${encodeURIComponent(simId)}/settings`" in js
    assert "`/api/agents/${encodeURIComponent(name)}/settings`" in js and '["settings", "Settings"]' in js
    assert "await put(st.path, {set, reset})" in js
    assert 'data-act="settings"' not in js                     # no global entry: settings live under their service
    assert "`Restarts: ${who.join(\", \")} — each writes its session summary first.`" in js
    assert 'save: "Save and restart"' in js
    assert "if (settingsOpen() && !manual) {" in js
    assert 'S.drawer?.kind === "agent" && S.drawer.tab === "settings"' in js
    assert 'value="${esc(value)}"' in js and "${esc(r.description)}" in js            # escaped, never raw
    icons = (STATIC_DIR / "icons.js").read_text(encoding="utf-8")
    assert '"sliders":' in icons


def test_claudes_files_tab_lists_opens_downloads_uploads_and_confirms_a_delete_or_replace():
    """v4.7 (the owner, 2026-10-11): Claude's folder from his card — the tab only for the claude-sdk engine."""
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    assert '["files", "Files"]' in js and '(k !== "files" || a.engine === "claude-sdk")' in js
    assert 'send("PUT", filePath(agent, path, overwrite ? "?overwrite=1" : ""), file, true)' in js
    assert 'await send("DELETE", filePath(agent, path));' in js and 'api(filePath(agent, path, "?download=1"), "blob")' in js
    assert "Claude loses this note — it is not kept anywhere else." in js
    assert "The file in Claude's folder is overwritten with the one you chose." in js
    assert "Empty — nothing written yet" in js and "${esc(F.open.text)}" in js and "${esc(f.path)}" in js
    icons = (STATIC_DIR / "icons.js").read_text(encoding="utf-8")
    assert all(f'"{name}":' in icons for name in ("folder", "upload", "trash"))


def test_a_setting_field_starts_from_what_the_agents_run_with():
    """v4.7 review #3: the field showed `override ?? default`, never the server's .env value — the live
    CAT_REACT_P=0.6 showed as 0.3, and typing 0.3 counted as no change."""
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    assert "const currentValue = (r) => r.override ?? serverValue(r);" in js
    assert 'e.source !== "panel"' in js and "reset → server value" in js
    assert "!== String(currentValue(rows[n]))" in js


def test_typing_updates_only_the_save_bar():
    """v4.7 review #4: a re-render on blur rebuilt the DOM under the click — the first Save after typing was lost."""
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    assert "bar.innerHTML = saveBarHtml(pendingSettings(), S.settings.busy);" in js
    assert 'document.addEventListener("change", (e) => { if (e.target?.dataset?.setting' not in js


def test_the_open_settings_follow_the_agents_when_nothing_is_pending_and_load_no_log():
    """v4.7 review #8: «runs:» stayed stale after a save, and the poll asked for /api/simulations/undefined/logs."""
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    assert "if (st && st.view && !st.busy && !pendingSettings().names.length) {" in js
    assert 'if (!dr || dr.kind === "settings" || (dr.kind === "agent" && dr.tab !== "log")) return;' in js


def test_a_settings_save_marks_its_agents_restarting_and_refreshes_after():
    """The owner, 2026-10-11: after a shared save Claude's card read «stopped» mid-restart and invited a manual Start
    (it was already running). The restarted agents show «restarting…», their buttons wait, and the page refreshes
    again a few seconds later."""
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    assert 'for (const c of marked) S.busy[c] = "restarting… applying settings";' in js
    assert "for (const c of marked) delete S.busy[c];" in js and "setTimeout(() => refresh(true), 5000);" in js


def test_the_cards_stay_live_behind_the_settings_and_no_load_lands_in_the_wrong_drawer():
    """The owner, 2026-10-11: uptimes froze behind the open settings after a restart. AGORA-078 review #1–#3: a poll
    or a slow load could land in another drawer or over fresh typing; a failed load showed «Loading…» forever."""
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    assert 'if (stack && S.drawer?.kind === "settings") stack.innerHTML = dashboardHtml();' in js
    assert "const untouched = S.settings === st && !st.busy" in js
    assert "if (settingsPath() !== path) return false;" in js
    assert 'data-act="settings-retry"' in js and "Settings unavailable: ${esc(st.error)}" in js


def test_the_file_picker_survives_the_redraw():
    """The owner, 2026-10-11: download worked, upload never sent a request — the 10 s redraw replaced the picker
    inside #app while a file was being chosen. It now lives on <body>, outside the redraw."""
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    assert "document.body.appendChild(pickerEl);" in js and 'act === "file-pick") filePicker().click();' in js
    assert '<input id="file-pick" type="file" hidden>' not in js


def test_hermes_card_shows_his_digests_and_the_tables_their_characters():
    """v5.1: «last digest 14:05 · 2 today», the month's characters against the cap (or text only), a chars column
    only when some row has characters."""
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    assert '${can(a, "digest") ? `<div style="display:flex;flex-direction:column;gap:3px"><div class="label">Digests</div>${digestLine(mem)}' in js
    assert "function digestLine(mem)" in js and '"text only — no voice id"' in js and "chars this month" in js
    assert 'pill("warn", "monthly cap reached")' in js
    assert 'const chars = u.rows.some((r) => r.characters);' in js and '<th class="r">chars</th>' in js
    assert '"digest_voice", "ask", "tts", "stt", ' in js  # v5.2: hearing (v5.6: the private chat's kinds follow)



def test_every_kind_shows_in_the_agents_tokens_tab():
    """Review #11: the cat's `sky` calls were in his total but not in his rows; an unlisted kind now shows too."""
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    from agents.usage import KINDS
    order = js.split("const KIND_ORDER = [")[1].split("]")[0]
    assert all(f'"{k}"' in order for k in (*KINDS, "sky"))
    assert "function kindsOf(byKind)" in js and "${kindsOf(byKind).map((k) =>" in js
    assert "KIND_ORDER.filter((k) => byKind[k]).map" not in js


def test_the_facts_tab_and_the_archive_line():
    """v5.8: Кіра's facts — re-pin at once, delete after a confirmation; her card shows the archive's size."""
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    assert '["facts", "Facts"]' in js and "function factsTabHtml(a, mem)" in js
    assert 'data-act="fact-pin"' in js and 'data-act="fact-delete"' in js
    assert '{action: "delete", kind: "fact", id, fresh: true}' in js            # a delete is confirmed first
    assert 'send("DELETE", `/api/agents/${encodeURIComponent(agent)}/facts/${encodeURIComponent(id)}`)' in js
    assert "function archiveLine(mem)" in js and 'can(a, "recall")' in js


def test_the_update_now_button():
    """AGORA-116: «Update now» in the Facts tab — disabled while her update is pending."""
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    assert 'data-act="facts-update" ${mem.facts_pending ? "disabled" : ""}' in js
    assert 'send("POST", `/api/agents/${encodeURIComponent(agent)}/facts/update`)' in js


def test_the_models_lines_and_the_voice_tab():
    """v5.9 (AGORA-121): a Gemini speaker's card names its models and voice; a Voice tab lists the emotion palette."""
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    assert '["voice", "Voice"]' in js and "function voiceTabHtml(a, mem)" in js and "function modelLines(m)" in js
    assert 'a.engine === "gemini" && mem.models' in js and "emotion: ${m.emotion.tags.length} tags" in js
    assert "performed by her voice · never shown in the text" in js


def test_the_card_shows_her_last_event():
    """v5.11: an agent with `events` shows its latest event of the week on the card, under the mood — the text, its
    day, time and kind, labelled as in the Events tab; none without the capability."""
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    assert ('${a.capabilities && can(a, "events") ? `<div style="display:flex;flex-direction:column;gap:3px">'
            '<div class="label">Last event</div>${lastEventLine(mem)}</div>` : ""}') in js
    assert js.index("${moodLine(mem)}${weatherLine(mem)}") < js.index("${lastEventLine(mem)}")
    assert "const day = mem.events[0], e = day && day.events[day.events.length - 1];" in js
    assert "${esc(shortDay(day.date))} · ${esc(e.time)} · ${esc(eventLabel(e))}" in js
    assert "const label = eventLabel(e);" in js and "Nothing has happened this week yet" in js


# --- v5.12: her thoughts ------------------------------------------------------------------------------------------
def test_the_thoughts_tab_and_the_card_line():
    """v5.12: an agent with `thoughts` gets a Thoughts tab — by day, each thought's time, kind and source as a label,
    a news thought's title and an https-only source link, every text escaped — and «Last thought» under «Last
    event» on her card."""
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    assert '["events", "Events"], ["thoughts", "Thoughts"], ["facts", "Facts"]' in js
    assert 'if (tab === "thoughts") return thoughtsTabHtml(a, mem);' in js
    tab = js[js.index("function thoughtsTabHtml(a, mem) {"):]
    tab = tab[:tab.index("\n}\n")]
    assert "const link = t.link && /^https:\\/\\//.test(t.link)" in tab
    assert 'target="_blank" rel="noopener noreferrer"' in tab
    assert "${esc(t.title)}" in tab and "${esc(t.text)}" in tab and "${esc(t.time)}" in tab
    assert "${esc(thoughtLabel(t))}" in tab and "Thoughts unreadable." in tab
    assert 'THOUGHT_SOURCE = {zaxid: "Zaxid.net", guardian: "The Guardian", private: "alone", agora: "Agora"}' in js
    assert ('${a.capabilities && can(a, "thoughts") ? `<div style="display:flex;flex-direction:column;gap:3px">'
            '<div class="label">Last thought</div>${lastThoughtLine(mem)}</div>` : ""}') in js
    assert js.index("${lastEventLine(mem)}") < js.index("${lastThoughtLine(mem)}")
    assert "const day = mem.thoughts[0], t = day && day.thoughts[day.thoughts.length - 1];" in js
    assert "No thoughts this week yet" in js


def test_an_agents_card_shows_its_blocks_today_only_when_there_are_any():
    """v5.13 — «Blocks today» from the usage view's per-agent counts, escaped, for any agent."""
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    assert "    ${blocksLine(a.name)}\n" in js[js.index("function agentCardHtml(a) {"):]
    fn = js[js.index("function blocksLine(name) {"):]
    fn = fn[:fn.index("\n}\n")]
    assert "if (!t || !(t.blocked_today > 0)) return \"\";" in fn
    assert '<div class="label">Blocks today</div>' in fn
    assert "${esc(fmtInt(t.blocked_today))} · ${esc(fmtInt(t.blocked))} in ${esc(fmtInt(u.per_day.length))} days" in fn
