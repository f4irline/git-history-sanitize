"""Sensitive-path filtering through git-filter-repo."""

from __future__ import annotations

import json
import os

from .errors import DependencyError
from .git import GitError, Repository
from .policy import Policy

_CALLBACK = r'''
import json
import os

rules = json.loads(os.environ["GIT_HISTORY_SANITIZE_PATH_RULES"])
include_exact, include_directories = (
    tuple(path.encode("utf-8") for path in paths)
    for paths in rules["include"]
)
exclude_exact, exclude_directories = (
    tuple(path.encode("utf-8") for path in paths)
    for paths in rules["exclude"]
)
mixed_message = os.environ["GIT_HISTORY_SANITIZE_MIXED_MESSAGE"].encode("utf-8") + b"\n"

def matches(filename, exact_paths, directory_paths):
    return filename in exact_paths or filename.startswith(directory_paths)

def is_removed(filename):
    included = not include_exact and not include_directories or matches(
        filename, include_exact, include_directories
    )
    return not included or matches(filename, exclude_exact, exclude_directories)

original_changes = list(commit.file_changes)
removed_changes = [change for change in original_changes if is_removed(change.filename)]
if removed_changes:
    commit.file_changes = [change for change in original_changes if not is_removed(change.filename)]
    if commit.parents:
        commit.message = mixed_message
'''


def is_excluded_path(path: bytes, excluded_paths: tuple[str, ...]) -> bool:
    """Match a repository path against the canonical filter-repo rule forms."""
    exact_paths, directory_paths = _path_rules(excluded_paths)
    return path in exact_paths or path.startswith(directory_paths)


def is_included_path(path: bytes, included_paths: tuple[str, ...] | None) -> bool:
    """Return true for all paths when allowlisting is inactive."""
    if included_paths is None:
        return True
    exact_paths, directory_paths = _path_rules(included_paths)
    return path in exact_paths or path.startswith(directory_paths)


def is_retained_path(path: bytes, policy: Policy) -> bool:
    """Apply the policy's order-independent include-then-exclude predicate."""
    return is_included_path(path, policy.included_paths) and not is_excluded_path(
        path, policy.excluded_paths
    )


def retained_head_path_count(repository: Repository, policy: Policy) -> int:
    """Count source-HEAD paths retained by the combined path policy."""
    paths = repository.run("ls-tree", "-r", "-z", "--name-only", "HEAD").split(b"\0")
    return sum(
        bool(path) and is_retained_path(path, policy)
        for path in paths
    )


def _path_rules(excluded_paths: tuple[str, ...]) -> tuple[tuple[bytes, ...], tuple[bytes, ...]]:
    rules = tuple(path.encode("utf-8") for path in excluded_paths)
    return (
        tuple(path for path in rules if not path.endswith(b"/")),
        tuple(path for path in rules if path.endswith(b"/")),
    )


def filter_paths(repository: Repository, policy: Policy) -> None:
    included_paths = getattr(policy, "included_paths", None)
    if included_paths is None and not policy.excluded_paths:
        return
    environment = os.environ.copy()
    environment["GIT_HISTORY_SANITIZE_PATH_RULES"] = json.dumps({
        "include": (
            tuple(path for path in (included_paths or ()) if not path.endswith("/")),
            tuple(path for path in (included_paths or ()) if path.endswith("/")),
        ),
        "exclude": (
            tuple(path for path in policy.excluded_paths if not path.endswith("/")),
            tuple(path for path in policy.excluded_paths if path.endswith("/")),
        ),
    })
    environment["GIT_HISTORY_SANITIZE_MIXED_MESSAGE"] = policy.mixed_message
    try:
        repository.run(
            "filter-repo",
            "--force",
            "--prune-empty",
            "always",
            "--commit-callback",
            _CALLBACK,
            environment=environment,
        )
    except GitError as error:
        raise DependencyError("git-filter-repo failed during path filtering") from error
