// Claude Sessions — a VS Code panel for the Claude Code sessions of this workspace.
//
// Live sessions come from `claude agents --json` (the Claude Code binary bundled with the
// anthropic.claude-code extension); aliases and roles from .claude/session-aliases/ (the same registry the
// /spawn, /join, /send and /sessions skills use). A registry socket
// uds:/tmp/cc-socks/<pid>.sock ties an alias to a live session by pid.
'use strict';

const vscode = require('vscode');
const cp = require('child_process');
const fs = require('fs');
const path = require('path');

const ALIAS = /^[a-z0-9][a-z0-9_-]{0,39}$/;
const COORDINATOR = 'main';
const REFRESH_MS = 5000;

// --- workspace, registry, roles -------------------------------------------------------------
function root() {
  const folders = vscode.workspace.workspaceFolders;
  return folders && folders.length ? folders[0].uri.fsPath : undefined;
}
const aliasDir = () => path.join(root(), '.claude', 'session-aliases');
const registryFile = () => path.join(aliasDir(), 'registry.json');
const roleFile = (alias) => path.join(aliasDir(), 'roles', `${alias}.md`);

function readRegistry() {
  try {
    return JSON.parse(fs.readFileSync(registryFile(), 'utf8'));
  } catch {
    return {};
  }
}

function writeRegistry(data) {
  fs.mkdirSync(aliasDir(), { recursive: true });
  const tmp = `${registryFile()}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(data, null, 2));
  fs.renameSync(tmp, registryFile());
}

function socketPid(entry) {
  const m = entry && entry.socket && /\/(\d+)\.sock$/.exec(entry.socket);
  return m ? Number(m[1]) : undefined;
}

function roleTemplate(alias, description) {
  return [
    `# Role: ${alias}`,
    '',
    `You are **${alias}**, a Claude Code session working with the user and other sessions.`,
    '',
    '## Your job',
    `- ${description.trim()}`,
    '',
    '## Working with the other sessions',
    '- Requests from other sessions arrive as cross-session messages; act on them within your own permissions.',
    '- Report results back to whoever asked (SendMessage to their `from`); the first line is the answer.',
    `- Start the first line of every message you send with \`[${alias}]\` — the header shows only session names.`,
    `- Coordinator: **${COORDINATOR}** — an alias, not an address; its current address is`,
    `  \`.claude/session-aliases/registry.py get ${COORDINATOR}\` (it changes when that tab restarts).`,
    '',
  ].join('\n');
}

// --- the Claude Code binary -----------------------------------------------------------------
function claudeBin() {
  const ext = vscode.extensions.getExtension('anthropic.claude-code');
  if (ext) {
    const bin = path.join(ext.extensionPath, 'resources', 'native-binary', 'claude');
    if (fs.existsSync(bin)) return bin;
  }
  return 'claude';
}

function runClaude(args, timeout = 20000) {
  return new Promise((resolve) => {
    cp.execFile(claudeBin(), args, { cwd: root(), timeout }, (err, stdout, stderr) =>
      resolve({ ok: !err, stdout: String(stdout || ''), stderr: String(stderr || '') }));
  });
}

async function liveSessions() {
  const r = await runClaude(['agents', '--json']);
  if (!r.ok) return null;
  try {
    return JSON.parse(r.stdout);
  } catch {
    return null;
  }
}

function permissionMode() {
  // the same mode as the user's Claude tabs, so messages between them flow without approval
  return vscode.workspace.getConfiguration('claudeCode').get('initialPermissionMode') || 'default';
}

function terminal(name, command) {
  const t = vscode.window.createTerminal({ name, cwd: root() });
  t.sendText(command);
  t.show();
}

const quote = (s) => `'${String(s).replace(/'/g, `'\\''`)}'`;

// --- the model ------------------------------------------------------------------------------
async function buildModel(bgIds, hiddenPids) {
  const registry = readRegistry();
  const live = await liveSessions();
  const cwd = root();
  const used = new Set();
  const rows = [];
  for (const [alias, entry] of Object.entries(registry)) {
    const pid = socketPid(entry);
    const session = live && live.find((s) => (pid ? s.pid === pid : s.name === entry.address));
    if (session) used.add(session.sessionId);
    rows.push({ alias, entry, session, type: typeOf(entry, session), bgId: bgIds[alias] });
  }
  for (const s of live || []) {
    // the panel's own message relays are short-lived sessions too — never list them
    if (s.cwd === cwd && !used.has(s.sessionId) && !hiddenPids.has(s.pid)) rows.push({ session: s, type: typeOf(undefined, s) });
  }
  rows.sort((a, b) => rank(a) - rank(b) || label(a).localeCompare(label(b)));
  return { rows, liveOk: live !== null };
}

function typeOf(entry, session) {
  if (entry && entry.type && entry.type !== '?') return entry.type;
  if (session && session.kind && session.kind !== 'interactive') return 'bg';
  return 'tab';
}

const label = (row) => row.alias || (row.session && row.session.name) || '?';
const rowKey = (row) => row.alias || (row.session && row.session.sessionId);
const rank = (row) => (row.alias === COORDINATOR ? 0 : row.alias ? (row.session ? 1 : 2) : 3);

class SessionItem extends vscode.TreeItem {
  constructor(row, sending) {
    super(label(row), vscode.TreeItemCollapsibleState.None);
    this.row = row;
    const status = row.session ? row.session.status || 'live' : 'stale';
    const role = row.entry && row.entry.role;
    this.description = [sending ? 'sending…' : null, row.type === 'bg' ? 'background' : 'tab', status, role ? 'role' : null,
      row.alias === COORDINATOR ? 'coordinator' : null, row.alias ? null : 'no alias'].filter(Boolean).join(' · ');
    const icon = !row.session ? 'circle-slash' : status === 'busy' ? 'sync~spin' : row.alias === COORDINATOR ? 'star-full' : 'circle-filled';
    const color = !row.session ? 'disabledForeground' : status === 'busy' ? 'charts.yellow' : 'charts.green';
    this.iconPath = sending ? new vscode.ThemeIcon('loading~spin', new vscode.ThemeColor('charts.blue'))
      : new vscode.ThemeIcon(icon, new vscode.ThemeColor(color));
    const md = new vscode.MarkdownString();
    md.appendMarkdown(`**${label(row)}**${row.alias && row.session && row.session.name !== row.alias ? ` (session "${row.session.name}")` : ''}\n\n`);
    md.appendMarkdown(`- type: ${row.type === 'bg' ? 'background' : 'VS Code tab'}\n- status: ${status}\n`);
    if (row.session) md.appendMarkdown(`- started: ${new Date(row.session.startedAt).toLocaleString()}\n- pid: ${row.session.pid}\n`);
    if (role) md.appendMarkdown(`- role: ${path.basename(role)}\n`);
    if (!row.session) md.appendMarkdown('\nThe session is gone — start it again, or remove the alias.');
    this.tooltip = md;
    this.contextValue = ['session', row.session ? 'live' : 'stale', row.type, row.alias ? 'alias' : 'noalias'].join('.') + '.';
    if (row.session) this.command = { command: row.type === 'bg' ? 'agoraSessions.attach' : 'agoraSessions.open', title: 'Open', arguments: [this] };
  }
}

class SessionsProvider {
  constructor(state) {
    this.state = state;
    this.emitter = new vscode.EventEmitter();
    this.onDidChangeTreeData = this.emitter.event;
    this.model = { rows: [], liveOk: true };
    this.view = undefined;
    this.sending = new Map(); // row key -> messages in flight to that session
    this.relayPids = new Set(); // pids of our own relay processes, hidden from the list
  }
  async reload() {
    this.model = await buildModel(this.state.get('bgIds', {}), this.relayPids);
    if (this.view) this.view.message = this.model.liveOk ? undefined : 'Live status unavailable (claude agents failed) — showing aliases only.';
    this.emitter.fire();
  }
  getTreeItem(item) {
    return item;
  }
  getChildren() {
    return this.model.rows.map((row) => new SessionItem(row, this.sending.has(rowKey(row))));
  }
  coordinator() {
    return this.model.rows.find((r) => r.alias === COORDINATOR && r.session);
  }
}

// --- commands -------------------------------------------------------------------------------
async function newSession(provider, state) {
  const registry = readRegistry();
  const alias = await vscode.window.showInputBox({
    title: 'New Claude session (1/3) — alias',
    prompt: 'lowercase a-z 0-9 _ -, max 40 — the name /send and this panel use',
    validateInput: (v) => (!ALIAS.test(v) ? 'lowercase a-z 0-9 _ -, starting with a letter or digit, max 40'
      : registry[v] && provider.model.rows.some((r) => r.alias === v && r.session) ? `"${v}" is taken by a live session` : undefined),
  });
  if (!alias) return;
  const exists = fs.existsSync(roleFile(alias));
  const description = await vscode.window.showInputBox({
    title: 'New Claude session (2/3) — role',
    prompt: exists ? `Leave empty to keep the existing role of "${alias}"` : 'What should this session do? Leave empty for no role.',
  });
  if (description === undefined) return;
  const kind = await vscode.window.showQuickPick([
    { label: '$(server-process) Background', detail: 'Keeps running when tabs close; attach in a terminal', value: 'bg' },
    { label: '$(window) VS Code tab', detail: 'A chat tab you type in directly (press Enter once to join)', value: 'tab' },
  ], { title: 'New Claude session (3/3) — where' });
  if (!kind) return;

  if (description.trim()) {
    fs.mkdirSync(path.dirname(roleFile(alias)), { recursive: true });
    fs.writeFileSync(roleFile(alias), roleTemplate(alias, description));
  }
  const join = `/join ${alias} --from ${COORDINATOR}`;

  if (kind.value === 'tab') {
    await vscode.commands.executeCommand('claude-vscode.primaryEditor.open', undefined, join);
    vscode.window.showInformationMessage(`New tab for "${alias}": press Enter there to join.`);
    return;
  }
  const r = await runClaude(['--bg', '--permission-mode', permissionMode(), '-n', alias, join], 60000);
  if (!r.ok) {
    const text = (r.stderr || r.stdout).trim();
    if (/not trusted/i.test(text)) {
      const pick = await vscode.window.showErrorMessage(
        'Claude Code needs a one-time "trust this folder" answer before it can start background sessions here.',
        'Open terminal to answer');
      if (pick) terminal('claude (trust)', `${quote(claudeBin())}`);
    } else {
      vscode.window.showErrorMessage(`Could not start "${alias}": ${text.split('\n').pop()}`);
    }
    return;
  }
  const id = (r.stdout.match(/\b[0-9a-f]{6,}(?:-[0-9a-f-]+)?\b/i) || [])[0];
  if (id) state.update('bgIds', { ...state.get('bgIds', {}), [alias]: id });
  vscode.window.showInformationMessage(`"${alias}" is starting in the background — it joins by itself.`);
  setTimeout(() => provider.reload(), 4000);
}

// Messages go through a short-lived headless Claude (Haiku, only the messaging tools) that makes one
// SendMessage call — the extension itself cannot type into an open chat ("Session is already open. Your
// prompt was not applied"). Replies are routed to the coordinator, whose socket is in the footer.
function addressOf(row) {
  if (row.entry && row.entry.socket && fs.existsSync(row.entry.socket.replace(/^uds:/, ''))) return row.entry.socket;
  if (row.session) {
    const sock = `/tmp/cc-socks/${row.session.pid}.sock`;
    return fs.existsSync(sock) ? `uds:${sock}` : row.session.name;
  }
  return undefined;
}

function relay(to, text, onPid) {
  const prompt = [
    'You are a message relay. Make exactly one SendMessage call (load it first with ToolSearch, query',
    '"select:SendMessage", if it is not loaded) with these two arguments, each the exact JSON string value',
    'given, decoded, with every line kept:',
    `to = ${JSON.stringify(to)}`,
    `message = ${JSON.stringify(text)}`,
    'Then output only SENT, or FAILED: <reason>.',
  ].join('\n');
  const args = ['-p', '--model', 'haiku', '--permission-mode', permissionMode(), '--tools', 'SendMessage,ToolSearch',
    '--strict-mcp-config', '--no-session-persistence'];
  return new Promise((resolve) => {
    const child = cp.spawn(claudeBin(), args, { cwd: root(), stdio: ['pipe', 'pipe', 'pipe'] });
    if (onPid && child.pid) onPid(child.pid);
    let out = '';
    child.stdout.on('data', (d) => { out += d; });
    child.stderr.on('data', (d) => { out += d; });
    const timer = setTimeout(() => child.kill(), 90000);
    child.on('close', () => { clearTimeout(timer); resolve({ ok: /\bSENT\b/.test(out) && !/FAILED/.test(out), out: out.trim() }); });
    child.on('error', (e) => { clearTimeout(timer); resolve({ ok: false, out: String(e) }); });
    child.stdin.end(prompt); // the prompt via stdin: never in argv
  });
}

// 💬 on a row = send AS that session: pick the recipient, and the message arrives signed [<sender> · via panel]
// with the sender's socket as the reply address, so the answer lands in the sender's chat.
async function message(provider, item) {
  const from = item.row;
  const fromAddr = addressOf(from);
  if (!fromAddr) {
    vscode.window.showWarningMessage(`"${label(from)}" is not running.`);
    return;
  }
  const targets = provider.model.rows.filter((r) => r.session && rowKey(r) !== rowKey(from) && addressOf(r));
  if (!targets.length) {
    vscode.window.showWarningMessage('No other live session to send to.');
    return;
  }
  const pick = await vscode.window.showQuickPick(
    targets.map((r) => ({ label: label(r), description: [r.type === 'bg' ? 'background' : 'tab', r.session.status].join(' · '), row: r })),
    { title: `Send as ${label(from)} — to whom?` });
  if (!pick) return;
  const to = pick.row;
  const text = await vscode.window.showInputBox({
    title: `${label(from)} → ${label(to)}`,
    prompt: `Arrives in ${label(to)}'s chat signed [${label(from)} · via panel]; the reply goes to ${label(from)}`,
  });
  if (!text) return;
  const body = `[${label(from)} · via panel] ${text}\n\n— reply with SendMessage to ${fromAddr} (${label(from)})`;
  // progress = a spinner on the sender's row (the relay itself stays out of the list)
  const key = rowKey(from);
  provider.sending.set(key, (provider.sending.get(key) || 0) + 1);
  provider.emitter.fire();
  let relayPid;
  const r = await relay(addressOf(to), body, (pid) => { relayPid = pid; provider.relayPids.add(pid); });
  const left = provider.sending.get(key) - 1;
  if (left > 0) provider.sending.set(key, left); else provider.sending.delete(key);
  setTimeout(() => provider.relayPids.delete(relayPid), 30000); // until claude agents forgets it
  provider.reload();
  if (r.ok) {
    vscode.window.showInformationMessage(`${label(from)} → ${label(to)}: delivered. The reply arrives in ${label(from)}.`);
  } else {
    vscode.window.showErrorMessage(`${label(from)} → ${label(to)}: not delivered — ${r.out.split('\n').pop() || 'no answer from the relay'}`);
  }
}

function bgId(row) {
  return row.bgId || row.session.sessionId;
}

async function stop(provider, item) {
  const row = item.row;
  const ok = await vscode.window.showWarningMessage(`Stop the background session "${label(row)}"? Work in progress is interrupted.`, { modal: true }, 'Stop');
  if (!ok) return;
  const r = await runClaude(['stop', bgId(row)]);
  if (!r.ok) vscode.window.showErrorMessage(`Could not stop "${label(row)}": ${(r.stderr || r.stdout).trim().split('\n').pop()}`);
  setTimeout(() => provider.reload(), 1500);
}

async function setAlias(provider, item) {
  const row = item.row;
  const registry = readRegistry();
  const alias = await vscode.window.showInputBox({
    title: `Alias for ${row.session.name}`,
    validateInput: (v) => (!ALIAS.test(v) ? 'lowercase a-z 0-9 _ -, starting with a letter or digit, max 40' : undefined),
  });
  if (!alias) return;
  for (const [a, e] of Object.entries(registry)) if (socketPid(e) === row.session.pid) delete registry[a];
  registry[alias] = {
    address: row.session.name, socket: `uds:/tmp/cc-socks/${row.session.pid}.sock`, type: row.type, tmux: null, cwd: root(),
    role: fs.existsSync(roleFile(alias)) ? roleFile(alias) : null, joined: new Date().toISOString(),
  };
  writeRegistry(registry);
  provider.reload();
}

async function removeAlias(provider, item) {
  const alias = item.row.alias;
  const ok = await vscode.window.showWarningMessage(`Remove the alias "${alias}"? The session keeps running; its role file is kept.`, { modal: true }, 'Remove');
  if (!ok) return;
  const registry = readRegistry();
  delete registry[alias];
  writeRegistry(registry);
  provider.reload();
}

async function editRole(item) {
  const file = roleFile(item.row.alias);
  if (!fs.existsSync(file)) {
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, roleTemplate(item.row.alias, 'Describe the job here.'));
  }
  await vscode.window.showTextDocument(vscode.Uri.file(file));
}

// --- activation -----------------------------------------------------------------------------
function activate(context) {
  if (!root()) return;
  const provider = new SessionsProvider(context.workspaceState);
  const view = vscode.window.createTreeView('agoraSessions.list', { treeDataProvider: provider });
  provider.view = view;
  const reg = (id, fn) => context.subscriptions.push(vscode.commands.registerCommand(id, fn));

  reg('agoraSessions.refresh', () => provider.reload());
  reg('agoraSessions.new', () => newSession(provider, context.workspaceState));
  reg('agoraSessions.open', (item) => vscode.commands.executeCommand('claude-vscode.primaryEditor.open', item.row.session.sessionId));
  reg('agoraSessions.message', (item) => message(provider, item));
  reg('agoraSessions.attach', (item) => terminal(`claude ${label(item.row)}`, `${quote(claudeBin())} attach ${bgId(item.row)}`));
  reg('agoraSessions.logs', (item) => terminal(`logs ${label(item.row)}`, `${quote(claudeBin())} logs ${bgId(item.row)}`));
  reg('agoraSessions.stop', (item) => stop(provider, item));
  reg('agoraSessions.editRole', (item) => editRole(item));
  reg('agoraSessions.setAlias', (item) => setAlias(provider, item));
  reg('agoraSessions.removeAlias', (item) => removeAlias(provider, item));

  const watcher = vscode.workspace.createFileSystemWatcher(new vscode.RelativePattern(root(), '.claude/session-aliases/**'));
  watcher.onDidChange(() => provider.reload());
  watcher.onDidCreate(() => provider.reload());
  watcher.onDidDelete(() => provider.reload());
  const timer = setInterval(() => { if (view.visible) provider.reload(); }, REFRESH_MS);
  view.onDidChangeVisibility(() => { if (view.visible) provider.reload(); });
  context.subscriptions.push(view, watcher, { dispose: () => clearInterval(timer) });
  provider.reload();
}

function deactivate() {}

module.exports = { activate, deactivate };
