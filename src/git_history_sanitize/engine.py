"""Non-mutating rewrite orchestration."""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from .cleanup import cleanup, retain_head_only
from ._version import __version__
from .compact import CompactResult, compact, restore_empty_synthetic_root
from .errors import SanitizeError
from .filtering import filter_paths, retained_head_path_count
from .git import Repository, ensure_dependencies
from .hooks import HookInventory, discover as discover_hooks, install as install_hooks
from .policy import Policy
from .publication import (
    publish,
    set_private_mode,
    sync_published_parent,
    sync_staged_directory,
    sync_staged_file,
    sync_staged_tree,
)
from .receipt import Receipt
from .scope_metadata import write as write_scope_metadata
from .rewrite_analysis import RewriteAnalysis
from .verify import VerificationReport, verify


@dataclass(frozen=True)
class Plan:
    source_commits: int
    discarded_commits: int
    retained_commits_before_path_filter: int
    mode: str
    scope: str
    boundary_count: int
    included_commit_count: int
    included_object_count: int
    retained_head_path_count: int
    excluded_paths: tuple[str, ...]
    hooks: HookInventory
    hooks_stripped: bool

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result.pop("hooks")
        result.pop("hooks_stripped")
        result["hooks"] = _hook_report(self.hooks, "stripped" if self.hooks_stripped else "preserved")
        return result


@dataclass(frozen=True)
class RewriteReport:
    compact: CompactResult
    verification: VerificationReport
    hooks: HookInventory
    hooks_stripped: bool

    def to_dict(self) -> dict:
        return {
            "history": {
                "source_commits": self.compact.original_commits,
                "discarded_commits": self.compact.discarded_commits,
            },
            "verification": asdict(self.verification),
            "hooks": _hook_report(self.hooks, "stripped" if self.hooks_stripped else "preserved"),
        }


def _hook_report(inventory: HookInventory, action: str) -> dict[str, object]:
    return {
        "action": action,
        "count": len(inventory.hooks),
        "names": list(inventory.names),
        "warnings": {name: list(names) for name, names in inventory.warning_categories.items()},
    }


def plan(source: str | Path, policy: Policy, *, preserve_hooks: bool = True) -> Plan:
    repository = Repository(source)
    analysis = RewriteAnalysis.create(repository, policy)
    return Plan(
        source_commits=analysis.source_commits,
        discarded_commits=analysis.discarded_commits,
        retained_commits_before_path_filter=analysis.retained_commits,
        mode=analysis.scope.mode,
        scope=analysis.scope.description,
        boundary_count=analysis.scope.boundary_count,
        included_commit_count=len(analysis.scope.commits),
        included_object_count=len(analysis.scope.objects),
        retained_head_path_count=retained_head_path_count(repository, policy),
        excluded_paths=policy.excluded_paths,
        hooks=discover_hooks(repository),
        hooks_stripped=not preserve_hooks,
    )


def _destination(path: str | Path, protected: tuple[Path, ...], label: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute() or any(part in {".", ".."} for part in candidate.parts):
        raise SanitizeError(f"{label} path must be an absolute path without aliases")
    for parent in (candidate, *candidate.parents):
        if parent.is_symlink():
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
    source: str | Path, output: str | Path, policy: Policy, receipt: str | Path | None = None,
    *, preserve_hooks: bool = True,
) -> RewriteReport:
    source_repository = Repository(source)
    protected = tuple(root for root in (source_repository.git_dir, source_repository.worktree_root()) if root)
    output_path = _destination(output, protected, "Output")
    if policy.source.mode == "snapshot" and receipt is not None:
        raise SanitizeError("snapshot source.mode does not accept --receipt")
    if policy.history.cutoff_commit and receipt is None:
        raise SanitizeError("cutoffCommit rewrite requires --receipt")
    if not policy.history.cutoff_commit and receipt is not None:
        raise SanitizeError("history.cutoff does not accept --receipt")
    receipt_path = _destination(receipt, (*protected, output_path), "Receipt") if receipt else None
    if receipt_path and (output_path in receipt_path.parents or receipt_path in output_path.parents):
        raise SanitizeError("Receipt path must not be inside the output path")
    if not output_path.parent.exists():
        raise SanitizeError("Output parent directory does not exist")

    analysis = RewriteAnalysis.create(source_repository, policy)
    hooks = discover_hooks(source_repository)
    ensure_dependencies()

    boundary = analysis.boundary_commit
    source_format, source_head, source_fingerprint, tree_lookup = _source_fingerprint(source_repository)
    boundary_tree = tree_lookup(boundary)

    temporary_root = Path(
        tempfile.mkdtemp(prefix=".git-history-sanitize-", dir=output_path.parent)
    )
    set_private_mode(temporary_root, 0o700)
    staged_receipt: Path | None = None
    receipt_published = False
    try:
        template_directory = temporary_root / "template"
        template_directory.mkdir(mode=0o700)
        rewrite_repository = source_repository.clone_to(
            temporary_root / "rewrite", template_directory=template_directory
        )
        retain_head_only(rewrite_repository)
        compact_result = compact(rewrite_repository, policy, analysis)
        filter_paths(rewrite_repository, policy)
        restore_empty_synthetic_root(rewrite_repository, compact_result.synthetic_root_context)
        cleanup(rewrite_repository)

        bare_repository = rewrite_repository.clone_to(
            temporary_root / "sanitized.git", bare=True, template_directory=template_directory
        )
        set_private_mode(bare_repository.path, 0o700)
        cleanup(bare_repository)
        if preserve_hooks:
            install_hooks(bare_repository, hooks)
        write_scope_metadata(bare_repository.path, analysis.scope)
        if receipt_path:
            roots = bare_repository.text("rev-list", "--max-parents=0", "--all").splitlines()
            descriptor, staged_receipt_name = tempfile.mkstemp(
                prefix=f".{receipt_path.name}.", dir=receipt_path.parent
            )
            staged_receipt = Path(staged_receipt_name)
            evidence = Receipt.create(
                generator_version=__version__,
                source_object_format=source_format,
                source_fingerprint=source_fingerprint,
                source_head=source_head,
                cutoff_commit=boundary,
                boundary_tree=boundary_tree,
                policy_digest=policy.digest,
                sanitized_object_format=bare_repository.object_format(),
                sanitized_root=roots[0],
                sanitized_head=bare_repository.text("rev-parse", "HEAD"),
                scope_mode=analysis.scope.mode,
                scope_fingerprint=analysis.scope.fingerprint,
                boundary_count=analysis.scope.boundary_count,
            )
            with os.fdopen(descriptor, "wb") as handle:
                os.fchmod(handle.fileno(), 0o600)
                handle.write(evidence.to_bytes())
                handle.flush()
                os.fsync(handle.fileno())
            verification = verify(bare_repository.path, policy, source=source, receipt=staged_receipt)
            sync_staged_file(staged_receipt)
            sync_staged_tree(bare_repository.path)
            sync_staged_directory(temporary_root)
            publish(staged_receipt, receipt_path)
            receipt_published = True
            sync_published_parent(
                receipt_path.parent,
                "Receipt was published but output was not; parent-directory durability could not be confirmed",
            )
            publish(bare_repository.path, output_path)
            sync_published_parent(output_path.parent)
        else:
            verification = verify(bare_repository.path, policy)
            sync_staged_tree(bare_repository.path)
            sync_staged_directory(temporary_root)
            publish(bare_repository.path, output_path)
            sync_published_parent(output_path.parent)
        return RewriteReport(compact_result, verification, hooks, not preserve_hooks)
    finally:
        if staged_receipt and not receipt_published:
            staged_receipt.unlink(missing_ok=True)
        shutil.rmtree(temporary_root, ignore_errors=True)
