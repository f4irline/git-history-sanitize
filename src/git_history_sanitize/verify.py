"""Independent verification of a sanitized Git database."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .errors import VerificationError
from .git import Repository
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


def _fail(message: str) -> None:
    raise VerificationError(message)


def _assert_no_pre_cutoff(repository: Repository, policy: Policy) -> None:
    if policy.history.cutoff_epoch is None:
        return
    for timestamp in repository.text("log", "--all", "--format=%ct").splitlines():
        if int(timestamp) < policy.history.cutoff_epoch:
            _fail("A reachable commit predates history.cutoff")


def _assert_paths_absent(repository: Repository, policy: Policy) -> None:
    object_lines = repository.text("rev-list", "--objects", "--all").splitlines()
    for path in policy.excluded_paths:
        if repository.text("log", "--all", "--format=%H", "--", path):
            _fail(f"A configured path remains in reachable history: {path}")
        for line in object_lines:
            _, _, object_path = line.partition(" ")
            if object_path == path or (path.endswith("/") and object_path.startswith(path)):
                _fail(f"A configured object remains reachable: {path}")


def _assert_metadata_removed(repository: Repository, head_ref: str) -> tuple[str, ...]:
    refs = tuple(repository.text("for-each-ref", "--format=%(refname)").splitlines())
    if refs != (head_ref,):
        _fail("Unexpected refs remain")
    if repository.text("remote"):
        _fail("A remote remains in sanitized output")
    for path in (
        repository.git_dir / "logs",
        repository.git_dir / "refs" / "original",
        repository.git_dir / "filter-repo",
    ):
        if path.exists():
            _fail("Temporary Git metadata remains")
    fsck = repository.run("fsck", "--full", "--unreachable", "--no-reflogs").decode().strip()
    if fsck:
        _fail("Unreachable objects remain after cleanup")
    return refs


def verify(
    repository_path: str | Path,
    policy: Policy,
    forbidden: tuple[str, ...] = (),
    *,
    source: str | Path | None = None,
    receipt: str | Path | None = None,
) -> VerificationReport:
    repository = Repository(repository_path)
    if policy.history.cutoff_commit:
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
        roots = repository.text("rev-list", "--max-parents=0", "--all").splitlines()
        sanitized = payload["sanitized"]
        if (
            repository.object_format() != sanitized["object_format"]
            or len(roots) != 1
            or roots[0] != sanitized["root"]
            or repository.text("rev-parse", "HEAD") != sanitized["head"]
        ):
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
        if (
            source_repository.object_format() != source_binding["object_format"]
            or source_repository.object_format() != repository.object_format()
            or cutoff != source_binding["cutoff_commit"]
            or source_repository.commit_tree(cutoff) != source_binding["boundary_tree"]
            or head != source_binding["head"]
            or fingerprint != source_binding["repository_fingerprint"]
        ):
            _fail("sanitization receipt does not match source repository")
    elif source is not None or receipt is not None:
        _fail("history.cutoff does not accept --receipt or --source")
    head_ref = repository.head_ref()
    _assert_no_pre_cutoff(repository, policy)
    roots = repository.text("rev-list", "--max-parents=0", "--all").splitlines()
    if len(roots) != 1:
        _fail("Sanitized output must have exactly one root")
    if repository.text("show", "-s", "--format=%B", roots[0]).rstrip("\n") != policy.history.prefix_message:
        _fail("Synthetic root does not have the configured prefix message")
    _assert_paths_absent(repository, policy)
    refs = _assert_metadata_removed(repository, head_ref)

    for value in forbidden:
        if not value:
            continue
        objects = repository.run(
            "cat-file", "--batch-all-objects", "--batch-check=%(objectname)"
        )
        content = repository.run("cat-file", "--batch", "--buffer", input_bytes=objects)
        if value.encode() in content:
            _fail("Forbidden content remains in the object database")

    return VerificationReport(
        head=repository.text("rev-parse", "HEAD"),
        commit_count=int(repository.text("rev-list", "--count", "--all")),
        root=roots[0],
        retained_refs=refs,
        excluded_paths=policy.excluded_paths,
    )
