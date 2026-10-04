// Agora panel — the page (v3.3: view only). Vanilla JS, no build step, no outside requests.
// Built to specification/design/design_handoff_agora_panel/ with the owner's adoption notes
// (specification/design/README.md): English UI, the agents' own texts as-is, only what is recorded.
"use strict";

const POLL_MS = 10000;  // one tick for everything — the dashboard, an open log, an open agent's memory (owner)
const KIND_ORDER = ["reply", "summary", "plan", "day_memory", "digest", "today"];
const TABS = [["log", "Log"], ["session", "Last session"], ["memory", "Memories"], ["plans", "Plans"],
              ["today", "Today"], ["tokens", "Tokens"]];

const S = {
  token: store(sessionStorage, "agora-token"),
  data: null, fetchedAt: 0, loading: false, gateError: false,
  drawer: null,            // {kind: "agent"|"service", id, tab}
  drawerFresh: false,      // true only for the render that opens it: the slide-in plays once
  log: {lines: [], available: true, follow: true, seen: 0},
  usageFilter: "all", expandedDays: {}, toast: null,
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
async function api(path) {
  const resp = await fetch(path, {headers: {Authorization: `Bearer ${S.token}`}, cache: "no-store"});
  if (resp.status === 401) throw new Unauthorized();
  if (resp.status === 404) throw new Error(`not found: ${path}`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

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
    if (same && !logMoved && !memMoved && !manual) return;  // nothing new: the "updated N s ago" ticker says so
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
  return {running: ["ok", "running"], stopped: ["stop", "stopped"], crashed: ["err", "crashed"],
          missing: ["none", "container not created"], unknown: ["unknown", "unknown"]}[state] || ["unknown", "unknown"];
}
function agentStatus(agent) {
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

// ── render ───────────────────────────────────────────────────────────────────
function render() {
  const root = $("#app");
  if (!S.token) { root.innerHTML = gateHtml(); bindGate(); return; }
  // the page re-renders on every poll: keep each scroll area where the reader left it
  const keep = [".main", ".drawer-body", ".table-scroll", "#log"].map((sel) => [sel, $(sel)?.scrollTop ?? 0]);
  root.innerHTML = topbarHtml() + `<div class="body">${railHtml()}<main class="main"><div class="stack">${
    S.data ? dashboardHtml() : skeletonHtml()}</div></main></div>${drawerHtml()}${toastHtml()}`;
  keep.forEach(([sel, top]) => { const el = $(sel); if (el) el.scrollTop = top; });
  if (S.drawer) afterDrawerRender();
  S.drawerFresh = false;
  if (S.toast) S.toast.fresh = false;
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
      ${sims.map((s) => `<button class="rail-item" aria-current="page" data-act="top">${icon("squares-four", 16)}<span style="flex:1">${esc(s.title)}</span><span class="dot ${simHealth(s).cls}"></span></button>
        ${d.agents.filter((a) => a.simulation === s.id).map((a) => `<button class="rail-item sub" data-act="agent" data-id="${esc(a.name)}"><span style="flex:1">${esc(a.display)}</span><span class="dot ${agentStatus(a)[0]}"></span></button>`).join("")}`).join("")}
    </div>
    <div class="rail-group"><div class="section-label">System</div>
      <button class="rail-item" data-act="scroll" data-id="host-card">${icon("hard-drives", 16)}Server</button>
      <button class="rail-item" data-act="scroll" data-id="usage-card">${icon("coins", 16)}Tokens</button>
    </div>
    <div class="rail-phase">v3.3 · view only</div>
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
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">${pill(h.cls, h.label)}<span class="muted num" style="font-size:12px">${esc(latency)} · ${esc(checked)}</span></div></div>
    ${sim.health.status === "unreachable" ? `<div class="notice err" role="status">${icon("plugs", 16)}Matrix server unreachable — agents are waiting</div>` : ""}
    <div class="cols"><div class="col-services"><div class="section-label">Services</div>
      ${d.health.docker ? "" : `<div class="notice unknown">${icon("cube", 16)}Docker unreachable — container state unknown</div>`}
      ${sim.services.map((svc) => {
        const c = sim.service_states[svc] || {state: "unknown"};
        const [cls, label] = containerPill(d.health.docker ? c.state : "unknown");
        return `<div class="inset-row"><span class="svc-name">${esc(svc)}</span><span class="svc-image">${esc(c.image || "")}</span>${pill(cls, label)}
          <span class="muted num" style="font-size:12px">uptime ${esc(fmtDur(c.uptime_s))}</span>
          <span class="svc-actions"><button class="btn btn-ghost" data-act="svclog" data-sim="${esc(sim.id)}" data-id="${esc(svc)}">${icon("scroll", 15)}Log</button></span></div>`;
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
  return `${fmtInt(t.calls)} calls · ${fmtM(t.total)} tokens${u.priced ? ` · ${fmtUsd(t.cost)}` : ""}`;
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
    <div style="display:flex;flex-direction:column;gap:3px"><div class="label">Today</div>${today}</div>
    <div class="card-foot rule-t"><div class="meta">${tokens == null ? `${icon("database", 13)} Memory unavailable` : `7 days · ${esc(tokens)}`}</div>
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
  const head = (extra = "") => `<div class="usage-head"><h3 class="card-title">Tokens, last 7 days</h3>${extra}</div>`;
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
    const a = filter === "all" || filter === names[0] ? d.agents[names[0]] || 0 : 0;
    const b = filter === "all" || filter === names[1] ? d.agents[names[1]] || 0 : 0;
    return `<div title="${esc(d.day)}: ${fmtInt(a + b)} tokens"><span class="b" style="height:${(b / max) * 100}%"></span><span class="a" style="height:${(a / max) * 100}%"></span></div>`;
  }).join("")}</div><div class="bar-labels">${u.per_day.map((d) => `<span class="${d.day === u.until ? "today" : ""}">${esc(shortDay(d.day))}</span>`).join("")}</div>`;
  const legend = `<div class="legend">${agents.slice(0, 2).map((a, i) => `<span><i class="${i ? "b" : "a"}"></i>${esc(a.display)}</span>`).join("")}</div>`;
  const sorted = [...rows].sort((x, y) => y.day.localeCompare(x.day) || names.indexOf(x.agent) - names.indexOf(y.agent) ||
    KIND_ORDER.indexOf(x.kind) - KIND_ORDER.indexOf(y.kind));
  let prevDay = "";
  const body = sorted.map((r) => {
    const day = r.day === prevDay ? "" : r.day; prevDay = r.day;
    return `<tr><td class="day">${esc(day)}</td><td>${esc(r.agent)}</td><td class="kind">${esc(r.kind)}</td><td class="r">${fmtInt(r.calls)}</td>
      <td class="r">${fmtInt(r.input)}</td><td class="r">${fmtInt(r.output)}</td>${u.priced ? `<td class="r">${r.cost.toFixed(4)}</td>` : ""}</tr>`;
  }).join("");
  const foot = [...(filter === "all" ? names : [filter]).filter((n) => u.per_agent[n]).map((n) => [`total · ${n}`, u.per_agent[n], ""]), ["total", tot, "grand"]]
    .map(([lbl, t, cls]) => `<tr class="${cls}"><td colspan="3">${esc(lbl)}</td><td class="r">${fmtInt(t.calls)}</td><td class="r">${fmtInt(t.input)}</td>
      <td class="r">${fmtInt(t.output)}</td>${u.priced ? `<td class="r">${fmtUsd(t.cost)}</td>` : ""}</tr>`).join("");
  return `<section class="card usage-card" id="usage-card">${headHtml}
    <div class="usage-sum"><div><div class="big-num">${fmtM(tot.total)} tokens</div>
      <div class="muted num" style="font-size:12px">${fmtInt(tot.calls)} calls · ${fmtInt(tot.input)} in · ${fmtInt(tot.output)} out${u.priced ? ` · ${fmtUsd(tot.cost)}` : ""}</div></div>
      <div style="display:flex;gap:14px;align-items:flex-end"><div>${bars}</div>${filter === "all" ? legend : ""}</div></div>
    <div class="table-scroll"><table class="table"><thead><tr><th>day</th><th>agent</th><th>kind</th><th class="r">calls</th><th class="r">input</th><th class="r">output</th>${u.priced ? `<th class="r">cost $</th>` : ""}</tr></thead>
      <tbody>${body}</tbody><tfoot>${foot}</tfoot></table></div>
    ${u.priced ? "" : `<div class="muted" style="font-size:12px">Prices are not configured — cost is not calculated.</div>`}
  </section>`;
}

// ── the drawer: agent detail / service log ───────────────────────────────────
function drawerHtml() {
  if (!S.drawer || !S.data) return "";
  const dr = S.drawer;
  let head, tabs = "", body;
  if (dr.kind === "agent") {
    const a = S.data.agents.find((x) => x.name === dr.id);
    if (!a) return "";
    const [cls, label] = agentStatus(a), mem = S.data.mem[a.name];
    head = `<div class="avatar">${esc(a.display[0])}</div><div style="flex:1;min-width:0"><div class="drawer-title">${esc(a.display)}</div><div class="drawer-sub">${esc(a.role)}</div></div>${pill(cls, label)}`;
    tabs = `<div class="tabs rule-b" role="tablist">${TABS.map(([k, lbl]) => {
      const dim = k !== "log" && !mem.available;
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
  return `<div class="scrim ${settled}" data-act="close"></div><aside class="drawer ${settled}" role="dialog" aria-modal="true">
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

function agentTabHtml(a, mem, tab) {
  if (!mem.available) return unavailableBox();
  if (tab === "session") {
    if (!mem.summary) return `<p class="muted">No summary — the next one is written when a session ends.</p>`;
    const at = new Date(mem.summary.written_at);
    return `<div class="meta-line">${icon("clock", 14)}written ${esc(at.toLocaleDateString("en-US", {month: "long", day: "numeric"}))} at ${esc(at.toLocaleTimeString("en-GB", {hour: "2-digit", minute: "2-digit"}))} · ${mem.summary.words} words</div>
      <p class="read" lang="uk">${esc(mem.summary.text)}</p>`;
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
    rows.forEach((r) => { const k = byKind[r.kind] ||= {calls: 0, input: 0, output: 0, cost: 0}; k.calls += r.calls; k.input += r.input; k.output += r.output; k.cost += r.cost || 0; });
    const max = Math.max(1, ...u.per_day.map((d) => d.agents[a.name] || 0));
    return `<div class="usage-sum" style="margin-bottom:14px"><div><div class="big-num">${fmtM(t.total)} tokens</div><div class="muted num" style="font-size:12px">${fmtInt(t.calls)} calls${u.priced ? ` · ${fmtUsd(t.cost)}` : ""}</div></div>
      <div><div class="bars">${u.per_day.map((d) => `<div><span class="a" style="height:${((d.agents[a.name] || 0) / max) * 100}%"></span></div>`).join("")}</div>
      <div class="bar-labels">${u.per_day.map((d) => `<span class="${d.day === u.until ? "today" : ""}">${esc(shortDay(d.day))}</span>`).join("")}</div></div></div>
      <table class="table" style="min-width:0"><thead><tr><th>kind</th><th class="r">calls</th><th class="r">input</th><th class="r">output</th>${u.priced ? `<th class="r">cost $</th>` : ""}</tr></thead>
      <tbody>${KIND_ORDER.filter((k) => byKind[k]).map((k) => `<tr><td class="kind">${k}</td><td class="r">${fmtInt(byKind[k].calls)}</td><td class="r">${fmtInt(byKind[k].input)}</td><td class="r">${fmtInt(byKind[k].output)}</td>${u.priced ? `<td class="r">${byKind[k].cost.toFixed(4)}</td>` : ""}</tr>`).join("")}</tbody>
      <tfoot><tr class="grand"><td>total</td><td class="r">${fmtInt(t.calls)}</td><td class="r">${fmtInt(t.input)}</td><td class="r">${fmtInt(t.output)}</td>${u.priced ? `<td class="r">${fmtUsd(t.cost)}</td>` : ""}</tr></tfoot></table>`;
  }
  return "";
}

function afterDrawerRender() {
  const log = $("#log");
  if (log && S.log.follow) log.scrollTop = log.scrollHeight;
  if (log) log.addEventListener("scroll", () => {
    if (S.log.follow && log.scrollHeight - log.scrollTop - log.clientHeight > 12) { S.log.follow = false; render(); }
  }, {passive: true});
  S.log.seen = S.log.lines.length;
}

async function loadLog(redraw = true) {
  const dr = S.drawer;
  if (!dr || (dr.kind === "agent" && dr.tab !== "log")) return;
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

document.addEventListener("click", (e) => {
  const el = e.target.closest("[data-act]");
  if (!el) return;
  const {act, id} = el.dataset;
  if (act === "refresh") refresh(true);
  else if (act === "theme") { applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"); render(); }
  else if (act === "signout") signOut();
  else if (act === "agent") openDrawer({kind: "agent", id, tab: "log"});
  else if (act === "svclog") openDrawer({kind: "service", id, sim: el.dataset.sim});
  else if (act === "close") { S.drawer = null; render(); }
  else if (act === "tab") { S.drawer.tab = id; S.log = {lines: [], available: true, follow: true, seen: 0}; render(); if (id === "log") loadLog(); }
  else if (act === "follow") { S.log.follow = !S.log.follow; render(); if (S.log.follow) loadLog(); }
  else if (act === "ufilter") { S.usageFilter = id; render(); }
  else if (act === "day") { S.expandedDays[id] = el.dataset.open !== "true"; render(); }
  else if (act === "scroll") document.getElementById(id)?.scrollIntoView({behavior: "smooth", block: "start"});
  else if (act === "top") $(".main")?.scrollTo({top: 0, behavior: "smooth"});
  else if (act === "toast-close") { S.toast = null; render(); }
});
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && S.drawer) { S.drawer = null; render(); } });

setInterval(() => { const el = $("#refreshed"); if (el && S.data) el.textContent = `updated ${ago((Date.now() - S.fetchedAt) / 1000)}`; }, 1000);
setInterval(() => { if (S.token && !document.hidden) refresh(); }, POLL_MS);

applyTheme(store(localStorage, "agora-theme") || "dark");
S.loading = Boolean(S.token);
render();
refresh();
