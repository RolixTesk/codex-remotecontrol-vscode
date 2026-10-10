'use strict';

const vscode = require('vscode');
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

  async function getBackend() {
    if (vscode.env.remoteName && vscode.env.remoteName !== 'wsl') {
      throw new Error('当前版本支持 Windows + WSL 和 Remote-WSL 窗口。');
    }
    return backend(context.extensionPath);
  }

  async function project() {
    const folders = vscode.workspace.workspaceFolders || [];
    if (!folders.length) throw new Error('请先打开要连接的项目文件夹。');
    const folder = folders.length === 1 ? folders[0] : (await vscode.window.showQuickPick(
      folders.map(folder => ({ label: folder.name, description: folder.uri.fsPath, folder })),
      { title: '选择要连接的项目' },
    ))?.folder;
    if (folder && !['file', 'vscode-remote'].includes(folder.uri.scheme)) throw new Error('当前项目不是可连接的本地或 WSL 文件夹。');
    return folder;
  }

  async function operation(action) {
    const folder = await project();
    if (!folder) return;
    const bridge = await getBackend();
    const location = await bridge.info();
    if (!location.installed) throw new Error('请先运行“Codex Remote: 启用 / 更新接入”。');
    const cwd = await bridge.linuxPath(folder.uri.fsPath);
    const threads = await bridge.cli(location.cli, 'list', cwd);
    const pids = [...new Set(threads.map(thread => thread.childPid))];
    if (!pids.length) throw new Error('此项目没有已加载的 Codex 聊天。请在官方 Codex 面板打开聊天，必要时在空闲窗口重载。');
    const pid = pids.length === 1 ? pids[0] : (await vscode.window.showQuickPick(
      pids.map(pid => ({ label: `Codex 进程 ${pid}`, description: threads.some(t => t.childPid === pid && t.active) ? '有任务正在运行' : '当前空闲', pid })),
      { title: '此项目有多个会话进程，请明确选择' },
    ))?.pid;
    if (pid === undefined) return;
    const report = await bridge.cli(location.cli, action, cwd, pid, action === 'pair');
    status.text = `$(device-mobile) Codex Remote：${report.status === 'connected' ? '已连接' : report.status === 'disabled' ? '未连接' : report.status}`;
    status.tooltip = `${folder.name} · Codex PID ${pid} · 最近查询结果`;
    if (action === 'pair') {
      // Notification choices must not keep a completed backend operation busy.
      void vscode.window.showInformationMessage('配对页已生成；请在手机 ChatGPT 中配对，选择此主机的同一聊天。', '打开配对页').then(async choice => {
        if (choice === '打开配对页') {
          const distro = bridge.distro || (folder.uri.authority?.startsWith('wsl+') ? decodeURIComponent(folder.uri.authority.slice(4)) : undefined);
          const page = distro ? vscode.Uri.from({ scheme: 'file', authority: 'wsl.localhost', path: `/${distro}${report.pairingPage}` }) : vscode.Uri.file(report.pairingPage);
          if (!await vscode.env.openExternal(page)) void vscode.window.showWarningMessage(`浏览器未打开，请手动打开已生成的配对页：${report.pairingPage}`);
        }
      }).catch(error => { void vscode.window.showErrorMessage(error.message || '配对页未打开，请手动打开已生成的页面。'); });
    } else if (action !== 'status') {
      void vscode.window.showInformationMessage(`Codex Remote：${report.status === 'connected' ? '已连接' : '已断开'} ${folder.name}`);
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
    void vscode.window.showInformationMessage('接入已配置。请在任务结束后重载该窗口，打开 Codex 聊天，再运行“连接当前项目”。');
  }

  async function restore() {
    const bridge = await getBackend();
    const { backup } = await bridge.info();
    if (!backup) throw new Error('没有找到插件启用前的配置备份。');
    const current = previousSetting();
    if (current.value !== backup.managedValue) throw new Error('当前 cliExecutable 已被其他操作更改；本次未覆盖。');
    await vscode.workspace.getConfiguration('chatgpt').update('cliExecutable', backup.wasSet ? backup.value : undefined, vscode.ConfigurationTarget.Global);
    status.text = '$(device-mobile) Codex Remote：接入配置已恢复';
    void vscode.window.showInformationMessage('已恢复启用插件前的 CLI 配置。请在任务结束后重载窗口，再卸载插件。');
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
      try {
        return await vscode.window.withProgress({ location: vscode.ProgressLocation.Notification, title: 'Codex Remote', cancellable: false }, action);
      } catch (error) {
        status.text = '$(device-mobile) Codex Remote：操作未完成';
        void vscode.window.showErrorMessage(error.message || '操作未完成，请先查询状态。');
      } finally { busy = false; }
    }));
  }
}

module.exports = { activate };
