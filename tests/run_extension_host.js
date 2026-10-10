'use strict';

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { runTests } = require('@vscode/test-electron');

async function main() {
  if (process.platform !== 'win32') throw new Error('Run this script with the installed Code.exe as Windows Node');
  const root = path.resolve(__dirname, '..');
  const isolated = path.join(os.tmpdir(), 'codex-remote-host-test');
  fs.mkdirSync(isolated); // Refuse an existing directory; cleanup belongs only to this run.
  try {
    delete process.env.ELECTRON_RUN_AS_NODE;
    await runTests({
      vscodeExecutablePath: 'D:\\Users\\RolixTesk\\AppData\\Local\\Programs\\Microsoft VS Code\\Code.exe',
      extensionDevelopmentPath: root,
      extensionTestsPath: path.join(root, 'tests/check_extension_host.js'),
      launchArgs: [
        '--new-window', '--disable-extensions', '--disable-telemetry',
        `--user-data-dir=${path.join(isolated, 'user-data')}`,
        `--extensions-dir=${path.join(isolated, 'extensions')}`,
      ],
    });
  } finally {
    fs.rmSync(isolated, { recursive: true, force: true, maxRetries: 3, retryDelay: 100 });
  }
  console.log('PASS host exited and isolated test directory removed');
}

main().catch(error => { console.error(error); process.exitCode = 1; });
