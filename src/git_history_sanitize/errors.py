"""Redacted error categories exposed by the command-line JSON contract."""

from __future__ import annotations

from dataclasses import dataclass


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


class DependencyError(SanitizeError):
    """Raised when a required executable cannot be used."""

    metadata = ErrorMetadata(
        "dependency.unavailable", "dependency", "A required dependency is unavailable.",
        "Install the supported Git and git-filter-repo toolchain.",
    )


class SourceError(SanitizeError):
    """Raised when the source repository cannot safely be inspected."""

    metadata = ErrorMetadata(
        "source.invalid", "source", "The source repository is invalid or unavailable."
    )


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
