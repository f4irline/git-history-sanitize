"""Non-mutating rewrite orchestration."""

from __future__ import annotations

import os
import shutil
import tempfile
from importlib.metadata import version
from dataclasses import asdict, dataclass
from pathlib import Path

from .cleanup import cleanup, retain_head_only
from .compact import CompactResult, compact
from .errors import SanitizeError
from .filtering import filter_paths
from .git import Repository, ensure_dependencies
from .policy import Policy
from .publication import fsync_path, publish
from .receipt import Receipt
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
        target = repository.resolve_cutoff_commit(policy.history.cutoff_commit)
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


def _destination(path: str | Path, protected: tuple[Path, ...], label: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute() or any(part in {".", ".."} for part in candidate.parts):
        raise SanitizeError(f"{label} path must be an absolute path without aliases")
    for parent in (candidate, *candidate.parents):
        if parent.exists() and parent.is_symlink():
            raise SanitizeError(f"{label} path must not contain symlinks")
    if candidate.exists():
        raise SanitizeError(f"{label} path already exists")
    parent = candidate.parent.resolve()
    resolved = parent / candidate.name
    if any(resolved == root or root in resolved.parents for root in protected):
        raise SanitizeError(f"{label} path must not be inside the source repository")
    return resolved


def _source_fingerprint(repository: Repository) -> tuple[str, str, str, str]:
    object_format = repository.object_format()
    head_kind, head_ref, head = repository.head_identity()
    return object_format, head, Receipt.source_fingerprint(object_format, head_kind, head_ref, head, repository.direct_refs()), repository.commit_tree


def rewrite(
    source: str | Path, output: str | Path, policy: Policy, receipt: str | Path | None = None
) -> RewriteReport:
    ensure_dependencies()
    source_repository = Repository(source)
    protected = tuple(root for root in (source_repository.git_dir, source_repository.worktree_root()) if root)
    output_path = _destination(output, protected, "Output")
    if policy.history.cutoff_commit and receipt is None:
        raise SanitizeError("cutoffCommit rewrite requires --receipt")
    if not policy.history.cutoff_commit and receipt is not None:
        raise SanitizeError("history.cutoff does not accept --receipt")
    receipt_path = _destination(receipt, (*protected, output_path), "Receipt") if receipt else None
    if receipt_path and (output_path in receipt_path.parents or receipt_path in output_path.parents):
        raise SanitizeError("Receipt path must not be inside the output path")
    if not output_path.parent.exists():
        raise SanitizeError("Output parent directory does not exist")

    boundary = source_repository.resolve_cutoff_commit(policy.history.cutoff_commit) if policy.history.cutoff_commit else None
    source_format, source_head, source_fingerprint, tree_lookup = _source_fingerprint(source_repository)
    boundary_tree = tree_lookup(boundary) if boundary else None

    temporary_root = Path(
        tempfile.mkdtemp(prefix=".git-history-sanitize-", dir=output_path.parent)
    )
    staged_receipt: Path | None = None
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
        if receipt_path:
            roots = bare_repository.text("rev-list", "--max-parents=0", "--all").splitlines()
            descriptor, staged_receipt_name = tempfile.mkstemp(
                prefix=f".{receipt_path.name}.", dir=receipt_path.parent
            )
            staged_receipt = Path(staged_receipt_name)
            evidence = Receipt.create(
                generator_version=version("git-history-sanitize"),
                source_object_format=source_format,
                source_fingerprint=source_fingerprint,
                source_head=source_head,
                cutoff_commit=boundary or "",
                boundary_tree=boundary_tree or "",
                policy_digest=policy.digest,
                sanitized_object_format=bare_repository.object_format(),
                sanitized_root=roots[0],
                sanitized_head=bare_repository.text("rev-parse", "HEAD"),
            )
            with os.fdopen(descriptor, "wb") as handle:
                os.fchmod(handle.fileno(), 0o600)
                handle.write(evidence.to_bytes())
                handle.flush()
                os.fsync(handle.fileno())
            verification = verify(bare_repository.path, policy, source=source, receipt=staged_receipt)
            fsync_path(bare_repository.path)
            fsync_path(temporary_root)
            publish(staged_receipt, receipt_path)
            fsync_path(receipt_path.parent)
            publish(bare_repository.path, output_path)
        else:
            verification = verify(bare_repository.path, policy)
            fsync_path(bare_repository.path)
            publish(bare_repository.path, output_path)
        return RewriteReport(compact_result, verification)
    finally:
        if staged_receipt:
            staged_receipt.unlink(missing_ok=True)
        shutil.rmtree(temporary_root, ignore_errors=True)
