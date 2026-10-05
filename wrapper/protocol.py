"""JSONL framing confirmed against the official extension's captured streams."""

import json
from pathlib import Path


def same_directory(first, second):
    try:
        return Path(first).samefile(second)
    except (OSError, TypeError, ValueError):
        return False


class JsonlReader:
    def __init__(self):
        self.buffer = b""

    def feed(self, chunk):
        self.buffer += chunk
        lines = self.buffer.split(b"\n")
        self.buffer = lines.pop()
        return [self.decode(line) for line in lines if line.strip()]

    @staticmethod
    def decode(line):
        try:
            message = json.loads(line)
        except (ValueError, UnicodeError):
            raise ValueError("Invalid JSONL frame") from None
        if not isinstance(message, dict):
            raise ValueError("JSONL frame must be an object")
        return message

    def finish(self):
        if self.buffer:
            raise ValueError("Incomplete JSONL frame")
