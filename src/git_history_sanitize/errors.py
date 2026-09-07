class SanitizeError(Exception):
    """Raised when sanitization cannot safely proceed."""


class PolicyError(SanitizeError):
    """Raised when a policy is invalid or unsupported."""


class VerificationError(SanitizeError):
    """Raised when a sanitized repository fails verification."""

    def __init__(self, message: str, *, invariant: str | None = None):
        super().__init__(message)
        self.invariant = invariant
