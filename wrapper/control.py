"""A private control socket sharing the VS Code-owned app-server's stdio."""

import json
import os
from pathlib import Path
import queue
import socket
import threading
import uuid

from protocol import JsonlReader, same_directory

METHODS = {"thread/read", "turn/steer", "remoteControl/status/read",
           "remoteControl/enable", "remoteControl/disable",
           "remoteControl/pairing/start", "remoteControl/pairing/status", "remoteControl/client/list"}


def error(message):
    return {"error": {"code": -32090, "message": message}}


class Control:
    def __init__(self, path, cwd, child_pid, write):
        self.path, self.cwd, self.child_pid, self.write = Path(path), cwd, child_pid, write
        self.lock = threading.Lock()
        self.pending, self.owned, self.vscode_requests = {}, set(), {}
        self.ready, self.closed = False, False
        self.threads, self.active = set(), {}
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.listener.bind(str(self.path))
        self.path.chmod(0o600)
        self.listener.listen(1)
        self.listener.settimeout(1)
        threading.Thread(target=self.serve, daemon=True).start()

    def client_frame(self, raw):
        try:
            m = JsonlReader.decode(raw)
        except ValueError:
            m = {}
        with self.lock:
            if (m.get("method") in ("initialize", "thread/start", "thread/resume")
                    and type(m.get("id")) in (str, int)):
                self.vscode_requests[m.get("id")] = m["method"]
            self.write(raw)

    def server_frame(self, raw):
        try:
            m = JsonlReader.decode(raw)
        except ValueError:
            return raw
        if "id" in m and type(m["id"]) not in (str, int):
            return raw
        # Keep original server request IDs; this control socket never answers them.
        if "method" not in m and m.get("id") in self.owned:
            waiter = self.pending.pop(m["id"], None)
            if waiter is not None:
                try:
                    waiter.put_nowait(m)
                except queue.Full:
                    pass
            return b""
        method = self.vscode_requests.pop(m.get("id"), None) if "method" not in m else None
        if method == "initialize":
            self.ready = "result" in m and "error" not in m
        elif method in ("thread/start", "thread/resume"):
            thread = m.get("result", {}).get("thread", {})
            if ((self.cwd is None or same_directory(thread.get("cwd"), self.cwd))
                    and thread.get("ephemeral") is not True):
                self.threads.add(thread["id"])
        params = m.get("params") or {}
        thread_id = params.get("threadId")
        if m.get("method") == "turn/started" and thread_id in self.threads:
            self.active[thread_id] = params["turn"]["id"]
        elif m.get("method") == "turn/completed":
            if self.active.get(thread_id) == params["turn"]["id"]:
                self.active.pop(thread_id, None)
        elif m.get("method") in ("thread/closed", "thread/deleted"):
            self.threads.discard(thread_id)
            self.active.pop(thread_id, None)
        return raw

    def call(self, request):
        method = request.get("method")
        if method == "status":
            return {"result": {"initialized": self.ready, "childPid": self.child_pid,
                               "threads": sorted(self.threads), "activeTurns": dict(self.active)}}
        params = request.get("params", {})
        if not isinstance(method, str) or method not in METHODS or not isinstance(params, dict):
            return error("Method is outside the control allowlist")
        if not self.ready or self.closed:
            return error("VS Code initialization is not ready or the connection closed")
        if method in ("thread/read", "turn/steer") and params.get("threadId") not in self.threads:
            return error("Thread is not loaded in this control scope")
        if method == "turn/steer":
            if not params.get("expectedTurnId") or self.active.get(params["threadId"]) != params["expectedTurnId"]:
                return error("Expected turn is not the observed active turn")
            if not isinstance(params.get("input"), list) or not params["input"]:
                return error("Steering input is required")
        if (method in ("remoteControl/enable", "remoteControl/disable")
                and (set(params) != {"ephemeral"} or params["ephemeral"] is not True)):
            return error("Remote control requires ephemeral=true")
        if (method == "remoteControl/pairing/start"
                and (set(params) != {"manualCode"} or params["manualCode"] is not True)):
            return error("Pairing requires manualCode=true")
        if (method == "remoteControl/pairing/status"
                and (set(params) != {"pairingCode"} or not isinstance(params["pairingCode"], str)
                     or not params["pairingCode"])):
            return error("Pairing status requires the issued pairingCode")
        if (method == "remoteControl/client/list"
                and (set(params) != {"environmentId", "limit"}
                     or not isinstance(params["environmentId"], str) or not params["environmentId"]
                     or type(params["limit"]) is not int or params["limit"] != 1)):
            return error("Client lookup requires environmentId and limit=1")
        request_id = "__codex_bridge__/" + uuid.uuid4().hex
        waiter = queue.Queue(maxsize=1)
        with self.lock:
            if self.closed:
                return error("App-server connection closed")
            self.pending[request_id] = waiter
            # ponytail: retain IDs until app-server exit so even late replies stay private.
            self.owned.add(request_id)
            raw = json.dumps({"id": request_id, "method": method, "params": params}).encode() + b"\n"
            try:
                self.write(raw)
            except OSError:
                self.pending.pop(request_id, None)
                return error("Write failed; request outcome is unknown, do not retry automatically")
        try:
            return waiter.get(timeout=30)
        except queue.Empty:
            self.pending.pop(request_id, None)
            return error("Response timed out; request outcome is unknown, do not retry automatically")

    def serve(self):
        while not self.closed:
            try:
                conn, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with conn:
                conn.settimeout(5)
                try:
                    with conn.makefile("rb") as f:
                        raw = f.readline(65537)
                    if len(raw) > 65536 or not raw.endswith(b"\n"):
                        result = error("Invalid control frame")
                    else:
                        result = self.call(JsonlReader.decode(raw))
                    conn.sendall(json.dumps(result).encode() + b"\n")
                except (OSError, ValueError, TypeError):
                    # A disconnected controller must not close VS Code's connection.
                    continue

    def close(self):
        with self.lock:
            self.closed = True
            self.listener.close()
            for waiter in list(self.pending.values()):
                try:
                    waiter.put_nowait(error("App-server connection closed"))
                except queue.Full:
                    pass
            self.pending.clear()
        self.path.unlink(missing_ok=True)
