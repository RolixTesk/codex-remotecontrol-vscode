'use strict';

// Native assertions and mocks only: no VS Code, WSL, settings, or processes are launched.
const assert = require('node:assert/strict');
const Module = require('node:module');
const path = require('node:path');
const root = path.resolve(__dirname, '..');

function load(file, mocks) {
  const previous = Module._load;
  Module._load = function (name, parent, isMain) {
    return Object.hasOwn(mocks, name) ? mocks[name] : previous.call(this, name, parent, isMain);
  };
  try {
    delete require.cache[require.resolve(file)];
    return require(file);
  } finally { Module._load = previous; }
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

const flushCallbacks = () => new Promise(resolve => setImmediate(resolve));

async function completes(promise, description) {
  let timer;
  try {
    return await Promise.race([promise, new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error(`${description}: command still waits for a notification`)), 200);
    })]);
  } finally { clearTimeout(timer); }
}

async function checkTransport() {
  const executed = [];
  let nextError;
  const api = load(path.join(root, 'extension/backend.js'), {
    'node:child_process': {
      execFile(command, args, options, callback) {
        const record = { command, args, options };
        executed.push(record);
        queueMicrotask(() => callback(nextError, Buffer.from(nextError ? '{"error":"synthetic failure"}' : '{}'), Buffer.alloc(0)));
        return { stdin: { on() {}, end(input) { record.input = input; } } };
      },
    },
  });
  const literal = "C:\\space 'quoted'\\中文\\file.py";
  await api.execute('python3', [literal, "space '中文'"], { wasSet: true, value: null });
  assert.deepEqual(executed[0].args, [literal, "space '中文'"]);
  assert.equal(executed[0].input, JSON.stringify({ wasSet: true, value: null }));
  assert.equal(executed[0].options.shell, undefined);
  assert.equal(executed[0].options.encoding, 'buffer');
  nextError = new Error('synthetic child error');
  await assert.rejects(api.execute('python3', [literal]), /synthetic failure/);

  const listing = Buffer.from('\ufeffDebian\r\nUbuntu-24.04\r\nUbuntu-22.04\r\n', 'utf16le');
  assert.deepEqual(api.decodeWslList(listing), ['Debian', 'Ubuntu-24.04', 'Ubuntu-22.04']);
  assert.deepEqual(api.decodeWslList(Buffer.from('Ubuntu\n', 'utf8')), ['Ubuntu']);
  const calls = [];
  const packageRoot = "C:\\package space'中文";
  const officialRoot = "C:\\official space'中文";
  const conversions = new Map([[packageRoot, "/mnt/c/package space'中文"], [officialRoot, "/mnt/c/official space'中文"]]);
  const run = async (command, args, input) => {
    calls.push({ command, args, input });
    if (args[0] === '--list') return listing;
    if (args.includes('wslpath')) return Buffer.from(conversions.get(args.at(-1)) + '\n');
    return Buffer.from('{}');
  };
  const backend = await api.backend(packageRoot, 'win32', run);
  assert.equal(backend.distro, 'Ubuntu-24.04');
  await backend.info();
  await backend.install(officialRoot, { wasSet: false, value: null });
  await backend.cli("/private/script space'中文.py", 'pair', "/project space'中文", 202, true);
  for (const call of calls.slice(1)) {
    assert.equal(call.command, 'wsl.exe');
    assert.deepEqual(call.args.slice(0, 3), ['-d', 'Ubuntu-24.04', '--exec']);
  }
  assert.deepEqual(calls[1].args, ['-d', 'Ubuntu-24.04', '--exec', 'wslpath', '-a', '-u', packageRoot]);
  assert.deepEqual(calls.at(-1).args, ['-d', 'Ubuntu-24.04', '--exec', 'python3',
    "/private/script space'中文.py", 'pair', '--workspace', "/project space'中文", '--pid', '202', '--open']);
  assert.deepEqual(calls.find(call => call.input).input, { wasSet: false, value: null });
  await assert.rejects(api.transport('win32', async () => Buffer.from('Debian\n')), /Ubuntu/);
  const localCalls = [];
  const local = await api.backend("/package space'中文", 'linux', async (...args) => {
    localCalls.push(args);
    return Buffer.from('{}');
  });
  assert.equal(await local.linuxPath("/local space'中文"), "/local space'中文");
  await local.info();
  assert.deepEqual(localCalls, [['python3', ["/package space'中文/scripts/deploy_backend.py", 'info'], undefined]]);
  console.log('PASS transport: UTF-16 first Ubuntu, explicit distro, local/WSL Python, literal argv/input without shell');
}

async function harness(options = {}) {
  const managed = '/stable/wrapper/codex-wrapper';
  const folders = options.folders || [{ name: '项目 A', uri: { fsPath: "/project A'中文", scheme: 'file' } }];
  const state = { global: options.global, updates: [], calls: [], picks: [...(options.picks || [])],
    information: [], errors: [], warnings: [], opened: [], quickPicks: [], status: undefined,
    notifications: [], progress: { started: 0, completed: 0, active: 0 } };
  function notification(kind, args, result) {
    state[kind].push(kind === 'information' ? args : args[0]);
    if (!options.deferNotifications) return Promise.resolve(result);
    const pending = { kind, args, ...deferred() };
    state.notifications.push(pending);
    return pending.promise;
  }
  const backup = Object.hasOwn(options, 'backup') ? options.backup : {
    wasSet: options.global !== undefined, value: options.global ?? null, managedValue: managed,
  };
  const bridge = {
    distro: options.distro,
    async info() { state.calls.push(['info']); return { installed: true, wrapper: managed, cli: '/stable/scripts/remote.py', backup }; },
    async install(official, previous) { state.calls.push(['install', official, previous]); return { wrapper: managed }; },
    async linuxPath(value) { state.calls.push(['linuxPath', value]); return value; },
    async cli(...args) {
      state.calls.push(['cli', ...args]);
      if (args[1] === 'list') return options.threads || [{ childPid: 101, active: false }];
      if (options.cli) return options.cli(...args);
      return { status: args[1] === 'disconnect' ? 'disabled' : 'connected', pairingPage: '/private/pairing.html' };
    },
  };
  const commands = new Map();
  const vscode = {
    StatusBarAlignment: { Right: 2 }, ConfigurationTarget: { Global: 1 }, ProgressLocation: { Notification: 15 },
    env: { remoteName: 'wsl', async openExternal(uri) {
      state.opened.push(uri);
      if (options.openError) throw options.openError;
      return options.openResult !== false;
    } },
    Uri: { from(value) { return value; }, file(value) { return { scheme: 'file', path: value }; } },
    workspace: {
      workspaceFolders: folders,
      getConfiguration(namespace) {
        assert.equal(namespace, 'chatgpt');
        return {
          inspect(key) { assert.equal(key, 'cliExecutable'); return { globalValue: state.global }; },
          get(key) { assert.equal(key, 'runCodexInWindowsSubsystemForLinux'); return options.runInWsl !== false; },
          async update(key, value, target) { state.updates.push([key, value, target]); state.global = value; },
        };
      },
    },
    window: {
      createStatusBarItem() { state.status = { show() {}, dispose() {} }; return state.status; },
      async showQuickPick(items, opts) { state.quickPicks.push([items, opts]); const index = state.picks.shift(); return index === undefined ? undefined : items[index]; },
      showInformationMessage(...args) { return notification('information', args, options.informationChoice); },
      showErrorMessage(...args) { return notification('errors', args); },
      showWarningMessage(...args) { return notification('warnings', args); },
      async withProgress(_opts, action) {
        state.progress.started++;
        state.progress.active++;
        try { return await action(); }
        finally { state.progress.completed++; state.progress.active--; }
      },
    },
    commands: {
      registerCommand(name, callback) { commands.set(name, callback); return { dispose() { commands.delete(name); } }; },
      executeCommand() { throw new Error('unexpected reload or other VS Code command'); },
    },
    extensions: { getExtension(name) { assert.equal(name, 'openai.chatgpt'); return { extensionPath: "/official space'中文" }; } },
  };
  const extension = load(path.join(root, 'extension/extension.js'), {
    vscode, './backend': { async backend(value) { state.calls.push(['backend', value]); return bridge; } },
  });
  const context = { extensionPath: "/package space'中文", subscriptions: [] };
  await extension.activate(context);
  assert.deepEqual([...commands.keys()].sort(), ['connect', 'disconnect', 'enable', 'pair', 'restore', 'status'].map(name => `codexRemote.${name}`).sort());
  assert.deepEqual(state.calls, []);
  assert.deepEqual(state.updates, []);
  return { state, bridge, context, extension, command: name => commands.get(`codexRemote.${name}`)() };
}

async function checkSettings() {
  for (const original of [undefined, null, "/old executable space'中文"]) {
    const app = await harness({ global: original });
    await app.command('enable');
    assert.deepEqual(app.state.calls.find(call => call[0] === 'install').slice(1),
      ["/official space'中文", { wasSet: original !== undefined, value: original ?? null }]);
    assert.deepEqual(app.state.updates, [['cliExecutable', '/stable/wrapper/codex-wrapper', 1]]);
    assert.match(app.state.status.text, /等待重载/);
    await app.command('restore');
    assert.equal(app.state.global, original);
    assert.equal(app.state.updates.at(-1)[2], 1);
    assert.deepEqual(app.state.errors, []);
  }
  const external = await harness({ global: '/external change', backup: { wasSet: false, value: null, managedValue: '/stable/wrapper/codex-wrapper' } });
  await external.command('restore');
  assert.equal(external.state.global, '/external change');
  assert.deepEqual(external.state.updates, []);
  assert.match(external.state.errors[0], /未覆盖/);
  const active = await harness();
  await active.command('enable');
  const before = [...active.state.updates];
  if (typeof active.extension.deactivate === 'function') await active.extension.deactivate();
  for (const subscription of active.context.subscriptions) subscription.dispose();
  assert.equal(active.state.global, '/stable/wrapper/codex-wrapper');
  assert.deepEqual(active.state.updates, before);
  const platform = Object.getOwnPropertyDescriptor(process, 'platform');
  try {
    Object.defineProperty(process, 'platform', { value: 'win32' });
    const blocked = await harness({ runInWsl: false });
    await blocked.command('enable');
    assert.deepEqual(blocked.state.updates, []);
    assert.match(blocked.state.errors[0], /WSL/);
    const restore = await harness({ runInWsl: false, global: '/stable/wrapper/codex-wrapper',
      backup: { wasSet: false, value: null, managedValue: '/stable/wrapper/codex-wrapper' } });
    await restore.command('restore');
    assert.equal(restore.state.global, undefined);
    assert.deepEqual(restore.state.errors, []);
  } finally { Object.defineProperty(process, 'platform', platform); }
  console.log('PASS activation/settings: six commands, no automatic enable/connect, exact Global backups/restore, external-change refusal, deactivate preserves config');
}

async function checkCommands() {
  const folders = [{ name: '项目 A', uri: { fsPath: '/project A', scheme: 'file' } },
    { name: '项目 B', uri: { fsPath: "/project B'中文", scheme: 'vscode-remote' } }];
  const app = await harness({ folders, picks: [1, 1], threads: [{ childPid: 101 }, { childPid: 202, active: true }] });
  await app.command('connect');
  assert.deepEqual(app.state.calls.filter(call => call[0] === 'cli').map(call => call.slice(2)),
    [['list', "/project B'中文"], ['connect', "/project B'中文", 202, false]]);
  assert.match(app.state.status.text, /已连接/);
  assert.match(app.state.status.tooltip, /项目 B.*202/);
  assert.equal(app.state.quickPicks.length, 2);
  const cancelledFolder = await harness({ folders });
  await cancelledFolder.command('connect');
  assert.deepEqual(cancelledFolder.state.calls, []);
  const cancelledPid = await harness({ threads: [{ childPid: 101 }, { childPid: 202 }] });
  await cancelledPid.command('connect');
  assert.deepEqual(cancelledPid.state.calls.filter(call => call[0] === 'cli').map(call => call[2]), ['list']);
  assert.deepEqual(cancelledPid.state.updates, []);

  for (const name of ['status', 'disconnect', 'pair']) {
    const item = await harness();
    await item.command(name);
    assert.deepEqual(item.state.calls.filter(call => call[0] === 'cli').map(call => call.slice(2)),
      [['list', "/project A'中文"], [name, "/project A'中文", 101, name === 'pair']]);
    assert.match(item.state.status.text, name === 'disconnect' ? /未连接/ : /已连接/);
    assert.deepEqual(item.state.updates, []);
  }
  let finish;
  const busy = await harness({ cli: () => new Promise(resolve => { finish = resolve; }) });
  const first = busy.command('connect');
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(typeof finish, 'function');
  await busy.command('disconnect');
  assert.deepEqual(busy.state.calls.filter(call => call[0] === 'cli').map(call => call[2]), ['list', 'connect']);
  finish({ status: 'connected' });
  await first;
  assert.match(busy.state.information[0][0], /正在执行/);
  console.log('PASS commands: explicit project/PID, cancellation reads only, CLI/status-bar routing, busy clicks do not duplicate writes');

  const opened = await harness({ distro: 'Ubuntu-24.04', informationChoice: '打开配对页' });
  await opened.command('pair');
  await flushCallbacks();
  assert.deepEqual(opened.state.opened, [{ scheme: 'file', authority: 'wsl.localhost', path: '/Ubuntu-24.04/private/pairing.html' }]);
  assert.deepEqual(opened.state.calls.filter(call => call[0] === 'cli').map(call => call[2]), ['list', 'pair']);
  const fallback = await harness({ informationChoice: '打开配对页', openResult: false,
    folders: [{ name: 'WSL', uri: { scheme: 'vscode-remote', authority: 'wsl+Ubuntu%20Preview', fsPath: '/project' } }] });
  await fallback.command('pair');
  await flushCallbacks();
  assert.deepEqual(fallback.state.opened, [{ scheme: 'file', authority: 'wsl.localhost', path: '/Ubuntu Preview/private/pairing.html' }]);
  assert.match(fallback.state.warnings[0], /\/private\/pairing\.html/);
  assert.deepEqual(fallback.state.calls.filter(call => call[0] === 'cli').map(call => call[2]), ['list', 'pair']);
  console.log('PASS pairing fallback: same private page/WSL distro, no repeated RPC, warning preserves existing page');
}

async function checkNotificationLifecycle() {
  for (const action of ['connect', 'disconnect', 'enable', 'restore']) {
    const app = await harness({ deferNotifications: true,
      global: action === 'restore' ? '/stable/wrapper/codex-wrapper' : undefined });
    await completes(app.command(action), `${action} success`);
    assert.equal(app.state.information.length, 1);
    assert.equal(app.state.notifications.length, 1, 'notification remains undismissed');
    assert.deepEqual(app.state.progress, { started: 1, completed: 1, active: 0 });
    await completes(app.command('status'), `${action} followed by status`);
    assert.equal(app.state.calls.filter(call => call[0] === 'cli' && call[2] === 'status').length, 1);
    assert.deepEqual(app.state.progress, { started: 2, completed: 2, active: 0 });
  }
  const failure = await harness({ deferNotifications: true, cli: async (_script, action) => {
    if (action === 'connect') throw new Error('synthetic backend failure');
    return { status: 'connected' };
  } });
  await completes(failure.command('connect'), 'backend failure');
  assert.deepEqual(failure.state.errors, ['synthetic backend failure']);
  assert.equal(failure.state.notifications[0].kind, 'errors');
  await completes(failure.command('status'), 'backend failure followed by status');
  assert.deepEqual(failure.state.progress, { started: 2, completed: 2, active: 0 });

  const pair = await harness({ deferNotifications: true, distro: 'Ubuntu-24.04' });
  await completes(pair.command('pair'), 'pairing before selecting notification');
  assert.deepEqual(pair.state.opened, []);
  await completes(pair.command('status'), 'pairing followed by status');
  pair.state.notifications[0].resolve('打开配对页');
  await flushCallbacks();
  assert.deepEqual(pair.state.opened, [{ scheme: 'file', authority: 'wsl.localhost', path: '/Ubuntu-24.04/private/pairing.html' }]);
  assert.equal(pair.state.calls.filter(call => call[0] === 'cli' && call[2] === 'pair').length, 1);
  assert.deepEqual(pair.state.progress, { started: 2, completed: 2, active: 0 });

  const unhandled = [];
  const recordUnhandled = error => unhandled.push(error);
  process.on('unhandledRejection', recordUnhandled);
  try {
    for (const mode of ['browser declined', 'browser rejected', 'notification rejected']) {
      const message = `synthetic ${mode}`;
      const app = await harness({ deferNotifications: true, openResult: mode !== 'browser declined',
        openError: mode === 'browser rejected' ? new Error(message) : undefined });
      await completes(app.command('pair'), mode);
      if (mode === 'notification rejected') app.state.notifications[0].reject(new Error(message));
      else app.state.notifications[0].resolve('打开配对页');
      await flushCallbacks();
      await flushCallbacks();
      if (mode === 'browser declined') assert.match(app.state.warnings[0], /\/private\/pairing\.html/);
      else assert.match(app.state.errors[0], new RegExp(message));
      await completes(app.command('status'), `${mode} followed by status`);
      assert.equal(app.state.calls.filter(call => call[0] === 'cli' && call[2] === 'pair').length, 1);
    }
    assert.deepEqual(unhandled, []);
  } finally { process.removeListener('unhandledRejection', recordUnhandled); }

  const backendWork = deferred();
  const busy = await harness({ deferNotifications: true, cli: () => backendWork.promise });
  const first = busy.command('connect');
  await flushCallbacks();
  const duplicate = busy.command('disconnect');
  await flushCallbacks();
  assert.deepEqual(busy.state.calls.filter(call => call[0] === 'cli').map(call => call[2]), ['list', 'connect']);
  assert.deepEqual(busy.state.progress, { started: 1, completed: 0, active: 1 });
  assert.match(busy.state.information[0][0], /正在执行/);
  busy.state.notifications[0].resolve();
  await completes(duplicate, 'duplicate operation notice');
  backendWork.resolve({ status: 'connected' });
  await completes(first, 'backend completion with success notification undismissed');
  assert.deepEqual(busy.state.progress, { started: 1, completed: 1, active: 0 });
  console.log('PASS notification lifecycle: undismissed success/error/pairing notices release progress and busy, delayed pairing opens once, browser/notification rejection handled, running backend remains exclusive');
}

(async () => {
  if (process.argv.includes('--notification-lifecycle')) {
    await checkNotificationLifecycle();
    return;
  }
  await checkTransport();
  await checkSettings();
  await checkCommands();
  await checkNotificationLifecycle();
})().catch(error => { console.error(error); process.exitCode = 1; });
