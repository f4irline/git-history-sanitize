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
