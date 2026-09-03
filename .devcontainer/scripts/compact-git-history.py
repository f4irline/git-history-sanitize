#!/usr/bin/env python3
"""Collapse a linear Git history prefix into a synthetic root commit."""

from __future__ import annotations

import datetime as dt
import os
import subprocess
import sys
from pathlib import Path


def git(repository: Path, *arguments: str, input_bytes: bytes | None = None) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        input=input_bytes,
        stdout=subprocess.PIPE,
    )
    return result.stdout


def read_cutoff(path: Path) -> tuple[str, int]:
    values = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if len(values) != 1:
        raise SystemExit(f"{path} must contain exactly one cutoff timestamp")

    value = values[0]
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise SystemExit(f"Invalid RFC 3339 cutoff timestamp {value!r}: {error}") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SystemExit("The Git-history cutoff must include an explicit timezone")
    return value, int(parsed.timestamp())


def commit_environment(repository: Path, commit: str) -> dict[str, str]:
    fields = git(
        repository,
        "show",
        "-s",
        "--format=%an%x00%ae%x00%aI%x00%cn%x00%ce%x00%cI",
        commit,
    ).rstrip(b"\n").split(b"\x00")
    if len(fields) != 6:
        raise SystemExit(f"Could not read author and committer metadata for {commit}")

    environment = os.environ.copy()
    keys = (
        "GIT_AUTHOR_NAME",
        "GIT_AUTHOR_EMAIL",
        "GIT_AUTHOR_DATE",
        "GIT_COMMITTER_NAME",
        "GIT_COMMITTER_EMAIL",
        "GIT_COMMITTER_DATE",
    )
    environment.update(
        {key: value.decode("utf-8", "surrogateescape") for key, value in zip(keys, fields)}
    )
    return environment


def commit_message(repository: Path, commit: str) -> bytes:
    raw_commit = git(repository, "cat-file", "commit", commit)
    try:
        return raw_commit.split(b"\n\n", 1)[1]
    except IndexError as error:
        raise SystemExit(f"Malformed commit object: {commit}") from error


def create_commit(
    repository: Path,
    source_commit: str,
    parent: str | None,
    message: bytes,
) -> str:
    tree = git(repository, "rev-parse", f"{source_commit}^{{tree}}").decode().strip()
    command = ["git", "-C", str(repository), "commit-tree", tree]
    if parent is not None:
        command.extend(["-p", parent])
    command.extend(["-F", "-"])
    result = subprocess.run(
        command,
        check=True,
        env=commit_environment(repository, source_commit),
        input=message,
        stdout=subprocess.PIPE,
    )
    return result.stdout.decode().strip()


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: compact-git-history.py REPOSITORY CUTOFF_FILE")

    repository = Path(sys.argv[1]).resolve()
    cutoff_file = Path(sys.argv[2]).resolve()
    cutoff_text, cutoff_epoch = read_cutoff(cutoff_file)

    head_ref = git(repository, "symbolic-ref", "-q", "HEAD").decode().strip()
    commits = git(repository, "rev-list", "--reverse", "HEAD").decode().splitlines()
    if not commits:
        raise SystemExit("Cannot compact an empty Git repository")

    previous: str | None = None
    for commit in commits:
        parents = git(repository, "show", "-s", "--format=%P", commit).decode().split()
        expected = [] if previous is None else [previous]
        if parents != expected:
            raise SystemExit(
                "Cutoff compaction currently requires a linear HEAD history; "
                f"commit {commit} has unexpected parents"
            )
        previous = commit

    allowed_index: int | None = None
    for index, commit in enumerate(commits):
        committer_epoch = int(git(repository, "show", "-s", "--format=%ct", commit))
        if committer_epoch >= cutoff_epoch:
            allowed_index = index
            break

    if allowed_index is None:
        raise SystemExit(
            f"No commit exists at or after the configured cutoff {cutoff_text}"
        )
    if any(
        int(git(repository, "show", "-s", "--format=%ct", commit)) < cutoff_epoch
        for commit in commits[allowed_index:]
    ):
        raise SystemExit(
            "Committer timestamps cross the cutoff more than once; refusing an "
            "ambiguous history rewrite"
        )
    if allowed_index == 0:
        print("No commits predate the configured Git-history cutoff.")
        return

    boundary = commits[allowed_index]
    new_head = create_commit(repository, boundary, None, b"[sanitized]\n")
    for commit in commits[allowed_index + 1 :]:
        new_head = create_commit(
            repository,
            commit,
            new_head,
            commit_message(repository, commit),
        )

    old_head = commits[-1]
    git(repository, "update-ref", head_ref, new_head, old_head)
    print(
        f"Collapsed {allowed_index} pre-cutoff commit(s) into synthetic root "
        f"{new_head[:12]}."
    )


if __name__ == "__main__":
    main()
