"""Sensitive-path filtering through git-filter-repo."""

from __future__ import annotations

import json
import os

from .git import Repository
from .policy import Policy

_CALLBACK = r'''
import json
import os

exact_paths, directory_paths = (
    tuple(path.encode("utf-8") for path in paths)
    for paths in json.loads(os.environ["GIT_HISTORY_SANITIZE_PATH_RULES"])
)
mixed_message = os.environ["GIT_HISTORY_SANITIZE_MIXED_MESSAGE"].encode("utf-8") + b"\n"

def is_sensitive(filename):
    return filename in exact_paths or filename.startswith(directory_paths)

original_changes = list(commit.file_changes)
sensitive_changes = [
    change for change in original_changes if is_sensitive(change.filename)
]
if sensitive_changes:
    remaining_changes = [
        change for change in original_changes if not is_sensitive(change.filename)
    ]
    if remaining_changes:
        commit.file_changes = remaining_changes
        if commit.parents:
            commit.message = mixed_message
    else:
        commit.file_changes = []
'''


def is_excluded_path(path: bytes, excluded_paths: tuple[str, ...]) -> bool:
    """Match a repository path against the canonical filter-repo rule forms."""
    exact_paths, directory_paths = _path_rules(excluded_paths)
    return path in exact_paths or path.startswith(directory_paths)


def retained_head_path_count(repository: Repository, policy: Policy) -> int:
    """Count source-HEAD paths that remain after the configured exclusions."""
    paths = repository.run("ls-tree", "-r", "-z", "--name-only", "HEAD").split(b"\0")
    return sum(
        bool(path) and not is_excluded_path(path, policy.excluded_paths)
        for path in paths
    )


def _path_rules(excluded_paths: tuple[str, ...]) -> tuple[tuple[bytes, ...], tuple[bytes, ...]]:
    rules = tuple(path.encode("utf-8") for path in excluded_paths)
    return (
        tuple(path for path in rules if not path.endswith(b"/")),
        tuple(path for path in rules if path.endswith(b"/")),
    )


def filter_paths(repository: Repository, policy: Policy) -> None:
    if not policy.excluded_paths:
        return
    environment = os.environ.copy()
    environment["GIT_HISTORY_SANITIZE_PATH_RULES"] = json.dumps(
        (
            tuple(path for path in policy.excluded_paths if not path.endswith("/")),
            tuple(path for path in policy.excluded_paths if path.endswith("/")),
        )
    )
    environment["GIT_HISTORY_SANITIZE_MIXED_MESSAGE"] = policy.mixed_message
    repository.run(
        "filter-repo",
        "--force",
        "--prune-empty",
        "always",
        "--commit-callback",
        _CALLBACK,
        environment=environment,
    )
