"""Canonical non-sensitive scope description stored with published output."""

from __future__ import annotations

import json
from pathlib import Path

from .errors import VerificationError
from .source_scope import SourceScope

_NAME = "git-history-sanitize-scope.json"


def _value(scope: SourceScope) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": scope.mode,
        "coverage": scope.description,
        "boundary_count": scope.boundary_count,
        "included_commit_count": len(scope.commits),
        "included_object_count": len(scope.objects),
    }


def write(repository: Path, scope: SourceScope) -> None:
    (repository / _NAME).write_bytes(json.dumps(_value(scope), sort_keys=True, separators=(",", ":")).encode() + b"\n")


def read(repository: Path, mode: str) -> dict[str, object]:
    path = repository / _NAME
    try:
        data = path.read_bytes()
        value = json.loads(data.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise VerificationError("verification failed: scope.metadata", invariant="scope.metadata") from error
    if not isinstance(value, dict) or set(value) != {"schema_version", "mode", "coverage", "boundary_count", "included_commit_count", "included_object_count"}:
        raise VerificationError("verification failed: scope.metadata", invariant="scope.metadata")
    if value.get("schema_version") != 1 or value.get("mode") != mode or value.get("coverage") not in {
        "complete reachable history", "declared shallow HEAD history only", "HEAD tree snapshot; inherited history excluded",
    } or any(type(value.get(key)) is not int or value[key] < 0 for key in ("boundary_count", "included_commit_count", "included_object_count")):
        raise VerificationError("verification failed: scope.metadata", invariant="scope.metadata")
    if data != json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n":
        raise VerificationError("verification failed: scope.metadata", invariant="scope.metadata")
    return value
