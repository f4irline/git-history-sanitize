"""Read-only selected-ref DAG analysis shared by plan and rewrite."""

from __future__ import annotations

from dataclasses import dataclass

from .errors import SourceError
from .git import Repository
from .policy import Policy
from .source_scope import SourceScope, inspect_source


@dataclass(frozen=True)
class RewriteAnalysis:
    """Deterministic selected-ref graph facts required before compaction."""

    scope: SourceScope
    commits: tuple[str, ...]
    retained_source_parents: dict[str, tuple[str, ...]]

    @classmethod
    def create(cls, repository: Repository, policy: Policy) -> "RewriteAnalysis":
        scope = inspect_source(repository, policy)
        commits = scope.commits
        if not commits:
            raise SourceError("Cannot sanitize an empty repository")
        if scope.mode == "snapshot":
            return cls(scope, commits, {commits[0]: ()})

        retained = _retained(repository, policy, scope)
        retained_set = set(retained)
        parents = {
            commit: tuple(
                parent
                for parent in repository.text("show", "-s", "--format=%P", commit).split()
                if parent in retained_set
            )
            for commit in retained
        }
        return cls(scope, commits, parents)

    @property
    def selected_refs(self) -> tuple[str, ...]:
        return tuple(ref.name for ref in self.scope.selected_refs)

    @property
    def retained_commits_list(self) -> tuple[str, ...]:
        return tuple(commit for commit in self.commits if commit in self.retained_source_parents)

    @property
    def boundary_index(self) -> int:
        return self.commits.index(self.boundary_commit)

    @property
    def boundary_commit(self) -> str:
        return self.retained_commits_list[0]

    @property
    def source_commits(self) -> int:
        return len(self.commits)

    @property
    def discarded_commits(self) -> int:
        return self.source_commits - self.retained_commits

    @property
    def retained_commits(self) -> int:
        return len(self.retained_source_parents)


def _retained(repository: Repository, policy: Policy, scope: SourceScope) -> tuple[str, ...]:
    if policy.history.cutoff_commit:
        cutoff = repository.resolve_cutoff_commit(policy.history.cutoff_commit)
        for selected in scope.selected_refs:
            if cutoff not in repository.text("rev-list", selected.target).splitlines():
                raise SourceError("history.cutoffCommit is not reachable from every selected reference")
        result = tuple(
            commit
            for commit in scope.commits
            if cutoff in repository.text("rev-list", commit).splitlines()
        )
    else:
        cutoff = policy.history.cutoff_epoch
        assert cutoff is not None
        result = tuple(
            commit
            for commit in scope.commits
            if int(repository.text("show", "-s", "--format=%ct", commit)) >= cutoff
        )
    retained = set(result)
    if not retained or any(selected.target not in retained for selected in scope.selected_refs):
        raise SourceError("A selected reference has no commit eligible for retention")
    return result
