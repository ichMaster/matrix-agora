// Agora panel — the page (v3.3 views, v3.4 control). Vanilla JS, no build step, no outside requests.
// Built to specification/design/design_handoff_agora_panel/ with the owner's adoption notes
// (specification/design/README.md): English UI, the agents' own texts as-is, only what is recorded.
"use strict";

const POLL_MS = 10000;  // one tick for everything — the dashboard, an open log, an open agent's memory (owner)
const KIND_ORDER = ["reply", "summary", "plan", "day_memory", "digest", "today", "mood", "sky", "digest_voice", "ask", "tts", "stt", "private", "private_nudge", "embed", "facts", "event", "reading", "thought", "reflection", "judge", "probe", "photo", "video", "video_note", "frame"];
// review #11: a kind not listed above still shows, after the listed ones — a tab's rows always add up to its total
function kindsOf(byKind) { return [...KIND_ORDER.filter((k) => byKind[k]), ...Object.keys(byKind).filter((k) => !KIND_ORDER.includes(k)).sort()]; }
const TABS = [["log", "Log"], ["session", "Last session"], ["memory", "Memories"], ["plans", "Plans"],
              ["today", "Today"], ["mood", "Mood"], ["events", "Events"], ["thoughts", "Thoughts"], ["talk", "Talk"], ["prompt", "Prompt"], ["facts", "Facts"], ["voice", "Voice"], ["tokens", "Tokens"],
              ["files", "Files"], ["settings", "Settings"]];
// v4.1: a tab needs its capability; "Log" and "Tokens" every agent has
const TAB_CAP = {session: "summary", memory: "chronicle", plans: "plans", today: "today", mood: "mood", facts: "facts",
                 voice: "voice", events: "events", thoughts: "thoughts", talk: "talk", prompt: "private"};
const SERIES = ["a", "b", "c", "d", "e"];  // stacked token bars: one tint of the accent per agent (v4.2: N agents)
const PRONOUN = {she: "She", he: "He", it: "It"};
function can(a, cap) { return !a.capabilities || a.capabilities.includes(cap); }
// v4.7: "Files" — Claude's own folder — only for the claude-sdk engine
function agentTabs(a) { return TABS.filter(([k]) => (k !== "files" || a.engine === "claude-sdk") && (!TAB_CAP[k] || can(a, TAB_CAP[k]))); }

const S = {
  token: store(sessionStorage, "agora-token"),
  data: null, fetchedAt: 0, loading: false, gateError: false,
  drawer: null,            // {kind: "agent"|"service", id, tab}
  drawerFresh: false,      // true only for the render that opens it: the slide-in plays once
  log: {lines: [], available: true, follow: true, seen: 0},
  usageFilter: "all", expandedDays: {}, openDetails: {}, toast: null,
  busy: {},                // target → busy label while its action runs (v3.4)
  dialog: null,            // {action, kind: "agent"|"service", id, sim} awaiting confirmation
  settings: null,          // v4.7: {view, edits: {name: value}, reset: {name: true}, busy}
  files: {list: null, open: null, prefix: "", busy: false},  // v4.7: Claude's folder
  prompt: undefined,  // v5.20: her last private prompt, fetched when its tab opens
  view: "dashboard",       // v5.19: or "analytics", kept in the address
  an: {range: "30d", since: "", until: "", agent: "all", metric: "calls", data: null, loading: false, error: null,
       open: {}, req: 0, resize: 0, tab: "cost"},  // v5.22: the view — cost, speed, prompts or media
};

// ── tiny helpers ─────────────────────────────────────────────────────────────
function store(area, key, value) {
  try {
    if (value === undefined) return area.getItem(key);
    if (value === null) area.removeItem(key); else area.setItem(key, value);
  } catch { return null; }
}
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const $ = (sel) => document.querySelector(sel);
const fmtInt = (n) => (n ?? 0).toLocaleString("en-US");
const fmtM = (n) => n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${Math.round(n / 1e3)}K` : String(n ?? 0);
const fmtUsd = (n, digits = 2) => n == null ? "" : `$${n.toFixed(digits)}`;
const costSuffix = (n) => n == null ? "" : ` · ${fmtUsd(n)}`;  // v4.4 review #13: no dangling « · » for a subscription
const fmtGB = (b) => `${(b / 1024 ** 3).toFixed(1)}`;
function fmtDur(s) {
  if (s == null) return "—";
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  if (h >= 24) return `${h} h`;
  if (h > 0) return m ? `${h} h ${m} min` : `${h} h`;
  return m > 0 ? `${m} min` : `${s} s`;
}
function ago(sec) {
  if (sec < 5) return "just now";
  if (sec < 60) return `${Math.floor(sec)} s ago`;
  if (sec < 3600) return `${Math.floor(sec / 60)} min ago`;
  return `${Math.floor(sec / 3600)} h ago`;
}
const parseDay = (iso) => new Date(`${iso}T12:00:00`);
const longDay = (iso) => parseDay(iso).toLocaleDateString("en-US", {month: "long", day: "numeric"}) + " · " +
  parseDay(iso).toLocaleDateString("en-US", {weekday: "long"});
const shortDay = (iso) => parseDay(iso).toLocaleDateString("en-US", {weekday: "short"}).slice(0, 2) + " " + parseDay(iso).getDate();
const rangeLabel = (a, b) => `${parseDay(a).toLocaleDateString("en-US", {month: "short", day: "numeric"})} – ${parseDay(b).toLocaleDateString("en-US", {month: "short", day: "numeric"})}`;
const pill = (cls, label) => `<span class="pill ${cls}">${esc(label)}</span>`;

// ── API ──────────────────────────────────────────────────────────────────────
class Unauthorized extends Error {}
async function api(path, as = "json") {
  const resp = await fetch(path, {headers: {Authorization: `Bearer ${S.token}`}, cache: "no-store"});
  if (resp.status === 401) throw new Unauthorized();
  if (resp.status === 404) throw new Error(`not found: ${path}`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return as === "blob" ? resp.blob() : resp.json();
}

// The only calls in the page that change anything: POST / PUT / DELETE + the owner token (same-origin by
// construction). `raw` sends a file's bytes as they are (v4.7: an upload to Claude's folder).
async function send(method, path, payload, raw = false) {
  const headers = {Authorization: `Bearer ${S.token}`};
  if (payload !== undefined && !raw) headers["Content-Type"] = "application/json";
  const resp = await fetch(path, {method, headers, cache: "no-store",
                                  body: payload === undefined ? undefined : raw ? payload : JSON.stringify(payload)});
  if (resp.status === 401) throw new Unauthorized();
  const body = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const inv = body.detail && body.detail.invalid;
    const err = new Error(inv ? Object.entries(inv).map(([k, v]) => `${k}: ${v}`).join("; ") : (body.detail || `HTTP ${resp.status}`));
    err.status = resp.status;
    throw err;
  }
  return body;
}
const post = (path) => send("POST", path);
const put = (path, payload) => send("PUT", path, payload);  // v4.7: the settings save

async function loadDashboard() {
  const [health, sims, agents, usage] = await Promise.all([
    api("/api/health"), api("/api/simulations"), api("/api/agents"), api("/api/usage?days=7")]);
  const simDetails = await Promise.all(sims.map((s) => api(`/api/simulations/${encodeURIComponent(s.id)}`)));
  const agentDetails = await Promise.all(agents.map((a) => api(`/api/agents/${encodeURIComponent(a.name)}`)));
  const memories = await Promise.all(agents.map((a) => api(`/api/agents/${encodeURIComponent(a.name)}/memory`).catch(() => ({available: false}))));
  const mem = {};
  agents.forEach((a, i) => { mem[a.name] = memories[i]; });
  return {health, sims: simDetails, agents: agentDetails, mem, usage};
}

async function refresh(manual = false) {
  if (!S.token) return render();
  if (manual) spinRefresh();
  try {
    const data = await loadDashboard();
    const same = S.data && JSON.stringify(data) === JSON.stringify(S.data);
    const openMem = S.drawer?.kind === "agent" ? S.data?.mem[S.drawer.id] : undefined;
    S.data = data;
    if (openMem !== undefined) S.data.mem[S.drawer.id] = openMem;  // the drawer's copy is refreshed below
    S.fetchedAt = Date.now();
    S.loading = false;
    const [logMoved, memMoved] = S.drawer ? await Promise.all([
      S.log.follow ? loadLog(false) : false, S.drawer.kind === "agent" ? refreshMemory(false) : false]) : [false, false];
    if (settingsOpen() && !manual) {                           // v4.7: never redraw under the owner's typing…
      // …but the cards behind stay live: the dashboard alone is redrawn in place (the owner: uptimes froze after a
      // restart while the settings stayed open)
      const stack = $(".main .stack");
      if (stack && S.drawer?.kind === "settings" && S.view !== "analytics") stack.innerHTML = dashboardHtml();
      const st = S.settings;                                   // with nothing pending, follow the agents (review #8)
      if (st && st.view && !st.busy && !pendingSettings().names.length) {
        const view = await api(st.path).catch(() => null);
        // the drawer may have changed or the owner typed meanwhile: only the same, untouched view is replaced
        const untouched = S.settings === st && !st.busy && !Object.keys(st.edits).length && !Object.keys(st.reset).length;
        if (view && untouched && settingsOpen() && JSON.stringify(view) !== JSON.stringify(st.view)) {
          S.settings = {path: st.path, view, edits: {}, reset: {}, busy: false}; render();
        }
      }
      return;
    }
    if (same && !logMoved && !memMoved && !manual) return;  // nothing new: the "updated N s ago" ticker says so
    if (S.view === "analytics") {  // v5.19: the view loads on its own choices, never under the owner's hand on a poll
      if (!S.an.data && !S.an.loading && !S.an.error) loadAnalytics();
      if (!manual && !S.drawer) return;
      if (manual) loadAnalytics();
    }
  } catch (err) {
    if (err instanceof Unauthorized) return signOut(true);
    if (S.data) showToast("err", `Refresh failed: ${err.message}`);
    S.loading = false;
  }
  render();
}

// ── status logic (handoff §Status logic, adapted: only what is recorded) ─────
function simHealth(sim) {
  const st = sim?.health?.status;
  if (st === "healthy") return {cls: "ok", label: "Healthy"};
  if (st === "unreachable") return {cls: "err", label: "Unreachable"};
  return {cls: "unknown", label: "Unknown"};
}
function containerPill(state) {
  return {running: ["ok", "running"], restarting: ["warn", "restarting"], stopped: ["stop", "stopped"], crashed: ["err", "crashed"],
          missing: ["none", "container not created"], unknown: ["unknown", "unknown"]}[state] || ["unknown", "unknown"];
}
function agentStatus(agent) {
  if (S.busy[agent.container]) return ["work", S.busy[agent.container]];
  const st = agent.container_state?.state;
  const sim = S.data.sims.find((s) => s.id === agent.simulation);
  if (!S.data.health.docker) return ["unknown", "unknown"];
  if (st === "running" && sim?.health?.status === "unreachable") return ["warn", "reconnecting"];
  return containerPill(st);
}
function globalPill(h) {
  return {ok: ["ok", "All systems running"], matrix: ["err", "Matrix unreachable"],
          docker: ["unknown", "Docker unreachable"], memory: ["warn", "Memory unavailable"]}[h.status] || ["unknown", "Unknown"];
}

// ── controls (v3.4) ──────────────────────────────────────────────────────────
const VERB = {start: "started", stop: "stopped", restart: "restarted"};
function canAct(state, action, target) {
  if (!S.data.health.docker || S.busy[target]) return false;
  if (action === "start") return ["stopped", "missing", "crashed"].includes(state);
  return ["running", "restarting"].includes(state);
}
function busyLabel(action, state, isAgent) {
  if (action === "start") return state === "missing" ? "creating container…" : "starting…";
  if (action === "forget") return "forgetting…";
  return `${action === "stop" ? "stopping" : "restarting"}…${isAgent ? " writing summary" : ""}`;
}
function actionButtons({kind, id, sim, state, big}) {
  const tip = (a) => a === "start" && state === "missing" ? "Creates the container and starts it" : a[0].toUpperCase() + a.slice(1);
  return [["start", "play"], ["stop", "stop"], ["restart", "arrow-clockwise"]].map(([a, ic]) => {
    const target = kind === "agent" ? S.data.agents.find((x) => x.name === id).container : id;
    const attrs = `data-act="do" data-action="${a}" data-kind="${kind}" data-id="${esc(id)}" data-sim="${esc(sim || "")}" title="${esc(tip(a))}" ${canAct(state, a, target) ? "" : "disabled"}`;
    return big ? `<button class="btn btn-secondary" ${attrs}>${icon(ic, 14)}${a[0].toUpperCase() + a.slice(1)}</button>`
      : `<button class="btn btn-secondary btn-icon" ${attrs} aria-label="${esc(tip(a))} ${esc(id)}">${icon(ic, 14)}</button>`;
  }).join("");
}
function dialogText(d) {
  if (d.kind === "settings") {
    const {names, agents} = pendingSettings();
    const who = agents.map((n) => S.data.agents.find((a) => a.name === n)?.display || n);
    return [`Save ${names.length} setting${names.length === 1 ? "" : "s"}?`,
      `${names.join(", ")}. ${who.length ? `Restarts: ${who.join(", ")} — each writes its session summary first.` : "No agent needs a restart."}`];
  }
  if (d.kind === "fact") return ["Delete this fact?", "She stops knowing it at her next answer — it is not kept anywhere else."];
  if (d.kind === "file") {
    return d.action === "delete" ? [`Delete ${d.id}?`, "Claude loses this note — it is not kept anywhere else."]
      : [`Replace ${d.id}?`, "The file in Claude's folder is overwritten with the one you chose."];
  }
  if (d.kind === "service") {
    return d.action === "stop" ? [`Stop ${d.id}?`, "Agents will keep reconnecting until it is back."]
      : [`Restart ${d.id}?`, "Agents will reconnect briefly."];
  }
  const a = S.data.agents.find((x) => x.name === d.id);
  const subject = PRONOUN[a.pronoun] || "They";
  const summary = can(a, "summary");  // only agents that write summaries promise one
  if (d.action === "stop") return [`Stop ${a.display}?`, summary ? `${subject} will write a session summary — up to 30 seconds.` : "The container stops — up to 30 seconds."];
  if (d.action === "restart") return [`Restart ${a.display}?`, summary ? "The current session will end with a summary." : "The container restarts."];
  return [`Forget ${a.display}’s last session?`, "The summary will be deleted; day memories stay. Stopped agents only."];
}
function dialogHtml() {
  const d = S.dialog;
  if (!d) return "";
  const [title, body] = dialogText(d);
  const danger = d.action === "forget" || d.action === "delete";
  const ic = {stop: "stop", restart: "arrow-clockwise", forget: "eraser", save: "check-circle", delete: "trash", replace: "upload"}[d.action];
  const label = {stop: "Stop", restart: "Restart", forget: "Forget", save: "Save and restart", delete: "Delete", replace: "Replace"}[d.action];
  return `<div class="dialog-backdrop ${d.fresh ? "" : "settled"}" data-act="dialog-cancel"><div class="dialog" role="alertdialog" aria-modal="true" aria-labelledby="dlg-title">
    <div class="dialog-title" id="dlg-title">${esc(title)}</div><div class="dialog-body">${esc(body)}</div>
    <div class="dialog-actions"><button class="btn btn-secondary" data-act="dialog-cancel">Cancel</button>
      <button class="btn ${danger ? "btn-danger" : "btn-primary"}" data-act="dialog-ok" autofocus>${icon(ic, 14)}${label}</button></div></div></div>`;
}
async function perform(action, kind, id, sim) {
  const agent = kind === "agent" ? S.data.agents.find((x) => x.name === id) : null;
  const target = agent ? agent.container : id;
  const state = agent ? agent.container_state?.state : S.data.sims.find((s) => s.id === sim)?.service_states?.[id]?.state;
  const name = agent ? agent.display : id;
  S.busy[target] = busyLabel(action, state, Boolean(agent) && can(agent, "summary"));
  render();
  const path = action === "forget" ? `/api/agents/${encodeURIComponent(id)}/forget`
    : agent ? `/api/agents/${encodeURIComponent(id)}/${action}`
    : `/api/simulations/${encodeURIComponent(sim)}/services/${encodeURIComponent(id)}/${action}`;
  try {
    const res = await post(path);
    showToast("ok", action === "forget" ? (res.forgotten ? `${name}’s last session forgotten` : `${name} had no last session`) : `${name} ${VERB[action]}`);
  } catch (err) {
    if (err instanceof Unauthorized) return signOut(true);
    showToast("err", `Failed: ${err.message}`);
  } finally {
    delete S.busy[target];
  }
  await refresh();
  if (S.drawer?.kind === "agent") await refreshMemory();
}

// ── render ───────────────────────────────────────────────────────────────────
function render() {
  const root = $("#app");
  if (!S.token) { root.innerHTML = gateHtml(); bindGate(); return; }
  // the page re-renders on every poll: keep each scroll area where the reader left it
  const keep = [".main", ".drawer-body", ".table-scroll", "#log"].map((sel) => [sel, $(sel)?.scrollTop ?? 0]);
  root.innerHTML = topbarHtml() + `<div class="body">${railHtml()}<main class="main"><div class="stack">${
    S.data ? (S.view === "analytics" ? analyticsHtml() : dashboardHtml()) : skeletonHtml()}</div></main></div>${drawerHtml()}${dialogHtml()}${toastHtml()}`;
  keep.forEach(([sel, top]) => { const el = $(sel); if (el) el.scrollTop = top; });
  if (S.drawer) afterDrawerRender();
  S.drawerFresh = false;
  if (S.toast) S.toast.fresh = false;
  if (S.dialog) S.dialog.fresh = false;
}

function gateHtml() {
  return `<div class="gate"><form class="gate-card" id="gate-form" novalidate>
    <div style="display:flex;align-items:center;gap:10px"><div class="brand-mark" style="width:30px;height:30px;font-size:15px">A</div>
      <span class="muted" style="font-size:14px">Agora · panel</span></div>
    <h1 style="font-size:26px">Sign in</h1>
    <div class="field"><label for="token">Owner token</label>
      <input id="token" class="input" type="password" autocomplete="current-password" aria-invalid="${S.gateError}" autofocus>
      ${S.gateError ? `<div class="field-error" role="alert">${icon("warning-circle", 15)}Invalid token</div>` : ""}</div>
    <button class="btn btn-primary" type="submit" style="width:100%;height:40px">Sign in</button>
    <div class="rule-t muted" style="display:flex;align-items:center;gap:8px;padding-top:14px;font-size:12.5px">${icon("house-line", 15)}The panel is available only on the home network</div>
  </form></div>`;
}
function bindGate() {
  const form = $("#gate-form"), input = $("#token");
  input.addEventListener("input", () => { if (S.gateError) { S.gateError = false; input.setAttribute("aria-invalid", "false"); form.querySelector(".field-error")?.remove(); } });
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    S.token = input.value.trim();
    try { await api("/api/health"); } catch (err) {
      if (err instanceof Unauthorized) { S.token = null; S.gateError = true; return render(); }
    }
    store(sessionStorage, "agora-token", S.token);
    S.loading = true; render(); refresh();
  });
}
function signOut(expired = false) {
  S.token = null; S.data = null; S.drawer = null; S.gateError = expired;
  store(sessionStorage, "agora-token", null);
  render();
}

function topbarHtml() {
  const h = S.data?.health;
  const [cls, label] = h ? globalPill(h) : ["unknown", "loading…"];
  const refreshed = S.data ? `updated ${ago((Date.now() - S.fetchedAt) / 1000)}` : "loading…";
  const theme = document.documentElement.dataset.theme;
  return `<header class="topbar rule-b">
    <div class="brand"><div class="brand-mark">A</div>Agora · panel<span class="wide-only" style="margin-left:6px">${pill(cls, label)}</span></div>
    <span class="refreshed wide-only" id="refreshed">${esc(refreshed)}</span>
    <button class="btn btn-ghost btn-icon lg" data-act="refresh" title="Refresh now" aria-label="Refresh now">${icon("arrow-clockwise", 17, S.data ? "" : "spinning")}</button>
    <button class="btn btn-ghost btn-icon lg" data-act="theme" title="${theme === "dark" ? "Light theme" : "Dark theme"}" aria-label="Toggle theme">${icon(theme === "dark" ? "sun" : "moon", 17)}</button>
    <button class="btn btn-secondary wide-only" data-act="signout" style="height:32px;padding:0 12px">Sign out</button>
    <button class="btn btn-ghost btn-icon lg narrow-only" data-act="signout" title="Sign out" aria-label="Sign out">${icon("sign-out", 17)}</button>
    <div class="narrow-only topbar-row2">${pill(cls, label)}<span class="refreshed">${esc(refreshed)}</span></div>
  </header>`;
}

function railHtml() {
  const d = S.data;
  const sims = d ? d.sims : [];
  return `<nav class="rail wide-only" aria-label="Simulations">
    <div class="rail-group"><div class="section-label">Simulations</div>
      ${sims.map((s) => `<button class="rail-item" aria-current="${S.view === "dashboard" ? "page" : "false"}" data-act="top">${icon("squares-four", 16)}<span style="flex:1">${esc(s.title)}</span><span class="dot ${simHealth(s).cls}"></span></button>
        ${d.agents.filter((a) => a.simulation === s.id).map((a) => `<button class="rail-item sub" data-act="agent" data-id="${esc(a.name)}"><span style="flex:1">${esc(a.display)}</span><span class="dot ${agentStatus(a)[0]}"></span></button>`).join("")}`).join("")}
    </div>
    <div class="rail-group"><div class="section-label">System</div>
      <button class="rail-item" data-act="scroll" data-id="host-card">${icon("hard-drives", 16)}Server</button>
      <button class="rail-item" data-act="scroll" data-id="usage-card">${icon("coins", 16)}Tokens</button>
      <button class="rail-item" data-act="view" data-id="analytics" aria-current="${S.view === "analytics" ? "page" : "false"}">${icon("chart-bar", 16)}Analytics</button>
    </div>
    <div class="rail-phase">v4.7 · settings</div>
  </nav>`;
}

function skeletonHtml() {
  const bar = (w, h = 14) => `<div class="skel" style="width:${w};height:${h}px"></div>`;
  return `<section class="section"><div class="section-label">Simulations</div><div class="card">${bar("200px", 18)}${bar("100%", 40)}</div></section>
    <section class="section"><div class="section-label">Agents</div><div class="grid-agents">${[1, 2].map(() => `<div class="card">${bar("60%", 40)}${bar("100%", 30)}${bar("70%", 12)}</div>`).join("")}</div></section>
    <div class="row-wrap"><div class="card host-card">${bar("70px")}${bar("100%", 90)}</div><div class="card usage-card">${bar("140px")}${bar("100%", 120)}</div></div>`;
}

function dashboardHtml() {
  const d = S.data;
  return `<section class="section"><h2 class="section-label">Simulations</h2>${d.sims.map(simCardHtml).join("")}</section>
    <section class="section" id="agents"><div style="display:flex;align-items:baseline;gap:8px"><h2 class="section-label">Agents</h2>
      <span class="muted" style="font-size:12px">in ${esc(d.sims.map((s) => s.title).join(", "))}</span></div>
      <div class="grid-agents">${d.agents.map(agentCardHtml).join("")}</div></section>
    <div class="row-wrap">${hostCardHtml()}${usageCardHtml()}</div>`;
}

function simCardHtml(sim) {
  const d = S.data, h = simHealth(sim);
  const checked = sim.health.checked_at ? `checked ${ago(Date.now() / 1000 - sim.health.checked_at)}` : "not checked yet";
  const latency = sim.health.status === "healthy" ? `${sim.health.latency_ms} ms` : sim.health.status === "unreachable" ? "no response" : "—";
  const agents = d.agents.filter((a) => a.simulation === sim.id);
  const running = agents.filter((a) => a.container_state?.state === "running").length;
  let line = running === agents.length ? (agents.length === 2 ? "both running" : "all running") : `${running} running`;
  if (!d.health.docker) line = "state unknown";
  else if (sim.health.status === "unreachable") line = "waiting for the server";
  else if (running !== agents.length) {
    const stopped = agents.filter((a) => a.container_state?.state === "stopped").length;
    const missing = agents.filter((a) => a.container_state?.state === "missing").length;
    line = [running && `${running} running`, stopped && `${stopped} stopped`, missing && `${missing} not created`].filter(Boolean).join(" · ");
  }
  return `<article class="card">
    <div class="sim-head"><div class="sim-title"><h3 style="font-size:18px">${esc(sim.title)}</h3><span class="kind-tag">${esc(sim.kind)}</span>
      <span class="muted" style="font-size:13px">${esc(sim.description)}</span></div>
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">${pill(h.cls, h.label)}<span class="muted num" style="font-size:12px">${esc(latency)} · ${esc(checked)}</span>
        <button class="btn btn-secondary" data-act="sim-settings" data-id="${esc(sim.id)}" title="The service's settings">${icon("sliders", 14)}Settings</button></div></div>
    ${sim.health.status === "unreachable" ? `<div class="notice err" role="status">${icon("plugs", 16)}Matrix server unreachable — agents are waiting</div>` : ""}
    <div class="cols"><div class="col-services"><div class="section-label">Services</div>
      ${d.health.docker ? "" : `<div class="notice unknown">${icon("cube", 16)}Docker unreachable — container state unknown</div>`}
      ${sim.services.map((svc) => {
        const c = sim.service_states[svc] || {state: "unknown"};
        const [cls, label] = S.busy[svc] ? ["work", S.busy[svc]] : containerPill(d.health.docker ? c.state : "unknown");
        return `<div class="inset-row"><span class="svc-name">${esc(svc)}</span><span class="svc-image">${esc(c.image || "")}</span>${pill(cls, label)}
          <span class="muted num" style="font-size:12px">uptime ${esc(fmtDur(c.uptime_s))}</span>
          <span class="svc-actions"><button class="btn btn-ghost" data-act="svclog" data-sim="${esc(sim.id)}" data-id="${esc(svc)}">${icon("scroll", 15)}Log</button>
            ${actionButtons({kind: "service", id: svc, sim: sim.id, state: d.health.docker ? c.state : "unknown"})}</span></div>`;
      }).join("")}</div>
      <div class="col-agents"><div class="section-label">Agents</div>
        <button class="agents-link" data-act="scroll" data-id="agents"><span style="display:flex;gap:4px">${agents.map((a) => `<span class="mono-sq">${esc(a.display[0])}</span>`).join("")}</span>
          <span>${agents.length} agents · ${esc(line)}</span></button></div></div>
  </article>`;
}

function tokensLine(name) {
  const u = S.data.usage;
  if (!u.available) return null;
  const t = u.per_agent[name];
  if (!t || !t.calls) return "No data yet";
  return `${fmtInt(t.calls)} calls · ${fmtM(t.total)} tokens${u.priced ? costSuffix(t.cost) : ""}`;
}

function agentCardHtml(a) {
  const d = S.data, [cls, label] = agentStatus(a), mem = d.mem[a.name];
  const c = a.container_state || {};
  const today = mem.available ? (mem.today ? `<div class="today-line" lang="uk">${esc(mem.today.first_line)}</div>`
      : `<div class="muted" style="font-size:13px">No today block yet</div>`)
    : `<div class="muted" style="display:flex;align-items:center;gap:6px;font-size:13px">${icon("database", 15)}Memory unavailable</div>`;
  const tokens = tokensLine(a.name);
  return `<article class="card"><div class="agent-head"><div class="avatar">${esc(a.display[0])}</div>
      <div style="flex:1;min-width:0"><h3 class="agent-name">${esc(a.display)}</h3><div class="role">${esc(a.role)}</div></div>${pill(cls, label)}</div>
    ${d.health.docker ? "" : `<div class="notice unknown">${icon("cube", 16)}<span>Docker unreachable — state unknown</span></div>`}
    <dl class="fields ${d.health.docker ? "" : "faded"}">
      <div><dt class="label">Runs on</dt><dd>server · container <code class="chip-code">${esc(a.container)}</code></dd></div>
      <div><dt class="label">Uptime</dt><dd>${esc(c.state === "running" ? fmtDur(c.uptime_s) : "—")}</dd></div>
    </dl>
    ${can(a, "today") ? `<div style="display:flex;flex-direction:column;gap:3px"><div class="label">Today</div>${today}</div>` : ""}
    ${can(a, "mood") ? `<div style="display:flex;flex-direction:column;gap:3px"><div class="label">Mood of the day</div>${moodLine(mem)}${weatherLine(mem)}</div>` : ""}
    ${a.capabilities && can(a, "events") ? `<div style="display:flex;flex-direction:column;gap:3px"><div class="label">Last event</div>${lastEventLine(mem)}</div>` : ""}
    ${a.capabilities && can(a, "thoughts") ? `<div style="display:flex;flex-direction:column;gap:3px"><div class="label">Last thought</div>${lastThoughtLine(mem)}</div>` : ""}
    ${can(a, "pastlife") || can(a, "nudge") ? `<div class="muted" style="font-size:12px">${pastLifeLine(mem)}</div>` : ""}
    ${a.engine === "claude-sdk" ? `<div style="display:flex;flex-direction:column;gap:3px"><div class="label">Subscription</div>${claudeLines(mem)}</div>` : ""}
    ${can(a, "digest") ? `<div style="display:flex;flex-direction:column;gap:3px"><div class="label">Digests</div>${digestLine(mem)}</div>` : ""}
    ${a.capabilities && can(a, "recall") ? `<div class="muted" style="font-size:12px">${archiveLine(mem)}</div>` : ""}
    ${a.capabilities && can(a, "fallback") ? `<div style="display:flex;flex-direction:column;gap:3px"><div class="label">Route</div><div class="muted" style="font-size:13px">${esc(routeLine(mem))}</div></div>` : ""}
    ${blocksLine(a.name)}
    ${a.engine === "gemini" && mem.models ? `<div style="display:flex;flex-direction:column;gap:3px"><div class="label">Models</div>${modelLines(mem.models)}</div>` : ""}
    <div class="card-foot rule-t"><div class="meta">${tokens == null ? `${icon("database", 13)} Memory unavailable` : `7 days · ${esc(tokens)}`}</div>
      <div style="display:flex;gap:6px;flex-wrap:wrap">${actionButtons({kind: "agent", id: a.name, state: d.health.docker ? c.state : "unknown", big: true})}</div>
      <button class="btn btn-primary" data-act="agent" data-id="${esc(a.name)}">Details${icon("arrow-right", 14)}</button></div>
  </article>`;
}

function hostCardHtml() {
  const h = S.data.health.host || {}, docker = S.data.health.docker;
  const meter = (pct) => `<div class="meter"><span style="width:${Math.max(0, Math.min(100, pct)).toFixed(0)}%"></span></div>`;
  const disk = h.disk ? `${fmtGB(h.disk.free)} GB free of ${fmtGB(h.disk.total)} GB${meter(100 - (h.disk.free / h.disk.total) * 100)}` : "—";
  const memory = h.memory ? `${fmtGB(h.memory.used)} / ${fmtGB(h.memory.total)} GB${meter((h.memory.used / h.memory.total) * 100)}` : "—";
  const load = h.load ? `${h.load.map((x) => x.toFixed(2)).join(" · ")} <span class="muted">1 · 5 · 15 min</span>` : "—";
  return `<section class="card host-card" id="host-card"><div style="display:flex;align-items:baseline;gap:8px;flex-wrap:wrap">
      <h3 class="card-title">Server</h3><span class="muted mono" style="margin-left:auto;font-size:12px">${esc([h.os, h.address].filter(Boolean).join(" · "))}</span></div>
    <div class="kv num"><span class="label">Uptime</span><span>${esc(fmtDur(h.uptime_s))}</span>
      <span class="label">Disk</span><span>${disk}</span>
      <span class="label">Memory</span><span>${memory}</span>
      <span class="label">Load</span><span>${load}</span>
      <span class="label">Containers</span><span>${docker && h.containers_running != null ? `${h.containers_running} running` : pill("unknown", "unknown")}</span></div>
  </section>`;
}

function usageCardHtml() {
  const u = S.data.usage;
  const open = `<button class="btn btn-ghost" data-act="view" data-id="analytics">Analytics${icon("arrow-right", 13)}</button>`;  // v5.19
  const head = (extra = "") => `<div class="usage-head"><h3 class="card-title">Tokens, last 7 days</h3>${extra}${open}</div>`;
  if (!u.available) {
    return `<section class="card usage-card" id="usage-card">${head()}<div class="empty-box">${icon("database", 18)}<span>Memory unavailable</span></div></section>`;
  }
  const agents = S.data.agents;
  const filter = S.usageFilter;
  const rows = u.rows.filter((r) => filter === "all" || r.agent === filter);
  const seg = `<div class="seg" role="group" aria-label="Filter by agent" style="margin-left:auto">${[["all", "All"], ...agents.map((a) => [a.name, a.display])]
    .map(([k, lbl]) => `<button data-act="ufilter" data-id="${esc(k)}" aria-pressed="${filter === k}">${esc(lbl)}</button>`).join("")}</div>`;
  const headHtml = head(`<span class="muted" style="font-size:12px">${esc(rangeLabel(u.since, u.until))}</span>${seg}`);
  if (!u.total.calls) {
    return `<section class="card usage-card" id="usage-card">${headHtml}<div class="empty-usage">${icon("coins", 20)}<strong style="font-weight:500">No data yet</strong>
      <span class="muted" style="font-size:13px">The square is still quiet. The table fills in after the first model call.</span></div></section>`;
  }
  const tot = filter === "all" ? u.total : (u.per_agent[filter] || {calls: 0, input: 0, output: 0, total: 0, cost: null});
  const names = agents.map((a) => a.name);
  const max = Math.max(1, ...u.per_day.map((d) => names.reduce((s, n) => s + (filter === "all" || filter === n ? d.agents[n] || 0 : 0), 0)));
  const bars = `<div class="bars">${u.per_day.map((d) => {
    const seg = names.map((n, i) => [SERIES[i % SERIES.length], filter === "all" || filter === n ? d.agents[n] || 0 : 0]);
    const sum = seg.reduce((s, [, v]) => s + v, 0);
    // a column stacks bottom-up: the first agent at the bottom, so the spans go in reverse
    return `<div title="${esc(d.day)}: ${fmtInt(sum)} tokens">${[...seg].reverse().map(([c, v]) => `<span class="${c}" style="height:${(v / max) * 100}%"></span>`).join("")}</div>`;
  }).join("")}</div><div class="bar-labels">${u.per_day.map((d) => `<span class="${d.day === u.until ? "today" : ""}">${esc(shortDay(d.day))}</span>`).join("")}</div>`;
  const legend = `<div class="legend">${agents.map((a, i) => `<span><i class="${SERIES[i % SERIES.length]}"></i>${esc(a.display)}</span>`).join("")}</div>`;
  const sorted = [...rows].sort((x, y) => y.day.localeCompare(x.day) || names.indexOf(x.agent) - names.indexOf(y.agent) ||
    KIND_ORDER.indexOf(x.kind) - KIND_ORDER.indexOf(y.kind));
  let prevDay = "";
  const chars = u.rows.some((r) => r.characters);  // v5.1: Hermes's voice is counted in characters
  const video = u.rows.some((r) => r.video_ms);  // v5.18: her кружечки are counted in seconds
  const charCell = (n) => chars ? `<td class="r">${n ? fmtInt(n) : "—"}</td>` : "";
  const secCell = (ms) => video ? `<td class="r">${ms ? fmtInt(Math.round(ms / 1000)) : "—"}</td>` : "";
  const body = sorted.map((r) => {
    const day = r.day === prevDay ? "" : r.day; prevDay = r.day;
    return `<tr><td class="day">${esc(day)}</td><td>${esc(r.agent)}</td><td class="kind">${esc(r.kind)}</td><td class="r">${fmtInt(r.calls)}</td>
      <td class="r">${fmtInt(r.input)}</td><td class="r">${fmtInt(r.output)}</td>${charCell(r.characters)}${secCell(r.video_ms)}<td class="muted">${esc(r.billing || "api")}</td>${u.priced ? `<td class="r">${r.cost == null ? "—" : r.cost.toFixed(4)}</td>` : ""}</tr>`;
  }).join("");
  const foot = [...(filter === "all" ? names : [filter]).filter((n) => u.per_agent[n]).map((n) => [`total · ${n}`, u.per_agent[n], ""]), ["total", tot, "grand"]]
    .map(([lbl, t, cls]) => `<tr class="${cls}"><td colspan="3">${esc(lbl)}</td><td class="r">${fmtInt(t.calls)}</td><td class="r">${fmtInt(t.input)}</td>
      <td class="r">${fmtInt(t.output)}</td>${charCell(t.characters)}${secCell(t.video_ms)}<td class="muted">${esc(t.billing || "")}</td>${u.priced ? `<td class="r">${t.cost == null ? "—" : fmtUsd(t.cost)}</td>` : ""}</tr>`).join("");
  return `<section class="card usage-card" id="usage-card">${headHtml}
    <div class="usage-sum"><div><div class="big-num">${fmtM(tot.total)} tokens</div>
      <div class="muted num" style="font-size:12px">${fmtInt(tot.calls)} calls · ${fmtInt(tot.input)} in · ${fmtInt(tot.output)} out${u.priced ? costSuffix(tot.cost) : ""}</div></div>
      <div style="display:flex;gap:14px;align-items:flex-end"><div>${bars}</div>${filter === "all" ? legend : ""}</div></div>
    <div class="table-scroll"><table class="table"><thead><tr><th>day</th><th>agent</th><th>kind</th><th class="r">calls</th><th class="r">input</th><th class="r">output</th>${chars ? `<th class="r">chars</th>` : ""}${video ? `<th class="r">video s</th>` : ""}<th>billing</th>${u.priced ? `<th class="r">cost $</th>` : ""}</tr></thead>
      <tbody>${body}</tbody><tfoot>${foot}</tfoot></table></div>
    ${u.priced ? (u.default_priced === false ? `<div class="muted" style="font-size:12px">Only some models have prices (PRICE_MODELS) — a cost that includes the others shows —.</div>` : "")
      : `<div class="muted" style="font-size:12px">Prices are not configured — cost is not calculated.</div>`}
  </section>`;
}

// ── v5.19: Analytics — one period's spending by service, model, kind, day and agent, with charts and trends ─────
// The colours follow the service, never its rank: one fixed slot each (`--viz-N` in panel.css, validated for both
// themes); a legend always names them, and the tables carry every number a chart shows.
const SERVICES = {gemini: ["Gemini", 1], fal: ["fal.ai", 2], openrouter: ["OpenRouter", 3], elevenlabs: ["ElevenLabs", 4],
                  deepgram: ["Deepgram", 5], novelai: ["NovelAI", 6], "claude-sdk": ["Claude", 7]};
const svcName = (s) => SERVICES[s]?.[0] || s;
const svcColor = (s) => `var(--viz-${SERVICES[s]?.[1] || 8})`;
const PRESETS = [["today", "Today"], ["yesterday", "Yesterday"], ["7d", "7 days"], ["30d", "30 days"],
                 ["month", "This month"], ["lastmonth", "Last month"], ["custom", "Custom"]];
const CSV_HEAD = ["day", "agent", "service", "model", "kind", "calls", "failed", "blocked", "input", "output", "tokens",
                  "characters", "audio_s", "video_s", "billing", "cost",
                  "latency_median_ms", "latency_p95_ms"];  // v5.22: the calls' time
const AN_TABS = [["cost", "Cost"], ["speed", "Speed"], ["prompts", "Prompts"], ["media", "Media"]];  // v5.22
const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;
const fmtCost = (c) => c == null ? "—" : c !== 0 && Math.abs(c) < 0.01 ? `$${c.toFixed(4)}` : `$${c.toFixed(2)}`;
const isoShift = (iso, days) => { const d = new Date(`${iso}T00:00:00Z`); d.setUTCDate(d.getUTCDate() + days); return d.toISOString().slice(0, 10); };
// the panel's today is the server's local day once the dashboard has it — never only the browser's clock
const panelToday = () => S.data?.usage?.until || new Date().toLocaleDateString("en-CA");

function anPeriod(a = S.an) {
  const t = panelToday(), first = `${t.slice(0, 8)}01`;
  if (a.range === "today") return [t, t];
  if (a.range === "yesterday") return [isoShift(t, -1), isoShift(t, -1)];
  if (a.range === "7d") return [isoShift(t, -6), t];
  if (a.range === "month") return [first, t];
  if (a.range === "lastmonth") { const end = isoShift(first, -1); return [`${end.slice(0, 8)}01`, end]; }
  if (a.range === "custom") return [a.since, a.until];
  return [isoShift(t, -29), t];
}
// the choice lives in the address: a preset reopens as the same preset, a custom range as its days
function anHash() {
  const q = new URLSearchParams(S.an.range === "custom" ? {since: S.an.since, until: S.an.until} : {range: S.an.range});
  if (S.an.agent !== "all") q.set("agent", S.an.agent);
  if (S.an.tab !== "cost") q.set("view", S.an.tab);  // v5.22
  return `#analytics?${q}`;
}
function readHash() {
  if (!location.hash.startsWith("#analytics")) { S.view = "dashboard"; return; }
  S.view = "analytics";
  const q = new URLSearchParams(location.hash.split("?")[1] || "");
  if (ISO_DAY.test(q.get("since") || "") && ISO_DAY.test(q.get("until") || "")) {
    Object.assign(S.an, {range: "custom", since: q.get("since"), until: q.get("until")});
  } else {
    S.an.range = PRESETS.some(([k]) => k === q.get("range") && k !== "custom") ? q.get("range") : "30d";
  }
  S.an.agent = q.get("agent") || "all";
  S.an.tab = AN_TABS.some(([k]) => k === q.get("view")) ? q.get("view") : "cost";  // v5.22
}
async function loadAnalytics() {
  const [since, until] = anPeriod();
  if (!ISO_DAY.test(since) || !ISO_DAY.test(until)) return;
  const q = new URLSearchParams({since, until});
  if (S.an.agent !== "all") q.set("agent", S.an.agent);
  const req = ++S.an.req;
  S.an.loading = true; S.an.error = null; render();
  try {
    const data = await api(`/api/analytics?${q}`);
    if (req === S.an.req) S.an.data = data;          // a newer choice may be on its way: only the latest lands
  } catch (err) {
    if (err instanceof Unauthorized) return signOut(true);
    if (req === S.an.req) S.an.error = err.message;
  }
  if (req === S.an.req) { S.an.loading = false; render(); }
}
function anChoose(change) {
  Object.assign(S.an, change);
  history.replaceState(null, "", anHash());
  loadAnalytics();
}
function openAnalytics() {
  if (S.view !== "analytics") history.pushState(null, "", anHash());
  S.view = "analytics";
  loadAnalytics();
}
function leaveAnalytics() {
  if (S.view !== "analytics") return;
  S.view = "dashboard";
  history.pushState(null, "", location.pathname + location.search);
  render();
}

// a change from the previous period: an arrow, ± the amount and %, «—» when either side is unknown
function change(now, before, money = false) {
  if (now == null || before == null) return "—";
  const diff = now - before, sign = diff > 0 ? "+" : diff < 0 ? "−" : "±";
  const arrow = diff > 0 ? "↑" : diff < 0 ? "↓" : "→";
  const pct = before ? ` (${sign}${Math.abs(diff / before * 100).toFixed(0)}%)` : "";
  return `${arrow} ${sign}${money ? fmtCost(Math.abs(diff)) : fmtM(Math.abs(diff))}${pct}`;
}
const costCell = (x) => x.billing === "subscription" ? `<span class="muted">subscription</span>`
  : x.cost == null ? "—" : `${x.complete ? "" : "≥"}${fmtCost(x.cost)}`;  // a subscription is never $0
const nCell = (n, digits = 0) => `<td class="r">${n ? (digits ? n.toFixed(digits) : fmtInt(n)) : "—"}</td>`;

// ── the charts: pure builders → inline SVG; marks carry a native tooltip (<title>), colours are CSS variables ──
const PAD = {l: 56, r: 14, t: 10, b: 26};
function niceMax(v) {
  if (!(v > 0)) return 1;
  const p = 10 ** Math.floor(Math.log10(v)), m = v / p;
  return [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10].find((step) => m <= step) * p;  // a top close above the data
}
function axes(days, top, W, H, fmt) {
  const y = (v) => PAD.t + (H - PAD.t - PAD.b) * (1 - v / top);
  const grid = [0, 0.25, 0.5, 0.75, 1].map((f) => `<line class="an-grid${f ? "" : " base"}" x1="${PAD.l}" x2="${W - PAD.r}" y1="${y(top * f)}" y2="${y(top * f)}"/>` +
    `<text class="an-tick" x="${PAD.l - 6}" y="${y(top * f) + 4}" text-anchor="end">${esc(fmt(top * f))}</text>`).join("");
  const band = (W - PAD.l - PAD.r) / days.length, every = Math.max(1, Math.ceil(days.length / Math.max(2, Math.floor((W - PAD.l) / 64))));
  const labels = days.map((d, i) => i % every ? "" : `<text class="an-tick" x="${PAD.l + band * (i + 0.5)}" y="${H - 8}" text-anchor="middle">${esc(bucketLabel(d))}</text>`).join("");
  return {y, band, x: (i) => PAD.l + band * (i + 0.5), html: grid + labels};
}
// one column per day, as tall as the plot: the reader aims at a day, never at a 2px line
const hits = (days, ax, H, tip) => days.map((d, i) => `<rect class="an-hit" x="${ax.x(i) - ax.band / 2}" y="${PAD.t}" width="${ax.band}" height="${H - PAD.t - PAD.b}"><title>${esc(tip(i))}</title></rect>`).join("");
const topRounded = (x, y, w, h, r) => r <= 0 ? `M${x},${y + h}V${y}H${x + w}V${y + h}Z`
  : `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
const pathOf = (pts) => pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join("");
// v5.22: a line with gaps — a bucket with no value (null) breaks it, never a drop to zero
const pathGaps = (pts) => pts.map((p, i) => p == null ? "" : `${i && pts[i - 1] != null ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join("");
// v5.22: a bucket is a day, or an hour («08») when the period is one day
const bucketLabel = (b) => /^\d{2}$/.test(b) ? `${b}:00` : shortDay(b);

function svgStackedBars({days, keys, parts, line, tip, fmt, W, H = 220, color = svcColor, label = "Cost a day by service"}) {
  // bars stacked by key (a 2px surface gap between segments, 4px rounded tops), with `line` drawn over them
  const max = Math.max(...days.map((_, i) => keys.reduce((s, k) => s + (parts[i][k] || 0), 0)), ...line);
  const top = niceMax(max), ax = axes(days, top, W, H, fmt), bw = Math.max(2, Math.min(24, ax.band * 0.7));
  let marks = "";
  days.forEach((_, i) => {
    let base = ax.y(0);
    const present = keys.filter((k) => parts[i][k] > 0);
    present.forEach((k, j) => {
      const h = ax.y(0) - ax.y(parts[i][k]), gap = j ? 2 : 0, hh = Math.max(0, h - gap);
      marks += `<path style="fill:${color(k)}" d="${topRounded(ax.x(i) - bw / 2, base - h, bw, hh, j === present.length - 1 ? Math.min(4, hh) : 0)}"/>`;
      base -= h;
    });
  });
  const avg = line.length ? `<path class="an-line ink" d="${pathOf(line.map((v, i) => [ax.x(i), ax.y(v)]))}"/>` : "";
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(label)}">${ax.html}${marks}${avg}${hits(days, ax, H, tip)}</svg>`;
}
function svgLines({days, series, tip, fmt, W, H = 200}) {
  // one 2px line per series (`dashed` for a comparison); a single day draws markers
  const top = niceMax(Math.max(0, ...series.flatMap((s) => s.values))), ax = axes(days, top, W, H, fmt);
  const marks = series.map((s) => days.length === 1
    ? (s.values[0] == null ? "" : `<circle class="an-dot" cx="${ax.x(0)}" cy="${ax.y(s.values[0])}" r="4" style="fill:${s.color}"/>`)
    : `<path class="an-line${s.dashed ? " dash" : ""}" style="stroke:${s.color}" d="${pathGaps(s.values.map((v, i) => v == null ? null : [ax.x(i), ax.y(v)]))}"/>` +
      // v5.22: a value with no neighbour draws no line — a dot shows it
      s.values.map((v, i) => v != null && s.values[i - 1] == null && s.values[i + 1] == null
        ? `<circle class="an-dot" cx="${ax.x(i)}" cy="${ax.y(v)}" r="3" style="fill:${s.color}"/>` : "").join("")).join("");
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(series.map((s) => s.label).join(", "))}">${ax.html}${marks}${hits(days, ax, H, tip)}</svg>`;
}
function svgShare({rows, W}) {
  // 100 % bars, one per row: segments by service, a 2px surface gap between them
  const lw = 64, bh = 16, step = 30, H = rows.length * step;
  const out = rows.map((row, r) => {
    const total = row.parts.reduce((s, p) => s + p.value, 0);
    let x = lw;
    const segs = total ? row.parts.filter((p) => p.value > 0).map((p) => {
      const w = Math.max(0, (W - lw) * p.value / total - 2);
      const seg = `<rect x="${x}" y="${r * step + 4}" width="${w}" height="${bh}" rx="2" style="fill:${svcColor(p.key)}"><title>${esc(`${svcName(p.key)} · ${row.fmt(p.value)} · ${(p.value / total * 100).toFixed(0)}%`)}</title></rect>`;
      x += w + 2;
      return seg;
    }).join("") : `<text class="an-tick" x="${lw}" y="${r * step + 16}">none</text>`;
    return `<text class="an-tick name" x="0" y="${r * step + 16}">${esc(row.label)}</text>${segs}`;
  }).join("");
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Shares by service">${out}</svg>`;
}
function svgSparkline(values, color, w = 84, h = 22) {
  const max = Math.max(0, ...values), n = values.length;
  const pts = values.map((v, i) => [n > 1 ? 1 + (w - 2) * i / (n - 1) : w / 2, h - 2 - (max ? (h - 4) * v / max : 0)]);
  return `<svg class="an-spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true"><path class="an-line thin" style="stroke:${color}" d="${pathOf(pts)}"/></svg>`;
}
function svgAgents({rows, W}) {
  // the cost by agent: one bar each (a single series: no legend), the previous period's cost as a tick
  const lw = 96, vw = 70, bh = 14, step = 26, H = rows.length * step + 4;
  const max = niceMax(Math.max(0, ...rows.flatMap((r) => [r.value || 0, r.prev || 0])));
  const x = (v) => lw + (W - lw - vw) * v / max;
  const out = rows.map((r, i) => {
    const y0 = i * step + 4;
    const bar = r.value ? `<path class="an-bar" d="${topRounded(lw, y0, Math.max(1, x(r.value) - lw), bh, 0)}"/>` : "";
    const tick = r.prev ? `<line class="an-prev" x1="${x(r.prev)}" x2="${x(r.prev)}" y1="${y0 - 3}" y2="${y0 + bh + 3}"/>` : "";
    return `<g><title>${esc(`${r.label} · ${fmtCost(r.value)} · previous ${fmtCost(r.prev)}`)}</title>
      <text class="an-tick name" x="0" y="${y0 + 11}">${esc(r.label)}</text>${bar}${tick}
      <text class="an-tick" x="${(r.value ? x(r.value) : lw) + 6}" y="${y0 + 11}">${esc(r.value == null ? "subscription" : fmtCost(r.value))}</text></g>`;
  }).join("");
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Cost by agent">${out}</svg>`;
}
const legend = (items) => `<div class="an-legend">${items.map(([label, color, kind]) =>
  `<span><i class="${kind || ""}" style="${kind ? `border-color:${color}` : `background:${color}`}"></i>${esc(label)}</span>`).join("")}</div>`;
const chartW = () => Math.max(300, Math.min(1300, (document.querySelector(".main")?.clientWidth || 900) - 90));

// ── the view ─────────────────────────────────────────────────────────────────
function analyticsHtml() {
  const a = S.an, d = a.data, [since, until] = anPeriod();
  const agents = S.data?.agents || [];
  const presets = `<div class="seg" role="group" aria-label="Period">${PRESETS.map(([k, l]) =>
    `<button data-act="an-range" data-id="${k}" aria-pressed="${a.range === k}">${l}</button>`).join("")}</div>`;
  const dates = a.range !== "custom" ? "" : ["since", "until"].map((k) => `<label class="an-field">${k === "since" ? "From" : "To"}
    <input class="input" type="date" data-an="${k}" value="${esc(a[k])}"></label>`).join("");
  const who = `<label class="an-field">Agent <select class="input" data-an="agent"><option value="all"${a.agent === "all" ? " selected" : ""}>All</option>${
    agents.map((x) => `<option value="${esc(x.name)}"${a.agent === x.name ? " selected" : ""}>${esc(x.display)}</option>`).join("")}</select></label>`;
  const csv = `<button class="btn btn-secondary" data-act="an-csv" ${d?.available && d.rows?.length ? "" : "disabled"}>${icon("arrow-line-down", 14)}Download CSV</button>`;
  const shown = ISO_DAY.test(since) && ISO_DAY.test(until) ? rangeLabel(since, until) : "choose the days";
  const tabs = `<div class="seg" role="group" aria-label="View">${AN_TABS.map(([k, l]) =>
    `<button data-act="an-tab" data-id="${k}" aria-pressed="${a.tab === k}">${l}</button>`).join("")}</div>`;
  const head = `<div class="an-head"><button class="btn btn-ghost" data-act="dashboard">← Dashboard</button>
      <h1 class="an-title">Analytics</h1>${tabs}<span class="muted">${esc(shown)}${a.loading ? " · loading…" : ""}</span></div>
    <div class="an-controls">${presets}${dates}${who}<span style="margin-left:auto">${csv}</span></div>`;
  let body;
  if (a.error) {
    body = `<section class="card"><div class="empty-box">${icon("warning-circle", 18)}<span>Could not load the analytics: ${esc(a.error)}${
      a.error.includes("400") ? " — check the days (at most 366)" : ""}</span><button class="btn btn-secondary" data-act="an-retry">Retry</button></div></section>`;
  } else if (!d) {
    body = `<section class="card"><div class="empty-box">${icon("circle-notch", 18, "spinning")}<span>Loading…</span></div></section>`;
  } else if (!d.available) {
    body = `<section class="card"><div class="empty-box">${icon("database", 18)}<span>Memory unavailable</span></div></section>`;
  } else {
    body = a.tab === "speed" ? anSpeedHtml(d) : a.tab === "prompts" ? anPromptsHtml(d) : a.tab === "media" ? anMediaHtml(d)
      : anTilesHtml(d) + (d.total.calls ? anChartsHtml(d) + anTablesHtml(d)
        : `<section class="card"><div class="empty-box">${icon("coins", 18)}<span>No data for this period</span></div></section>`);
  }
  return `<section class="section an">${head}${body}</section>`;
}
function anTilesHtml(d) {
  const t = d.total, p = d.previous, tr = d.trend;
  const trendValue = tr.direction === "flat" ? "→ flat" : `${tr.direction === "rising" ? "↑" : "↓"} ${fmtCost(Math.abs(tr.slope_per_week))}`;
  const tiles = [
    ["Cost", t.cost == null ? "—" : `${t.complete ? "" : "≥"}${fmtCost(t.cost)}`, `${change(t.cost, p.cost, true)} vs previous`],
    ["Calls", fmtInt(t.calls), `${fmtInt(t.failed)} failed · ${fmtInt(t.blocked)} blocked`],
    ["Tokens", fmtM(t.tokens), `${change(t.tokens, p.tokens)} vs previous`],
    ["Cost a day", fmtCost(t.cost_per_day), `over ${d.days} day${d.days === 1 ? "" : "s"}`],
    ["Trend", trendValue, tr.direction === "flat" ? "the daily cost holds" : `a week · the daily cost is ${tr.direction}`],
    ["Month at this rate", tr.month_at_rate == null ? "—" : `≈ ${fmtCost(tr.month_at_rate)}`, "the cost a day × 30"],
  ];
  return `<div class="an-tiles">${tiles.map(([l, v, sub]) => `<div class="card an-tile"><div class="an-tile-label">${esc(l)}</div>
    <div class="an-tile-value">${esc(v)}</div><div class="muted an-tile-sub">${esc(sub)}</div></div>`).join("")}</div>`;
}
function anChartsHtml(d) {
  // v5.22 (the owner: «за сьогодні і за вчора по годинах»): one day is drawn by the hour, against the day before
  const hourly = Boolean(d.by_hour && d.hour_series?.length);
  const W = chartW(), ds = hourly ? d.hour_series : d.day_series, days = ds.map((x) => hourly ? x.hour : x.day);
  const at = (i) => hourly ? tipBucket(ds[i].hour) : ds[i].day, prevCum = hourly ? d.previous_hour_cumulative : d.previous_cumulative;
  const priced = d.services.filter((s) => s.cost).map((s) => s.service);
  const card = (title, sub, inner, extra = "") => `<section class="card an-chart"><div class="usage-head"><h3 class="card-title">${esc(title)}</h3>
    <span class="muted" style="font-size:12px">${esc(sub)}</span>${extra}</div>${inner}</section>`;
  const costTitle = hourly ? "Cost an hour" : "Cost a day";
  const cost = priced.length ? card(costTitle, hourly ? "by service" : "by service, with the 7-day moving average",
    svgStackedBars({days, keys: priced, parts: ds.map((x) => x.cost_by_service), line: hourly ? [] : ds.map((x) => x.cost_avg7), fmt: fmtCost, W,
                    tip: (i) => [`${at(i)} · ${fmtCost(ds[i].cost)}`, ...priced.filter((k) => ds[i].cost_by_service[k]).map((k) => `${svcName(k)} ${fmtCost(ds[i].cost_by_service[k])}`),
                                 ...(hourly ? [] : [`7-day average ${fmtCost(ds[i].cost_avg7)}`])].join("\n")}) +
    legend([...priced.map((k) => [svcName(k), svcColor(k)]), ...(hourly ? [] : [["7-day average", "var(--color-text)", "ln"]])]))
    : card(costTitle, "nothing priced in this period", "");
  const prevTotal = prevCum.at(-1);
  const running = card("Running total", hourly ? "this day against the day before, hour by hour" : "this period against the previous one, day by day",
    svgLines({days, fmt: fmtCost, W, series: [
      // today's hours to come are no line: it stops at the current hour
      {label: "This period", color: "var(--color-accent)", values: ds.map((x, i) => hourly && d.since === panelToday() && i > new Date().getHours() ? null : x.cost_cumulative)},
      {label: "Previous period", color: "var(--muted)", dashed: true, values: prevCum}],
    tip: (i) => `${at(i)} · this period ${fmtCost(ds[i].cost_cumulative)} · previous ${fmtCost(prevCum[i])}`}) +
    legend([[`This period · ${fmtCost(ds.at(-1).cost_cumulative)}`, "var(--color-accent)", "ln"],
            [`Previous period · ${fmtCost(prevTotal)}`, "var(--muted)", "ln dash"]]));
  const metric = S.an.metric, all = d.services.map((s) => s.service), field = metric === "tokens" ? "tokens_by_service" : "calls_by_service";
  const toggle = `<div class="seg" role="group" aria-label="Activity" style="margin-left:auto">${[["calls", "Calls"], ["tokens", "Tokens"]].map(([k, l]) =>
    `<button data-act="an-metric" data-id="${k}" aria-pressed="${metric === k}">${l}</button>`).join("")}</div>`;
  const activity = card(hourly ? "Activity an hour" : "Activity a day", `${metric} by service`, svgLines({days, fmt: (v) => fmtM(Math.round(v)), W,
    series: all.map((k) => ({label: svcName(k), color: svcColor(k), values: ds.map((x) => x[field][k] || 0)})),
    tip: (i) => [`${at(i)}`, ...all.filter((k) => ds[i][field][k]).map((k) => `${svcName(k)} ${fmtInt(ds[i][field][k])}`)].join("\n")}) +
    legend(all.map((k) => [svcName(k), svcColor(k), "ln"])), toggle);
  const shares = card("Shares", "of the cost (priced services) and of the calls (every service)", svgShare({W, rows: [
    {label: "Cost", fmt: fmtCost, parts: d.services.filter((s) => s.cost).map((s) => ({key: s.service, value: s.cost}))},
    {label: "Calls", fmt: fmtInt, parts: d.services.map((s) => ({key: s.service, value: s.calls}))}]}) +
    legend(all.map((k) => [svcName(k), svcColor(k)])));
  const agents = d.agents.length ? card("Agents", "the cost of each, the tick is the previous period's",
    svgAgents({W, rows: d.agents.map((x) => ({label: S.data?.agents.find((g) => g.name === x.agent)?.display || x.agent, value: x.cost, prev: x.previous.cost}))})) : "";
  return cost + running + activity + shares + agents;
}
function anTablesHtml(d) {
  const svcRows = d.services.map((s) => {
    const open = S.an.open[s.service], sub = s.billing === "subscription";
    const delta = sub ? change(s.calls, s.previous.calls) : change(s.cost, s.previous.cost, true);
    const cells = (x) => [x.calls, x.failed, x.input, x.output, x.characters].map((n) => nCell(n)).join("") + nCell(x.audio_s, 1) + nCell(x.video_s, 1);
    const main = `<tr><td><button class="an-caret" data-act="an-open" data-id="${esc(s.service)}" aria-expanded="${Boolean(open)}" aria-label="Models of ${esc(svcName(s.service))}">${icon(open ? "caret-down" : "caret-right", 12)}</button><i class="an-key" style="background:${svcColor(s.service)}"></i>${esc(svcName(s.service))}</td>
      <td class="muted">${esc(s.billing)}</td><td>${svgSparkline(sub ? s.series.calls : s.series.cost, svcColor(s.service))}</td>${cells(s)}<td class="r">${costCell(s)}</td><td class="r muted">${esc(delta)}</td></tr>`;
    const models = open ? s.models.map((m) => `<tr class="an-sub"><td>${esc(m.model)}</td><td class="muted">${esc(m.billing)}</td><td></td>${cells(m)}<td class="r">${costCell(m)}</td>
      <td class="r muted">${esc(m.billing === "subscription" ? change(m.calls, m.previous.calls) : change(m.cost, m.previous.cost, true))}</td></tr>`).join("") : "";
    return main + models;
  }).join("");
  const services = `<section class="card"><h3 class="card-title">Services</h3><div class="table-scroll an-table"><table class="table"><thead><tr>
    <th>service</th><th>billing</th><th>trend</th><th class="r">calls</th><th class="r">failed</th><th class="r">input</th><th class="r">output</th><th class="r">chars</th>
    <th class="r">audio s</th><th class="r">video s</th><th class="r">cost</th><th class="r">vs previous</th></tr></thead><tbody>${svcRows}</tbody></table></div>
    ${d.unpriced.length ? `<div class="muted" style="font-size:12px">No price for ${esc(d.unpriced.join(", "))} (PRICE_MODELS): a cost with them shows «≥».</div>` : ""}</section>`;
  const kinds = `<section class="card"><h3 class="card-title">What it was for</h3><div class="table-scroll an-table"><table class="table"><thead><tr><th>kind</th>
    <th class="r">calls</th><th class="r">tokens</th><th class="r">cost</th><th class="r">share</th><th class="r">vs previous</th></tr></thead><tbody>${d.kinds.map((k) =>
    `<tr><td class="kind">${esc(k.kind)}</td>${nCell(k.calls)}${nCell(k.tokens)}<td class="r">${costCell(k)}</td><td class="r">${k.share == null ? "—" : `${(k.share * 100).toFixed(0)}%`}</td>
      <td class="r muted">${esc(k.cost == null ? change(k.calls, k.previous.calls) : change(k.cost, k.previous.cost, true))}</td></tr>`).join("")}</tbody></table></div></section>`;
  const agents = d.agents.length ? `<section class="card"><h3 class="card-title">Agents</h3><div class="table-scroll an-table"><table class="table"><thead><tr><th>agent</th>
    <th class="r">calls</th><th class="r">tokens</th><th class="r">cost</th><th class="r">vs previous</th><th>services</th></tr></thead><tbody>${d.agents.map((x) =>
    `<tr><td>${esc(S.data?.agents.find((g) => g.name === x.agent)?.display || x.agent)}</td>${nCell(x.calls)}${nCell(x.tokens)}<td class="r">${costCell(x)}</td>
      <td class="r muted">${esc(change(x.cost, x.previous.cost, true))}</td><td class="muted">${esc(x.services.map(svcName).join(", "))}</td></tr>`).join("")}</tbody></table></div></section>` : "";
  const fees = d.subscriptions.length ? `<section class="card"><h3 class="card-title">Subscriptions</h3><div class="table-scroll an-table"><table class="table"><thead><tr>
    <th>service</th><th class="r">a month</th><th class="r">this period</th></tr></thead><tbody>${d.subscriptions.map((x) =>
    `<tr><td>${esc(svcName(x.service))}</td><td class="r">${fmtCost(x.monthly)}</td><td class="r">${fmtCost(x.period_cost)}</td></tr>`).join("")}</tbody></table></div>
    <div class="muted" style="font-size:12px">The monthly fees (PRICE_SUBSCRIPTIONS), prorated by day — shared by every agent, never split.</div></section>` : "";
  return services + kinds + agents + fees;
}

// ── v5.22: Speed, Prompts and Media — pure builders over the route's `speed`, `answers`, `prompts` and `media` ───
const fmtMs = (ms) => ms == null ? "—" : ms < 1000 ? `${Math.round(ms)} ms` : ms < 60000 ? `${(ms / 1000).toFixed(1)} s` : `${(ms / 60000).toFixed(1)} min`;
function msChange(now, before) {
  if (now == null || before == null) return "—";
  const diff = now - before, arrow = diff > 0 ? "↑" : diff < 0 ? "↓" : "→", sign = diff > 0 ? "+" : diff < 0 ? "−" : "±";
  return `${arrow} ${sign}${fmtMs(Math.abs(diff))}${before ? ` (${sign}${Math.abs(diff / before * 100).toFixed(0)}%)` : ""}`;
}
function tokChange(now, before) {
  if (now == null || before == null) return "—";
  const diff = now - before, arrow = diff > 0 ? "↑" : diff < 0 ? "↓" : "→", sign = diff > 0 ? "+" : diff < 0 ? "−" : "±";
  return `${arrow} ${sign}${fmtM(Math.abs(diff))}${before ? ` (${sign}${Math.abs(diff / before * 100).toFixed(0)}%)` : ""}`;
}
const anCard = (title, sub, inner) => `<section class="card an-chart"><div class="usage-head"><h3 class="card-title">${esc(title)}</h3>
  <span class="muted" style="font-size:12px">${esc(sub)}</span></div>${inner}</section>`;
const anTiles = (tiles) => `<div class="an-tiles">${tiles.map(([l, v, sub]) => `<div class="card an-tile"><div class="an-tile-label">${esc(l)}</div>
  <div class="an-tile-value">${esc(v)}</div><div class="muted an-tile-sub">${esc(sub)}</div></div>`).join("")}</div>`;
const anEmpty = (name, text) => `<section class="card"><div class="empty-box">${icon(name, 18)}<span>${esc(text)}</span></div></section>`;
const agentName = (n) => S.data?.agents.find((g) => g.name === n)?.display || n;
const tipBucket = (b) => /^\d{2}$/.test(b) ? `${b}:00–${b}:59` : b;
const anTable = (title, head, rows, foot = "") => `<section class="card"><h3 class="card-title">${esc(title)}</h3><div class="table-scroll an-table"><table class="table"><thead><tr>${
  head.map(([h, right]) => `<th${right ? ' class="r"' : ""}>${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table></div>${foot}</section>`;
const msCell = (v) => `<td class="r">${esc(fmtMs(v))}</td>`;
const tokCell = (v) => `<td class="r">${v == null ? "—" : esc(fmtM(v))}</td>`;
const mutedCell = (text) => `<td class="r muted">${esc(text)}</td>`;
// a service's row with its models under a caret (the state's `open`, keyed by the view)
function caretRows(view, s, mainCells, subCells) {
  const key = `${view}:${s.service}`, open = S.an.open[key];
  const name = `<td><button class="an-caret" data-act="an-open" data-id="${esc(key)}" aria-expanded="${Boolean(open)}" aria-label="Models of ${esc(svcName(s.service))}">${
    icon(open ? "caret-down" : "caret-right", 12)}</button><i class="an-key" style="background:${svcColor(s.service)}"></i>${esc(svcName(s.service))}</td>`;
  return `<tr>${name}${mainCells(s)}</tr>` + (open ? s.models.map((m) => `<tr class="an-sub"><td>${esc(m.model)}</td>${subCells(m)}</tr>`).join("") : "");
}

function anSpeedHtml(d) {
  const sp = d.speed, an = d.answers, W = chartW(), b = d.buckets, per = d.by_hour ? "an hour" : "a day";
  const tiles = anTiles([
    ["Your wait", fmtMs(an.owner.wait.median), `median · p95 ${fmtMs(an.owner.wait.p95)} · ${fmtInt(an.owner.wait.n)} answers`],
    ["Without the pause", fmtMs(an.owner.net.median), "median · the deliberate pause taken out"],
    ["vs previous", msChange(an.owner.wait.median, an.owner.previous_median), "your median wait"],
    ["Slowest service", sp.slowest ? svcName(sp.slowest.service) : "—", sp.slowest ? `p95 ${fmtMs(sp.slowest.p95)}` : "no timed calls"],
  ]);
  if (!sp.services.length && !an.groups.length) return tiles + anEmpty("clock", "No timed calls or answers in this period — the time is kept from v5.22 on");
  const lines = sp.services.length ? anCard("Call time", `each service's median ${per}`,
    svgLines({days: b, fmt: fmtMs, W, series: sp.services.map((s) => ({label: svcName(s.service), color: svcColor(s.service), values: s.series})),
      tip: (i) => [tipBucket(b[i]), ...sp.services.filter((s) => s.series[i] != null).map((s) => `${svcName(s.service)} ${fmtMs(s.series[i])}`)].join("\n")}) +
    legend(sp.services.map((s) => [svcName(s.service), svcColor(s.service), "ln"]))) : "";
  const wait = an.owner.wait.n ? anCard("Your wait for an answer", `the median ${per}, the pause included`,
    svgLines({days: b, fmt: fmtMs, W, series: [{label: "Your wait", color: "var(--color-accent)", values: an.series}],
      tip: (i) => `${tipBucket(b[i])} · ${fmtMs(an.series[i])}`})) : "";
  const timeCells = (x) => nCell(x.n) + msCell(x.median) + msCell(x.p95) + msCell(x.max) + mutedCell(msChange(x.median, x.previous_median));
  const services = sp.services.length ? anTable("Services", [["service"], ["trend"], ["calls timed", 1], ["median", 1], ["p95", 1], ["max", 1], ["vs previous", 1]],
    sp.services.map((s) => caretRows("speed", s, (x) => `<td>${svgSparkline(x.series.map((v) => v || 0), svcColor(x.service))}</td>` + timeCells(x),
                                     (m) => "<td></td>" + timeCells(m))).join("")) : "";
  const kinds = sp.kinds.length ? anTable("What it was for", [["kind"], ["calls timed", 1], ["median", 1], ["p95", 1], ["max", 1], ["vs previous", 1]],
    sp.kinds.map((k) => `<tr><td class="kind">${esc(k.kind)}</td>${timeCells(k)}</tr>`).join("")) : "";
  const answers = an.groups.length ? anTable("Answers", [["agent"], ["where"], ["by"], ["to"], ["answers", 1], ["median wait", 1], ["p95", 1], ["without the pause", 1], ["vs previous", 1]],
    an.groups.map((g) => `<tr><td>${esc(agentName(g.agent))}</td><td class="muted">${esc(`${g.place} · ${g.door}`)}</td><td>${esc(g.by)}</td>
      <td class="muted">${g.answered === "owner" ? "you" : "an agent"}</td>${nCell(g.wait.n)}${msCell(g.wait.median)}${msCell(g.wait.p95)}${msCell(g.net.median)}${mutedCell(msChange(g.wait.median, g.previous_median))}</tr>`).join(""),
    an.first ? `<div class="muted" style="font-size:12px">${fmtInt(an.first)} line${an.first === 1 ? "" : "s"} written first, answering nothing.</div>` : "") : "";
  return tiles + lines + wait + services + kinds + answers;
}

// v5.22 (the owner: «аналіз структури промпта … і динаміка»): an answer's prompt by its parts
const PART_LABEL = {canon: "Canon", life: "Life so far", world: "Place and time", memories: "Day memories", plans: "Plans",
  today: "Today", mood: "Mood of the day", thoughts: "Thoughts", facts: "Facts", agora_today: "Agora today",
  recall: "Recall (RAG)", talk: "Talk summaries", summary: "Last session", brief: "Brief and skills", voice: "Voice tags",
  rules: "Rules", history: "History", move: "Move", asked: "Asked before", pastlife: "Past life", nudge: "Nudge",
  rules_extra: "Creature rules", discretion: "Discretion"};
const partName = (k) => k === "other" ? "Other" : PART_LABEL[k] || k;
function structureHtml(st, d) {
  // the 7 largest parts by colour, the rest as «Other» (a fixed slot each, never more hues than the palette)
  const W = chartW(), b = d.buckets, per = d.by_hour ? "an hour" : "a day";
  const top = st.parts.slice(0, 7).map((p) => p.part), rest = st.parts.slice(7);
  const color = (k) => k === "other" ? "var(--muted)" : `var(--viz-${top.indexOf(k) + 1})`;
  const keys = rest.length ? [...top, "other"] : top;
  const parts = b.map((_, i) => Object.fromEntries([...top.map((k) => [k, st.parts.find((p) => p.part === k).series[i] || 0]),
    ...(rest.length ? [["other", rest.reduce((sum, p) => sum + (p.series[i] || 0), 0)]] : [])]));
  const chart = anCard(`Prompt structure · ${st.kind}`, `the mean tokens a call by part, ${per} · ${fmtInt(st.calls)} calls`,
    svgStackedBars({days: b, keys, parts, line: [], fmt: (v) => fmtM(Math.round(v)), W, color, label: `Prompt structure, ${st.kind}`,
      tip: (i) => [tipBucket(b[i]), ...keys.filter((k) => parts[i][k]).map((k) => `${partName(k)} ${fmtM(Math.round(parts[i][k]))}`)].join("\n")}) +
    legend(keys.map((k) => [partName(k), color(k)])));
  const table = anTable(`Parts · ${st.kind}`, [["part"], ["tokens a call", 1], ["share", 1], ["vs previous", 1]],
    st.parts.map((p) => `<tr><td>${esc(partName(p.part))}</td>${tokCell(p.tokens)}<td class="r">${p.share == null ? "—" : `${(p.share * 100).toFixed(0)}%`}</td>${
      mutedCell(tokChange(p.tokens, p.previous_tokens))}</tr>`).join(""),
    `<div class="muted" style="font-size:12px">Each call's parts are kept in characters and shared out over its own prompt tokens · ${esc(fmtM(st.tokens))} tokens a call in all.</div>`);
  return chart + table;
}

function anPromptsHtml(d) {
  const pr = d.prompts, W = chartW(), b = d.buckets, per = d.by_hour ? "an hour" : "a day";
  if (!pr.services.length) return anEmpty("scroll", "No call in this period reported its prompt's tokens");
  const calls = pr.services.reduce((sum, x) => sum + x.calls, 0);
  const mean = calls ? Math.round(pr.services.reduce((sum, x) => sum + x.mean * x.calls, 0) / calls) : null;
  const top = pr.kinds[0];
  const tiles = anTiles([
    ["Mean prompt", `${fmtM(mean)} tokens`, `a call · ${fmtInt(calls)} calls`],
    ["Largest prompt", `${fmtM(Math.max(...pr.services.map((x) => x.max || 0)))} tokens`, "one call"],
    ["Longest kind", top ? top.kind : "—", top ? `${fmtM(top.mean)} tokens a call` : ""],
  ]);
  const lines = anCard("Prompt length", `each service's mean ${per}, in tokens`,
    svgLines({days: b, fmt: (v) => fmtM(Math.round(v)), W, series: pr.services.map((s) => ({label: svcName(s.service), color: svcColor(s.service), values: s.series})),
      tip: (i) => [tipBucket(b[i]), ...pr.services.filter((s) => s.series[i] != null).map((s) => `${svcName(s.service)} ${fmtM(s.series[i])}`)].join("\n")}) +
    legend(pr.services.map((s) => [svcName(s.service), svcColor(s.service), "ln"])));
  const cells = (x) => nCell(x.calls) + tokCell(x.mean) + tokCell(x.max) + mutedCell(tokChange(x.mean, x.previous_mean));
  const head = [["calls", 1], ["mean", 1], ["max", 1], ["vs previous", 1]];
  const services = anTable("Services", [["service"], ["trend"], ...head],
    pr.services.map((s) => caretRows("prompts", s, (x) => `<td>${svgSparkline(x.series.map((v) => v || 0), svcColor(x.service))}</td>` + cells(x),
                                     (m) => "<td></td>" + cells(m))).join(""));
  const kinds = anTable("What it was for", [["kind"], ...head], pr.kinds.map((k) => `<tr><td class="kind">${esc(k.kind)}</td>${cells(k)}</tr>`).join(""));
  const agents = pr.agents.length > 1 ? anTable("Agents", [["agent"], ...head], pr.agents.map((x) => `<tr><td>${esc(agentName(x.agent))}</td>${cells(x)}</tr>`).join("")) : "";
  const structure = (pr.structure || []).slice(0, 3).map((st) => structureHtml(st, d)).join("")
    || anEmpty("scroll", "The prompt's parts are kept from v5.22 on — none yet in this period");
  return tiles + structure + lines + services + kinds + agents;
}

const MEDIA_COLOR = {photos: "var(--viz-1)", videos: "var(--viz-2)"};
function anMediaHtml(d) {
  const m = d.media, W = chartW(), b = d.buckets, per = d.by_hour ? "an hour" : "a day";
  const cost = m.cost.photos == null || m.cost.videos == null ? null : m.cost.photos + m.cost.videos;
  const tiles = anTiles([
    ["Photos", fmtInt(m.photos), `${m.photos_per_hour.toFixed(2)} an hour · her selfies with them`],
    ["Videos", fmtInt(m.videos), `${m.videos_per_hour.toFixed(2)} an hour · her кружечки with them`],
    ["Cost", fmtCost(cost), `photos ${fmtCost(m.cost.photos)} · videos ${fmtCost(m.cost.videos)}`],
  ]);
  if (!m.photos && !m.videos) return tiles + anEmpty("chart-bar", "No photos or videos in this period");
  const chart = anCard(`Photos and videos ${per}`, m.frames ? `a video's first frame (${fmtInt(m.frames)}) counts with its video, never as a photo` : "",
    svgStackedBars({days: b, keys: ["photos", "videos"], parts: m.series, line: [], fmt: (v) => Number.isInteger(v) ? fmtInt(v) : "", W,
      color: (k) => MEDIA_COLOR[k], label: "Photos and videos",
      tip: (i) => `${tipBucket(b[i])} · ${m.series[i].photos} photos · ${m.series[i].videos} videos`}) +
    legend([["Photos", MEDIA_COLOR.photos], ["Videos", MEDIA_COLOR.videos]]));
  return tiles + chart;
}

// ── the CSV: the period's atomic rows, made in the browser from the data already here ───────────────────────────
function csvField(v) {
  let s = v == null ? "" : String(v);
  if (/^[=+\-@]/.test(s)) s = `'${s}`;                       // a spreadsheet never runs a cell as a formula
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}
const analyticsCsv = (d) => [CSV_HEAD, ...d.rows.map((r) => CSV_HEAD.map((k) => r[k]))].map((row) => row.map(csvField).join(",")).join("\r\n") + "\r\n";
function downloadCsv() {
  const d = S.an.data;
  if (!d?.rows?.length) return;
  const url = URL.createObjectURL(new Blob([analyticsCsv(d)], {type: "text/csv"}));
  const link = document.createElement("a");
  link.href = url; link.download = `agora-usage-${d.agent || "all"}-${d.since}-${d.until}.csv`;
  document.body.appendChild(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}
// review #3: Chromium fires `change` on a date field at each keystroke that leaves a whole date, and the re-render
// dropped the year being typed — a date waits until the typing stops, and a year before 2000 is never asked for
const wholeDay = (v) => ISO_DAY.test(v || "") && v >= "2000-01-01";
document.addEventListener("change", (e) => {
  const k = e.target?.dataset?.an;
  if (!k) return;
  if (k === "agent") return anChoose({agent: e.target.value});
  S.an[k] = e.target.value;
  clearTimeout(S.an.typing);
  if (wholeDay(S.an.since) && wholeDay(S.an.until)) S.an.typing = setTimeout(() => anChoose({}), 700);
});
["popstate", "hashchange"].forEach((ev) => window.addEventListener(ev, () => { readHash(); if (S.view === "analytics") loadAnalytics(); else render(); }));
window.addEventListener("resize", () => { if (S.view === "analytics") { clearTimeout(S.an.resize); S.an.resize = setTimeout(render, 150); } });

// ── the drawer: agent detail / service log ───────────────────────────────────
function drawerHtml() {
  if (!S.drawer || !S.data) return "";
  const dr = S.drawer;
  let head, tabs = "", body;
  if (dr.kind === "settings") {
    const sim = S.data.sims.find((x) => x.id === dr.id);
    head = `<div class="avatar">${icon("sliders", 20)}</div><div style="flex:1;min-width:0"><div class="drawer-title">Settings · ${esc(sim?.title || dr.id)}</div>
      <div class="drawer-sub">${esc(sim?.kind || "")} · the service's settings · a save restarts the agents it concerns</div></div>`;
    body = `<div class="drawer-body">${settingsHtml()}</div>`;
  } else if (dr.kind === "agent") {
    const a = S.data.agents.find((x) => x.name === dr.id);
    if (!a) return "";
    const [cls, label] = agentStatus(a), mem = S.data.mem[a.name];
    head = `<div class="avatar">${esc(a.display[0])}</div><div style="flex:1;min-width:0"><div class="drawer-title">${esc(a.display)}</div><div class="drawer-sub">${esc(a.role)}</div></div>${pill(cls, label)}`;
    const shown = agentTabs(a);
    if (!shown.some(([k]) => k === dr.tab)) dr.tab = "log";  // a tab the agent cannot have falls back to its log
    tabs = `<div class="tabs rule-b" role="tablist">${shown.map(([k, lbl]) => {
      const dim = !["log", "files", "settings"].includes(k) && !mem.available;  // the folder and settings need no memory
      return `<button class="tab ${dim ? "dim" : ""}" role="tab" aria-selected="${dr.tab === k}" data-act="tab" data-id="${k}">${dim ? icon("database", 13) : ""}${esc(lbl)}</button>`;
    }).join("")}</div>`;
    body = dr.tab === "log" ? logHtml(`last 200 lines · docker logs ${a.container}`) : `<div class="drawer-body">${agentTabHtml(a, mem, dr.tab)}</div>`;
  } else {
    const sim = S.data.sims.find((s) => s.id === dr.sim);
    const c = sim?.service_states?.[dr.id] || {state: "unknown"};
    const [cls, label] = containerPill(S.data.health.docker ? c.state : "unknown");
    head = `<div class="avatar">${icon("scroll", 20)}</div><div style="flex:1;min-width:0"><div class="drawer-title">Log · ${esc(dr.id)}</div>
      <div class="drawer-sub mono">${esc(c.image || "")} · container ${esc(dr.id)}</div></div>${pill(cls, label)}`;
    body = logHtml(`last 200 lines · docker logs ${dr.id}`);
  }
  const settled = S.drawerFresh ? "" : "settled";  // re-renders by polling never replay the entrance
  const fit = S.drawerFit?.key === drawerKey(dr) ? ` style="width:${S.drawerFit.w}px"` : "";  // its width, kept by poll
  return `<div class="scrim ${settled}" data-act="close"></div><aside class="drawer ${settled}"${fit} role="dialog" aria-modal="true">
    <div class="drawer-head">${head}<button class="btn btn-ghost btn-icon" style="width:34px;height:34px;color:var(--muted)" data-act="close" aria-label="Close">${icon("x", 18)}</button></div>
    ${tabs}${body}</aside>`;
}

function logHtml(caption) {
  const L = S.log;
  let inner;
  if (!L.available) {
    inner = S.data.health.docker ? `<div class="muted" style="display:flex;align-items:center;gap:8px">${icon("package", 16)}Container not created — no log yet</div>`
      : `<div class="muted" style="display:flex;align-items:center;gap:8px">${icon("cube", 16)}Docker unreachable</div>`;
  } else {
    inner = L.lines.map((l, i) => `<div class="log-line ${i >= L.seen ? "new" : ""}"><span class="t">${esc(l.time)}</span><span class="src">${esc(l.source)}</span>` +
      `<span class="lvl ${esc(l.level)}">${esc(l.level)}</span><span>${esc(l.message)}</span></div>`).join("") +
      (L.follow ? `<div class="follow-line">following new lines</div>` : "");
  }
  return `<div class="log-wrap"><div class="log-bar"><span>${esc(caption)}</span>
      <button class="btn btn-secondary" data-act="follow" aria-pressed="${L.follow}" style="height:28px">${icon("arrow-line-down", 14)}Follow</button></div>
    <div class="log" id="log">${inner}</div></div>`;
}

function unavailableBox() {
  return `<div class="empty-box">${icon("database", 18)}<strong style="font-weight:500;color:var(--color-text)">Memory unavailable</strong>
    <span>state/ cannot be read — memories, plans and tokens appear as soon as it is back.</span></div>`;
}

// v5.10 — a person's day of Lviv weather, under her mood (the cat has none: no line)
function weatherLine(mem) {
  return mem.available && mem.weather ? `<div class="muted" style="font-size:12px" lang="uk">${icon("sun", 13)} ${esc(mem.weather.line)}</div>` : "";
}

// v5.11 — her latest event this week on the card, under her mood: the text (three lines at most), its day, time and kind
function lastEventLine(mem) {
  if (!mem.available) return `<div class="muted" style="font-size:13px">Memory unavailable</div>`;
  if (!mem.events) return `<div class="muted" style="font-size:13px">Events unreadable</div>`;
  const day = mem.events[0], e = day && day.events[day.events.length - 1];
  if (!e) return `<div class="muted" style="font-size:13px">Nothing has happened this week yet</div>`;
  return `<div class="today-line" lang="uk" style="display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden">${esc(e.text)}</div>
    <div class="muted" style="font-size:12px">${esc(shortDay(day.date))} · ${esc(e.time)} · ${esc(eventLabel(e))}</div>`;
}

// v5.12 — her latest thought this week on the card, under her last event: the text (three lines at most), its day,
// time and label
function lastThoughtLine(mem) {
  if (!mem.available) return `<div class="muted" style="font-size:13px">Memory unavailable</div>`;
  if (!mem.thoughts) return `<div class="muted" style="font-size:13px">Thoughts unreadable</div>`;
  const day = mem.thoughts[0], t = day && day.thoughts[day.thoughts.length - 1];
  if (!t) return `<div class="muted" style="font-size:13px">No thoughts this week yet</div>`;
  return `<div class="today-line" lang="uk" style="display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden">${esc(t.text)}</div>
    <div class="muted" style="font-size:12px">${esc(shortDay(day.date))} · ${esc(t.time)} · ${esc(thoughtLabel(t))}</div>`;
}

function moodLine(mem) {
  if (!mem.available) return `<div class="muted" style="font-size:13px">Memory unavailable</div>`;
  return mem.mood ? `<div class="today-line" lang="uk">${esc(mem.mood.resolution.split("\n")[0])}</div>`
    : `<div class="muted" style="font-size:13px">No horoscope yet — it is cast once a day</div>`;
}

// v4.4 — Claude on the subscription: model and billing, the rate-limit status, the startup auth check
function claudeLines(mem) {
  if (!mem.available) return `<div class="muted" style="font-size:13px">Memory unavailable</div>`;
  const r = mem.ratelimit || {};
  const at = (s) => s ? new Date(s * 1000).toLocaleString("en-GB", {weekday: "short", hour: "2-digit", minute: "2-digit"}) : "";
  const muted = r.muted_until && r.muted_until * 1000 > Date.now();
  const limit = muted ? (r.status === "rejected" ? `limit reached until ${at(r.muted_until)}` : `muted until ${at(r.muted_until)}`)
    : r.status ? `${r.status}${r.utilization != null ? ` · ${Math.round(r.utilization * 100)} %` : ""}${r.resets_at ? ` · resets ${at(r.resets_at)}` : ""}`
    : "no limit event yet";
  const auth = r.last_error ? `last call failed: ${r.last_error}` : !r.auth ? "auth not checked yet"
    : r.auth === "oauth" ? "OAuth ✓ (no API key)" : r.auth;
  // the design's pill: ok / warn when muted / err when rejected, blocked or failing (a dead token — review #14)
  const cls = (r.auth && r.auth !== "oauth") || r.last_error || (muted && r.status === "rejected") ? "err"
    : muted ? "warn" : r.status ? "ok" : "unknown";
  // v4.5: his news — the last one he brought and today's count
  const n = mem.news, nAt = n?.last ? new Date(n.last) : null;
  const news = n ? (nAt ? `news ${nAt.toDateString() === new Date().toDateString() ? "" : `${nAt.toLocaleDateString("en-US", {month: "short", day: "numeric"})}, `}${nAt.toLocaleTimeString("en-GB", {hour: "2-digit", minute: "2-digit"})} · ${Number(n.today)} today` : `no news yet · ${Number(n.today)} today`) : "";
  return `<div class="today-line">${esc(`claude-sdk · ${r.model || "opus"} · subscription`)}</div>
    ${news ? `<div class="muted" style="font-size:12px">${esc(news)}</div>` : ""}
    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">${pill(cls, limit)}<span class="muted" style="font-size:12px">${esc(auth)}</span></div>`;
}

// v5.1 — Hermes, the herald: «last digest 14:05 · 2 today» and the month's spoken characters against the cap
function digestLine(mem) {
  if (!mem.available) return `<div class="muted" style="font-size:13px">Memory unavailable</div>`;
  const g = mem.digest;
  if (!g) return `<div class="muted" style="font-size:13px">Digest state unreadable</div>`;
  const last = g.last ? new Date(g.last) : null;
  const time = last ? last.toLocaleTimeString("en-GB", {hour: "2-digit", minute: "2-digit"}) : "";
  const when = last && last.toDateString() !== new Date().toDateString()
    ? `${last.toLocaleDateString("en-US", {month: "short", day: "numeric"})}, ${time}` : time;
  const head = `${last ? `last digest ${when}` : "no digest yet"} · ${Number(g.today)} today`;
  const voice = g.voice === false ? "text only — no voice id"
    : `${fmtInt(g.month_chars)}${g.cap != null ? ` / ${fmtInt(g.cap)}` : ""} chars this month`;
  const full = g.cap != null && g.cap > 0 && g.month_chars >= g.cap;
  return `<div class="today-line">${esc(head)}</div>
    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">${full ? pill("warn", "monthly cap reached") : ""}<span class="muted" style="font-size:12px">${esc(voice)}</span></div>`;
}

// v5.9 (AGORA-121) — what a Gemini speaker runs on: «answers … · background …» and «voice … · emotion: N tags»
function modelLines(m) {
  const answers = m.answers === m.background ? `model ${m.answers}`
    : `answers ${m.answers}${m.thinking ? ` (thinking ${m.thinking})` : ""} · background ${m.background}`;
  const v = m.voice;
  const voice = !v ? "" : `voice ${v.model} · stability ${v.stability}${v.speed !== "1.0" && v.speed !== "1" ? ` · speed ${v.speed}` : ""}`
    + (m.emotion ? ` · emotion: ${m.emotion.tags.length} tags` : "");
  return `<div class="today-line mono" style="font-size:12px">${esc(answers)}</div>${voice ? `<div class="muted mono" style="font-size:12px">${esc(voice)}</div>` : ""}`;
}
function voiceTabHtml(a, mem) {
  const m = mem.models;
  if (!m || !m.voice) return `<p class="muted">${esc(a.display)}'s voice runs on its engine's own settings — see the Settings tab.</p>`;
  const v = m.voice;
  const rows = [["Voice model", v.model], ["Stability", v.stability], ["Speed", v.speed],
                ["Answers", m.answers + (m.thinking ? ` · thinking ${m.thinking}` : "")], ["Background", m.background]];
  const table = `<dl class="fields">${rows.map(([k, val]) => `<div><dt class="label">${esc(k)}</dt><dd class="mono">${esc(val)}</dd></div>`).join("")}</dl>`;
  if (!m.emotion) return `${table}<p class="muted" style="margin-top:14px">No emotion palette — the voice reads the words as they are.</p>`;
  const chips = m.emotion.tags.map((t) => `<code class="chip-code">${esc(t)}</code>`).join(" ");
  const how = m.emotion.performed ? "performed by her voice · never shown in the text"
    : "this voice model reads tags aloud — they are kept out of it, and out of the text";
  return `${table}<div class="label" style="margin-top:16px">Emotion · ${m.emotion.tags.length} tags</div>
    <div style="display:flex;flex-wrap:wrap;gap:6px;margin:8px 0">${chips}</div>
    <div class="muted" style="font-size:12.5px">${esc(how)}</div>`;
}

// v5.8 — Кіра's archive: «archive: 1,820 lines · 1,790 embedded»
function blocksLine(name) {
  // v5.13: Gemini's safety blocks of this agent today, only when there are any
  const u = S.data.usage, t = u && u.available ? u.per_agent[name] : null;
  if (!t || !(t.blocked_today > 0)) return "";
  return `<div style="display:flex;flex-direction:column;gap:3px"><div class="label">Blocks today</div><div class="muted" style="font-size:13px">${esc(fmtInt(t.blocked_today))} · ${esc(fmtInt(t.blocked))} in ${esc(fmtInt(u.per_day.length))} days</div></div>`;
}

function routeLine(mem) {
  // v5.21: her private answer's route — gemini, the backup until its end, or the backup by hand; the last hour's
  // blocks, today's backup answers, the blocked lines
  if (!mem.available) return "Memory unavailable";
  const r = mem.route;
  if (!r) return "Route unreadable";
  const where = r.pin === "backup" ? "backup by hand" : r.mode === "backup" && r.until ? `backup until ${r.until.slice(11, 16)}` : "gemini";
  const blocked = mem.archive ? ` · blocked ${fmtInt(mem.archive.blocked || 0)}` : "";
  return `${where} · blocks in the last hour ${fmtInt(r.blocks_hour)} · backup answers today ${fmtInt(r.answers.backup)}${blocked}`;
}

function archiveLine(mem) {
  if (!mem.available) return "Memory unavailable";
  const g = mem.archive;
  if (!g) return "Archive unreadable";
  return `archive: ${fmtInt(g.lines)} lines · ${fmtInt(g.embedded)} embedded`;
}

// v5.8 — what she knows about the owner: pin 1 always in her private prompt, pin 2 while there is room, pin 0 only
// for a recall; re-pin at once, delete after a confirmation
const PIN_LABEL = {1: "always", 2: "if room", 0: "recall only"};
function factsTabHtml(a, mem) {
  const facts = mem.facts;
  if (!facts) return `<p class="muted">Facts unreadable.</p>`;
  // AGORA-116: «Update now» — her facts from the talk so far, without waiting for the session's end
  const update = `<div style="display:flex;gap:10px;align-items:center;margin-bottom:12px">
      <button class="btn btn-primary" data-act="facts-update" ${mem.facts_pending ? "disabled" : ""}>${icon("arrow-clockwise", 14)}Update now</button>
      <span class="muted" style="font-size:12.5px">${mem.facts_pending ? "Updating — she is reading the talk so far…" : "from what you said since the last update"}</span></div>`;
  if (!facts.length) return `${update}<p class="muted">${esc(a.display)} knows no facts about you yet.</p>`;
  const rows = facts.map((f) => `<div class="rule-b" style="padding:10px 0;display:flex;gap:12px;align-items:flex-start">
      <div style="flex:1;min-width:0"><div lang="uk">${esc(f.text)}</div>
        <div class="muted mono" style="font-size:11.5px;margin-top:3px">${esc(f.source)} · ${esc(f.added || "—")}</div></div>
      <div style="display:flex;gap:4px;flex-wrap:wrap">${[1, 2, 0].map((p) => `<button class="btn ${p === f.pin ? "btn-primary" : "btn-ghost"}" data-act="fact-pin" data-id="${esc(f.id)}" data-pin="${p}" ${p === f.pin ? "disabled" : ""}>${PIN_LABEL[p]}</button>`).join("")}
        <button class="btn btn-ghost btn-icon" data-act="fact-delete" data-id="${esc(f.id)}" title="Delete" aria-label="Delete this fact">${icon("trash", 14)}</button></div></div>`).join("");
  return `${update}<div class="muted" style="font-size:12.5px;margin-bottom:12px">${facts.length} facts · only her private chat sees them · a change counts at her next answer</div>${rows}`;
}
async function updateFacts(agent) {
  try {
    await send("POST", `/api/agents/${encodeURIComponent(agent)}/facts/update`);
    showToast("ok", "Update asked — new facts in under a minute");
  } catch (err) {
    if (err instanceof Unauthorized) return signOut(true);
    showToast("err", `Update failed: ${err.message}`);
  }
  await refreshMemory();
}
async function changeFact(agent, id, pin) {
  try {
    if (pin === null) await send("DELETE", `/api/agents/${encodeURIComponent(agent)}/facts/${encodeURIComponent(id)}`);
    else await send("PUT", `/api/agents/${encodeURIComponent(agent)}/facts/${encodeURIComponent(id)}`, {pin});
    showToast("ok", pin === null ? "Fact deleted" : "Fact re-pinned");
  } catch (err) {
    if (err instanceof Unauthorized) return signOut(true);
    showToast("err", `Change failed: ${err.message}`);
  }
  await refreshMemory();
}

// v4.3 — the cat's past life and initiative: «93 theses · last nudge 14:05 · 2 today»
function pastLifeLine(mem) {
  if (!mem.available) return "";
  const parts = [];
  if (mem.pastlife) parts.push(`${Number(mem.pastlife.theses)} theses`);
  if (mem.nudge) {
    const last = mem.nudge.last ? new Date(mem.nudge.last) : null;
    const time = last ? last.toLocaleTimeString("en-GB", {hour: "2-digit", minute: "2-digit"}) : "";
    // another day's nudge carries its date, so it never reads as today's (v4.3 review #10)
    const when = last && last.toDateString() !== new Date().toDateString()
      ? `${last.toLocaleDateString("en-US", {month: "short", day: "numeric"})}, ${time}` : time;
    parts.push(last ? `last nudge ${when}` : "no nudge yet");
    parts.push(`${Number(mem.nudge.today)} today`);
  }
  return esc(parts.join(" · "));
}

function moodTabHtml(mem) {
  const past = mem.pastlife || mem.nudge ? `<div class="meta-line" style="margin-bottom:10px">${pastLifeLine(mem)}</div>` : "";
  if (!mem.mood) return `${past}<p class="muted">No horoscope yet — it is cast once a day, before the first reply.</p>`;
  const rhythms = mem.mood.biorhythms.map((c) => `<li><span class="mono">${esc(c.name)}</span> ${c.value >= 0 ? "+" : ""}${c.value.toFixed(2)} · ${esc(c.label)}</li>`).join("");
  const weather = mem.weather ? `<div class="meta-line" lang="uk">${icon("sun", 14)}${esc(mem.weather.line)}</div>` : "";
  return `${past}<div class="meta-line">${icon("clock", 14)}${esc(mem.mood.date)}</div>${weather}
    <p class="read" lang="uk">${esc(mem.mood.resolution)}</p>
    ${rhythms ? `<div class="label" style="margin-top:14px">Biorhythms</div><ul class="plain">${rhythms}</ul>` : ""}
    <details data-keep="mood:${esc(mem.mood.date)}" ${S.openDetails[`mood:${mem.mood.date}`] ? "open" : ""} style="margin-top:14px"><summary class="muted">The full reading</summary><p class="read" lang="uk" style="white-space:pre-wrap">${esc(mem.mood.reading)}</p></details>`;
}

// v5.11 — what happened to her: by day, newest first; the kind as a label, her story's and the news marked by source
const EVENT_LABEL = {everyday: "everyday", joyful: "joyful", inspiring: "inspiring", heavy: "heavy", story: "story"};
const eventLabel = (e) => e.source === "news" ? `news · ${e.kind}` : e.source === "rolled" ? EVENT_LABEL[e.kind] || e.kind : `${e.source}`;
function eventsTabHtml(a, mem) {
  const days = mem.events;
  if (!days) return `<p class="muted">Events unreadable.</p>`;
  if (!days.length) return `<p class="muted">Nothing has happened to ${esc(a.display)} this week yet — events fall in her waking hours.</p>`;
  return days.map((d) => `<div class="section-label" style="margin:14px 0 6px">${esc(longDay(d.date))}</div>` + d.events.map((e) => {
    const label = eventLabel(e);
    const link = e.link && /^https:\/\//.test(e.link)
      ? ` <a href="${esc(e.link)}" target="_blank" rel="noopener noreferrer" class="muted" style="font-size:12px">source</a>` : "";
    return `<div class="rule-b" style="padding:8px 0;display:flex;gap:12px;align-items:flex-start">
      <span class="mono muted" style="font-size:12px;min-width:42px">${esc(e.time)}</span>
      <span class="kind-tag" style="white-space:nowrap">${esc(label)}</span>
      <div style="flex:1;min-width:0" lang="uk">${esc(e.text)}${link}</div></div>`;
  }).join("")).join("");
}

// v5.12 — what she read and thought: by day, newest first; a news thought with its title and source link
const THOUGHT_SOURCE = {zaxid: "Zaxid.net", guardian: "The Guardian", private: "alone", agora: "Agora"};
const thoughtLabel = (t) => `${t.kind} · ${THOUGHT_SOURCE[t.source] || t.source}`;
function thoughtsTabHtml(a, mem) {
  const days = mem.thoughts;
  if (!days) return `<p class="muted">Thoughts unreadable.</p>`;
  if (!days.length) return `<p class="muted">${esc(a.display)} has had no thoughts this week yet — she reads every few hours and thinks over her talks.</p>`;
  return days.map((d) => `<div class="section-label" style="margin:14px 0 6px">${esc(longDay(d.date))}</div>` + d.thoughts.map((t) => {
    const link = t.link && /^https:\/\//.test(t.link)
      ? ` <a href="${esc(t.link)}" target="_blank" rel="noopener noreferrer" class="muted" style="font-size:12px">source</a>` : "";
    const title = t.kind === "news" && t.title ? `<div class="muted" style="font-size:12px" lang="${t.source === "guardian" ? "en" : "uk"}">${esc(t.title)}</div>` : "";
    return `<div class="rule-b" style="padding:8px 0;display:flex;gap:12px;align-items:flex-start">
      <span class="mono muted" style="font-size:12px;min-width:42px">${esc(t.time)}</span>
      <span class="kind-tag" style="white-space:nowrap">${esc(thoughtLabel(t))}</span>
      <div style="flex:1;min-width:0">${title}<div lang="uk">${esc(t.text)}${link}</div></div></div>`;
  }).join("")).join("");
}

// v5.20 — her private chat in layers: the summaries by level, newest first, each with its closed lines' count only
const TALK_LEVELS = [["hour", "Hours"], ["4h", "Four hours"], ["week", "Weeks"]];
function talkSpan(r) {
  const s = new Date(r.start), e = new Date(r.end);
  const day = s.toLocaleDateString("en-US", {weekday: "short", month: "short", day: "numeric"});
  const hm = (d) => d.toTimeString().slice(0, 5);
  return r.level === "week" ? `week of ${day}` : `${day} · ${hm(s)}–${hm(e)}`;
}
function talkTabHtml(a, mem) {
  const rows = mem.talk;
  if (!rows) return `<p class="muted">Talk unreadable.</p>`;
  if (!rows.length) return `<p class="muted">${esc(a.display)}'s private chat has no summaries yet — each hour is written once it is over.</p>`;
  return TALK_LEVELS.map(([level, title]) => {
    const mine = rows.filter((r) => r.level === level);
    if (!mine.length) return "";
    return `<div class="section-label" style="margin:14px 0 6px">${esc(title)}</div>` + mine.map((r) => {
      const notes = [r.closed_lines ? `${r.closed_lines} closed` : "", r.left_out ? `${r.left_out} left out` : ""].filter(Boolean);
      return `<div class="rule-b" style="padding:8px 0;display:flex;gap:12px;align-items:flex-start">
      <span class="mono muted" style="font-size:12px;min-width:150px">${esc(talkSpan(r))}</span>
      <div style="flex:1;min-width:0"><div lang="uk">${r.text ? esc(r.text) : `<span class="muted">—</span>`}</div>${
        notes.length ? `<div class="muted" style="font-size:12px">${esc(notes.join(" · "))}</div>` : ""}</div></div>`;
    }).join("");
  }).join("");
}

function agentTabHtml(a, mem, tab) {
  if (tab === "files") return filesTabHtml(a);
  if (tab === "settings") return `<div class="muted" style="font-size:12.5px;margin-bottom:12px">${esc(a.display)}'s own settings, whatever the service · a save restarts ${esc(a.display)}</div>${settingsHtml()}`;
  if (!mem.available) return unavailableBox();
  if (tab === "mood") return moodTabHtml(mem);
  if (tab === "events") return eventsTabHtml(a, mem);
  if (tab === "thoughts") return thoughtsTabHtml(a, mem);
  if (tab === "talk") return talkTabHtml(a, mem);
  if (tab === "prompt") return promptTabHtml(a);
  if (tab === "facts") return factsTabHtml(a, mem);
  if (tab === "voice") return voiceTabHtml(a, mem);
  if (tab === "session") {
    const state = a.container_state?.state;
    const stopped = S.data.health.docker && ["stopped", "missing"].includes(state) && !S.busy[a.container];
    const forget = `<div class="rule-t" style="margin-top:22px;padding-top:16px;display:flex;align-items:center;gap:12px;flex-wrap:wrap">
      <button class="btn btn-danger" data-act="ask" data-action="forget" data-kind="agent" data-id="${esc(a.name)}" ${stopped && mem.summary ? "" : "disabled"}>${icon("eraser", 14)}Forget last session</button>
      <span class="muted" style="font-size:12px">${stopped ? "Deletes only the last-session summary; day memories stay." : "Stopped agents only"}</span></div>`;
    if (!mem.summary) return `<p class="muted">No summary — the next one is written when a session ends.</p>${forget}`;
    const at = new Date(mem.summary.written_at);
    return `<div class="meta-line">${icon("clock", 14)}written ${esc(at.toLocaleDateString("en-US", {month: "long", day: "numeric"}))} at ${esc(at.toLocaleTimeString("en-GB", {hour: "2-digit", minute: "2-digit"}))} · ${mem.summary.words} words</div>
      <p class="read" lang="uk">${esc(mem.summary.text)}</p>${forget}`;
  }
  if (tab === "memory") {
    const digests = [["year", "Year"], ["month", "Month"], ["week", "Week"]].map(([k, lbl]) => {
      const dg = mem.digests[k];
      return `<div class="digest rule-b"><span class="label">${lbl}</span><div>${dg ? `<div class="muted mono" style="font-size:12px">${esc(dg.period)}</div><div class="excerpt" lang="uk">${esc(dg.text.slice(0, 220))}${dg.text.length > 220 ? "…" : ""}</div>`
        : `<span class="muted" style="font-size:13px">not composed yet</span>`}</div></div>`;
    }).join("");
    const days = mem.days.length ? mem.days.map((d, i) => {
      const open = S.expandedDays[`${a.name}:${d.date}`] ?? i === 0;
      return `<div><button class="day-row" data-act="day" data-id="${esc(`${a.name}:${d.date}`)}" data-open="${open}" aria-expanded="${open}">${icon(open ? "caret-down" : "caret-right", 14)}
        <span class="d">${esc(longDay(d.date).split(" · ")[0])}</span><span class="muted" style="font-size:13px">${esc(longDay(d.date).split(" · ")[1])}</span><span class="w">${d.words} words</span></button>
        ${open ? `<div class="day-text" lang="uk">${esc(d.text)}</div>` : ""}</div>`;
    }).join("") : `<p class="muted">No day memories yet.</p>`;
    return `<div class="section-label" style="margin-bottom:6px">Digests</div>${digests}<div class="section-label" style="margin:18px 0 6px">Days</div>${days}`;
  }
  if (tab === "plans") {
    const anyDev = Object.values(mem.plans).some((p) => p?.items.some((it) => it.deviation));
    return `<div class="plans">${[["year", "Year"], ["month", "Month"], ["week", "Week"], ["day", "Day"]].map(([k, lbl]) => {
      const p = mem.plans[k];
      return `<div class="plan-box"><div style="display:flex;align-items:baseline;gap:8px"><span class="label">${lbl}</span><span class="muted mono" style="font-size:12px">${esc(p?.period || "")}</span></div>
        ${p ? `<ul lang="uk">${p.items.map((it) => `<li>${esc(it.text)}${it.deviation ? `<span class="deviation" title="This plan departs from the character’s life story">deviation</span>` : ""}</li>`).join("")}</ul>`
          : `<span class="muted" style="font-size:13px">not planned yet</span>`}</div>`;
    }).join("")}</div>${anyDev ? `<div class="meta-line" style="margin-top:14px">${icon("eye-slash", 14)}“deviation” marks a plan that departs from the character’s life story. Only you see it — never the characters.</div>` : ""}`;
  }
  if (tab === "today") {
    if (!mem.today) return `<p class="muted">No today block yet — it is written hourly while the agent runs.</p>`;
    return `<div class="meta-line">${icon("clock", 14)}updated at ${String(mem.today.hour).padStart(2, "0")}:00 · refreshed hourly</div>
      <p class="read lg" lang="uk" style="max-width:62ch;white-space:pre-line">${esc(mem.today.text)}</p>`;
  }
  if (tab === "tokens") {
    const u = S.data.usage;
    if (!u.available) return unavailableBox();
    const rows = u.rows.filter((r) => r.agent === a.name);
    const t = u.per_agent[a.name];
    if (!t || !t.calls) return `<p class="muted">No data yet</p>`;
    const byKind = {};
    rows.forEach((r) => { const k = byKind[r.kind] ||= {calls: 0, input: 0, output: 0, characters: 0, cost: null}; k.calls += r.calls; k.input += r.input; k.output += r.output; k.characters += r.characters || 0; if (r.cost != null) k.cost = (k.cost ?? 0) + r.cost; });
    const chars = rows.some((r) => r.characters), cc = (n) => chars ? `<td class="r">${n ? fmtInt(n) : "—"}</td>` : "";
    const max = Math.max(1, ...u.per_day.map((d) => d.agents[a.name] || 0));
    return `<div class="usage-sum" style="margin-bottom:14px"><div><div class="big-num">${fmtM(t.total)} tokens</div><div class="muted num" style="font-size:12px">${fmtInt(t.calls)} calls${u.priced ? costSuffix(t.cost) : ""}</div></div>
      <div><div class="bars">${u.per_day.map((d) => `<div><span class="a" style="height:${((d.agents[a.name] || 0) / max) * 100}%"></span></div>`).join("")}</div>
      <div class="bar-labels">${u.per_day.map((d) => `<span class="${d.day === u.until ? "today" : ""}">${esc(shortDay(d.day))}</span>`).join("")}</div></div></div>
      <table class="table" style="min-width:0"><thead><tr><th>kind</th><th class="r">calls</th><th class="r">input</th><th class="r">output</th>${chars ? `<th class="r">chars</th>` : ""}${u.priced ? `<th class="r">cost $</th>` : ""}</tr></thead>
      <tbody>${kindsOf(byKind).map((k) => `<tr><td class="kind">${k}</td><td class="r">${fmtInt(byKind[k].calls)}</td><td class="r">${fmtInt(byKind[k].input)}</td><td class="r">${fmtInt(byKind[k].output)}</td>${cc(byKind[k].characters)}${u.priced ? `<td class="r">${byKind[k].cost == null ? "—" : byKind[k].cost.toFixed(4)}</td>` : ""}</tr>`).join("")}</tbody>
      <tfoot><tr class="grand"><td>total</td><td class="r">${fmtInt(t.calls)}</td><td class="r">${fmtInt(t.input)}</td><td class="r">${fmtInt(t.output)}</td>${cc(t.characters)}${u.priced ? `<td class="r">${t.cost == null ? "—" : fmtUsd(t.cost)}</td>` : ""}</tr></tfoot></table>`;
  }
  return "";
}

// ── v4.7: settings — the schema's non-secret settings; a save restarts the agents they concern ─────────────
const SOURCE_LABEL = {default: "default", env: "server .env", panel: "panel"};
// AGORA-078 (the owner, 2026-10-11): settings under their service — a simulation's on its card, an agent's own in
// its drawer (a future portal brings its own card)
// the path the open drawer's settings come from — a slow load for another drawer is never shown here (078 review #2)
function settingsPath() {
  if (S.drawer?.kind === "settings") return `/api/simulations/${encodeURIComponent(S.drawer.id)}/settings`;
  if (S.drawer?.kind === "agent" && S.drawer.tab === "settings") return `/api/agents/${encodeURIComponent(S.drawer.id)}/settings`;
  return null;
}
async function loadSettings(path) {
  try {
    const view = await api(path);
    if (settingsPath() !== path) return false;                 // the owner moved on meanwhile
    S.settings = {path, view, edits: {}, reset: {}, busy: false};
    return true;
  } catch (err) {
    if (err instanceof Unauthorized) { signOut(true); return false; }
    if (settingsPath() === path) S.settings = {path, view: null, error: err.message, edits: {}, reset: {}, busy: false};
    return false;
  }
}
async function openSimSettings(simId) {
  S.drawer = {kind: "settings", id: simId}; S.settings = null;
  await loadSettings(`/api/simulations/${encodeURIComponent(simId)}/settings`);
  if (S.drawer?.kind !== "settings" || S.drawer.id !== simId) return;
  S.drawerFresh = true;
  render();
}
async function openAgentSettings(name) {
  S.settings = null; render();
  await loadSettings(`/api/agents/${encodeURIComponent(name)}/settings`);
  render();
}
const settingsOpen = () => S.drawer?.kind === "settings" || (S.drawer?.kind === "agent" && S.drawer.tab === "settings");
// v4.7 review #3: what the agents run with when the panel overrides nothing — the server's .env, else the default
function serverValue(r) {
  const vals = Object.values(r.effective).filter((e) => e && e.source !== "panel").map((e) => e.value);
  return vals.length && vals.every((v) => v === vals[0]) ? vals[0] : r.default;
}
const currentValue = (r) => r.override ?? serverValue(r);
function pendingSettings() {
  const st = S.settings;
  if (!st) return {names: [], agents: []};
  const rows = Object.fromEntries(st.view.settings.map((r) => [r.name, r]));
  const names = [...Object.keys(st.edits).filter((n) => !st.reset[n] && String(st.edits[n]).trim() !== String(currentValue(rows[n]))),
                 ...Object.keys(st.reset).filter((n) => rows[n].override != null)];
  const agents = [...new Set(names.flatMap((n) => rows[n].agents))];
  return {names: [...new Set(names)], agents};
}
function nowLine(r) {
  const vals = Object.entries(r.effective);
  if (!vals.length) return "";
  const groups = {};
  for (const [agent, e] of vals) {
    const key = e ? `${e.value} · ${SOURCE_LABEL[e.source] || e.source}` : "unknown";
    (groups[key] = groups[key] || []).push(S.data.agents.find((a) => a.name === agent)?.display || agent);
  }
  const keys = Object.keys(groups);
  return keys.length === 1 && vals.length > 1 ? `runs: ${keys[0]}` : `runs: ${keys.map((k) => `${k} (${groups[k].join(", ")})`).join("; ")}`;
}
function settingField(r) {
  const st = S.settings, resetting = st.reset[r.name];
  const value = st.edits[r.name] ?? (resetting ? serverValue(r) : currentValue(r));
  const attrs = `data-setting="${esc(r.name)}" aria-label="${esc(r.name)}" ${resetting ? "disabled" : ""}`;
  let input;
  if (r.kind === "choice") {
    input = `<select class="input" ${attrs}>${r.choices.map((c) => `<option value="${esc(c)}" ${c === value ? "selected" : ""}>${esc(c)}</option>`).join("")}</select>`;
  } else if (r.kind === "int" || r.kind === "float") {
    input = `<input class="input" type="number" inputmode="decimal" step="${r.kind === "int" ? 1 : 0.01}" ${r.low != null ? `min="${r.low}"` : ""} ${r.high != null ? `max="${r.high}"` : ""} value="${esc(value)}" ${attrs}>`;
  } else {
    input = `<input class="input" type="text" ${r.kind === "hours" ? 'placeholder="HH-HH"' : ""} value="${esc(value)}" ${attrs}>`;
  }
  const mark = resetting ? `<span class="pill unknown">reset → server value</span><button class="btn btn-ghost" data-act="set-undo" data-id="${esc(r.name)}">Undo</button>`
    : r.override != null ? `<span class="pill ok">panel</span><button class="btn btn-ghost" data-act="set-reset" data-id="${esc(r.name)}" title="Back to the server value">Reset</button>` : "";
  return `<div class="field" style="margin-bottom:14px">
    <label>${esc(r.description)} <span class="mono muted" style="font-size:11px">${esc(r.name)}</span></label>
    <div style="display:flex;gap:8px;align-items:center">${input}${r.unit ? `<span class="muted" style="font-size:12px">${esc(r.unit)}</span>` : ""}${mark}</div>
    <div class="muted" style="font-size:12px;margin-top:4px">default ${esc(r.default)}${nowLine(r) ? ` · ${esc(nowLine(r))}` : ""}</div></div>`;
}
function settingsHtml() {
  const st = S.settings;
  if (!st) return `<div class="muted">Loading…</div>`;
  if (st.error) return `<div class="notice err" role="status">${icon("warning-circle", 16)}Settings unavailable: ${esc(st.error)}
    <button class="btn btn-ghost" data-act="settings-retry">Retry</button></div>`;  // 078 review #3: never «Loading…» forever
  const pending = pendingSettings();
  const groups = st.view.groups.map((g) => {
    const rows = st.view.settings.filter((r) => r.group === g.id);
    if (!rows.length) return "";
    const key = `set-${g.id}`;
    return `<details class="card" data-keep="${key}" ${S.openDetails[key] === false ? "" : "open"} style="margin-bottom:12px">
      <summary class="card-title" style="cursor:pointer">${esc(g.title)}</summary><div style="margin-top:12px">${rows.map(settingField).join("")}</div></details>`;
  }).join("");
  return `${groups}<div style="position:sticky;bottom:0;padding:12px 0;background:var(--color-bg);display:flex;gap:8px;align-items:center">${saveBarHtml(pending, st.busy)}</div>`;
}
function saveBarHtml(pending, busy) {
  return `<button class="btn btn-primary" data-act="set-save" ${pending.names.length && !busy ? "" : "disabled"}>${icon("check-circle", 14)}${busy ? "Saving…" : `Save${pending.names.length ? ` (${pending.names.length})` : ""}`}</button>
    <span class="muted" style="font-size:12px">${pending.names.length ? `restarts ${esc(pending.agents.map((n) => S.data.agents.find((a) => a.name === n)?.display || n).join(", ") || "nobody")}` : "No changes"}</span>`;
}
async function saveSettings() {
  const st = S.settings, {names, agents} = pendingSettings();
  const set = {}, reset = [];
  for (const n of names) { if (st.reset[n]) reset.push(n); else set[n] = st.edits[n]; }
  // the owner, 2026-10-11: a card caught mid-restart read «stopped» and invited a manual Start — while the save runs,
  // the agents it restarts show «restarting…» and their buttons wait
  const marked = agents.map((n) => S.data.agents.find((a) => a.name === n)?.container).filter(Boolean);
  for (const c of marked) S.busy[c] = "restarting… applying settings";
  st.busy = true; render();
  try {
    const res = await put(st.path, {set, reset});
    const skipped = res.skipped.map((x) => `${x.agent} (${x.why})`);
    showToast("ok", `Saved ${res.saved.join(", ") || "nothing"}${res.restarted.length ? ` · restarted ${res.restarted.join(", ")}` : ""}${skipped.length ? ` · skipped ${skipped.join(", ")}` : ""}`);
    S.settings = {path: st.path, view: await api(st.path), edits: {}, reset: {}, busy: false};
  } catch (err) {
    if (err instanceof Unauthorized) return signOut(true);
    st.busy = false; showToast("err", `Not saved: ${err.message}`);
  } finally {
    for (const c of marked) delete S.busy[c];
  }
  render();
  await refresh(true);
  setTimeout(() => refresh(true), 5000);  // the last agent restarted may still be joining the room
}
// typed values live in S, so a render (a toast, a save) never loses them; a keystroke updates only the Save bar in
// place — a full redraw on blur ate the first click on Save (v4.7 review #4)
document.addEventListener("input", (e) => {
  const name = e.target?.dataset?.setting;
  if (!name || !S.settings) return;
  S.settings.edits[name] = e.target.value;
  const bar = $('[data-act="set-save"]')?.parentElement;
  if (bar) bar.innerHTML = saveBarHtml(pendingSettings(), S.settings.busy);
});

// ── v4.7: Claude's files — his own folder: list, open, download, upload, delete ─────────────────────────────
const filePath = (agent, path, q = "") => `/api/agents/${encodeURIComponent(agent)}/files/${path.split("/").map(encodeURIComponent).join("/")}${q}`;
const fmtSize = (n) => n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : n >= 1024 ? `${Math.round(n / 1024)} KB` : `${n} B`;
// v5.20 (the owner, 2026-11-02) — her last private prompt to Gemini, read when the tab opens: long, so never polled
async function loadPrompt(agent) {
  S.prompt = undefined; render();
  try { S.prompt = (await api(`/api/agents/${encodeURIComponent(agent)}/prompt`)).prompt; } catch (err) {
    if (err instanceof Unauthorized) return signOut(true);
    S.prompt = null;
  }
  render();
}
function promptTabHtml(a) {
  const P = S.prompt;
  if (P === undefined) return `<div class="muted">Loading…</div>`;
  if (P === null) return `<p class="muted">Prompt unreadable.</p>`;
  if (!P.system) return `<p class="muted">No prompt yet — ${esc(a.display)}'s next private answer to Gemini is kept here.</p>`;
  const words = (t) => (t || "").split(/\s+/).filter(Boolean).length;
  const outcome = P.outcome === "blocked" && P.block ? `Blocked · ${P.block.slice(0, 2).filter(Boolean).join(" · ")}` : P.outcome === "answered" ? "Answered" : "No answer";
  // the owner, 2026-11-02 («один скрол на кожен текст бокс»): the two boxes share the drawer's height, each scrolling on
  // its own; a caret folds one, and the other takes the whole height; a copy button each
  const block = (title, part, text) => {
    const folded = Boolean(S.promptFold?.[part]);
    return `<div class="prompt-part${folded ? " folded" : ""}"><div class="prompt-head">
      <button class="an-caret" data-act="prompt-fold" data-id="${part}" aria-expanded="${!folded}" aria-label="${folded ? "Show" : "Hide"} ${esc(title)}">${icon(folded ? "caret-right" : "caret-down", 12)}</button>
      <div class="section-label">${esc(title)} · ${words(text)} words</div>
      <button class="btn btn-ghost" style="margin-left:auto" data-act="prompt-copy" data-id="${part}">Copy</button></div>
    ${folded ? "" : `<pre class="mono prompt-box">${esc(text || "")}</pre>`}</div>`;
  };
  return `<div class="prompt-tab"><div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;flex:none">
      <span class="kind-tag">${esc(outcome)}</span><span class="muted" style="font-size:12.5px">${esc(new Date(P.at).toLocaleString("en-GB"))} · ${esc(P.model || "")}</span>
      <span style="margin-left:auto;display:flex;gap:6px"><button class="btn btn-ghost" data-act="prompt-copy" data-id="all">Copy all</button>
      <button class="btn btn-ghost" data-act="prompt-reload">Reload</button></span></div>${block("System instruction", "system", P.system)}${block("Transcript", "transcript", P.transcript)}</div>`;
}
// the panel is plain http on the LAN, where a page gets no Clipboard API: the old way (a hidden field, «copy») then
async function copyText(text) {
  try {
    if (window.isSecureContext && navigator.clipboard) { await navigator.clipboard.writeText(text); return true; }
  } catch { /* the old way below */ }
  const area = document.createElement("textarea");
  area.value = text; area.setAttribute("readonly", ""); area.style.position = "fixed"; area.style.opacity = "0";
  document.body.appendChild(area); area.select();
  let ok = false;
  try { ok = document.execCommand("copy"); } catch { ok = false; }
  area.remove();
  return ok;
}
async function copyPrompt(part) {
  const P = S.prompt;
  if (!P?.system) return;
  const text = part === "system" ? P.system : part === "transcript" ? P.transcript || "" : `${P.system}\n\n${P.transcript || ""}`;
  const label = part === "system" ? "System instruction" : part === "transcript" ? "Transcript" : "The whole prompt";
  if (await copyText(text)) showToast("ok", `${label} copied`);
  else showToast("err", "Could not copy — select the text and copy it by hand");
}
async function loadFiles(agent) {
  try {
    S.files.list = (await api(`/api/agents/${encodeURIComponent(agent)}/files`)).files;
  } catch (err) {
    if (err instanceof Unauthorized) return signOut(true);
    S.files.list = []; showToast("err", `Files unavailable: ${err.message}`);
  }
  render();
}
async function openFile(agent, path) {
  try { S.files.open = await api(filePath(agent, path)); } catch (err) {
    if (err instanceof Unauthorized) return signOut(true);
    return showToast("err", `${path}: ${err.message.includes("415") ? "not text — download it" : err.message.includes("413") ? "too large to show — download it" : err.message}`);
  }
  render();
}
async function downloadFile(agent, path) {
  try {
    const url = URL.createObjectURL(await api(filePath(agent, path, "?download=1"), "blob"));
    const link = document.createElement("a");
    link.href = url; link.download = path.split("/").pop();
    document.body.appendChild(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  } catch (err) {
    if (err instanceof Unauthorized) return signOut(true);
    showToast("err", `Download failed: ${err.message}`);
  }
}
async function uploadFile(agent, file, path, overwrite = false) {
  S.files.busy = true; render();
  try {
    await send("PUT", filePath(agent, path, overwrite ? "?overwrite=1" : ""), file, true);
    showToast("ok", `${path} ${overwrite ? "replaced" : "uploaded"} — Claude can read it`);
  } catch (err) {
    if (err instanceof Unauthorized) return signOut(true);
    if (err.status === 409 && !overwrite && err.message.startsWith("exists")) { S.files.busy = false; S.dialog = {action: "replace", kind: "file", id: path, file, fresh: true}; return render(); }
    showToast("err", `Upload failed: ${err.message}`);
  }
  S.files.busy = false;
  await loadFiles(agent);
}
async function deleteFile(agent, path) {
  try {
    await send("DELETE", filePath(agent, path));
    if (S.files.open?.path === path) S.files.open = null;
    showToast("ok", `${path} deleted`);
  } catch (err) {
    if (err instanceof Unauthorized) return signOut(true);
    showToast("err", `Delete failed: ${err.message}`);
  }
  await loadFiles(agent);
}
function filesTabHtml(a) {
  const F = S.files;
  if (F.list === null) return `<div class="muted">Loading…</div>`;
  const upload = `<div class="card" style="margin-bottom:14px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
    <input class="input" style="flex:1;min-width:140px;letter-spacing:0" type="text" placeholder="folder (optional), e.g. for-claude" value="${esc(F.prefix)}" data-files-prefix aria-label="Folder for the upload">
    <button class="btn btn-secondary" data-act="file-pick" ${F.busy ? "disabled" : ""}>${icon("upload", 14)}${F.busy ? "Uploading…" : "Upload a file"}</button>
    <span class="muted" style="font-size:12px;width:100%">Up to 5 MB. Claude reads it with his tools in /workspace.</span></div>`;
  const opened = F.open ? `<div class="card" style="margin-bottom:14px"><div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
      <span class="mono" style="flex:1;min-width:0;overflow-wrap:anywhere">${esc(F.open.path)}</span><button class="btn btn-ghost btn-icon" data-act="file-close" aria-label="Close">${icon("x", 14)}</button></div>
      <pre class="mono" style="white-space:pre-wrap;overflow-wrap:anywhere;font-size:12.5px;margin:0">${esc(F.open.text)}</pre></div>` : "";
  const rows = F.list.length ? F.list.map((f) => `<div class="rule-b" style="display:flex;gap:8px;align-items:center;padding:8px 0">
      <span style="flex:1;min-width:0"><span class="mono" style="overflow-wrap:anywhere">${esc(f.path)}</span><span class="muted" style="font-size:12px;display:block">${esc(fmtSize(f.size))} · ${esc(new Date(f.modified).toLocaleString("en-GB"))}</span></span>
      <button class="btn btn-ghost" data-act="file-open" data-id="${esc(f.path)}">Open</button>
      <button class="btn btn-ghost btn-icon" data-act="file-download" data-id="${esc(f.path)}" title="Download" aria-label="Download ${esc(f.path)}">${icon("arrow-line-down", 14)}</button>
      <button class="btn btn-ghost btn-icon" data-act="file-delete" data-id="${esc(f.path)}" title="Delete" aria-label="Delete ${esc(f.path)}">${icon("trash", 14)}</button></div>`).join("")
    : `<div class="muted" style="display:flex;align-items:center;gap:8px">${icon("folder", 16)}Empty — nothing written yet</div>`;
  return `${upload}${opened}<div>${rows}</div>`;
}
document.addEventListener("input", (e) => { if (e.target?.dataset && "filesPrefix" in e.target.dataset) S.files.prefix = e.target.value.trim().replace(/^\/+|\/+$/g, ""); });
// the file picker lives outside #app: the 10 s redraw replaced an input inside it while the owner was choosing a
// file, and the choice landed on a detached element — nothing was ever uploaded (the owner, 2026-10-11)
let pickerEl = null;
function filePicker() {
  if (pickerEl) return pickerEl;
  pickerEl = document.createElement("input");
  pickerEl.type = "file"; pickerEl.hidden = true; pickerEl.id = "file-pick";
  pickerEl.addEventListener("change", () => {
    const file = pickerEl.files?.[0];
    if (file && S.drawer?.kind === "agent") {
      const path = S.files.prefix ? `${S.files.prefix}/${file.name}` : file.name;
      uploadFile(S.drawer.id, file, path);
    }
    pickerEl.value = "";  // the same file can be chosen again
  });
  document.body.appendChild(pickerEl);
  return pickerEl;
}

// the owner, 2026-11-02 («ширину панелі з пропертями автоматичною, щоб не було скрола вправо»): the drawer widens to
// what does not fit — its tabs, a table, its body, a log line — by just that much, never past 94% of the window; the
// width is the drawer's, kept across its tabs so it never jumps (a phone has the whole width already)
const drawerKey = (dr) => dr ? `${dr.kind}:${dr.id}` : "";
function fitDrawer() {
  const d = $(".drawer"), key = drawerKey(S.drawer);
  if (!d || window.innerWidth < 760) return;
  const over = Math.max(0, ...[...d.querySelectorAll(".tabs, .drawer-body, .table-scroll, pre")].map((el) => el.scrollWidth - el.clientWidth));
  if (over <= 1) return;
  const want = Math.min(Math.floor(window.innerWidth * 0.94), Math.ceil(d.getBoundingClientRect().width + over + 2));
  const now = S.drawerFit?.key === key ? S.drawerFit.w : 0;
  if (want > now + 1) { S.drawerFit = {key, w: want}; d.style.width = `${want}px`; }
}
function afterDrawerRender() {
  fitDrawer();
  const log = $("#log");
  if (log && S.log.follow) log.scrollTop = log.scrollHeight;
  if (log) log.addEventListener("scroll", () => {
    if (S.log.follow && log.scrollHeight - log.scrollTop - log.clientHeight > 12) { S.log.follow = false; render(); }
  }, {passive: true});
  S.log.seen = S.log.lines.length;
}

async function loadLog(redraw = true) {
  const dr = S.drawer;
  if (!dr || dr.kind === "settings" || (dr.kind === "agent" && dr.tab !== "log")) return;  // v4.7 review #8: no log there
  const path = dr.kind === "agent" ? `/api/agents/${encodeURIComponent(dr.id)}/logs?tail=200`
    : `/api/simulations/${encodeURIComponent(dr.sim)}/logs?service=${encodeURIComponent(dr.id)}&tail=200`;
  let changed = false;
  try {
    const res = await api(path);
    changed = res.available !== S.log.available || JSON.stringify(res.lines) !== JSON.stringify(S.log.lines);
    S.log.available = res.available; S.log.lines = res.lines;
  } catch (err) { if (err instanceof Unauthorized) return signOut(true); }
  if (redraw && S.drawer === dr && changed) render();  // redraw only when the log moved
  return changed;
}

async function refreshMemory(redraw = true) {
  const dr = S.drawer;
  if (!dr || dr.kind !== "agent") return;
  let changed = false;
  try {
    const mem = await api(`/api/agents/${encodeURIComponent(dr.id)}/memory`);
    changed = JSON.stringify(mem) !== JSON.stringify(S.data.mem[dr.id]);
    S.data.mem[dr.id] = mem;
  } catch (err) {
    if (err instanceof Unauthorized) return signOut(true);
  }
  if (redraw && S.drawer === dr && changed) render();
  return changed;
}

async function openDrawer(dr) {
  // fetch first, then one render: the slide-in plays once, uninterrupted by the data arriving
  S.drawer = dr; S.log = {lines: [], available: true, follow: true, seen: 0};
  S.files = {list: null, open: null, prefix: "", busy: false};  // v4.7: a fresh folder view per drawer
  S.settings = null;
  await Promise.all([loadLog(false), refreshMemory(false)]);
  if (S.drawer !== dr) return;
  S.drawerFresh = true;
  render();
}

// ── toast, theme, events, timers ─────────────────────────────────────────────
function toastHtml() {
  if (!S.toast) return "";
  return `<div class="toast ${S.toast.fresh === false ? "settled" : ""}" role="status">${icon(S.toast.kind === "ok" ? "check-circle" : "warning-circle", 18, S.toast.kind)}<span>${esc(S.toast.text)}</span>
    <button class="btn btn-ghost btn-icon" data-act="toast-close" aria-label="Dismiss">${icon("x", 14)}</button></div>`;
}
let toastTimer;
function showToast(kind, text) {
  S.toast = {kind, text, fresh: true}; render();
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { S.toast = null; render(); }, 4500);
}
function spinRefresh() { $('[data-act="refresh"] .ico')?.classList.add("spin"); }
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  store(localStorage, "agora-theme", theme);
}

// a <details> keeps its open state across the 10 s re-render (v4.2 review #10); toggle does not bubble: capture it
document.addEventListener("toggle", (e) => {
  const key = e.target?.dataset?.keep;
  if (key) S.openDetails[key] = e.target.open;
}, true);

document.addEventListener("click", (e) => {
  const el = e.target.closest("[data-act]");
  if (!el) return;
  const {act, id} = el.dataset;
  if (act === "refresh") refresh(true);
  else if (act === "theme") { applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"); render(); }
  else if (act === "signout") signOut();
  else if (act === "agent") openDrawer({kind: "agent", id, tab: "log"});
  else if (act === "svclog") openDrawer({kind: "service", id, sim: el.dataset.sim});
  else if (act === "sim-settings") openSimSettings(id);
  else if (act === "settings-retry") { const p = settingsPath(); if (p) loadSettings(p).then(render); }
  else if (act === "set-reset") { S.settings.reset[id] = true; delete S.settings.edits[id]; render(); }
  else if (act === "set-undo") { delete S.settings.reset[id]; delete S.settings.edits[id]; render(); }
  else if (act === "set-save") { if (pendingSettings().names.length) { S.dialog = {action: "save", kind: "settings", fresh: true}; render(); } }
  else if (act === "close") { S.drawer = null; S.settings = null; render(); }
  else if (act === "prompt-reload") loadPrompt(S.drawer.id);
  else if (act === "prompt-copy") copyPrompt(id);
  else if (act === "prompt-fold") { S.promptFold = {...S.promptFold, [id]: !S.promptFold?.[id]}; render(); }
  else if (act === "tab") { S.drawer.tab = id; S.log = {lines: [], available: true, follow: true, seen: 0}; render(); if (id === "log") loadLog(); if (id === "files") loadFiles(S.drawer.id); if (id === "prompt") loadPrompt(S.drawer.id); if (id === "settings") openAgentSettings(S.drawer.id); }
  else if (act === "file-open") openFile(S.drawer.id, id);
  else if (act === "file-close") { S.files.open = null; render(); }
  else if (act === "file-download") downloadFile(S.drawer.id, id);
  else if (act === "file-delete") { S.dialog = {action: "delete", kind: "file", id, fresh: true}; render(); }
  else if (act === "fact-pin") changeFact(S.drawer.id, id, Number(el.dataset.pin));
  else if (act === "facts-update") updateFacts(S.drawer.id);
  else if (act === "fact-delete") { S.dialog = {action: "delete", kind: "fact", id, fresh: true}; render(); }
  else if (act === "file-pick") filePicker().click();
  else if (act === "follow") { S.log.follow = !S.log.follow; render(); if (S.log.follow) loadLog(); }
  else if (act === "ufilter") { S.usageFilter = id; render(); }
  else if (act === "day") { S.expandedDays[id] = el.dataset.open !== "true"; render(); }
  else if (act === "scroll") { leaveAnalytics(); document.getElementById(id)?.scrollIntoView({behavior: "smooth", block: "start"}); }
  else if (act === "top") { leaveAnalytics(); $(".main")?.scrollTo({top: 0, behavior: "smooth"}); }
  else if (act === "view") openAnalytics();                                   // v5.19: Analytics
  else if (act === "dashboard") leaveAnalytics();
  else if (act === "an-range") anChoose(id === "custom" ? {range: "custom", since: anPeriod()[0], until: anPeriod()[1]} : {range: id});
  else if (act === "an-metric") { S.an.metric = id; render(); }
  else if (act === "an-tab") { S.an.tab = id; history.replaceState(null, "", anHash()); render(); }  // v5.22
  else if (act === "an-open") { S.an.open[id] = !S.an.open[id]; render(); }
  else if (act === "an-retry") loadAnalytics();
  else if (act === "an-csv") downloadCsv();
  else if (act === "toast-close") { S.toast = null; render(); }
  else if (act === "do" || act === "ask") {
    const {action, kind, sim} = el.dataset;
    if (action === "start") perform(action, kind, id, sim);       // start needs no confirmation
    else { S.dialog = {action, kind, id, sim, fresh: true}; render(); }
  } else if (act === "dialog-cancel" && e.target === el) { S.dialog = null; render(); }
  else if (act === "dialog-ok") {
    const d = S.dialog; S.dialog = null;
    if (d.kind === "settings") saveSettings();
    else if (d.kind === "fact") changeFact(S.drawer.id, d.id, null);
    else if (d.kind === "file") (d.action === "delete" ? deleteFile(S.drawer.id, d.id) : uploadFile(S.drawer.id, d.file, d.id, true));
    else perform(d.action, d.kind, d.id, d.sim);
  }
});
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  if (S.dialog) { S.dialog = null; render(); } else if (S.drawer) { S.drawer = null; render(); }
});

setInterval(() => { const el = $("#refreshed"); if (el && S.data) el.textContent = `updated ${ago((Date.now() - S.fetchedAt) / 1000)}`; }, 1000);
setInterval(() => { if (S.token && !document.hidden) refresh(); }, POLL_MS);

applyTheme(store(localStorage, "agora-theme") || "dark");
readHash();  // v5.19: a report reopens from its address
S.loading = Boolean(S.token);
render();
refresh();
