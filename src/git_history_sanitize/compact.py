"""Cutoff compaction for a single linear retained Git branch."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

from .errors import SanitizeError
from .git import Repository
from .policy import Policy


@dataclass(frozen=True)
class CompactResult:
    original_commits: int
    discarded_commits: int
    boundary_commit: str
    synthetic_root: str


def _commits(repository: Repository) -> list[str]:
    commits = repository.text("rev-list", "--reverse", "--topo-order", "HEAD").splitlines()
    if not commits:
        raise SanitizeError("Cannot compact an empty repository")
    previous: str | None = None
    for commit in commits:
        parents = repository.text("show", "-s", "--format=%P", commit).split()
        if parents != ([] if previous is None else [previous]):
            raise SanitizeError(
                "Version 1 cutoff compaction requires a linear retained HEAD history"
            )
        previous = commit
    return commits


def _boundary_index(repository: Repository, commits: list[str], policy: Policy) -> int:
    if policy.history.cutoff_commit:
        resolved = repository.text(
            "rev-parse", "--verify", f"{policy.history.cutoff_commit}^{{commit}}"
        )
        try:
            return commits.index(resolved)
        except ValueError as error:
            raise SanitizeError("history.cutoffCommit is not reachable from HEAD") from error

    cutoff = policy.history.cutoff_epoch
    assert cutoff is not None
    allowed: int | None = None
    for index, commit in enumerate(commits):
        if int(repository.text("show", "-s", "--format=%ct", commit)) >= cutoff:
            allowed = index
            break
    if allowed is None:
        raise SanitizeError("No retained commit exists at or after history.cutoff")
    for commit in commits[allowed:]:
        if int(repository.text("show", "-s", "--format=%ct", commit)) < cutoff:
            raise SanitizeError(
                "Committer timestamps cross the cutoff more than once; refusing "
                "an ambiguous history rewrite"
            )
    return allowed


def _metadata(repository: Repository, commit: str) -> dict[str, str]:
    fields = repository.run(
        "show",
        "-s",
        "--format=%an%x00%ae%x00%aI%x00%cn%x00%ce%x00%cI",
        commit,
    ).rstrip(b"\n").split(b"\x00")
    if len(fields) != 6:
        raise SanitizeError(f"Cannot read commit metadata for {commit}")
    keys = (
        "GIT_AUTHOR_NAME",
        "GIT_AUTHOR_EMAIL",
        "GIT_AUTHOR_DATE",
        "GIT_COMMITTER_NAME",
        "GIT_COMMITTER_EMAIL",
        "GIT_COMMITTER_DATE",
    )
    environment = os.environ.copy()
    environment.update(
        {key: value.decode("utf-8", "surrogateescape") for key, value in zip(keys, fields)}
    )
    return environment


def _message(repository: Repository, commit: str) -> bytes:
    raw = repository.run("cat-file", "commit", commit)
    try:
        return raw.split(b"\n\n", 1)[1]
    except IndexError as error:
        raise SanitizeError(f"Malformed commit object {commit}") from error


def _create_commit(
    repository: Repository, source: str, parent: str | None, message: bytes
) -> str:
    tree = repository.text("rev-parse", f"{source}^{{tree}}")
    command = ["git", "-C", str(repository.path), "commit-tree", tree]
    if parent:
        command.extend(["-p", parent])
    command.extend(["-F", "-"])
    result = subprocess.run(
        command,
        input=message,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_metadata(repository, source),
    )
    if result.returncode:
        raise SanitizeError("Could not recreate a sanitized commit")
    return result.stdout.decode().strip()


def compact(repository: Repository, policy: Policy) -> CompactResult:
    commits = _commits(repository)
    boundary_index = _boundary_index(repository, commits, policy)
    boundary = commits[boundary_index]
    synthetic_root = _create_commit(
        repository, boundary, None, f"{policy.history.prefix_message}\n".encode()
    )
    new_head = synthetic_root
    for commit in commits[boundary_index + 1 :]:
        new_head = _create_commit(repository, commit, new_head, _message(repository, commit))

    repository.run("update-ref", repository.head_ref(), new_head, commits[-1])
    return CompactResult(
        original_commits=len(commits),
        discarded_commits=boundary_index,
        boundary_commit=boundary,
        synthetic_root=synthetic_root,
    )
