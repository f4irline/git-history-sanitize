#!/usr/bin/env python3
"""Validate the reviewed OCI lock and generate its runtime declaration."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from pathlib import Path


REQUIRED = {"base_image", "apt_snapshot", "git", "git_filter_repo", "platforms", "schema_version"}


def lock(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != 1 or REQUIRED - value.keys():
        raise SystemExit("invalid container toolchain lock")
    if set(value["platforms"]) != {"amd64", "arm64"}:
        raise SystemExit("container toolchain lock must record amd64 and arm64")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--architecture", choices=("amd64", "arm64"), required=True)
    parser.add_argument("--package-version", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    value = lock(arguments.lock)
    architecture = value["platforms"][arguments.architecture]
    python_version = platform.python_version()
    if python_version != architecture["python_version"]:
        raise SystemExit("container Python version does not match the reviewed lock")
    content = arguments.lock.read_bytes()
    manifest = {
        "schema_version": 1,
        "git": value["git"]["version"],
        "git_filter_repo": value["git_filter_repo"]["fingerprint"],
        "python": python_version,
        "package_version": arguments.package_version,
        "source_revision": arguments.source_revision,
        "lock_sha256": hashlib.sha256(content).hexdigest(),
    }
    arguments.output.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
