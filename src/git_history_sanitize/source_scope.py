"""Fail-closed source graph validation shared by planning and rewriting."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .errors import SanitizeError
from .git import GitError, Repository
from .policy import Policy


@dataclass(frozen=True)
class SourceScope:
    mode: str
    commits: tuple[str, ...]
    objects: tuple[str, ...]
    shallow_roots: tuple[str, ...]
    fingerprint: str

    @property
    def boundary_count(self) -> int:
        return len(self.shallow_roots)

    @property
    def description(self) -> str:
        return {
            "complete": "complete reachable history",
            "bounded": "declared shallow HEAD history only",
            "snapshot": "HEAD tree snapshot; inherited history excluded",
        }[self.mode]


def _fail(message: str) -> None:
    raise SanitizeError(message)


def _shallow_roots(repository: Repository) -> tuple[str, ...]:
    marker = repository.git_dir / "shallow"
    if not marker.exists():
        return ()
    try:
        roots = tuple(sorted(line.strip() for line in marker.read_text("ascii").splitlines() if line.strip()))
    except (OSError, UnicodeError) as error:
        raise SanitizeError("Cannot inspect shallow history; fetch complete history or use bounded mode") from error
    if not roots:
        _fail("Cannot prove shallow history boundary; fetch complete history")
    return roots


def _unsupported(repository: Repository) -> None:
    if (repository.git_dir / "info" / "grafts").exists():
        _fail("Source uses grafts; remove graft state before sanitizing")
    if repository.text("for-each-ref", "refs/replace").strip():
        _fail("Source uses replace refs; remove replacement state before sanitizing")
    if (repository.git_dir / "objects" / "info" / "alternates").exists():
        _fail("Source uses alternates; repack without alternates before sanitizing")


def _promisor(repository: Repository) -> bool:
    return bool(
        repository.run("config", "--get", "extensions.partialClone", check=False).strip()
        or repository.run("config", "--get-regexp", r"^remote\..*\.promisor$", check=False).strip()
        or any((repository.git_dir / "objects" / "pack").glob("*.promisor"))
    )


def _closure(repository: Repository, revision: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    try:
        commits = tuple(repository.text("rev-list", "--reverse", "--topo-order", revision).splitlines())
        raw = repository.run("rev-list", "--objects", "--no-object-names", revision)
        objects = tuple(sorted(set(raw.decode("ascii").splitlines())))
        for oid in objects:
            if repository.run("cat-file", "-e", f"{oid}^{{object}}", check=False) is None:
                _fail("Source has unavailable required objects; explicitly materialize them before sanitizing")
            # A non-zero exit is represented by empty output, so ask cat-file for its type.
            if not repository.run("cat-file", "-t", oid, check=False).strip():
                _fail("Source has unavailable required objects; explicitly materialize them before sanitizing")
    except (GitError, UnicodeError) as error:
        raise SanitizeError("Source has unavailable required objects; explicitly materialize them before sanitizing") from error
    if not commits:
        _fail("Cannot sanitize an empty repository")
    return commits, objects


def inspect_source(repository: Repository, policy: Policy) -> SourceScope:
    """Return the exact local graph allowed by the policy without contacting remotes."""
    _unsupported(repository)
    shallow_roots = _shallow_roots(repository)
    partial = _promisor(repository)
    mode = policy.source.mode
    if mode == "complete":
        if shallow_roots:
            _fail("Source is shallow; fetch complete history or explicitly select bounded mode")
        if partial:
            _fail("Source is partial/promisor; explicitly materialize objects before sanitizing")
        commits, objects = _closure(repository, "--all")
    elif mode == "bounded":
        if not shallow_roots:
            _fail("bounded source.mode requires a shallow source repository")
        commits, objects = _closure(repository, "HEAD")
        if not set(shallow_roots).issubset(commits):
            _fail("Cannot prove shallow history boundary; recreate the bounded clone")
    else:
        commits, objects = _closure(repository, "HEAD")
        # Snapshot only covers the current tree, not inherited commit objects.
        head_tree = repository.commit_tree(repository.text("rev-parse", "HEAD"))
        objects = tuple(sorted(set(repository.run("rev-list", "--objects", "--no-object-names", head_tree).decode("ascii").splitlines())))
        for oid in objects:
            if not repository.run("cat-file", "-t", oid, check=False).strip():
                _fail("Source has unavailable required objects; explicitly materialize them before sanitizing")
    content = "\0".join((mode, *shallow_roots, *commits, *objects)).encode("ascii")
    return SourceScope(mode, commits, objects, shallow_roots, hashlib.sha256(content).hexdigest())
