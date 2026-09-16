"""Fail-closed parsing for OCI runtime toolchain metadata."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final


MANIFEST_SCHEMA_VERSION: Final = 1
REQUIRED_MANIFEST_FIELDS: Final = frozenset({
    "git", "git_filter_repo", "lock_sha256", "package_version", "python", "source_revision",
})


class ToolchainManifestError(ValueError):
    """Raised when the OCI-only toolchain declaration is not trustworthy."""


def load_manifest(path: Path) -> dict[str, str | int]:
    """Read the root-owned OCI declaration without accepting partial metadata."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ToolchainManifestError("required OCI toolchain manifest is unavailable") from error
    if not isinstance(value, dict) or value.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ToolchainManifestError("required OCI toolchain manifest is invalid")
    if any(not isinstance(value.get(field), str) or not value[field] for field in REQUIRED_MANIFEST_FIELDS):
        raise ToolchainManifestError("required OCI toolchain manifest is incomplete")
    return value


def load_required_manifest(sentinel: Path) -> dict[str, str | int]:
    """Resolve the sentinel-controlled manifest without a fallback path."""
    try:
        declaration = json.loads(sentinel.read_text(encoding="utf-8"))
        manifest_path = declaration["manifest"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise ToolchainManifestError("required OCI toolchain manifest is unavailable") from error
    if declaration.get("schema_version") != MANIFEST_SCHEMA_VERSION or not isinstance(manifest_path, str):
        raise ToolchainManifestError("required OCI toolchain manifest is invalid")
    return load_manifest(Path(manifest_path))
