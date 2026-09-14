"""Read-only source analysis shared by plan and rewrite."""

from __future__ import annotations

from dataclasses import dataclass

from .errors import SanitizeError
from .git import Repository
from .policy import Policy
from .source_scope import SourceScope, inspect_source


@dataclass(frozen=True)
class RewriteAnalysis:
    """Deterministic source facts required before compaction can begin."""

    scope: SourceScope
    commits: tuple[str, ...]
    boundary_index: int

    @classmethod
    def create(cls, repository: Repository, policy: Policy) -> "RewriteAnalysis":
        scope = inspect_source(repository, policy)
        repository.head_ref()
        commits = scope.commits
        if not commits:
            raise SanitizeError("Cannot sanitize an empty repository")
        if scope.mode == "snapshot":
            return cls(scope, commits, 0)
        _validate_linear_history(repository, commits)
        return cls(scope, commits, _boundary_index(repository, commits, policy))

    @property
    def boundary_commit(self) -> str:
        return self.commits[self.boundary_index]

    @property
    def source_commits(self) -> int:
        return len(self.commits)

    @property
    def discarded_commits(self) -> int:
        return self.boundary_index

    @property
    def retained_commits(self) -> int:
        return self.source_commits - self.boundary_index


def _validate_linear_history(repository: Repository, commits: tuple[str, ...]) -> None:
    previous: str | None = None
    for commit in commits:
        parents = repository.text("show", "-s", "--format=%P", commit).split()
        if parents != ([] if previous is None else [previous]):
            raise SanitizeError(
                "Version 1 cutoff compaction requires a linear retained HEAD history"
            )
        previous = commit


def _boundary_index(repository: Repository, commits: tuple[str, ...], policy: Policy) -> int:
    if policy.history.cutoff_commit:
        resolved = repository.resolve_cutoff_commit(policy.history.cutoff_commit)
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
