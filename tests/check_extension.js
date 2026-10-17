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

function checkManifest() {
  const manifest = require(path.join(root, 'package.json'));
  const expected = {
    'codexRemote.enable': '配置远程控制',
    'codexRemote.connect': '启动远程控制',
    'codexRemote.pair': '配对手机',
    'codexRemote.status': '查看远程控制状态',
    'codexRemote.disconnect': '停止远程控制',
    'codexRemote.restore': '恢复 Codex 启动设置（卸载前）',
  };
  const commands = manifest.contributes.commands;
  assert.equal(commands.length, 6);
  assert.deepEqual(Object.fromEntries(commands.map(command => [command.command, command.title])), expected);
  assert.ok(commands.every(command => command.category === 'Codex Remote'));
  const automatic = manifest.contributes.configuration.properties['codexRemote.autoConnect'];
  assert.equal(automatic.type, 'boolean');
  assert.equal(automatic.default, true, 'automatic Remote is enabled by default');
  assert.equal(automatic.scope, 'application', 'automatic Remote follows the user, not workspace settings');
  console.log('PASS command manifest: six stable command IDs/titles, automatic Remote boolean defaults on in user settings');
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
  nextError = undefined;
  await api.execute('python3', [literal], { action: 'list', pid: undefined, open: false });
  assert.deepEqual(executed.at(-1).args, [literal]);
  assert.equal(executed.at(-1).input, '{"action":"list","open":false}', 'serialized requests omit an undefined PID');

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
  assert.equal(Object.hasOwn(backend, 'linuxPath'), false, 'backend no longer exposes project path conversion');
  assert.equal(Object.hasOwn(backend, 'cli'), false, 'backend exposes requests instead of a custom CLI');
  await backend.info();
  await backend.install(officialRoot, { wasSet: false, value: null });
  await backend.maintain(officialRoot, { wasSet: true, value: '/stable/wrapper/codex-wrapper' });
  await backend.request("/private/script space'中文.py", 'pair', 202, true);
  for (const call of calls.slice(1)) {
    assert.equal(call.command, 'wsl.exe');
    assert.deepEqual(call.args.slice(0, 3), ['-d', 'Ubuntu-24.04', '--exec']);
  }
  assert.deepEqual(calls[1].args, ['-d', 'Ubuntu-24.04', '--exec', 'wslpath', '-a', '-u', packageRoot]);
  assert.deepEqual(calls.at(-1).args, ['-d', 'Ubuntu-24.04', '--exec', 'python3',
    "/private/script space'中文.py"]);
  assert.deepEqual(calls.at(-1).input, { action: 'pair', pid: 202, open: true });
  assert.deepEqual(calls.find(call => call.input).input, { wasSet: false, value: null });
  const maintenance = calls.find(call => call.args.includes('maintain'));
  assert.deepEqual(maintenance.args, ['-d', 'Ubuntu-24.04', '--exec', 'python3',
    "/mnt/c/package space'中文/scripts/deploy_backend.py", 'maintain', '--extension-root', "/mnt/c/official space'中文"]);
  assert.deepEqual(maintenance.input, { wasSet: true, value: '/stable/wrapper/codex-wrapper' });
  await backend.request("/private/script space'中文.py", 'list');
  assert.deepEqual(calls.at(-1).args, ['-d', 'Ubuntu-24.04', '--exec', 'python3',
    "/private/script space'中文.py"]);
  assert.deepEqual(calls.at(-1).input, { action: 'list', pid: undefined, open: false });
  await backend.request("/private/script space'中文.py", 'connect', 202);
  assert.deepEqual(calls.at(-1).args, ['-d', 'Ubuntu-24.04', '--exec', 'python3',
    "/private/script space'中文.py"]);
  assert.deepEqual(calls.at(-1).input, { action: 'connect', pid: 202, open: false });
  await backend.request("/private/script space'中文.py", 'pair', 202, true);
  assert.deepEqual(calls.at(-1).args, ['-d', 'Ubuntu-24.04', '--exec', 'python3',
    "/private/script space'中文.py"]);
  assert.deepEqual(calls.at(-1).input, { action: 'pair', pid: 202, open: true });
  await assert.rejects(api.transport('win32', async () => Buffer.from('Debian\n')), /Ubuntu/);
  const localCalls = [];
  const local = await api.backend("/package space'中文", 'linux', async (...args) => {
    localCalls.push(args);
    return Buffer.from('{}');
  });
  assert.equal(Object.hasOwn(local, 'linuxPath'), false);
  assert.equal(Object.hasOwn(local, 'cli'), false);
  const localHost = await api.transport('linux', async () => { throw new Error('unexpected local path command'); });
  assert.equal(await localHost.linuxPath("/local space'中文"), "/local space'中文");
  await local.info();
  await local.maintain("/official space'中文", { wasSet: true, value: '/stable/wrapper/codex-wrapper' });
  await local.request('/stable/scripts/remote_backend.py', 'status', 101);
  assert.deepEqual(localCalls, [
    ['python3', ["/package space'中文/scripts/deploy_backend.py", 'info'], undefined],
    ['python3', ["/package space'中文/scripts/deploy_backend.py", 'maintain', '--extension-root', "/official space'中文"],
      { wasSet: true, value: '/stable/wrapper/codex-wrapper' }],
    ['python3', ['/stable/scripts/remote_backend.py'], { action: 'status', pid: 101, open: false }],
  ]);
  assert.equal(calls.some(call => call.args.includes('--workspace')), false);
  assert.equal(localCalls.some(call => call[1].includes('--workspace')), false);
  console.log('PASS transport: UTF-16 first Ubuntu, explicit distro, local/WSL Python, stdin JSON controller, private path conversion, literal argv/input without shell');
}

async function harness(options = {}) {
  const managed = options.managedWrapper || '/stable/wrapper/codex-wrapper';
  const state = { global: options.global, updates: [], calls: [], picks: [...(options.picks || [])],
    information: [], errors: [], warnings: [], opened: [], copied: [], quickPicks: [], status: undefined,
    officialRoot: options.officialRoot || "/official space'中文",
    officialActive: options.officialActive === true, autoConnect: options.autoConnect !== false,
    instances: options.instances || [{ childPid: 101, cwd: '/backend cwd', active: false }],
    timers: new Map(),
    workspaceReads: 0, authenticationReads: 0, wslSettingReads: 0,
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
  const location = { installed: options.installed !== false, wrapper: managed, controller: options.controllerFile || '/stable/scripts/remote_backend.py', backup };
  const bridge = {
    distro: options.distro,
    async info() { state.calls.push(['info']); return options.info ? options.info(state, location) : location; },
    async install(official, previous) { state.calls.push(['install', official, previous]); return { wrapper: managed }; },
    async maintain(official, previous) {
      state.calls.push(['maintain', official, previous]);
      if (options.maintainError) throw options.maintainError;
      return options.maintain ? options.maintain(state, location)
        : { ...location, managed: true, updated: false, binaryChanged: false };
    },
    async request(...args) {
      state.calls.push(['request', ...args]);
      if (args[1] === 'list') return options.list ? options.list(state) : state.instances;
      if (options.request) return options.request(...args);
      return { status: args[1] === 'disconnect' ? 'disabled' : 'connected', pairingPage: options.pairingPage || '/private/pairing.html' };
    },
  };
  function uri(value) {
    return Object.defineProperty({ ...value }, 'toString', { value() {
      const encoded = this.path.split('/').map(part => encodeURIComponent(part)
        .replace(/[!'()*]/g, character => `%${character.charCodeAt(0).toString(16).toUpperCase()}`)).join('/');
      return `${this.scheme}://${this.authority || ''}${encoded}`;
    } });
  }
  const commands = new Map();
  const vscode = {
    StatusBarAlignment: { Right: 2 }, ConfigurationTarget: { Global: 1 }, ProgressLocation: { Notification: 15 },
    get authentication() { state.authenticationReads++; throw new Error('unexpected account or authentication API access'); },
    env: { remoteName: Object.hasOwn(options, 'remoteName') ? options.remoteName : 'wsl', async openExternal(uri) {
      state.opened.push(uri);
      throw new Error('unexpected second browser opening by extension');
    }, clipboard: { async writeText(value) {
      state.copied.push(value);
      if (options.clipboardError) throw options.clipboardError;
      if (options.clipboardWork) await options.clipboardWork.promise;
    } } },
    Uri: { from: uri, file(value) { return uri({ scheme: 'file', path: value }); } },
    workspace: {
      get workspaceFolders() { state.workspaceReads++; throw new Error('unexpected workspace folder access'); },
      getConfiguration(namespace) {
        if (namespace === 'codexRemote') return { get(key, fallback) {
          assert.equal(key, 'autoConnect'); return state.autoConnect ?? fallback;
        } };
        assert.equal(namespace, 'chatgpt');
        return {
          inspect(key) { assert.equal(key, 'cliExecutable'); return { globalValue: state.global }; },
          get(key) { assert.equal(key, 'runCodexInWindowsSubsystemForLinux'); state.wslSettingReads++; return options.runInWsl !== false; },
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
    extensions: { getExtension(name) { assert.equal(name, 'openai.chatgpt'); return options.officialMissing ? undefined : { extensionPath: state.officialRoot, isActive: state.officialActive }; } },
  };
  const extension = load(path.join(root, 'extension/extension.js'), {
    vscode, './backend': { async backend(value) { state.calls.push(['backend', value]); return bridge; } },
    'node:timers': {
      setInterval(callback, delay) { const handle = {}; state.timers.set(handle, { callback, delay }); return handle; },
      clearInterval(handle) { state.timers.delete(handle); },
    },
  });
  const context = { extensionPath: options.extensionPath || "/package space'中文", subscriptions: [] };
  await extension.activate(context);
  await flushCallbacks();
  assert.deepEqual([...commands.keys()].sort(), ['connect', 'disconnect', 'enable', 'pair', 'restore', 'status'].map(name => `codexRemote.${name}`).sort());
  if (!options.officialActive) assert.equal(state.calls.some(call => ['request', 'install'].includes(call[0])), false, 'inactive Codex never connects or enables');
  assert.deepEqual(state.updates, []);
  assert.equal(state.workspaceReads, 0);
  return { state, bridge, context, extension, command: name => commands.get(`codexRemote.${name}`)(),
    async tick() {
      for (const timer of state.timers.values()) timer.callback();
      await flushCallbacks();
    },
    dispose() { for (const subscription of context.subscriptions) subscription.dispose(); },
  };
}

async function checkAutoConnect() {
  const managed = '/stable/wrapper/codex-wrapper';
  const configured = { officialActive: true, global: managed,
    request: async () => ({ status: 'connected', paired: true }) };
  const requests = app => app.state.calls.filter(call => call[0] === 'request');
  const automatic = app => requests(app).filter(call => call[2] === 'auto-connect');
  const app = await harness(configured);
  assert.deepEqual(app.state.calls.filter(call => call[0] === 'request').map(call => call.slice(2)),
    [['list'], ['auto-connect', 101]], 'already paired Codex starts Remote after activation');
  assert.match(app.state.status.text, /已启动/);
  assert.deepEqual([...app.state.timers.values()].map(timer => timer.delay), [5000]);
  await app.tick();
  await app.tick();
  assert.equal(automatic(app).length, 1, 'automatic start is attempted once per backend');
  assert.deepEqual(app.state.progress, { started: 0, completed: 0, active: 0 });
  assert.deepEqual(app.state.information, [], 'automatic success stays quiet');
  assert.equal(app.state.workspaceReads, 0);
  assert.equal(app.state.authenticationReads, 0);
  assert.deepEqual(app.state.updates, []);

  const delayed = await harness({ ...configured, officialActive: false });
  await delayed.tick();
  assert.equal(requests(delayed).length, 0, 'does not activate official Codex');
  delayed.state.officialActive = true;
  await delayed.tick();
  assert.equal(automatic(delayed).length, 1, 'detects official Codex activated later');
  const lateBackend = await harness({ ...configured, instances: [] });
  assert.equal(automatic(lateBackend).length, 0);
  lateBackend.state.instances = [{ childPid: 201 }];
  await lateBackend.tick();
  assert.equal(automatic(lateBackend)[0][3], 201, 'discovers a backend that appears after activation');

  const unpaired = await harness({ ...configured,
    request: async () => ({ status: 'disabled', paired: false }) });
  await unpaired.tick();
  await unpaired.tick();
  assert.equal(automatic(unpaired).length, 1, 'unpaired backend is not repeatedly retried');
  assert.deepEqual(unpaired.state.information, []);
  assert.deepEqual(unpaired.state.warnings, []);
  assert.deepEqual(unpaired.state.opened, []);
  let pendingChecks = 0;
  const pending = await harness({ ...configured, request: async () => ++pendingChecks < 3
    ? { status: 'disabled', paired: false, pairingPending: true }
    : { status: 'connected', paired: true } });
  await pending.tick();
  await pending.tick();
  await pending.tick();
  assert.equal(automatic(pending).length, 3, 'pending manual pairing can be checked until confirmed');
  assert.match(pending.state.status.text, /已启动/);

  app.state.instances = [{ childPid: 202 }];
  await app.tick();
  assert.deepEqual(automatic(app).map(call => call[3]), [101, 202], 'a restarted backend receives a new attempt');
  app.state.instances = [{ childPid: 101 }];
  await app.tick();
  assert.equal(automatic(app).length, 2, 'rediscovery does not replay a previous backend attempt');

  const disabled = await harness({ ...configured, autoConnect: false });
  await disabled.tick();
  assert.equal(requests(disabled).length, 0);
  disabled.state.autoConnect = true;
  await disabled.tick();
  assert.equal(automatic(disabled).length, 1, 'configuration takes effect without reload');
  disabled.state.autoConnect = false;
  disabled.state.instances = [{ childPid: 303 }];
  const beforeDisabled = requests(disabled).length;
  await disabled.tick();
  assert.equal(requests(disabled).length, beforeDisabled);

  const stopped = await harness({ ...configured, request: async (_controller, action) =>
    ({ status: action === 'disconnect' ? 'disabled' : 'connected', paired: true }) });
  await stopped.command('disconnect');
  stopped.state.instances = [{ childPid: 404 }];
  const afterStop = requests(stopped).length;
  await stopped.tick();
  assert.equal(requests(stopped).length, afterStop, 'manual stop pauses automatic connections in this window');
  await stopped.command('connect');
  stopped.state.instances = [{ childPid: 405 }];
  await stopped.tick();
  assert.equal(automatic(stopped).at(-1)[3], 405, 'manual start resumes automatic detection');

  const restored = await harness(configured);
  await restored.command('restore');
  const afterRestore = requests(restored).length;
  restored.state.global = managed;
  restored.state.instances = [{ childPid: 505 }];
  await restored.tick();
  assert.equal(requests(restored).length, afterRestore, 'restore also pauses automatic connections');
  const changed = await harness({ ...configured, global: '/external/codex' });
  await changed.tick();
  assert.equal(requests(changed).length, 0, 'external executable settings remain unmanaged');
  changed.state.global = managed;
  await changed.tick();
  assert.equal(automatic(changed).length, 1);
  changed.state.global = '/external/new-codex';
  const beforeChange = requests(changed).length;
  await changed.tick();
  assert.equal(requests(changed).length, beforeChange, 'external changes suppress later automatic attempts');

  const multiple = await harness({ ...configured, instances: [{ childPid: 601 }, { childPid: 602 }] });
  await multiple.tick();
  assert.equal(automatic(multiple).length, 0, 'ambiguous backends require manual selection');
  assert.equal(multiple.state.quickPicks.length, 0, 'background detection never opens a picker');
  multiple.state.instances = [{ childPid: 602 }];
  await multiple.tick();
  assert.equal(automatic(multiple)[0][3], 602);

  for (const options of [{ installed: false }, { officialMissing: true }, { remoteName: 'ssh-remote' }]) {
    const excluded = await harness({ ...configured, ...options });
    await excluded.tick();
    assert.equal(requests(excluded).length, 0, 'unconfigured, missing official, or unsupported hosts do not connect');
    assert.deepEqual(excluded.state.updates, []);
  }
  const platform = Object.getOwnPropertyDescriptor(process, 'platform');
  try {
    Object.defineProperty(process, 'platform', { value: 'win32' });
    const native = await harness({ ...configured, runInWsl: false, remoteName: undefined });
    await native.tick();
    assert.equal(requests(native).length, 0, 'Windows requires an enabled WSL backend');
  } finally { Object.defineProperty(process, 'platform', platform); }

  const work = deferred();
  const busy = await harness({ ...configured, request: () => work.promise });
  await busy.tick();
  assert.equal(automatic(busy).length, 1, 'overlapping timer events do not duplicate in-flight work');
  assert.deepEqual(busy.state.progress, { started: 0, completed: 0, active: 0 });
  work.resolve({ status: 'connected', paired: true });
  await flushCallbacks();
  const manualWork = deferred();
  const manualBusy = await harness({ ...configured, officialActive: false,
    request: (_controller, action) => action === 'connect' ? manualWork.promise : { status: 'connected', paired: true } });
  const connecting = manualBusy.command('connect');
  await flushCallbacks();
  manualBusy.state.officialActive = true;
  await manualBusy.tick();
  assert.equal(automatic(manualBusy).length, 0, 'background detection waits for an active manual operation');
  manualWork.resolve({ status: 'connected' });
  await connecting;
  await manualBusy.tick();
  assert.equal(automatic(manualBusy).length, 1);

  const failed = await harness({ ...configured, request: async () => { throw new Error('synthetic automatic failure'); } });
  await failed.tick();
  await failed.tick();
  assert.equal(automatic(failed).length, 1, 'a failed backend attempt is not replayed');
  assert.equal(failed.state.warnings.length, 1);
  assert.match(failed.state.warnings[0], /状态/);
  assert.deepEqual(failed.state.errors, []);

  const disposed = await harness(configured);
  const staleTick = [...disposed.state.timers.values()][0].callback;
  disposed.dispose();
  assert.equal(disposed.state.timers.size, 0, 'dispose clears the timer');
  const afterDispose = requests(disposed).length;
  disposed.state.instances = [{ childPid: 701 }];
  await staleTick();
  await flushCallbacks();
  assert.equal(requests(disposed).length, afterDispose, 'a queued callback cannot act after dispose');
  const listing = deferred();
  const disposeDuringList = await harness({ ...configured, list: () => listing.promise });
  disposeDuringList.dispose();
  listing.resolve([{ childPid: 702 }]);
  await flushCallbacks();
  assert.equal(automatic(disposeDuringList).length, 0, 'disposal while discovering does not start Remote');
  console.log('PASS automatic Remote: default detection, late Codex/backend, pairing prerequisite and pending confirmation, once per PID, setting/host guards, manual pause/resume, busy exclusivity, quiet success, one failure notice, disposal');
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
  console.log('PASS activation/settings: inactive Codex does not connect, exact Global backups/restore, external-change refusal, deactivate preserves config');
}

async function checkCommands() {
  const app = await harness({ picks: [1], instances: [
    { childPid: 101, cwd: '/backend A', active: false },
    { childPid: 202, cwd: "/backend B'中文", active: true },
  ] });
  await app.command('connect');
  assert.deepEqual(app.state.calls.filter(call => call[0] === 'request').map(call => call.slice(2)),
    [['list'], ['connect', 202, false]]);
  assert.match(app.state.status.text, /已启动/);
  assert.doesNotMatch(app.state.status.tooltip || '', /作用于|不限于|定位项目/);
  assert.equal(app.state.quickPicks.length, 1, 'only the backend instance is selected');
  assert.equal(app.state.quickPicks[0][0].length, 2);
  assert.equal(app.state.workspaceReads, 0);
  assert.doesNotMatch(app.state.information[0][0], /PID|作用于|不限于|定位项目/);
  const cancelledPid = await harness({ instances: [{ childPid: 101, cwd: '/backend A' }, { childPid: 202, cwd: '/backend B' }] });
  await cancelledPid.command('connect');
  assert.deepEqual(cancelledPid.state.calls.filter(call => call[0] === 'request').map(call => call[2]), ['list']);
  assert.equal(cancelledPid.state.quickPicks.length, 1);
  assert.deepEqual(cancelledPid.state.updates, []);

  for (const name of ['connect', 'status', 'disconnect', 'pair']) {
    const item = await harness();
    await item.command(name);
    assert.deepEqual(item.state.calls.filter(call => call[0] === 'request').map(call => call.slice(2)),
      [['list'], [name, 101, name === 'pair']]);
    assert.match(item.state.status.text, name === 'disconnect' ? /未启动/ : /已启动/);
    assert.doesNotMatch(item.state.status.text, /已连接|未连接/);
    assert.deepEqual(item.state.updates, []);
    assert.deepEqual(item.state.errors, []);
    assert.equal(item.state.workspaceReads, 0, `${name} works without workspace or loaded thread`);
    assert.equal(item.state.quickPicks.length, 0);
    for (const notice of item.state.information) assert.doesNotMatch(notice[0], /PID|作用于|不限于|定位项目/);
    if (name === 'connect') assert.match(item.state.information[0][0], /已启动/);
    if (name === 'disconnect') assert.match(item.state.information[0][0], /已停止|未启动/);
    const absent = await harness({ instances: [] });
    await absent.command(name);
    assert.deepEqual(absent.state.calls.filter(call => call[0] === 'request').map(call => call.slice(2)), [['list']]);
    assert.match(absent.state.errors[0], /Codex.*面板/);
    assert.doesNotMatch(absent.state.errors[0], /项目|已加载.*聊天/);
    assert.equal(absent.state.workspaceReads, 0);
    assert.equal(absent.state.quickPicks.length, 0);
  }
  let finish;
  const busy = await harness({ request: () => new Promise(resolve => { finish = resolve; }) });
  const first = busy.command('connect');
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(typeof finish, 'function');
  await busy.command('disconnect');
  assert.deepEqual(busy.state.calls.filter(call => call[0] === 'request').map(call => call[2]), ['list', 'connect']);
  finish({ status: 'connected' });
  await first;
  assert.match(busy.state.information[0][0], /正在执行/);
  console.log('PASS backend commands: no workspace/thread requirement, one instance selection, cancellation reads only, missing backend opens-panel guidance, concise notices, busy clicks do not duplicate writes');

  const opened = await harness({ distro: 'Ubuntu-24.04', informationChoice: '复制网页链接' });
  await opened.command('pair');
  await flushCallbacks();
  assert.deepEqual(opened.state.copied, ['file://wsl.localhost/Ubuntu-24.04/private/pairing.html']);
  assert.deepEqual(opened.state.opened, []);
  assert.deepEqual(opened.state.calls.filter(call => call[0] === 'request').map(call => call[2]), ['list', 'pair']);
  const fallback = await harness({ informationChoice: '复制网页链接', distro: 'Ubuntu Preview',
    pairingPage: '/private/pair page 中文?#.html' });
  await fallback.command('pair');
  await flushCallbacks();
  assert.deepEqual(fallback.state.copied, ['file://wsl.localhost/Ubuntu%20Preview/private/pair%20page%20%E4%B8%AD%E6%96%87%3F%23.html']);
  assert.deepEqual(fallback.state.opened, []);
  assert.deepEqual(fallback.state.calls.filter(call => call[0] === 'request').map(call => call[2]), ['list', 'pair']);
  console.log('PASS pairing copy: same existing page URI, WSL distro and encoded path, no browser reopening or repeated RPC');
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
    assert.equal(app.state.calls.filter(call => call[0] === 'request' && call[2] === 'status').length, 1);
    assert.deepEqual(app.state.progress, { started: 2, completed: 2, active: 0 });
  }
  const failure = await harness({ deferNotifications: true, request: async (_script, action) => {
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
  assert.deepEqual(pair.state.copied, []);
  await completes(pair.command('status'), 'pairing followed by status');
  pair.state.notifications[0].resolve('复制网页链接');
  await flushCallbacks();
  assert.deepEqual(pair.state.copied, ['file://wsl.localhost/Ubuntu-24.04/private/pairing.html']);
  assert.deepEqual(pair.state.opened, []);
  assert.equal(pair.state.calls.filter(call => call[0] === 'request' && call[2] === 'pair').length, 1);
  assert.deepEqual(pair.state.progress, { started: 2, completed: 2, active: 0 });

  const unhandled = [];
  const recordUnhandled = error => unhandled.push(error);
  process.on('unhandledRejection', recordUnhandled);
  try {
    for (const mode of ['clipboard rejected', 'notification rejected']) {
      const message = `synthetic ${mode}`;
      const app = await harness({ deferNotifications: true,
        clipboardError: mode === 'clipboard rejected' ? new Error(message) : undefined });
      await completes(app.command('pair'), mode);
      if (mode === 'notification rejected') app.state.notifications[0].reject(new Error(message));
      else app.state.notifications[0].resolve('复制网页链接');
      await flushCallbacks();
      await flushCallbacks();
      assert.match(app.state.errors[0], /配对页链接未复制/);
      await completes(app.command('status'), `${mode} followed by status`);
      assert.equal(app.state.calls.filter(call => call[0] === 'request' && call[2] === 'pair').length, 1);
    }
    assert.deepEqual(unhandled, []);
  } finally { process.removeListener('unhandledRejection', recordUnhandled); }

  const backendWork = deferred();
  const busy = await harness({ deferNotifications: true, request: () => backendWork.promise });
  const first = busy.command('connect');
  await flushCallbacks();
  const duplicate = busy.command('disconnect');
  await flushCallbacks();
  assert.deepEqual(busy.state.calls.filter(call => call[0] === 'request').map(call => call[2]), ['list', 'connect']);
  assert.deepEqual(busy.state.progress, { started: 1, completed: 0, active: 1 });
  assert.match(busy.state.information[0][0], /正在执行/);
  busy.state.notifications[0].resolve();
  await completes(duplicate, 'duplicate operation notice');
  backendWork.resolve({ status: 'connected' });
  await completes(first, 'backend completion with success notification undismissed');
  assert.deepEqual(busy.state.progress, { started: 1, completed: 1, active: 0 });
  console.log('PASS notification lifecycle: undismissed success/error/pairing notices release progress and busy, delayed pairing copies once, clipboard/notification rejection handled, running backend remains exclusive');
}

async function checkPairingCopy() {
  for (const qrAvailable of [true, false]) {
    const clipboardWork = deferred();
    const app = await harness({ deferNotifications: true, distro: 'Ubuntu-24.04',
      clipboardWork,
      request: async (_script, action) => ({ status: 'connected',
        ...(action === 'pair' ? { qrAvailable, pairingPage: '/private/pairing.html' } : {}) }),
    });
    await completes(app.command('pair'), 'copy before selecting notification');
    const notification = app.state.notifications[0];
    assert.deepEqual(notification.args.slice(1), ['复制网页链接']);
    assert.deepEqual(app.state.progress, { started: 1, completed: 1, active: 0 });
    assert.deepEqual(app.state.opened, []);
    assert.deepEqual(app.state.copied, []);
    notification.resolve('复制网页链接');
    await flushCallbacks();
    assert.deepEqual(app.state.copied, ['file://wsl.localhost/Ubuntu-24.04/private/pairing.html']);
    assert.deepEqual(app.state.opened, []);
    await completes(app.command('status'), 'pending clipboard work followed by status');
    const pairCalls = app.state.calls.filter(call => call[0] === 'request' && call[2] === 'pair');
    assert.equal(pairCalls.length, 1);
    assert.equal(pairCalls[0].at(-1), true, 'backend pair open=true remains responsible for initial browser opening');
    assert.equal(app.state.calls.filter(call => call[0] === 'request' && call[2] === 'status').length, 1);
    assert.deepEqual(app.state.progress, { started: 2, completed: 2, active: 0 });
    clipboardWork.resolve();
    await flushCallbacks();
    assert.deepEqual(app.state.errors, []);
  }
  const local = await harness({ informationChoice: '复制网页链接', remoteName: undefined });
  await local.command('pair');
  await flushCallbacks();
  assert.deepEqual(local.state.copied, ['file:///private/pairing.html']);
  assert.deepEqual(local.state.opened, []);
  console.log('PASS pairing copy button: single choice, existing local/WSL file URI, one pair request with open=true, delayed clipboard work releases progress and busy');
}

async function checkMaintenance() {
  const managed = '/stable/wrapper/codex-wrapper';
  const backup = { wasSet: true, value: "/original executable'中文", managedValue: managed };
  const count = app => app.state.calls.filter(call => call[0] === 'maintain').length;
  const app = await harness({ global: managed, backup });
  assert.equal(count(app), 1, 'activation maintains managed wrapper');
  assert.deepEqual(app.state.calls.find(call => call[0] === 'maintain').slice(1),
    ["/official space'中文", { wasSet: true, value: managed }]);
  assert.deepEqual(app.state.updates, []);
  assert.equal(app.state.calls.some(call => call[0] === 'request'), false);
  app.state.officialRoot = "/new official version space'中文";
  await app.command('connect');
  assert.equal(count(app), 2, 'connect refreshes managed backend path');
  assert.equal(app.state.calls.filter(call => call[0] === 'maintain').at(-1)[1], app.state.officialRoot);
  await app.command('pair');
  assert.equal(count(app), 3, 'pair refreshes managed backend path');
  for (const action of ['status', 'disconnect']) await app.command(action);
  assert.equal(count(app), 3, 'status and disconnect do not maintain');
  assert.deepEqual(app.state.updates, []);
  assert.strictEqual((await app.bridge.info()).backup, backup);
  await app.command('restore');
  assert.equal(count(app), 3, 'restore does not maintain');
  assert.equal(app.state.global, backup.value);
  await app.command('connect');
  assert.equal(count(app), 3, 'restored external setting remains unmanaged');
  assert.deepEqual(app.state.updates, [['cliExecutable', backup.value, 1]]);

  for (const global of [undefined, null, '/external CLI']) {
    const external = await harness({ global });
    assert.equal(count(external), 0);
    await external.command('connect');
    await external.command('pair');
    assert.equal(count(external), 0, 'unmanaged settings never enable themselves');
    assert.deepEqual(external.state.updates, []);
    assert.equal(external.state.calls.some(call => call[0] === 'install'), false);
  }
  const unsupported = await harness({ global: managed, remoteName: 'ssh-remote' });
  assert.deepEqual(unsupported.state.calls, []);
  const platform = Object.getOwnPropertyDescriptor(process, 'platform');
  try {
    Object.defineProperty(process, 'platform', { value: 'win32' });
    const native = await harness({ global: managed, runInWsl: false, remoteName: undefined });
    assert.equal(count(native), 0);
    await native.command('restore');
    assert.equal(native.state.errors.length, 0);
  } finally { Object.defineProperty(process, 'platform', platform); }

  const upgraded = await harness({ global: managed, deferNotifications: true,
    maintain: (_state, location) => ({ ...location, managed: true, updated: true, binaryChanged: true }) });
  const notices = [...upgraded.state.information.map(args => args[0]), ...upgraded.state.warnings];
  assert.ok(notices.some(message => /重载/.test(message)), 'binary upgrade explains idle reload requirement');
  await completes(upgraded.command('status'), 'status after undismissed upgrade notice');
  assert.equal(count(upgraded), 1);
  assert.deepEqual(upgraded.state.updates, []);

  const broken = await harness({ global: managed, deferNotifications: true, backup,
    maintainError: new Error('synthetic automatic maintenance failure') });
  assert.match(broken.state.warnings[0], /synthetic automatic maintenance failure/);
  assert.deepEqual(broken.state.errors, []);
  await completes(broken.command('restore'), 'restore after undismissed automatic maintenance warning');
  assert.equal(broken.state.global, backup.value);
  assert.equal(count(broken), 1);

  let infoCalls = 0;
  const unreadable = await harness({ global: managed, backup,
    info: (_state, location) => {
      if (++infoCalls === 1) throw new Error('synthetic maintenance info failure');
      return location;
    } });
  assert.match(unreadable.state.warnings[0], /synthetic maintenance info failure/);
  await unreadable.command('restore');
  assert.equal(unreadable.state.global, backup.value);
  assert.deepEqual(unreadable.state.errors, []);
  console.log('PASS managed maintenance: activation/connect/pair refresh current official path, preserve backup/external settings, inactive Codex stays disconnected, status/disconnect/restore skip maintenance, failures keep restore usable');
}

async function checkNativeLinux() {
  const platform = Object.getOwnPropertyDescriptor(process, 'platform');
  const hadDistro = Object.hasOwn(process.env, 'WSL_DISTRO_NAME');
  const previousDistro = process.env.WSL_DISTRO_NAME;
  try {
    Object.defineProperty(process, 'platform', { value: 'linux' });
    delete process.env.WSL_DISTRO_NAME;
    const { publisher, name, version } = require(path.join(root, 'package.json'));
    const packageRoot = `/home/native-user/.vscode/extensions/${publisher}.${name}-${version}`;
    const officialRoot = '/home/native-user/.vscode/extensions/openai.chatgpt-26.1007.21434-linux-x64';
    const managed = '/home/native-user/.local/share/codex-remotecontrol/vscode/wrapper/codex-wrapper';
    const controller = '/home/native-user/.local/share/codex-remotecontrol/vscode/scripts/remote_backend.py';
    const info = { installed: true, wrapper: managed, controller };
    const instances = [{ childPid: 501, cwd: '/home/native-user/project', active: false }];
    const calls = [];
    const api = load(path.join(root, 'extension/backend.js'), {
      'node:child_process': { execFile() { throw new Error('unexpected real child process'); } },
    });
    const bridge = await api.backend(packageRoot, process.platform, async (command, args, input) => {
      calls.push([command, args, input]);
      assert.equal(command, 'python3');
      assert.equal(args.includes('wslpath'), false);
      assert.equal(args.includes('--workspace'), false);
      return Buffer.from(JSON.stringify(input?.action === 'list' ? instances : info));
    });
    assert.equal(bridge.distro, undefined);
    assert.deepEqual(await bridge.info(), info);
    await bridge.install(officialRoot, { wasSet: false, value: null });
    await bridge.maintain(officialRoot, { wasSet: true, value: managed });
    assert.deepEqual(await bridge.request(controller, 'list'), instances);
    assert.deepEqual(calls, [
      ['python3', [`${packageRoot}/scripts/deploy_backend.py`, 'info'], undefined],
      ['python3', [`${packageRoot}/scripts/deploy_backend.py`, 'install', '--extension-root', officialRoot],
        { wasSet: false, value: null }],
      ['python3', [`${packageRoot}/scripts/deploy_backend.py`, 'maintain', '--extension-root', officialRoot],
        { wasSet: true, value: managed }],
      ['python3', [controller], { action: 'list', pid: undefined, open: false }],
    ]);
    console.log('PASS native Linux transport: Ubuntu extension paths, direct python3 info/install/maintain/list, no WSL or workspace arguments');

    const original = '/home/native-user/bin/original-codex';
    const options = { remoteName: undefined, runInWsl: false, officialRoot, extensionPath: packageRoot,
      managedWrapper: managed, controllerFile: controller };
    const configured = await harness({ ...options, global: original });
    await configured.command('enable');
    assert.deepEqual(configured.state.calls.find(call => call[0] === 'install').slice(1),
      [officialRoot, { wasSet: true, value: original }]);
    assert.deepEqual(configured.state.updates, [['cliExecutable', managed, 1]]);
    assert.ok(configured.state.calls.filter(call => call[0] === 'backend').every(call => call[1] === packageRoot));
    assert.equal(configured.state.wslSettingReads, 0, 'native Linux does not require the Windows WSL setting');
    assert.equal(configured.state.authenticationReads, 0);
    assert.equal(configured.state.calls.some(call => call[0] === 'request'), false, 'enable does not start Remote');
    await configured.command('restore');
    assert.equal(configured.state.global, original);
    assert.deepEqual(configured.state.errors, []);
    console.log('PASS native Linux configuration: real activation commands use Linux official extension and Global wrapper, preserve restore backup, no account or Windows WSL setting');

    const found = await harness({ ...options, instances });
    await found.command('status');
    assert.deepEqual(found.state.calls.filter(call => call[0] === 'request'),
      [['request', controller, 'list'], ['request', controller, 'status', 501, false]]);
    assert.equal(found.state.quickPicks.length, 0);
    assert.equal(found.state.workspaceReads, 0);
    assert.equal(found.state.authenticationReads, 0);
    assert.deepEqual(found.state.errors, []);
    const multiple = await harness({ ...options, picks: [1], instances: [...instances,
      { childPid: 502, cwd: '/home/native-user/other-project', active: false }] });
    await multiple.command('status');
    assert.equal(multiple.state.quickPicks.length, 1);
    assert.deepEqual(multiple.state.calls.filter(call => call[0] === 'request'),
      [['request', controller, 'list'], ['request', controller, 'status', 502, false]]);
    assert.deepEqual(multiple.state.errors, []);
    assert.equal(multiple.state.authenticationReads, 0);
    assert.equal(multiple.state.calls.some(call => call[0] === 'request' && ['connect', 'pair', 'disconnect'].includes(call[2])), false);
    console.log('PASS native Linux local discovery: original backend without loaded chats/workspace, one optional instance choice, read-only status, no account or Remote start/pair/stop');
  } finally {
    Object.defineProperty(process, 'platform', platform);
    if (hadDistro) process.env.WSL_DISTRO_NAME = previousDistro;
    else delete process.env.WSL_DISTRO_NAME;
  }
}

(async () => {
  if (process.argv.includes('--auto-connect')) {
    await checkAutoConnect();
    return;
  }
  if (process.argv.includes('--linux-only')) {
    await checkNativeLinux();
    return;
  }
  if (process.argv.includes('--manifest')) {
    checkManifest();
    return;
  }
  if (process.argv.includes('--backend-only')) {
    await checkCommands();
    return;
  }
  if (process.argv.includes('--pairing-copy')) {
    await checkPairingCopy();
    return;
  }
  if (process.argv.includes('--maintenance')) {
    await checkMaintenance();
    return;
  }
  if (process.argv.includes('--notification-lifecycle')) {
    await checkNotificationLifecycle();
    return;
  }
  checkManifest();
  await checkTransport();
  await checkSettings();
  await checkCommands();
  await checkNotificationLifecycle();
  await checkPairingCopy();
  await checkMaintenance();
  await checkAutoConnect();
  await checkNativeLinux();
})().catch(error => { console.error(error); process.exitCode = 1; });
