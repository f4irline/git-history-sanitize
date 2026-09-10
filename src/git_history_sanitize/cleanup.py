"""Remove metadata and objects that must not survive sanitization."""

from __future__ import annotations

import shutil

from .git import Repository


def retain_head_only(repository: Repository) -> str:
    head_ref = repository.head_ref()
    for remote in repository.text("remote").splitlines():
        if remote:
            repository.run("remote", "remove", remote)
    for ref in repository.text("for-each-ref", "--format=%(refname)").splitlines():
        if ref and ref != head_ref:
            repository.run("update-ref", "-d", ref)
    branch = head_ref.removeprefix("refs/heads/")
    repository.run("config", "--local", "--remove-section", f"branch.{branch}", check=False)
    return head_ref


def cleanup(repository: Repository) -> None:
    retain_head_only(repository)
    shallow = repository.git_dir / "shallow"
    if shallow.exists():
        # Compaction creates new roots.  Retaining a source shallow marker would
        # make a complete published database appear bounded after those roots go.
        stale_roots = set(shallow.read_text("ascii").splitlines())
        reachable = set(repository.text("rev-list", "--all").splitlines())
        if stale_roots & reachable:
            raise RuntimeError("cannot clean shallow metadata while boundary is reachable")
        shallow.unlink()
    repository.run(
        "reflog", "expire", "--expire=now", "--expire-unreachable=now", "--all"
    )
    for path in (
        repository.git_dir / "logs",
        repository.git_dir / "refs" / "original",
        repository.git_dir / "filter-repo",
    ):
        if path.exists():
            shutil.rmtree(path)
    repository.run("gc", "--prune=now", "--aggressive")
