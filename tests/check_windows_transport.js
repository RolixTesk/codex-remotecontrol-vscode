'use strict';

// Run as Windows Node with a result file inside the launcher's own temporary directory.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { backend, transport, execute } = require('../extension/backend');

function installedDirectory(folder, prefix) {
  const names = fs.readdirSync(folder).filter(name => name.startsWith(prefix)
    && fs.statSync(path.join(folder, name)).isDirectory());
  names.sort((a, b) => a.localeCompare(b, 'en', { numeric: true }));
  assert.ok(names.length, `Missing installed extension: ${prefix}`);
  return path.join(folder, names.at(-1));
}

async function main() {
  assert.equal(process.platform, 'win32', 'Use the installed Code.exe as Windows Node');
  assert.ok(process.argv[2], 'Pass a result file in an owned temporary directory');
  const resultFile = path.resolve(process.argv[2]);
  const working = path.join(path.dirname(resultFile), "work space'中文 $value");
  fs.mkdirSync(working); // Never overwrite a directory left by another run.
  const report = { completed: false };
  try {
    const host = await transport('win32');
    report.distro = host.distro;
    const oldLiteral = 'C:\\Users\\RolixTesk\\.vscode\\extensions\\rolix.codex-live-remote-0.1.0';
    let reproduced = false;
    try {
      await execute('wsl.exe', ['-d', host.distro, '--', 'wslpath', oldLiteral]);
    } catch (error) {
      assert.match(error.message, /wslpath/i);
      assert.ok(error.message.toLowerCase().includes(oldLiteral.replace(/\\/g, '').toLowerCase()),
        'Old separator failed without reproducing the reported backslash loss');
      reproduced = true;
    }
    assert.equal(reproduced, true, 'Old separator unexpectedly preserved the reported literal path');
    report.oldSeparatorReproduced = true;

    const extensions = path.join(process.env.USERPROFILE, '.vscode', 'extensions');
    const plugin = installedDirectory(extensions, 'rolix.codex-live-remote-');
    const official = installedDirectory(extensions, 'openai.chatgpt-');
    const project = path.resolve(__dirname, '..');
    const windowsDirs = [plugin, official, project, working];
    const linuxDirs = [];
    for (const directory of windowsDirs) linuxDirs.push(await host.linuxPath(directory));
    assert.ok(linuxDirs.every(directory => directory.startsWith('/')));
    assert.ok(linuxDirs.at(-1).endsWith("/work space'中文 $value"));

    const script = path.join(working, "echo script'中文 $arg.py");
    fs.writeFileSync(script, [
      'import json, sys', 'from pathlib import Path',
      'payload = json.load(sys.stdin)',
      'print(json.dumps({"argv": sys.argv[1:], "stdin": payload,',
      '                  "directoriesExist": [Path(p).is_dir() for p in payload["directories"]]}, ensure_ascii=False))',
      '',
    ].join('\n'));
    const argv = ["space 'quote' 中文 $HOME ; literal", 'C:\\path with spaces\\中文\\file', 'backslash\\and"double"'];
    const payload = { wasSet: false, value: null, text: "stdin '中文' $HOME \\ line\nnext", directories: linuxDirs };
    const echoed = await host.python(await host.linuxPath(script), argv, payload);
    assert.deepEqual(echoed.argv, argv);
    assert.deepEqual(echoed.stdin, payload);
    assert.deepEqual(echoed.directoriesExist, [true, true, true, true]);
    report.realDirectoriesValidated = ['installed plugin', 'official extension', 'current project'];
    report.specialPathAndPythonArgvStdinExact = true;

    const info = await (await backend(plugin, 'win32')).info();
    assert.equal(info.installed, true);
    assert.equal(typeof info.wrapper, 'string');
    assert.equal(typeof info.cli, 'string');
    report.installedBackendInfoPassed = true;
    report.completed = true;
  } catch (error) {
    report.error = error.message;
    process.exitCode = 1;
  } finally {
    fs.rmSync(working, { recursive: true, force: true });
    report.temporaryWorkRemoved = !fs.existsSync(working);
    fs.writeFileSync(resultFile, JSON.stringify(report, null, 2) + '\n');
  }
}

main().catch(error => {
  if (process.argv[2]) fs.writeFileSync(process.argv[2], JSON.stringify({ completed: false, error: error.message }) + '\n');
  process.exitCode = 1;
});
