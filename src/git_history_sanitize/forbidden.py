"""Bounded byte matching and safe forbidden-content inputs."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from pathlib import Path
from typing import BinaryIO

from .errors import SanitizeError

INPUT_LIMIT = 64 * 1024
CHUNK_SIZE = 64 * 1024
TOTAL_LIMIT = 1024 * 1024


class ForbiddenInputError(SanitizeError):
    """Raised when forbidden-content input is unsafe or exceeds its budget."""


class Matcher:
    """A byte Aho-Corasick matcher whose state spans input chunks."""

    def __init__(self, patterns: tuple[bytes, ...]):
        self._next: list[dict[int, int]] = [{}]
        self._failure = [0]
        self._terminal = [False]
        for pattern in patterns:
            node = 0
            for byte in pattern:
                child = self._next[node].get(byte)
                if child is None:
                    child = self._new_node()
                    self._next[node][byte] = child
                node = child
            self._terminal[node] = True
        queue: deque[int] = deque(self._next[0].values())
        while queue:
            node = queue.popleft()
            for byte, child in self._next[node].items():
                failure = self._failure[node]
                while failure and byte not in self._next[failure]:
                    failure = self._failure[failure]
                self._failure[child] = self._next[failure].get(byte, 0)
                self._terminal[child] = self._terminal[child] or self._terminal[self._failure[child]]
                queue.append(child)
        self._state = 0

    def _new_node(self) -> int:
        self._next.append({})
        self._failure.append(0)
        self._terminal.append(False)
        return len(self._next) - 1

    def reset(self) -> None:
        self._state = 0

    def feed(self, data: bytes) -> bool:
        for byte in data:
            while self._state and byte not in self._next[self._state]:
                self._state = self._failure[self._state]
            self._state = self._next[self._state].get(byte, 0)
            if self._terminal[self._state]:
                return True
        return False


def _validated(patterns: Iterable[bytes]) -> tuple[bytes, ...]:
    result: list[bytes] = []
    seen: set[bytes] = set()
    total = 0
    for pattern in patterns:
        if not pattern or len(pattern) > INPUT_LIMIT:
            raise ForbiddenInputError("invalid forbidden-content input")
        total += len(pattern)
        if total > TOTAL_LIMIT:
            raise ForbiddenInputError("invalid forbidden-content input")
        if pattern not in seen:
            seen.add(pattern)
            result.append(pattern)
    return tuple(result)


def arguments(values: Iterable[str]) -> tuple[bytes, ...]:
    try:
        return _validated(value.encode("utf-8", "strict") for value in values)
    except UnicodeError as error:
        raise ForbiddenInputError("invalid forbidden-content input") from error


def read_records(stream: BinaryIO, *, total_limit: int = TOTAL_LIMIT) -> tuple[bytes, ...]:
    records: list[bytes] = []
    pending = bytearray()
    total = 0

    def append(record: bytes) -> None:
        nonlocal total
        total += len(record)
        if len(record) > INPUT_LIMIT or total > total_limit:
            raise ForbiddenInputError("invalid forbidden-content input")
        records.append(record)

    while chunk := stream.read(CHUNK_SIZE):
        pending.extend(chunk)
        while (newline := pending.find(b"\n")) >= 0:
            append(bytes(pending[:newline]))
            del pending[:newline + 1]
        if len(pending) > INPUT_LIMIT:
            raise ForbiddenInputError("invalid forbidden-content input")
    if pending:
        append(bytes(pending))
    return _validated(records)


def collect(values: Iterable[str], files: Iterable[str], stdin: BinaryIO | None) -> tuple[bytes, ...]:
    patterns = list(arguments(values))
    for name in files:
        try:
            with Path(name).open("rb") as stream:
                patterns.extend(read_records(stream, total_limit=TOTAL_LIMIT - sum(map(len, patterns))))
        except (OSError, ForbiddenInputError) as error:
            raise ForbiddenInputError("invalid forbidden-content input") from error
    if stdin is not None:
        try:
            patterns.extend(read_records(stdin, total_limit=TOTAL_LIMIT - sum(map(len, patterns))))
        except (OSError, ForbiddenInputError) as error:
            raise ForbiddenInputError("invalid forbidden-content input") from error
    return _validated(patterns)
