'use strict';

const assert = require('node:assert/strict');
const vscode = require('vscode');

async function run() {
  assert.equal(vscode.extensions.getExtension('openai.chatgpt'), undefined,
    'Official Codex must not be loaded in this isolated host');
  const extension = vscode.extensions.getExtension('rolix.codex-live-remote');
  assert.ok(extension, 'Development extension was not discovered');
  await extension.activate();
  assert.equal(extension.isActive, true);
  const commands = new Set(await vscode.commands.getCommands(true));
  for (const name of ['enable', 'restore', 'connect', 'pair', 'status', 'disconnect']) {
    assert.ok(commands.has(`codexRemote.${name}`), `Missing command: ${name}`);
  }
  console.log('PASS isolated ExtensionDevelopmentHost: activation and six commands; no commands executed');
}

module.exports = { run };
