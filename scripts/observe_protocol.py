#!/usr/bin/env python3
"""Create a structural fixture; never copy arbitrary strings or keys from captures."""

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "wrapper"))
from protocol import JsonlReader

METHODS = {
    "initialize", "thread/start", "thread/resume", "thread/read", "turn/start",
    "turn/steer", "turn/interrupt", "remoteControl/status/read",
    "thread/started", "thread/status/changed", "turn/started", "turn/completed",
    "item/started", "item/completed", "item/agentMessage/delta",
    "item/commandExecution/outputDelta",
}
KEYS = set("""id method params result error code message clientInfo name title version
capabilities experimentalApi extensions form mcpServerOpenaiFormElicitation
requestAttestation userAgent codexHome platformFamily platformOs thread turn item
threadId turnId itemId type status input text text_elements delta items itemsView
startedAt completedAt durationMs emittedAtMs startedAtMs completedAtMs cwd path
model modelProvider modelProviderName createdAt updatedAt recencyAt ephemeral
environments environmentId runtimeWorkspaceRoots sessionId preview turns
includeTurns excludeTurns history permissions approvalPolicy approvalsReviewer
config personality serviceTier threadSource experimentalRawEvents dynamicTools
approvalRequirements sandbox sandboxPolicy networkAccess reasoningEffort effort
summary collaborationMode mode settings reasoning_effort developer_instructions
clientUserMessageId disabledPluginIds additionalContext responsesapiClientMetadata
turnTrigger outputSchema multiAgentMode allowProviderModelFallback historyMode
forkedFromId parentThreadId projectId extra section sectionEnteredAt source
originator canAcceptDirectInput agentNickname agentRole gitInfo cliVersion
daybreakEnabled activePermissionProfile extends instructionSources initialTurnsPage
turnsBackwardsCursor itemsBackwardsCursor phase memoryCitation delivery questions
content command commandActions aggregatedOutput exitCode processId durationMs
serverName installationId trace _meta""".split())
ENUMS = {
    "text", "image", "userMessage", "agentMessage", "commandExecution", "fileChange",
    "mcpToolCall", "reasoning", "idle", "active", "running", "inProgress", "completed",
    "failed", "interrupted", "disabled", "enabled", "starting", "notLoaded",
}


class Redactor:
    def __init__(self):
        self.ids = {}
        self.keys = {}

    def redact(self, value, key="", top=False):
        if key == "id" or key.endswith("Id"):
            if value is not None and isinstance(value, (str, int)):
                token = (type(value).__name__, value)
                return self.ids.setdefault(token, f"id-{len(self.ids) + 1}")
        if isinstance(value, dict):
            return {
                k if k in KEYS else self.keys.setdefault(k, f"redacted-key-{len(self.keys) + 1}"):
                    self.redact(v, k, top=False)
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [self.redact(v) for v in value]
        if isinstance(value, str):
            if top and key == "method" and value in METHODS:
                return value
            if key in ("type", "status") and value in ENUMS:
                return value
            return "[redacted]"
        return value

    def message(self, message):
        result = self.redact(message)
        if message.get("method") in METHODS:
            result["method"] = message["method"]
        return result


def observe(root, fixture):
    redactor = Redactor()
    records, summaries = [], []
    for number, run in enumerate(sorted(root.iterdir()), 1):
        streams = {}
        for direction in ("stdin", "stdout"):
            reader = JsonlReader()
            messages = reader.feed((run / f"{direction}.bin").read_bytes())
            reader.finish()
            streams[direction] = messages
        requests = {m["id"]: m for m in streams["stdin"] if "id" in m and "method" in m}
        responses = {m["id"]: m for m in streams["stdout"] if "id" in m and "method" not in m}
        selected = {i for i, m in requests.items() if m["method"] in METHODS}
        seen = set()
        for direction, messages in streams.items():
            for m in messages:
                if "method" in m:
                    if m["method"] not in METHODS:
                        continue
                    # One sample per delta method; retain lifecycle events and requests.
                    if m["method"].endswith("delta") or m["method"].endswith("Delta"):
                        if m["method"] in seen:
                            continue
                        seen.add(m["method"])
                elif m.get("id") not in selected:
                    continue
                records.append({"run": f"run-{number}", "direction": direction,
                                "message": redactor.message(m)})
        summaries.append({
            "run": f"run-{number}",
            "frames": {d: len(v) for d, v in streams.items()},
            "methods": {d: dict(Counter(
                m["method"] if m.get("method") in METHODS else
                ("<other>" if "method" in m else "<response>") for m in v))
                        for d, v in streams.items()},
            "unmatchedRequests": sum(i not in responses for i in requests),
            "serverRequests": sum("id" in m and "method" in m for m in streams["stdout"]),
            "initializedNotifications": sum(m.get("method") == "initialized"
                                            for m in streams["stdin"]),
        })
    fixture.parent.mkdir(parents=True, exist_ok=True)
    fixture.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))
    return {"fixtureRecords": len(records), "runs": summaries,
            "ordering": "Per-stream order only; cross-stream timing was not captured."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture_root", type=Path)
    parser.add_argument("fixture", type=Path)
    args = parser.parse_args()
    print(json.dumps(observe(args.capture_root, args.fixture), indent=2))
