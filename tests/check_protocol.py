#!/usr/bin/env python3
"""Check framing and redaction using sanitized fixtures and synthetic secrets only."""

import json
from pathlib import Path
import random
import sys
import tempfile
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "wrapper"))
sys.path.insert(0, str(ROOT / "scripts"))
from protocol import JsonlReader
from observe_protocol import KEYS, METHODS, Redactor, observe


def encode(messages):
    return b"".join((json.dumps(m, ensure_ascii=False) + "\n").encode() for m in messages)


def parse_chunks(data, sizes):
    reader, messages, position = JsonlReader(), [], 0
    for size in sizes:
        messages.extend(reader.feed(data[position:position + size]))
        position += size
    messages.extend(reader.feed(data[position:]))
    reader.finish()
    return messages


def expect_error(callback, message, sentinel):
    try:
        callback()
    except ValueError as error:
        assert str(error) == message
        rendered = "".join(traceback.format_exception(error))
        assert sentinel not in rendered, "parser error exposed original frame"
    else:
        raise AssertionError("expected framing error")


def check_framing():
    messages = [
        {"id": 7, "method": "turn/start", "params": {"text": "你好 🧪\nsecond line"}},
        {"method": "item/agentMessage/delta", "params": {"delta": "é\r\n\x00"}},
        {"id": 7, "result": {"ok": True}},
    ]
    data = b"\n \r\n" + encode(messages)
    for size in (1, 2, 3, 7, 64, len(data)):
        assert parse_chunks(data, [size] * (len(data) // size)) == messages
    for cut in range(len(data) + 1):
        assert parse_chunks(data, [cut]) == messages
    for seed in range(10):
        randomizer = random.Random(seed)
        assert parse_chunks(data, [randomizer.randint(1, 37) for _ in range(30)]) == messages
    reader = JsonlReader()
    assert reader.feed(b'{"id":1}') == []
    expect_error(reader.finish, "Incomplete JSONL frame", "id")
    assert reader.feed(b"\n") == [{"id": 1}]
    reader.finish()
    sentinel = "SYNTHETIC_SECRET_INVALID_FRAME"
    for frame, error in [
        (b'{"text":"' + sentinel.encode() + b'", invalid}\n', "Invalid JSONL frame"),
        (b'{"text":"' + sentinel.encode() + b'\xff"}\n', "Invalid JSONL frame"),
        (json.dumps([sentinel]).encode() + b"\n", "JSONL frame must be an object"),
        (json.dumps(sentinel).encode() + b"\n", "JSONL frame must be an object"),
        (b"null\n", "JSONL frame must be an object"),
    ]:
        expect_error(lambda: JsonlReader().feed(frame), error, sentinel)
    print("PASS UTF-8 and JSONL fixed/random chunking, EOF, safe invalid-frame errors")


def check_fixture():
    data = (ROOT / "tests" / "fixtures" / "observed.jsonl").read_bytes()
    records = parse_chunks(data, [17] * (len(data) // 17))
    assert len(records) == 56
    requests = {(r["run"], r["message"]["id"]): r["message"] for r in records
                if r["direction"] == "stdin" and "method" in r["message"]}
    responses = {(r["run"], r["message"]["id"]): r["message"] for r in records
                 if r["direction"] == "stdout" and "id" in r["message"]
                 and "method" not in r["message"]}
    assert len(requests) == 12 and requests.keys() == responses.keys()
    threads, turns = set(), set()
    for request_key, request in requests.items():
        result = responses[request_key].get("result", {})
        if "thread" in result:
            thread_id = result["thread"]["id"]
            threads.add(thread_id)
            if request["method"] in ("thread/read", "thread/resume"):
                assert request["params"]["threadId"] == thread_id
        if request["method"] == "turn/start":
            turns.add((request["params"]["threadId"], result["turn"]["id"]))
    lifecycle = {method: set() for method in ("turn/started", "turn/completed")}
    methods = set()
    for record in records:
        message = record["message"]
        method = message.get("method")
        if method is None:
            continue
        assert method in METHODS
        assert Redactor().message(message)["method"] == method
        methods.add(method)
        params = message.get("params", {})
        if "threadId" in params:
            assert params["threadId"] in threads
        if "turnId" in params:
            assert (params["threadId"], params["turnId"]) in turns
        if method in lifecycle:
            lifecycle[method].add((params["threadId"], params["turn"]["id"]))
    assert len(turns) == 2 and all(pairs == turns for pairs in lifecycle.values())
    assert {"initialize", "thread/start", "thread/resume", "turn/start",
            "item/agentMessage/delta", "item/commandExecution/outputDelta"} <= methods
    print("PASS 56 observed records, 12 response pairs, 2 thread/turn lifecycle associations")


def check_redaction():
    secrets = ["SYNTHETIC_BEARER_TOKEN", "SYNTHETIC_COOKIE_VALUE", "SYNTHETIC_PATH_你好"]
    message = {"id": secrets[0], "method": "turn/start", "params": {
        "threadId": secrets[1], "turnId": secrets[2], "text": secrets[0],
        secrets[0]: {secrets[1]: [secrets[2], {"text": secrets[1]}]},
        "items": [{"type": "text", "text": secret} for secret in secrets],
        "status": "completed", "exitCode": 0, "networkAccess": False,
        "method": "turn/start", "error": None,
    }}
    redactor = Redactor()
    redacted = redactor.message(message)
    assert all(secret not in json.dumps(redacted, ensure_ascii=False) for secret in secrets)

    def shape(before, after):
        if isinstance(before, dict):
            assert isinstance(after, dict) and len(before) == len(after)
            for (old_key, old_value), (new_key, new_value) in zip(before.items(), after.items()):
                assert new_key == old_key if old_key in KEYS else new_key.startswith("redacted-key-")
                shape(old_value, new_value)
        elif isinstance(before, list):
            assert isinstance(after, list) and len(before) == len(after)
            for old, new in zip(before, after):
                shape(old, new)
        elif not isinstance(before, str):
            assert before == after

    shape(message, redacted)
    params = redacted["params"]
    assert redacted["method"] == "turn/start" and params["method"] == "[redacted]"
    assert params["status"] == "completed" and params["items"][0]["type"] == "text"
    linked = redactor.message({"id": secrets[0], "params": {
        "id": secrets[1], "threadId": secrets[1], "turnId": secrets[2],
    }})
    assert linked["id"] == redacted["id"]
    assert linked["params"]["id"] == linked["params"]["threadId"] == params["threadId"]
    assert linked["params"]["turnId"] == params["turnId"]
    assert redactor.message({"id": 17})["id"] != redactor.message({"id": "17"})["id"]
    assert redactor.message({"method": secrets[0]})["method"] == "[redacted]"
    print("PASS secret strings/unknown keys removed, structure and ID correlation retained")

    with tempfile.TemporaryDirectory(prefix="codex-protocol-check-") as temp:
        root = Path(temp)
        run = root / "captures" / "synthetic-run"
        run.mkdir(parents=True)
        (run / "stdin.bin").write_bytes(encode([
            {"id": 1, "method": "initialize", "params": {"text": secrets[0]}},
            {"id": 2, "method": secrets[1], "params": {secrets[2]: secrets[0]}},
        ]))
        (run / "stdout.bin").write_bytes(encode([
            {"id": 1, "result": {"text": secrets[0]}}, {"id": 2, "result": secrets[2]},
        ]))
        fixture = root / "fixture.jsonl"
        summary = observe(run.parent, fixture)
        exported = fixture.read_text() + json.dumps(summary, ensure_ascii=False)
        assert all(secret not in exported for secret in secrets), "observe summary leaked unknown method text"
        assert summary["fixtureRecords"] == 2
        selected = [json.loads(line)["message"] for line in fixture.read_text().splitlines()]
        assert selected[0]["id"] == selected[1]["id"]
    print("PASS synthetic observe fixture and summary contain no credential text")


if __name__ == "__main__":
    check_framing()
    check_fixture()
    check_redaction()
