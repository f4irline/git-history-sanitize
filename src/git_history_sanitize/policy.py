"""Restricted policy parsing and validation."""

from __future__ import annotations

import ast
import datetime as dt
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from .errors import PolicyError

_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")
_COMMIT = re.compile(r"^[0-9a-fA-F]{4,64}$")


def _without_comment(value: str) -> str:
    quote: str | None = None
    escaped = False
    for index, character in enumerate(value):
        if quote and quote == '"' and character == "\\" and not escaped:
            escaped = True
            continue
        if character in ("'", '"') and not escaped:
            quote = None if quote == character else character
        elif character == "#" and quote is None:
            return value[:index].rstrip()
        escaped = False
    return value.rstrip()


def _scalar(value: str, line_number: int) -> Any:
    value = _without_comment(value).strip()
    if not value:
        raise PolicyError(f"Missing value on line {line_number}")
    if value.startswith(('"', "'")):
        try:
            parsed = ast.literal_eval(value)
        except (SyntaxError, ValueError) as error:
            raise PolicyError(f"Invalid quoted value on line {line_number}") from error
        if not isinstance(parsed, str):
            raise PolicyError(f"Expected a string on line {line_number}")
        return parsed
    if value.isdigit():
        return int(value)
    if value in ("true", "false"):
        return value == "true"
    if any(token in value for token in ("[", "]", "{", "}", "&", "*", "!")):
        raise PolicyError(f"Unsupported YAML syntax on line {line_number}")
    return value


def _tokens(text: str) -> list[tuple[int, str, int]]:
    tokens: list[tuple[int, str, int]] = []
    for line_number, raw in enumerate(text.splitlines(), 1):
        if "\t" in raw:
            raise PolicyError(f"Tabs are not allowed in policy files (line {line_number})")
        content = _without_comment(raw).rstrip()
        if not content.strip():
            continue
        indent = len(content) - len(content.lstrip(" "))
        tokens.append((indent, content[indent:], line_number))
    return tokens


def _parse_block(
    tokens: list[tuple[int, str, int]], index: int, indent: int
) -> tuple[Any, int]:
    if index >= len(tokens):
        raise PolicyError("Unexpected end of policy")
    is_list = tokens[index][1].startswith("- ")
    if is_list:
        values: list[Any] = []
        while index < len(tokens):
            current_indent, content, line_number = tokens[index]
            if current_indent < indent:
                break
            if current_indent != indent or not content.startswith("- "):
                raise PolicyError(f"Invalid list indentation on line {line_number}")
            values.append(_scalar(content[2:], line_number))
            index += 1
        return values, index

    mapping: dict[str, Any] = {}
    while index < len(tokens):
        current_indent, content, line_number = tokens[index]
        if current_indent < indent:
            break
        if current_indent != indent:
            raise PolicyError(f"Invalid mapping indentation on line {line_number}")
        if content.startswith("- ") or ":" not in content:
            raise PolicyError(f"Expected a mapping entry on line {line_number}")
        key, raw_value = content.split(":", 1)
        key = key.strip()
        if not _KEY.fullmatch(key):
            raise PolicyError(f"Invalid policy key {key!r} on line {line_number}")
        if key in mapping:
            raise PolicyError(f"Duplicate policy key {key!r} on line {line_number}")
        raw_value = _without_comment(raw_value).strip()
        index += 1
        if raw_value:
            mapping[key] = _scalar(raw_value, line_number)
            continue
        if index >= len(tokens) or tokens[index][0] <= current_indent:
            raise PolicyError(f"Missing nested value for {key!r} on line {line_number}")
        mapping[key], index = _parse_block(tokens, index, tokens[index][0])
    return mapping, index


def parse_restricted_yaml(text: str) -> dict[str, Any]:
    tokens = _tokens(text)
    if not tokens:
        raise PolicyError("Policy file is empty")
    value, index = _parse_block(tokens, 0, tokens[0][0])
    if index != len(tokens) or not isinstance(value, dict):
        raise PolicyError("Policy root must be a mapping")
    return value


def _only_keys(value: dict[str, Any], allowed: set[str], location: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        names = ", ".join(sorted(unknown))
        raise PolicyError(f"Unknown key(s) in {location}: {names}")


def _mapping(value: Any, location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PolicyError(f"{location} must be a mapping")
    return value


def _string(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise PolicyError(f"{location} must be a non-empty string without NUL bytes")
    return value


def _message(value: Any, location: str) -> str:
    message = _string(value, location)
    if "\n" in message or "\r" in message:
        raise PolicyError(f"{location} must be a single line")
    return message


def _paths(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise PolicyError("paths.exclude must be a list")
    paths: list[str] = []
    for path in value:
        path = _string(path, "paths.exclude entry")
        stripped = path.rstrip("/")
        candidate = PurePosixPath(stripped)
        if (
            path.startswith("/")
            or not stripped
            or "\\" in path
            or any(part in (".", "..") for part in candidate.parts)
        ):
            raise PolicyError(f"Invalid excluded path: {path!r}")
        paths.append(path)
    if len(set(paths)) != len(paths):
        raise PolicyError("paths.exclude contains duplicate paths")
    return tuple(paths)


def _timestamp(value: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise PolicyError(f"Invalid RFC 3339 cutoff: {value!r}") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PolicyError("history.cutoff must include an explicit timezone")
    return parsed


@dataclass(frozen=True)
class History:
    cutoff_text: str | None
    cutoff_epoch: int | None
    cutoff_commit: str | None
    prefix_message: str


@dataclass(frozen=True)
class Policy:
    history: History
    excluded_paths: tuple[str, ...]
    mixed_message: str
    retained_refs: tuple[str, ...]

    @classmethod
    def from_text(cls, text: str) -> "Policy":
        root = parse_restricted_yaml(text)
        _only_keys(root, {"version", "history", "paths", "commits", "refs"}, "policy")
        if root.get("version") != 1:
            raise PolicyError("Only policy version 1 is supported")

        history_value = _mapping(root.get("history"), "history")
        _only_keys(history_value, {"cutoff", "cutoffCommit", "prefixMessage"}, "history")
        cutoff_text = history_value.get("cutoff")
        cutoff_commit = history_value.get("cutoffCommit")
        if (cutoff_text is None) == (cutoff_commit is None):
            raise PolicyError("Specify exactly one of history.cutoff or history.cutoffCommit")
        cutoff_epoch: int | None = None
        if cutoff_text is not None:
            cutoff_text = _string(cutoff_text, "history.cutoff")
            cutoff_epoch = int(_timestamp(cutoff_text).timestamp())
        if cutoff_commit is not None:
            cutoff_commit = _string(cutoff_commit, "history.cutoffCommit")
            if not _COMMIT.fullmatch(cutoff_commit):
                raise PolicyError("history.cutoffCommit must be a hexadecimal Git revision")
        prefix_message = _message(
            history_value.get("prefixMessage", "[sanitized]"), "history.prefixMessage"
        )

        paths_value = _mapping(root.get("paths", {"exclude": []}), "paths")
        _only_keys(paths_value, {"exclude"}, "paths")
        excluded_paths = _paths(paths_value.get("exclude", []))

        commits_value = _mapping(root.get("commits", {}), "commits")
        _only_keys(commits_value, {"mixedMessage"}, "commits")
        mixed_message = _message(
            commits_value.get("mixedMessage", "[sanitized]"), "commits.mixedMessage"
        )

        refs_value = _mapping(root.get("refs", {"keep": ["HEAD"]}), "refs")
        _only_keys(refs_value, {"keep"}, "refs")
        retained_refs = refs_value.get("keep", ["HEAD"])
        if retained_refs != ["HEAD"]:
            raise PolicyError("Version 1 supports only refs.keep: [HEAD]")

        return cls(
            history=History(cutoff_text, cutoff_epoch, cutoff_commit, prefix_message),
            excluded_paths=excluded_paths,
            mixed_message=mixed_message,
            retained_refs=("HEAD",),
        )

    @classmethod
    def from_file(cls, path: str) -> "Policy":
        try:
            return cls.from_text(open(path, encoding="utf-8").read())
        except OSError as error:
            raise PolicyError(f"Cannot read policy file {path!r}: {error.strerror}") from error
