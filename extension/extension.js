'use strict';

const vscode = require('vscode');
const { setInterval, clearInterval } = require('node:timers');
const { backend } = require('./backend');

function previousSetting() {
  const value = vscode.workspace.getConfiguration('chatgpt').inspect('cliExecutable')?.globalValue;
  return { wasSet: value !== undefined, value: value ?? null };
}

async function activate(context) {
  const status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 20);
  status.text = '$(device-mobile) Codex Remote：未查询';
  status.command = 'codexRemote.status';
  status.show();
  context.subscriptions.push(status);
  let busy = false;
  let autoStopped = false;
  let disposed = false;
  const attempted = new Set();

  function showStatus(report) {
    status.text = `$(device-mobile) Codex Remote：${report.status === 'connected' ? '已启动' : report.status === 'disabled' ? '未启动' : report.status}`;
    status.tooltip = '点击查看远程控制状态';
  }

  async function autoConnect() {
    if (busy || autoStopped || disposed || !vscode.workspace.getConfiguration('codexRemote').get('autoConnect', true)
        || !vscode.extensions.getExtension('openai.chatgpt')?.isActive
        || (vscode.env.remoteName && vscode.env.remoteName !== 'wsl')
        || (process.platform === 'win32' && !vscode.workspace.getConfiguration('chatgpt').get('runCodexInWindowsSubsystemForLinux'))
        || typeof previousSetting().value !== 'string') return;
    busy = true;
    let pid;
    try {
      const bridge = await getBackend();
      const location = await bridge.info();
      if (!location.installed || previousSetting().value !== location.wrapper || disposed) return;
      const instances = await bridge.request(location.controller, 'list');
      if (instances.length !== 1 || disposed) return;
      pid = instances[0].childPid;
      if (attempted.has(pid)) return;
      // A failed write may have succeeded upstream; never replay it automatically.
      attempted.add(pid);
      const report = await bridge.request(location.controller, 'auto-connect', pid);
      if (disposed) return;
      showStatus(report);
      if (!report.paired && report.pairingPending) attempted.delete(pid);
    } catch {
      if (pid !== undefined && !disposed) {
        status.text = '$(device-mobile) Codex Remote：自动启动未完成';
        void vscode.window.showWarningMessage('自动启动远程控制未完成，请运行“查看远程控制状态”，需要时手动启动。');
      }
    } finally { busy = false; }
  }

  async function getBackend() {
    if (vscode.env.remoteName && vscode.env.remoteName !== 'wsl') {
      throw new Error('请在 Ubuntu 本地、Windows + WSL 或 Remote-WSL 窗口使用。');
    }
    return backend(context.extensionPath);
  }

  async function maintain(bridge, location) {
    const current = previousSetting();
    if (current.value !== location.wrapper) return location;
    const official = vscode.extensions.getExtension('openai.chatgpt');
    if (!official) throw new Error('未找到官方 Codex 扩展。请安装后重试，或运行“恢复 Codex 启动设置（卸载前）”。');
    const updated = await bridge.maintain(official.extensionPath, current);
    if (updated.binaryChanged) {
      void vscode.window.showInformationMessage('远程控制配置已更新，请在任务结束后重载窗口。');
    }
    return updated;
  }

  async function operation(action) {
    const bridge = await getBackend();
    let location = await bridge.info();
    if (action === 'connect' || action === 'pair') location = await maintain(bridge, location);
    if (!location.installed) throw new Error('请先运行“Codex Remote: 配置远程控制”。');
    const instances = await bridge.request(location.controller, 'list');
    if (!instances.length) throw new Error('未找到可连接的 Codex。请打开 Codex 面板后重试。');
    const pid = instances.length === 1 ? instances[0].childPid : (await vscode.window.showQuickPick(
      instances.map(instance => ({ label: `Codex ${instance.childPid}`, description: instance.cwd,
        detail: instance.active ? '有任务正在运行' : '当前空闲', pid: instance.childPid })),
      { title: '选择 Codex' },
    ))?.pid;
    if (pid === undefined) return;
    const report = await bridge.request(location.controller, action, pid, action === 'pair');
    if (action === 'connect' || action === 'pair') attempted.delete(pid);
    showStatus(report);
    if (action === 'pair') {
      // Notification choices must not keep a completed backend operation busy.
      const message = '配对页已生成；浏览器未打开时可复制网页链接。';
      void vscode.window.showInformationMessage(message, '复制网页链接').then(async choice => {
        if (choice === '复制网页链接') {
          const distro = bridge.distro;
          const page = distro ? vscode.Uri.from({ scheme: 'file', authority: 'wsl.localhost', path: `/${distro}${report.pairingPage}` }) : vscode.Uri.file(report.pairingPage);
          await vscode.env.clipboard.writeText(page.toString());
        }
      }).catch(() => { void vscode.window.showErrorMessage('配对页链接未复制，请重试复制或手动打开已生成的页面。'); });
    } else if (action !== 'status') {
      void vscode.window.showInformationMessage(`远程控制${report.status === 'connected' ? '已启动' : '已停止'}。`);
    }
  }

  async function enable() {
    const official = vscode.extensions.getExtension('openai.chatgpt');
    if (!official) throw new Error('请先安装官方 Codex 扩展（openai.chatgpt）。');
    if (process.platform === 'win32' && !vscode.workspace.getConfiguration('chatgpt').get('runCodexInWindowsSubsystemForLinux')) {
      throw new Error('请在官方 Codex 设置中启用通过 WSL 运行。');
    }
    const bridge = await getBackend();
    const installed = await bridge.install(official.extensionPath, previousSetting());
    await vscode.workspace.getConfiguration('chatgpt').update('cliExecutable', installed.wrapper, vscode.ConfigurationTarget.Global);
    status.text = '$(device-mobile) Codex Remote：等待重载';
    void vscode.window.showInformationMessage('配置完成。请在任务结束后重载窗口，再运行“启动远程控制”。');
  }

  async function restore() {
    const bridge = await getBackend();
    const { backup } = await bridge.info();
    if (!backup) throw new Error('没有找到插件启用前的配置备份。');
    const current = previousSetting();
    if (current.value !== backup.managedValue) throw new Error('当前 cliExecutable 已被其他操作更改；本次未覆盖。');
    await vscode.workspace.getConfiguration('chatgpt').update('cliExecutable', backup.wasSet ? backup.value : undefined, vscode.ConfigurationTarget.Global);
    status.text = '$(device-mobile) Codex Remote：启动设置已恢复';
    void vscode.window.showInformationMessage('已恢复原 Codex 启动设置。请在任务结束后重载窗口，再卸载插件。');
  }

  const commands = { enable, restore, connect: () => operation('connect'), pair: () => operation('pair'),
    status: () => operation('status'), disconnect: () => operation('disconnect') };
  for (const [name, action] of Object.entries(commands)) {
    context.subscriptions.push(vscode.commands.registerCommand(`codexRemote.${name}`, async () => {
      if (busy) {
        void vscode.window.showInformationMessage('已有 Codex Remote 操作正在执行，请等待结果。');
        return;
      }
      busy = true;
      if (name === 'disconnect' || name === 'restore') autoStopped = true;
      if (name === 'connect' || name === 'pair' || name === 'enable') autoStopped = false;
      try {
        return await vscode.window.withProgress({ location: vscode.ProgressLocation.Notification, title: 'Codex Remote', cancellable: false }, action);
      } catch (error) {
        status.text = '$(device-mobile) Codex Remote：操作未完成';
        void vscode.window.showErrorMessage(error.message || '操作未完成，请先查询状态。');
      } finally { busy = false; }
    }));
  }

  // Startup maintenance never changes the user's startup settings or restarts Codex.
  if (typeof previousSetting().value === 'string' && (!vscode.env.remoteName || vscode.env.remoteName === 'wsl')
      && (process.platform !== 'win32' || vscode.workspace.getConfiguration('chatgpt').get('runCodexInWindowsSubsystemForLinux'))) {
    busy = true;
    try {
      const bridge = await getBackend();
      await maintain(bridge, await bridge.info());
    } catch (error) {
      void vscode.window.showWarningMessage(`远程控制配置更新失败：${error.message} 可运行“配置远程控制”或“恢复 Codex 启动设置（卸载前）”。`);
    } finally { busy = false; }
  }
  const timer = setInterval(() => { void autoConnect(); }, 5000);
  context.subscriptions.push({ dispose() { disposed = true; clearInterval(timer); } });
  void autoConnect();
}

module.exports = { activate };
