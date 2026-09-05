"""Non-mutating rewrite orchestration."""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from .cleanup import cleanup, retain_head_only
from .compact import CompactResult, compact
from .errors import SanitizeError
from .filtering import filter_paths
from .git import Repository, ensure_dependencies
from .policy import Policy
from .verify import VerificationReport, verify


@dataclass(frozen=True)
class Plan:
    source_commits: int
    discarded_commits: int
    retained_commits_before_path_filter: int


@dataclass(frozen=True)
class RewriteReport:
    compact: CompactResult
    verification: VerificationReport

    def to_dict(self) -> dict:
        return {
            "history": {
                "source_commits": self.compact.original_commits,
                "discarded_commits": self.compact.discarded_commits,
            },
            "verification": asdict(self.verification),
        }


def _boundary_index(repository: Repository, policy: Policy, commits: list[str]) -> int:
    if policy.history.cutoff_commit:
        target = repository.text(
            "rev-parse", "--verify", f"{policy.history.cutoff_commit}^{{commit}}"
        )
        try:
            return commits.index(target)
        except ValueError as error:
            raise SanitizeError("history.cutoffCommit is not reachable from HEAD") from error
    assert policy.history.cutoff_epoch is not None
    indices = [
        index
        for index, commit in enumerate(commits)
        if int(repository.text("show", "-s", "--format=%ct", commit))
        >= policy.history.cutoff_epoch
    ]
    if not indices:
        raise SanitizeError("No retained commit exists at or after history.cutoff")
    return indices[0]


def plan(source: str | Path, policy: Policy) -> Plan:
    repository = Repository(source)
    commits = repository.text("rev-list", "--reverse", "--topo-order", "HEAD").splitlines()
    if not commits:
        raise SanitizeError("Cannot sanitize an empty repository")
    boundary = _boundary_index(repository, policy, commits)
    return Plan(
        source_commits=len(commits),
        discarded_commits=boundary,
        retained_commits_before_path_filter=len(commits) - boundary,
    )


def rewrite(source: str | Path, output: str | Path, policy: Policy) -> RewriteReport:
    ensure_dependencies()
    source_repository = Repository(source)
    output_path = Path(output).resolve()
    if output_path.exists():
        raise SanitizeError(f"Output path already exists: {output_path}")
    if output_path == source_repository.git_dir or source_repository.git_dir in output_path.parents:
        raise SanitizeError("Output path must not be inside the source Git directory")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    temporary_root = Path(
        tempfile.mkdtemp(prefix=".git-history-sanitize-", dir=output_path.parent)
    )
    try:
        rewrite_repository = source_repository.clone_to(temporary_root / "rewrite")
        retain_head_only(rewrite_repository)
        compact_result = compact(rewrite_repository, policy)
        filter_paths(rewrite_repository, policy)
        cleanup(rewrite_repository)

        bare_repository = rewrite_repository.clone_to(
            temporary_root / "sanitized.git", bare=True
        )
        cleanup(bare_repository)
        verification = verify(bare_repository.path, policy)
        os.replace(bare_repository.path, output_path)
        return RewriteReport(compact_result, verification)
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)
