'use strict';

const { execFile } = require('node:child_process');
const path = require('node:path');

function execute(command, args, input) {
  return new Promise((resolve, reject) => {
    const child = execFile(command, args, {
      encoding: 'buffer', windowsHide: true, timeout: 120000, maxBuffer: 4 * 1024 * 1024,
    }, (error, stdout, stderr) => {
      if (error) {
        let message = stderr.toString('utf8').trim();
        if (!message) {
          try { message = JSON.parse(stdout.toString('utf8')).error; } catch {}
        }
        reject(new Error(message || '后端命令未完成；写操作结果可能未知，请先查询状态。'));
      } else resolve(stdout);
    });
    child.stdin.on('error', () => {});
    child.stdin.end(input === undefined ? undefined : JSON.stringify(input));
  });
}

function decodeWslList(buffer) {
  const utf16 = buffer[0] === 0xff && buffer[1] === 0xfe || buffer.includes(0);
  return buffer.toString(utf16 ? 'utf16le' : 'utf8').replace(/^\uFEFF/, '').split(/\r?\n/)
    .map(name => name.trim()).filter(Boolean);
}

async function transport(platform = process.platform, run = execute) {
  const distro = platform === 'win32'
    ? decodeWslList(await run('wsl.exe', ['--list', '--quiet'])).find(name => name.toLowerCase().startsWith('ubuntu'))
    : undefined;
  if (platform === 'win32' && !distro) throw new Error('没有找到官方 Codex 使用的 Ubuntu WSL 发行版。');
  // --exec keeps the default Linux shell from interpreting paths and arguments.
  return {
    async linuxPath(value) {
      if (platform !== 'win32') return value;
      return (await run('wsl.exe', ['-d', distro, '--exec', 'wslpath', '-a', '-u', value])).toString('utf8').trim();
    },
    async python(script, args, input) {
      const command = platform === 'win32' ? 'wsl.exe' : 'python3';
      const prefix = platform === 'win32' ? ['-d', distro, '--exec', 'python3'] : [];
      return JSON.parse((await run(command, [...prefix, script, ...args], input)).toString('utf8'));
    },
    distro,
  };
}

async function backend(packageRoot, platform = process.platform, run = execute) {
  const host = await transport(platform, run);
  const root = await host.linuxPath(packageRoot);
  const deploy = path.posix.join(root, 'scripts/deploy_backend.py');
  return {
    distro: host.distro || process.env.WSL_DISTRO_NAME,
    linuxPath: host.linuxPath,
    info: () => host.python(deploy, ['info']),
    async install(officialRoot, previous) {
      return host.python(deploy, ['install', '--extension-root', await host.linuxPath(officialRoot)], previous);
    },
    cli: (file, action, workspace, pid, open = false) => host.python(file, [
      action, '--workspace', workspace, ...(pid === undefined ? [] : ['--pid', String(pid)]), ...(open ? ['--open'] : []),
    ]),
  };
}

module.exports = { backend, transport, decodeWslList, execute };
