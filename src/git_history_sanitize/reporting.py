"""Explicit, redacted JSON v1 reporting owned by the CLI boundary."""

from __future__ import annotations

import json
from typing import Any

from .engine import Plan, RewriteReport
from .errors import ErrorMetadata, SanitizeError, VerificationError
from .verify import VerificationReport

SCHEMA_VERSION = 1
_PUBLICATION_STATES = {"not_published", "receipt_published", "output_published"}
_INTERNAL = ErrorMetadata(
    "internal_error", "internal", "An unexpected internal error occurred.",
    "Retry the command; if the problem persists, report it without sensitive inputs.",
)


def _safe_text(value: str) -> str:
    """Convert surrogateescaped bytes to unambiguous printable byte escapes.

    Literal backslashes are doubled before a surrogate becomes ``\\xHH``. This
    keeps a literal ``\\xFF`` distinct from a byte that failed UTF-8 decoding.
    """
    result: list[str] = []
    for character in value:
        codepoint = ord(character)
        if character == "\\":
            result.append("\\\\")
        elif 0xDC80 <= codepoint <= 0xDCFF:
            result.append(f"\\x{codepoint - 0xDC00:02x}")
        elif 0xD800 <= codepoint <= 0xDFFF:
            result.append("\\uFFFD")
        else:
            result.append(character)
    return "".join(result)


def _normalize(value: Any) -> Any:
    if isinstance(value, str):
        return _safe_text(value)
    if isinstance(value, tuple):
        return [_normalize(item) for item in value]
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, dict):
        return {_safe_text(str(key)): _normalize(item) for key, item in value.items()}
    return value


def _hooks(inventory: Any, stripped: bool) -> dict[str, Any]:
    return {
        "action": "stripped" if stripped else "preserved",
        "count": len(inventory.hooks),
        "names": list(inventory.names),
        "warnings": {name: list(names) for name, names in inventory.warning_categories.items()},
    }


def _plan_result(value: Plan) -> dict[str, Any]:
    return {
        "source_commits": value.source_commits,
        "discarded_commits": value.discarded_commits,
        "retained_commits_before_path_filter": value.retained_commits_before_path_filter,
        "mode": value.mode,
        "scope": value.scope,
        "boundary_count": value.boundary_count,
        "included_commit_count": value.included_commit_count,
        "included_object_count": value.included_object_count,
        "retained_head_path_count": value.retained_head_path_count,
        "excluded_paths": list(value.excluded_paths),
        "hooks": _hooks(value.hooks, value.hooks_stripped),
    }


def _verification_result(value: VerificationReport) -> dict[str, Any]:
    return {
        "head": value.head,
        "commit_count": value.commit_count,
        "root": value.root,
        "retained_refs": list(value.retained_refs),
        "excluded_paths": list(value.excluded_paths),
        "mode": value.mode,
        "scope": value.scope,
        "boundary_count": value.boundary_count,
        "included_commit_count": value.included_commit_count,
        "included_object_count": value.included_object_count,
    }


def _rewrite_result(value: RewriteReport) -> dict[str, Any]:
    return {
        "history": {
            "source_commits": value.compact.original_commits,
            "discarded_commits": value.compact.discarded_commits,
        },
        "verification": _verification_result(value.verification),
        "hooks": _hooks(value.hooks, value.hooks_stripped),
    }


def _result(command: str, value: Any) -> dict[str, Any]:
    if command == "doctor":
        return dict(value)
    if command == "plan" and isinstance(value, Plan):
        return _plan_result(value)
    if command == "rewrite" and isinstance(value, RewriteReport):
        return _rewrite_result(value)
    if command == "verify" and isinstance(value, VerificationReport):
        return _verification_result(value)
    raise TypeError("unsupported CLI reporting result")


def _document(payload: dict[str, Any]) -> str:
    return json.dumps(_normalize(payload), ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"


def success_document(command: str, value: Any) -> str:
    """Serialize one command success as the immutable v1 envelope."""
    return _document({
        "schema_version": SCHEMA_VERSION,
        "command": command,
        "status": "success",
        "result": _result(command, value),
    })


def error_document(command: str, error: SanitizeError | None = None) -> str:
    """Serialize fixed catalog data only; never expose exception text."""
    metadata = error.metadata if error is not None else _INTERNAL
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "command": command,
        "status": "error",
        "code": metadata.code,
        "stage": metadata.stage,
        "message": metadata.message,
    }
    if metadata.remediation is not None:
        payload["remediation"] = metadata.remediation
    if isinstance(error, VerificationError) and error.invariant:
        payload["invariant"] = error.invariant
    publication_state = getattr(error, "publication_state", None)
    if publication_state in _PUBLICATION_STATES:
        payload["publication_state"] = publication_state
    return _document(payload)
