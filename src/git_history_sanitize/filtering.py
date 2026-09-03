"""Sensitive-path filtering through git-filter-repo."""

from __future__ import annotations

import json
import os

from .git import Repository
from .policy import Policy

_CALLBACK = r'''
import json
import os

configured_paths = tuple(
    path.encode("utf-8")
    for path in json.loads(os.environ["GIT_HISTORY_SANITIZE_PATHS"])
)
mixed_message = os.environ["GIT_HISTORY_SANITIZE_MIXED_MESSAGE"].encode("utf-8") + b"\n"

def is_sensitive(filename):
    for path in configured_paths:
        if path.endswith(b"/"):
            if filename.startswith(path):
                return True
        elif filename == path:
            return True
    return False

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
        commit.message = mixed_message
    else:
        commit.file_changes = []
'''


def filter_paths(repository: Repository, policy: Policy) -> None:
    if not policy.excluded_paths:
        return
    environment = os.environ.copy()
    environment["GIT_HISTORY_SANITIZE_PATHS"] = json.dumps(policy.excluded_paths)
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
