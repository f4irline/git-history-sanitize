"""Independent verification of a sanitized Git database."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from .errors import VerificationError
from .git import GitError, Repository
from .policy import Policy
from .receipt import Receipt, ReceiptError


@dataclass(frozen=True)
class VerificationReport:
    head: str
    commit_count: int
    root: str
    retained_refs: tuple[str, ...]
    excluded_paths: tuple[str, ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)


@dataclass(frozen=True)
class _Invariant:
    name: str
    check: Callable[[], None]


@dataclass
class _VerificationState:
    commits: tuple[str, ...] = ()
    head_ref: str = ""
    refs: tuple[str, ...] = ()


def _fail(message: str) -> None:
    raise VerificationError(message)


def _contract_fail(invariant: str) -> None:
    raise VerificationError(f"verification failed: {invariant}", invariant=invariant)


def _inspect(invariant: _Invariant) -> None:
    try:
        invariant.check()
    except VerificationError:
        raise
    except (GitError, OSError, UnicodeError, ValueError):
        _contract_fail(invariant.name)


def _graph(repository: Repository) -> tuple[str, ...]:
    commits = tuple(repository.text("rev-list", "--reverse", "--topo-order", "HEAD").splitlines())
    if not commits:
        _contract_fail("graph.linear")
    for index, commit in enumerate(commits):
        parents = tuple(repository.text("show", "-s", "--format=%P", commit).split())
        expected = () if index == 0 else (commits[index - 1],)
        if parents != expected:
            _contract_fail("graph.linear")
    return commits


def _root(repository: Repository, policy: Policy, commits: tuple[str, ...]) -> None:
    if repository.text("show", "-s", "--format=%B", commits[0]).rstrip("\n") != policy.history.prefix_message:
        _contract_fail("root.synthetic")
    if policy.history.cutoff_epoch is not None:
        for commit in commits:
            if int(repository.text("show", "-s", "--format=%ct", commit)) < policy.history.cutoff_epoch:
                _contract_fail("root.synthetic")


def _head(repository: Repository) -> str:
    ref = repository.run("symbolic-ref", "-q", "HEAD", check=False).decode("utf-8", "surrogateescape").strip()
    if not ref.startswith("refs/heads/"):
        _contract_fail("head.symbolic")
    if repository.text("rev-parse", "HEAD") != repository.text("rev-parse", "--verify", ref):
        _contract_fail("head.symbolic")
    return ref


def _refs(repository: Repository, head_ref: str) -> tuple[str, ...]:
    refs = tuple(repository.text("for-each-ref", "--format=%(refname)").splitlines())
    if refs != (head_ref,):
        _contract_fail("refs.retained")
    return refs


def _paths(repository: Repository, policy: Policy, commits: tuple[str, ...]) -> None:
    excluded = tuple(path.encode("utf-8", "surrogateescape") for path in policy.excluded_paths)
    for commit in commits:
        paths = repository.run("ls-tree", "-r", "-z", "--name-only", commit).split(b"\0")
        for path in paths[:-1]:
            if any(path == item or (item.endswith(b"/") and path.startswith(item)) for item in excluded):
                _contract_fail("paths.excluded")


def _remotes(repository: Repository) -> None:
    if repository.text("remote"):
        _contract_fail("remotes.absent")


def _complete(repository: Repository) -> None:
    if repository.text("rev-parse", "--is-shallow-repository") != "false":
        _contract_fail("repository.complete")
    if (repository.git_dir / "shallow").exists() or (repository.git_dir / "objects" / "info" / "alternates").exists():
        _contract_fail("repository.complete")
    if repository.run("config", "--get", "extensions.partialClone", check=False).strip():
        _contract_fail("repository.complete")
    if repository.run("config", "--get-regexp", r"^remote\..*\.promisor$", check=False).strip():
        _contract_fail("repository.complete")
    if any((repository.git_dir / "objects" / "pack").glob("*.promisor")):
        _contract_fail("repository.complete")


def _metadata(repository: Repository) -> None:
    if any(path.exists() for path in (
        repository.git_dir / "logs",
        repository.git_dir / "refs" / "original",
        repository.git_dir / "filter-repo",
    )):
        _contract_fail("metadata.clean")


def _objects(repository: Repository) -> None:
    if repository.run("fsck", "--full", "--unreachable", "--no-reflogs").strip():
        _contract_fail("objects.reachable-only")


def _forbidden(repository: Repository, values: tuple[str, ...]) -> None:
    for value in values:
        if not value:
            continue
        objects = repository.run("cat-file", "--batch-all-objects", "--batch-check=%(objectname)")
        if value.encode() in repository.run("cat-file", "--batch", "--buffer", input_bytes=objects):
            _contract_fail("content.forbidden")


def _verify_receipt(
    repository: Repository, policy: Policy, source: str | Path | None, receipt: str | Path | None,
) -> None:
    if not policy.history.cutoff_commit:
        if source is not None or receipt is not None:
            _fail("history.cutoff does not accept --receipt or --source")
        return
    if source is None or receipt is None:
        _fail("cutoffCommit verification requires --receipt and --source")
    try:
        evidence = Receipt.from_bytes(Path(receipt).read_bytes())
    except OSError as error:
        raise VerificationError("sanitization receipt is missing") from error
    except ReceiptError as error:
        raise VerificationError(str(error)) from error
    payload = evidence.payload
    if payload["policy"]["sha256"] != policy.digest:
        _fail("sanitization receipt does not match the policy")
    sanitized = payload["sanitized"]
    roots = repository.text("rev-list", "--max-parents=0", "--all").splitlines()
    if (repository.object_format() != sanitized["object_format"] or len(roots) != 1
            or roots[0] != sanitized["root"] or repository.text("rev-parse", "HEAD") != sanitized["head"]):
        _fail("sanitization receipt does not match sanitized output")
    source_repository = Repository(source)
    source_binding = payload["source"]
    try:
        cutoff = source_repository.resolve_cutoff_commit(policy.history.cutoff_commit)
        kind, ref, head = source_repository.head_identity()
        fingerprint = Receipt.source_fingerprint(
            source_repository.object_format(), kind, ref, head, source_repository.direct_refs()
        )
    except Exception as error:
        raise VerificationError("sanitization receipt does not match source repository") from error
    if (source_repository.object_format() != source_binding["object_format"]
            or source_repository.object_format() != repository.object_format()
            or cutoff != source_binding["cutoff_commit"]
            or source_repository.commit_tree(cutoff) != source_binding["boundary_tree"]
            or head != source_binding["head"]
            or fingerprint != source_binding["repository_fingerprint"]):
        _fail("sanitization receipt does not match source repository")


def verify(
    repository_path: str | Path, policy: Policy, forbidden: tuple[str, ...] = (), *,
    source: str | Path | None = None, receipt: str | Path | None = None,
) -> VerificationReport:
    repository = Repository(repository_path)
    _verify_receipt(repository, policy, source, receipt)
    state = _VerificationState()
    checks = (
        _Invariant("repository.complete", lambda: _complete(repository)),
        _Invariant("graph.linear", lambda: setattr(state, "commits", _graph(repository))),
        _Invariant("root.synthetic", lambda: _root(repository, policy, state.commits)),
        _Invariant("head.symbolic", lambda: setattr(state, "head_ref", _head(repository))),
        _Invariant("refs.retained", lambda: setattr(state, "refs", _refs(repository, state.head_ref))),
        _Invariant("paths.excluded", lambda: _paths(repository, policy, state.commits)),
        _Invariant("remotes.absent", lambda: _remotes(repository)),
        _Invariant("metadata.clean", lambda: _metadata(repository)),
        _Invariant("objects.reachable-only", lambda: _objects(repository)),
        _Invariant("content.forbidden", lambda: _forbidden(repository, forbidden)),
    )
    for invariant in checks:
        _inspect(invariant)
    return VerificationReport(
        head=repository.text("rev-parse", "HEAD"), commit_count=len(state.commits), root=state.commits[0],
        retained_refs=state.refs, excluded_paths=policy.excluded_paths,
    )
