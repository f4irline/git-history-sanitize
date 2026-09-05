"""Hermetic, deterministic Git repositories for integration tests."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import unittest


@dataclass(frozen=True)
class SourceSnapshot:
    """Observable source state that sanitization must not change."""

    refs: str
    reachable_objects: str
    status: str
    index: bytes
    worktree: tuple[tuple[str, bytes], ...]


class GitFixture:
    """Create an isolated Git repository and subprocess environment for a test."""

    AUTHOR_NAME = "Fixture"
    AUTHOR_EMAIL = "fixture@example.invalid"
    TIMESTAMP = "2026-09-03T12:00:00+00:00"

    def __init__(self, case: unittest.TestCase) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        case.addCleanup(self._temporary.cleanup)
        self.root = Path(self._temporary.name)
        self.home = self.root / "home"
        self.xdg_config = self.root / "xdg-config"
        self.global_config = self.root / "gitconfig"
        self.template_dir = self.root / "templates"
        self.hooks_dir = self.root / "hooks"
        self.source = self.root / "source"
        self.git_executable = self._required_executable("git")
        self.python_executable = str(Path(sys.executable).resolve())
        self.filter_repo_executable = shutil.which("git-filter-repo")
        self.environment = self._environment()
        self.global_config.touch()
        self.template_dir.mkdir()
        self.hooks_dir.mkdir()
        self.git(self.root, "init", "--initial-branch=main", str(self.source))
        self.git(self.source, "config", "user.name", self.AUTHOR_NAME)
        self.git(self.source, "config", "user.email", self.AUTHOR_EMAIL)

    @staticmethod
    def _required_executable(name: str) -> str:
        executable = shutil.which(name)
        if executable is None:
            raise RuntimeError(f"Required test executable is unavailable: {name}")
        return str(Path(executable).resolve())

    def _environment(self) -> dict[str, str]:
        executable_dirs = {str(Path(self.git_executable).parent), str(Path(self.python_executable).parent)}
        if self.filter_repo_executable:
            executable_dirs.add(str(Path(self.filter_repo_executable).resolve().parent))
        project_source = Path(__file__).resolve().parents[2] / "src"
        return {
            "PATH": os.pathsep.join(sorted(executable_dirs)),
            "PYTHONPATH": str(project_source),
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.xdg_config),
            "LC_ALL": "C",
            "LANG": "C",
            "TZ": "UTC",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": str(self.global_config),
            "GIT_TEMPLATE_DIR": str(self.template_dir),
            "GIT_AUTHOR_NAME": self.AUTHOR_NAME,
            "GIT_AUTHOR_EMAIL": self.AUTHOR_EMAIL,
            "GIT_COMMITTER_NAME": self.AUTHOR_NAME,
            "GIT_COMMITTER_EMAIL": self.AUTHOR_EMAIL,
            "GIT_AUTHOR_DATE": self.TIMESTAMP,
            "GIT_COMMITTER_DATE": self.TIMESTAMP,
            "GIT_CONFIG_COUNT": "4",
            "GIT_CONFIG_KEY_0": "commit.gpgsign",
            "GIT_CONFIG_VALUE_0": "false",
            "GIT_CONFIG_KEY_1": "tag.gpgSign",
            "GIT_CONFIG_VALUE_1": "false",
            "GIT_CONFIG_KEY_2": "credential.helper",
            "GIT_CONFIG_VALUE_2": "",
            "GIT_CONFIG_KEY_3": "core.hooksPath",
            "GIT_CONFIG_VALUE_3": str(self.hooks_dir),
        }

    def git(
        self,
        repository: Path,
        *arguments: str,
        env: dict[str, str] | None = None,
        check: bool = True,
    ) -> str:
        environment = self.environment | (env or {})
        result = subprocess.run(
            [self.git_executable, "-C", str(repository), *arguments],
            check=check,
            capture_output=True,
            env=environment,
            text=True,
        )
        return result.stdout.strip()

    def run_cli(self, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [self.python_executable, "-m", "git_history_sanitize", *arguments],
            check=check,
            capture_output=True,
            env=self.environment,
            text=True,
        )

    def write(self, relative_path: str, content: str) -> Path:
        path = self.source / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def commit(self, message: str, *paths: str, timestamp: str | None = None) -> str:
        self.git(self.source, "add", *paths)
        dates = {}
        if timestamp:
            dates = {"GIT_AUTHOR_DATE": timestamp, "GIT_COMMITTER_DATE": timestamp}
        self.git(self.source, "commit", "-qm", message, env=dates)
        return self.git(self.source, "rev-parse", "HEAD")

    def tag(self, name: str, message: str) -> str:
        self.git(self.source, "tag", "-a", name, "-m", message)
        return self.git(self.source, "rev-parse", f"{name}^{{}}")

    def branch(self, name: str, start_point: str = "HEAD") -> str:
        self.git(self.source, "branch", name, start_point)
        return self.git(self.source, "rev-parse", name)

    def merge(self, branch: str, message: str) -> str:
        self.git(self.source, "merge", "--no-ff", "-m", message, branch)
        return self.git(self.source, "rev-parse", "HEAD")

    def add_unreachable_blob(self, content: str, repository: Path | None = None) -> str:
        repository = repository or self.source
        result = subprocess.run(
            [self.git_executable, "-C", str(repository), "hash-object", "-w", "--stdin"],
            check=True,
            capture_output=True,
            env=self.environment,
            input=content,
            text=True,
        )
        return result.stdout.strip()

    def snapshot_source(self) -> SourceSnapshot:
        worktree = tuple(
            (str(path.relative_to(self.source)), path.read_bytes())
            for path in sorted(self.source.rglob("*"))
            if path.is_file() and ".git" not in path.parts
        )
        return SourceSnapshot(
            refs=self.git(self.source, "for-each-ref", "--format=%(refname) %(objectname)"),
            reachable_objects=self.git(self.source, "rev-list", "--objects", "--all"),
            status=self.git(self.source, "status", "--porcelain=v1", "--untracked-files=all"),
            index=(self.source / ".git" / "index").read_bytes(),
            worktree=worktree,
        )

    def assert_source_snapshot(self, snapshot: SourceSnapshot) -> None:
        self.assertEqual(self.snapshot_source(), snapshot, "source repository was mutated")

    @staticmethod
    def assert_redacted(output: str, *sensitive_values: str) -> None:
        for value in sensitive_values:
            if value:
                assert value not in output, f"sensitive value leaked: {value!r}"

    def assertEqual(self, first: object, second: object, message: str = "") -> None:
        if first != second:
            raise AssertionError(message or f"{first!r} != {second!r}")
