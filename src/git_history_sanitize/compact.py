"""Cutoff compaction for a single linear retained Git branch."""

from __future__ import annotations

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
    synthetic_root_context: "SyntheticRootContext"


@dataclass(frozen=True)
class SyntheticRootContext:
    """Identity needed to recover an all-pruned synthetic root."""

    head_ref: str
    message: bytes
    metadata: tuple[tuple[str, str], ...]


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
    return {key: value.decode("utf-8", "surrogateescape") for key, value in zip(keys, fields)}


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
    return _create_commit_for_tree(repository, tree, parent, message, _metadata(repository, source))


def _create_commit_for_tree(
    repository: Repository,
    tree: str,
    parent: str | None,
    message: bytes,
    metadata: dict[str, str],
) -> str:
    arguments = ["commit-tree", tree]
    if parent:
        arguments.extend(["-p", parent])
    arguments.extend(["-F", "-"])
    try:
        result = repository.run(
            *arguments, input_bytes=message, environment=metadata
        )
    except SanitizeError:
        raise SanitizeError("Could not recreate a sanitized commit")
    return result.decode().strip()


def _synthetic_root_context(
    repository: Repository, synthetic_root: str, policy: Policy
) -> SyntheticRootContext:
    return SyntheticRootContext(
        head_ref=repository.head_ref(),
        message=f"{policy.history.prefix_message}\n".encode(),
        metadata=tuple(sorted(_metadata(repository, synthetic_root).items())),
    )


def restore_empty_synthetic_root(repository: Repository, context: SyntheticRootContext) -> bool:
    """Restore the captured root only if filtering pruned every retained commit."""
    head = repository.run("rev-parse", "--verify", "--quiet", "HEAD", check=False).strip()
    if head:
        return False
    if repository.head_ref() != context.head_ref:
        raise SanitizeError("Could not restore a valid sanitized HEAD")
    empty_tree = repository.run("mktree", input_bytes=b"").decode().strip()
    root = _create_commit_for_tree(
        repository, empty_tree, None, context.message, dict(context.metadata)
    )
    repository.run("update-ref", context.head_ref, root)
    resolved = repository.run("rev-parse", "--verify", "--quiet", "HEAD", check=False).strip()
    if not resolved or resolved.decode() != root or repository.head_ref() != context.head_ref:
        raise SanitizeError("Could not restore a valid sanitized HEAD")
    if repository.commit_tree(root) != empty_tree:
        raise SanitizeError("Could not restore a valid sanitized HEAD")
    return True


def compact(repository: Repository, policy: Policy) -> CompactResult:
    if policy.source.mode == "snapshot":
        head = repository.text("rev-parse", "HEAD")
        synthetic_root = _create_commit(
            repository, head, None, f"{policy.history.prefix_message}\n".encode()
        )
        repository.run("update-ref", repository.head_ref(), synthetic_root, head)
        return CompactResult(1, 0, head, synthetic_root, _synthetic_root_context(repository, synthetic_root, policy))
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
        synthetic_root_context=_synthetic_root_context(repository, synthetic_root, policy),
    )
