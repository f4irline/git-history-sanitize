"""Small, binary-safe wrappers around the Git command line."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

from .errors import SanitizeError


class GitError(SanitizeError):
    """Raised when Git rejects an operation."""


def git_environment(environment: dict[str, str] | None = None) -> dict[str, str]:
    """Prevent Git from resolving replacements or fetching promised objects."""
    env = os.environ.copy()
    if environment:
        env.update(environment)
    env["GIT_NO_LAZY_FETCH"] = "1"
    env["GIT_NO_REPLACE_OBJECTS"] = "1"
    return env


def run(
    arguments: Iterable[str],
    *,
    cwd: Path | None = None,
    input_bytes: bytes | None = None,
    environment: dict[str, str] | None = None,
    check: bool = True,
) -> bytes:
    command = ["git", *arguments]
    env = git_environment(environment)
    result = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    if check and result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip().splitlines()
        suffix = f": {detail[-1]}" if detail else ""
        raise GitError(f"Git command failed ({' '.join(command[:2])}){suffix}")
    return result.stdout


def ensure_dependencies() -> dict[str, str]:
    git_version = run(["--version"]).decode().strip()
    if shutil.which("git-filter-repo") is None:
        try:
            filter_repo_version = run(["filter-repo", "--version"]).decode().strip()
        except GitError as error:
            raise SanitizeError("git-filter-repo is required on PATH") from error
    else:
        filter_repo_version = subprocess.run(
            ["git-filter-repo", "--version"],
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        ).stdout.strip()
    return {"git": git_version, "git_filter_repo": filter_repo_version}


class Repository:
    def __init__(self, path: str | Path):
        self.path = Path(path).resolve()
        self._bare = False
        try:
            self.git_dir = Path(
                run(["-C", str(self.path), "rev-parse", "--absolute-git-dir"]).decode().strip()
            ).resolve()
        except GitError as error:
            if (self.path / "config").is_file() and (self.path / "objects").is_dir():
                self.git_dir = self.path
                self._bare = True
            else:
                raise SanitizeError(f"Not a Git repository: {self.path}") from error

    def run(
        self,
        *arguments: str,
        input_bytes: bytes | None = None,
        environment: dict[str, str] | None = None,
        check: bool = True,
    ) -> bytes:
        return run(
            [f"--git-dir={self.git_dir}", *arguments] if self._bare else ["-C", str(self.path), *arguments],
            input_bytes=input_bytes,
            environment=environment,
            check=check,
        )

    def command(self, *arguments: str) -> list[str]:
        """Return a Git command scoped to this repository."""
        return [
            "git",
            f"--git-dir={self.git_dir}" if self._bare else "-C",
            *(() if self._bare else (str(self.path),)),
            *arguments,
        ]

    def text(self, *arguments: str) -> str:
        return self.run(*arguments).decode("utf-8", "surrogateescape").strip()

    def head_ref(self) -> str:
        ref = self.run("symbolic-ref", "-q", "HEAD", check=False).decode().strip()
        if not ref:
            raise SanitizeError("The retained repository must have a symbolic HEAD")
        return ref

    def object_format(self) -> str:
        value = self.text("rev-parse", "--show-object-format=storage")
        if value not in {"sha1", "sha256"}:
            raise SanitizeError("Unsupported Git object format")
        return value

    def head_identity(self) -> tuple[str, bytes, str]:
        ref = self.run("symbolic-ref", "-q", "HEAD", check=False).rstrip(b"\n")
        return ("symref", ref, self.text("rev-parse", "HEAD")) if ref else ("detached", b"", self.text("rev-parse", "HEAD"))

    def direct_refs(self) -> tuple[tuple[bytes, str], ...]:
        records = self.run("for-each-ref", "--sort=refname", "--format=%(refname)%00%(objectname)%00").splitlines()
        result: list[tuple[bytes, str]] = []
        for record in records:
            fields = record.split(b"\0")
            if len(fields) != 3 or fields[-1]:
                raise SanitizeError("Cannot read source references")
            result.append((fields[0], fields[1].decode("ascii")))
        return tuple(result)

    def resolve_cutoff_commit(self, value: str) -> str:
        object_format = self.object_format()
        width = 40 if object_format == "sha1" else 64
        if len(value) != width or any(character not in "0123456789abcdef" for character in value):
            raise SanitizeError("history.cutoffCommit must be a full lowercase storage-format object ID")
        if self.run("cat-file", "-t", "--", value, check=False).decode().strip() != "commit":
            raise SanitizeError("history.cutoffCommit must resolve to a commit")
        result = self.run("rev-parse", "--verify", "--end-of-options", f"{value}^{{commit}}", check=False).decode().strip()
        if len(result) != width:
            raise SanitizeError("history.cutoffCommit must resolve to a commit")
        return result

    def commit_tree(self, commit: str) -> str:
        return self.text("rev-parse", "--verify", "--end-of-options", f"{commit}^{{tree}}")

    def worktree_root(self) -> Path | None:
        result = self.run("rev-parse", "--show-toplevel", check=False).decode().strip()
        return Path(result).resolve() if result else None

    def clone_to(self, destination: Path, *, bare: bool = False) -> "Repository":
        arguments = ["clone", "--no-checkout", "--no-local"]
        if bare:
            arguments.append("--bare")
        arguments.extend([str(self.path), str(destination)])
        run(arguments)
        return Repository(destination)
