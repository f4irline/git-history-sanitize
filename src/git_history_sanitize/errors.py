"""Redacted error categories exposed by the command-line JSON contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ErrorMetadata:
    """Fixed, safe metadata for one CLI-reachable error category."""

    code: str
    stage: str
    message: str
    remediation: str | None = None


class SanitizeError(Exception):
    """Raised when sanitization cannot safely proceed."""

    metadata = ErrorMetadata(
        "rewrite.failed", "rewrite", "Sanitization could not complete safely."
    )


class PolicyError(SanitizeError):
    """Raised when a policy is invalid or unsupported."""

    metadata = ErrorMetadata(
        "policy.invalid", "policy", "The policy is invalid or unsupported."
    )


class VerificationError(SanitizeError):
    """Raised when a sanitized repository fails verification."""

    def __init__(self, message: str, *, invariant: str | None = None):
        super().__init__(message)
        self.invariant = invariant

    metadata = ErrorMetadata(
        "verification.failed", "verification", "Verification did not satisfy the sanitizer contract."
    )


class UsageError(SanitizeError):
    """Raised for invalid command-line arguments without reflecting them."""

    metadata = ErrorMetadata(
        "usage.invalid_arguments", "parse", "The command arguments are invalid.",
        "Run the command with --help for usage.",
    )


@dataclass(frozen=True)
class DependencyCheck:
    """Resolver-owned doctor provenance; never populated from process diagnostics."""

    name: str
    executable_path: str | None
    detected_version: str | None
    required_range: str
    status: Literal["pass", "fail"]


_DEPENDENCY_REMEDIATION = (
    "Install Git >=2.36 and git-filter-repo==2.47.0; see README.md Requirements."
)
DEPENDENCY_FAILURES = {
    reason: ErrorMetadata(f"dependency.{reason}", "dependency", message, _DEPENDENCY_REMEDIATION)
    for reason, message in (
        ("missing", "A required dependency is missing."),
        ("not_executable", "A required dependency is not executable."),
        ("startup_failed", "A required dependency could not start."),
        ("execution_failed", "A required dependency command failed."),
        ("invalid_output", "A required dependency returned invalid version output."),
        ("unsupported", "A required dependency version is unsupported."),
        ("oci_mismatch", "The required OCI toolchain declaration is invalid or mismatched."),
    )
}


class DependencyError(SanitizeError):
    """Raised when a required executable cannot be used."""

    metadata = ErrorMetadata(
        "dependency.unavailable", "dependency", "A required dependency is unavailable.",
        "Install the supported Git and git-filter-repo toolchain.",
    )

    def __init__(
        self, message: str = "dependency check failed", *, reason: str | None = None,
        executable_path: str | None = None, checks: tuple[DependencyCheck, ...] = (),
    ):
        super().__init__(message)
        if reason is not None:
            self.metadata = DEPENDENCY_FAILURES[reason]
        self.executable_path = executable_path
        self.checks = checks


SOURCE_FAILURES = {
    reason: ErrorMetadata(f"source.{reason}", "source", message, remediation)
    for reason, message, remediation in (
        ("detached_head", "The source HEAD is detached.", "Switch to an existing branch or create a branch at the current commit, then retry."),
        ("unborn_head", "The source HEAD has no committed history.", "Create the repository's initial commit or select a repository with committed history."),
        ("invalid_location", "The source location is unsupported or unavailable.", "Pass a working-tree root, Git directory, bare root, or linked-worktree gitfile; omit --source only to discover from CWD."),
        ("state_unavailable", "Working-tree state could not be inspected.", "Restore readable source state or use an accessible validated metadata-only input."),
    )
}
DESTINATION_FAILURES = {
    reason: ErrorMetadata(f"destination.{reason}", "preflight", message, remediation)
    for reason, message, remediation in (
        ("invalid", "An output or receipt destination is unsafe or unavailable.", "Use distinct nonexistent absolute symlink-free output/receipt paths with existing directory parents outside source roots."),
        ("busy", "An output or receipt destination is already reserved.", "Another rewrite is using an output or receipt destination; wait for it to finish or select different destinations."),
        ("reservation_unsafe", "The destination reservation cannot be validated.", "Stop writers and have the owning user inspect the reservation, without bulk prefix deletion."),
    )
}


class DestinationError(UsageError):
    def __init__(self, *, reason: str = "invalid"):
        super().__init__("destination preflight failed")
        self.metadata = DESTINATION_FAILURES[reason]


class SourceError(SanitizeError):
    """Raised when the source repository cannot safely be inspected."""

    metadata = ErrorMetadata(
        "source.invalid", "source", "The source repository is invalid or unavailable."
    )

    def __init__(self, message: str = "source inspection failed", *, reason: str | None = None):
        super().__init__(message)
        if reason is not None:
            self.metadata = SOURCE_FAILURES[reason]


class PublicationError(SanitizeError):
    """Raised when atomic publication or its persistence contract fails."""

    metadata = ErrorMetadata(
        "publication.failed", "publication", "Sanitized output publication failed."
    )

    def __init__(self, message: str, *, publication_state: str = "not_published"):
        super().__init__(message)
        self.publication_state = publication_state

    def with_publication_state(self, publication_state: str) -> "PublicationError":
        return PublicationError(str(self), publication_state=publication_state)


class ForbiddenInputError(SanitizeError):
    """Raised when forbidden-content input is unsafe or exceeds its budget."""

    metadata = ErrorMetadata(
        "forbidden_input.invalid", "forbidden_input", "Forbidden-content input is invalid."
    )


class WorkspaceError(SanitizeError):
    """Raised when a temporary workspace cannot be safely managed."""

    metadata = ErrorMetadata(
        "workspace.unsafe",
        "workspace",
        "The sanitizer workspace could not be managed safely.",
        "List sanitizer workspaces under the parent and clean one validated stale ID.",
    )


class InterruptionError(SanitizeError):
    """Raised after a handled signal requests bounded rewrite shutdown."""

    metadata = ErrorMetadata(
        "rewrite.interrupted",
        "rewrite",
        "Sanitization was interrupted before completion.",
        "List sanitizer workspaces under the output parent and clean the stale ID before retrying.",
    )

    def __init__(self, signum: int):
        super().__init__("rewrite interrupted")
        self.signum = signum
