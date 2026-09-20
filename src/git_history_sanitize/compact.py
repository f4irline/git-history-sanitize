"""Selected-ref DAG cutoff compaction and post-filter ref recovery."""

from __future__ import annotations

from dataclasses import dataclass

from .errors import SanitizeError
from .git import Repository, RetainedRef
from .policy import Policy
from .rewrite_analysis import RewriteAnalysis

_RECOVERY_PREFIX = "refs/git-history-sanitize/recovery/"


@dataclass(frozen=True)
class SyntheticRootContext:
    """Identity needed to recover a selected component pruned by filtering."""

    head_ref: str
    message: bytes
    metadata: tuple[tuple[str, str], ...]
    recovery_ref: str = ""


@dataclass(frozen=True)
class CompactResult:
    original_commits: int
    discarded_commits: int
    boundary_commit: str
    synthetic_root: str
    synthetic_root_context: SyntheticRootContext
    synthetic_roots: tuple[str, ...] = ()
    recovery_contexts: tuple[SyntheticRootContext, ...] = ()
    selected_refs: tuple[RetainedRef, ...] = ()


def _metadata(repository: Repository, commit: str) -> dict[str, str]:
    fields = repository.run(
        "show", "-s", "--format=%an%x00%ae%x00%aI%x00%cn%x00%ce%x00%cI", commit
    ).rstrip(b"\n").split(b"\x00")
    if len(fields) != 6:
        raise SanitizeError("Cannot read selected commit metadata")
    keys = (
        "GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_AUTHOR_DATE",
        "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL", "GIT_COMMITTER_DATE",
    )
    return {key: value.decode("utf-8", "surrogateescape") for key, value in zip(keys, fields)}


def _message(repository: Repository, commit: str) -> bytes:
    raw = repository.run("cat-file", "commit", commit)
    try:
        return raw.split(b"\n\n", 1)[1]
    except IndexError as error:
        raise SanitizeError("Malformed selected commit object") from error


def _create_commit_for_tree(
    repository: Repository, tree: str, parents: tuple[str, ...], message: bytes, metadata: dict[str, str],
) -> str:
    arguments = ["commit-tree", tree]
    for parent in parents:
        arguments.extend(("-p", parent))
    arguments.extend(("-F", "-"))
    try:
        return repository.run(*arguments, input_bytes=message, environment=metadata).decode().strip()
    except SanitizeError as error:
        raise SanitizeError("Could not recreate a sanitized commit") from error


def _root_context(
    repository: Repository, selected: RetainedRef, recovery_source: str, policy: Policy, index: int,
) -> SyntheticRootContext:
    return SyntheticRootContext(
        selected.name,
        f"{policy.history.prefix_message}\n".encode(),
        tuple(sorted(_metadata(repository, recovery_source).items())),
        f"{_RECOVERY_PREFIX}{index:04d}",
    )


def _empty_root(repository: Repository, context: SyntheticRootContext) -> str:
    empty_tree = repository.run("mktree", input_bytes=b"").decode().strip()
    return _create_commit_for_tree(repository, empty_tree, (), context.message, dict(context.metadata))


def compact(repository: Repository, policy: Policy, analysis: RewriteAnalysis) -> CompactResult:
    mapped: dict[str, str] = {}
    roots: list[str] = []
    for source in analysis.retained_commits_list:
        parents = tuple(mapped[parent] for parent in analysis.retained_source_parents[source])
        if parents:
            mapped[source] = _create_commit_for_tree(
                repository, repository.commit_tree(source), parents, _message(repository, source), _metadata(repository, source)
            )
        else:
            mapped[source] = _create_commit_for_tree(
                repository, repository.commit_tree(source), (), f"{policy.history.prefix_message}\n".encode(), _metadata(repository, source)
            )
            roots.append(mapped[source])

    contexts = tuple(
        _root_context(
            repository,
            selected,
            next(
                source for source in analysis.retained_commits_list
                if not analysis.retained_source_parents[source]
                and source in repository.text("rev-list", selected.target).splitlines()
            ),
            policy,
            index,
        )
        for index, selected in enumerate(analysis.scope.selected_refs)
    )
    for selected, context in zip(analysis.scope.selected_refs, contexts):
        target = mapped[selected.target]
        repository.run("update-ref", context.recovery_ref, target)
        if selected.kind == "annotated-tag":
            repository.run("update-ref", "-d", selected.name, check=False)
        else:
            repository.run("update-ref", selected.name, target)
    if not roots:
        raise SanitizeError("Could not create a synthetic selected-ref frontier")
    return CompactResult(
        len(analysis.commits), analysis.discarded_commits, analysis.boundary_commit,
        roots[0], contexts[0], tuple(roots), contexts, analysis.scope.selected_refs,
    )


def _recreate_tag(repository: Repository, selected: RetainedRef, target: str) -> None:
    assert selected.annotation is not None
    headers, separator, body = selected.annotation.partition(b"\n\n")
    if not separator:
        raise SanitizeError("Cannot recreate selected annotated tag")
    rewritten = b"\n".join(
        f"object {target}".encode() if line.startswith(b"object ") else line
        for line in headers.splitlines()
    ) + separator + body
    tag = repository.run("mktag", input_bytes=rewritten).decode().strip()
    repository.run("update-ref", selected.name, tag)


def restore_selected_components(repository: Repository, result: CompactResult) -> tuple[str, ...]:
    """Restore selected refs after prune-empty and recreate unsigned annotations."""
    targets: list[str] = []
    for selected, context in zip(result.selected_refs, result.recovery_contexts):
        target = repository.run("rev-parse", "--verify", "--quiet", context.recovery_ref, check=False).strip().decode()
        if not target:
            target = _empty_root(repository, context)
            repository.run("update-ref", context.recovery_ref, target)
        if selected.kind != "annotated-tag":
            repository.run("update-ref", selected.name, target)
        targets.append(target)
    for selected, target in zip(result.selected_refs, targets):
        if selected.kind == "annotated-tag":
            _recreate_tag(repository, selected, target)
    for context in result.recovery_contexts:
        repository.run("update-ref", "-d", context.recovery_ref, check=False)
    return tuple(targets)


def restore_empty_synthetic_root(repository: Repository, context: SyntheticRootContext) -> bool:
    """Backward-compatible one-ref recovery used by legacy callers."""
    if repository.run("rev-parse", "--verify", "--quiet", context.head_ref, check=False).strip():
        return False
    root = _empty_root(repository, context)
    repository.run("update-ref", context.head_ref, root)
    return True
