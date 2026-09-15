"""Classified, deterministic CLI reporting for shared and trusted audiences."""

from __future__ import annotations

import json
from typing import Any, Literal

from .engine import Plan, RewriteReport
from .errors import ErrorMetadata, SanitizeError, VerificationError
from .verify import VerificationReport

SCHEMA_VERSION = 2
LEGACY_SCHEMA_VERSION = 1
Audience = Literal["public", "trusted"]
_PUBLICATION_STATES = {"not_published", "receipt_published", "output_published"}
_INTERNAL = ErrorMetadata(
    "internal_error", "internal", "An unexpected internal error occurred.",
    "Retry the command; if the problem persists, report it without sensitive inputs.",
)


def _safe_text(value: str) -> str:
    """Convert surrogateescaped bytes to unambiguous printable byte escapes."""
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
    if isinstance(value, tuple | list):
        return [_normalize(item) for item in value]
    if isinstance(value, dict):
        return {_safe_text(str(key)): _normalize(item) for key, item in value.items()}
    return value


def _hooks(inventory: Any, stripped: bool) -> dict[str, Any]:
    return {"action": "stripped" if stripped else "preserved", "count": len(inventory.hooks)}


def _hook_diagnostics(inventory: Any) -> dict[str, Any]:
    return {"hook_names": list(inventory.names), "hook_warnings": {
        name: list(names) for name, names in inventory.warning_categories.items()
    }}


def _public_plan(value: Plan) -> dict[str, Any]:
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
        "hooks": _hooks(value.hooks, value.hooks_stripped),
    }


def _public_verification(value: VerificationReport) -> dict[str, Any]:
    return {
        "commit_count": value.commit_count,
        "mode": value.mode,
        "scope": value.scope,
        "boundary_count": value.boundary_count,
        "included_commit_count": value.included_commit_count,
        "included_object_count": value.included_object_count,
    }


def _public_result(command: str, value: Any) -> dict[str, Any]:
    if command == "doctor":
        return dict(value)
    if command == "plan" and isinstance(value, Plan):
        return _public_plan(value)
    if command == "rewrite" and isinstance(value, RewriteReport):
        return {
            "history": {"source_commits": value.compact.original_commits, "discarded_commits": value.compact.discarded_commits},
            "verification": _public_verification(value.verification),
            "hooks": _hooks(value.hooks, value.hooks_stripped),
        }
    if command == "verify" and isinstance(value, VerificationReport):
        return _public_verification(value)
    raise TypeError("unsupported CLI reporting result")


def _diagnostics(command: str, value: Any) -> dict[str, Any]:
    if command == "plan" and isinstance(value, Plan):
        return {"excluded_paths": list(value.excluded_paths), **_hook_diagnostics(value.hooks)}
    if command == "rewrite" and isinstance(value, RewriteReport):
        return {
            "head": value.verification.head,
            "root": value.verification.root,
            "retained_refs": list(value.verification.retained_refs),
            "excluded_paths": list(value.verification.excluded_paths),
            **_hook_diagnostics(value.hooks),
        }
    if command == "verify" and isinstance(value, VerificationReport):
        return {
            "head": value.head,
            "root": value.root,
            "retained_refs": list(value.retained_refs),
            "excluded_paths": list(value.excluded_paths),
        }
    return {}


def _legacy_result(command: str, value: Any) -> dict[str, Any]:
    public = _public_result(command, value)
    diagnostics = _diagnostics(command, value)
    if command == "plan":
        return {**public, "excluded_paths": diagnostics["excluded_paths"], "hooks": {
            **public["hooks"], "names": diagnostics["hook_names"], "warnings": diagnostics["hook_warnings"],
        }}
    if command == "rewrite":
        verification = public["verification"]
        return {**public, "verification": {
            **verification,
            "head": diagnostics["head"], "root": diagnostics["root"],
            "retained_refs": diagnostics["retained_refs"], "excluded_paths": diagnostics["excluded_paths"],
        }, "hooks": {**public["hooks"], "names": diagnostics["hook_names"], "warnings": diagnostics["hook_warnings"]}}
    if command == "verify":
        return {**public, **diagnostics}
    return public


def _document(payload: dict[str, Any]) -> str:
    return json.dumps(_normalize(payload), ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"


def success_document(
    command: str, value: Any, *, diagnostics: Audience = "public", schema_version: int = SCHEMA_VERSION,
) -> str:
    """Serialize an explicit public or local-trusted report envelope."""
    if diagnostics not in ("public", "trusted"):
        raise ValueError("unsupported report audience")
    if schema_version == LEGACY_SCHEMA_VERSION:
        if diagnostics != "trusted" or command == "doctor":
            raise ValueError("legacy JSON requires trusted diagnostics")
        return _document({"schema_version": LEGACY_SCHEMA_VERSION, "command": command, "status": "success", "result": _legacy_result(command, value)})
    if schema_version != SCHEMA_VERSION:
        raise ValueError("unsupported JSON schema")
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "report_audience": diagnostics,
        "command": command,
        "status": "success",
        "result": _public_result(command, value),
    }
    if diagnostics == "trusted":
        payload["diagnostics"] = _diagnostics(command, value)
    return _document(payload)


def error_document(
    command: str, error: SanitizeError | None = None, *, schema_version: int = SCHEMA_VERSION,
    diagnostics: Audience = "public",
) -> str:
    """Serialize fixed catalog data only; never expose exception text."""
    if diagnostics not in ("public", "trusted") or schema_version not in (LEGACY_SCHEMA_VERSION, SCHEMA_VERSION):
        raise ValueError("unsupported reporting contract")
    metadata = error.metadata if error is not None else _INTERNAL
    payload: dict[str, Any] = {
        "schema_version": schema_version, "command": command, "status": "error",
        "code": metadata.code, "stage": metadata.stage, "message": metadata.message,
    }
    if schema_version == SCHEMA_VERSION:
        payload["report_audience"] = diagnostics
    if metadata.remediation is not None:
        payload["remediation"] = metadata.remediation
    if isinstance(error, VerificationError) and error.invariant:
        payload["invariant"] = error.invariant
    publication_state = getattr(error, "publication_state", None)
    if publication_state in _PUBLICATION_STATES:
        payload["publication_state"] = publication_state
    return _document(payload)


def success_text(command: str, value: Any, *, diagnostics: Audience = "public") -> str:
    """Render the same classified contract for human-facing output."""
    if command == "doctor":
        return "\n".join(_public_result(command, value).values()) + "\n"
    result = _public_result(command, value)
    if command == "plan":
        lines = [
            f"Source commits: {result['source_commits']}", f"Pre-cutoff commits: {result['discarded_commits']}",
            f"Commits before path filtering: {result['retained_commits_before_path_filter']}",
            f"Retained HEAD paths: {result['retained_head_path_count']}", f"Scope: {result['scope']}",
            f"Hooks: {result['hooks']['action']} ({result['hooks']['count']})",
        ]
        if diagnostics == "trusted":
            detail = _diagnostics(command, value)
            lines.extend((f"Excluded paths: {', '.join(detail['excluded_paths']) or 'none'}", f"Hook names: {', '.join(detail['hook_names']) or 'none'}"))
        return "\n".join(lines) + "\n"
    if command == "rewrite":
        lines = [f"Commits in output: {result['verification']['commit_count']}", f"Scope: {result['verification']['scope']}", f"Hooks: {result['hooks']['action']} ({result['hooks']['count']})"]
        if diagnostics == "trusted":
            lines.append(f"Sanitized HEAD: {_diagnostics(command, value)['head']}")
        return "\n".join(lines) + "\n"
    return "Verification passed.\n"


def error_text(error: SanitizeError | None = None) -> str:
    """Render a fixed safe summary, with allowlisted invariant metadata only."""
    metadata = error.metadata if error is not None else _INTERNAL
    if isinstance(error, VerificationError) and error.invariant:
        return f"error: verification failed: {error.invariant}\n"
    summaries = {
        "forbidden_input.invalid": "invalid forbidden-content input",
        "policy.invalid": "invalid policy",
        "source.invalid": "source repository unavailable",
        "usage.invalid_arguments": "invalid command arguments",
        "dependency.unavailable": "required dependency unavailable",
        "publication.failed": "sanitized output publication failed",
        "verification.failed": "verification failed",
        "rewrite.failed": "sanitization failed",
        "internal_error": "unexpected internal error",
    }
    return f"error: {summaries[metadata.code]}\n"
