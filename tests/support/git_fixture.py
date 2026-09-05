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
    all_objects: str
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
        # Keep the venv launcher path: resolving it escapes the active runtime.
        self.python_executable = sys.executable
        self.source_filter_repo_executable = shutil.which("git-filter-repo")
        self.environment = self._environment()
        self.home.mkdir()
        self.xdg_config.mkdir()
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
        return {
            "PATH": os.pathsep.join(sorted(executable_dirs)),
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

    def _runtime_environment(self, *, include_source_filter_repo: bool = False) -> dict[str, str]:
        environment = {key: value for key, value in self.environment.items() if key != "PYTHONPATH"}
        if include_source_filter_repo and self.source_filter_repo_executable:
            environment["PATH"] = os.pathsep.join(
                [str(Path(self.source_filter_repo_executable).resolve().parent), environment["PATH"]]
            )
        return environment

    def _wheel_cli(self, arguments: tuple[str, ...]) -> list[str]:
        wheel = os.environ.get("GHS_WHEEL")
        if not wheel:
            raise RuntimeError("GHS_WHEEL is required for the wheel test runtime")
        wheel_path = Path(wheel).resolve(strict=True)
        runtime = self.root / "wheel-runtime"
        if not runtime.exists():
            subprocess.run(
                [self.python_executable, "-I", "-m", "venv", str(runtime)],
                check=True,
                capture_output=True,
                env=self._runtime_environment(),
                text=True,
            )
            subprocess.run(
                [
                    str(runtime / "bin" / "python"),
                    "-I",
                    "-m",
                    "pip",
                    "install",
                    "--no-deps",
                    str(wheel_path),
                    "git-filter-repo==2.47.0",
                ],
                check=True,
                capture_output=True,
                env=self._runtime_environment(),
                text=True,
            )
        launcher = (runtime / "bin" / "git-history-sanitize").resolve(strict=True)
        try:
            launcher.relative_to(runtime.resolve(strict=True))
        except ValueError as error:
            raise RuntimeError(
                "wheel console script must resolve inside the fixture-owned wheel venv"
            ) from error
        return [str(launcher), *arguments]

    def _container_cli(self, arguments: tuple[str, ...]) -> list[str]:
        image = os.environ.get("GHS_CONTAINER_IMAGE")
        if not image:
            raise RuntimeError("GHS_CONTAINER_IMAGE is required for the container test runtime")
        runtime = shutil.which(os.environ.get("GHS_OCI_RUNTIME", "docker"))
        if not runtime:
            raise RuntimeError("an OCI runtime is required for the container test runtime")

        translated = list(arguments)
        mounts: list[str] = []
        fixed_paths = {"--source": ("/input.git", "ro"), "--policy": ("/policy.yml", "ro")}
        input_mounted = False
        for index, argument in enumerate(translated):
            if argument not in {*fixed_paths, "--repository", "--output"}:
                continue
            if index + 1 == len(translated):
                raise ValueError(f"{argument} requires a path")
            if argument in {"--output", "--repository"}:
                host_path = Path(translated[index + 1]).resolve()
                if argument == "--repository" and host_path == (self.source / ".git").resolve():
                    if input_mounted:
                        raise ValueError("container CLI accepts only one input repository")
                    input_mounted = True
                    mounts.extend(["--mount", f"type=bind,src={host_path},dst=/input.git,readonly"])
                    translated[index + 1] = "/input.git"
                    continue
                if host_path.name in {"", "."}:
                    raise ValueError(f"{argument} requires a named path")
                output_mount = f"type=bind,src={host_path.parent},dst=/output"
                if argument == "--repository":
                    output_mount += ",readonly"
                mounts.extend(["--mount", output_mount])
                translated[index + 1] = f"/output/{host_path.name}"
                continue
            fixed_path, mode = fixed_paths[argument]
            host_path = Path(translated[index + 1]).resolve(strict=mode == "ro")
            if fixed_path == "/input.git":
                if input_mounted:
                    raise ValueError("container CLI accepts only one input repository")
                input_mounted = True
            mounts.extend(["--mount", f"type=bind,src={host_path},dst={fixed_path},readonly"])
            translated[index + 1] = fixed_path
        if any(str(self.root) in argument for argument in translated):
            raise ValueError("container CLI arguments must not contain fixture host paths")

        environment = {
            "HOME": "/home/fixture",
            "XDG_CONFIG_HOME": "/xdg-config",
            "LC_ALL": "C",
            "LANG": "C",
            "TZ": "UTC",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/gitconfig",
            "GIT_TEMPLATE_DIR": "/templates",
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
            "GIT_CONFIG_VALUE_3": "/hooks",
        }
        translated_mounts = (
            (self.home, "/home/fixture"),
            (self.xdg_config, "/xdg-config"),
            (self.global_config, "/gitconfig"),
            (self.template_dir, "/templates"),
            (self.hooks_dir, "/hooks"),
        )
        mounts.extend(
            item
            for host_path, container_path in translated_mounts
            for item in ("--mount", f"type=bind,src={host_path},dst={container_path},readonly")
        )
        return [
            runtime,
            "run",
            "--rm",
            "--network=none",
            "--read-only",
            "--tmpfs",
            "/tmp",
            *mounts,
            *(item for key, value in environment.items() for item in ("--env", f"{key}={value}")),
            image,
            *translated,
        ]

    def _assert_container_result_redacted(
        self, result: subprocess.CompletedProcess[str], arguments: tuple[str, ...]
    ) -> None:
        host_paths = [
            self.root,
            self.source,
            self.home,
            self.xdg_config,
            self.global_config,
            self.template_dir,
            self.hooks_dir,
        ]
        path_options = {"--source", "--repository", "--policy", "--output"}
        host_paths.extend(
            Path(arguments[index + 1]).resolve()
            for index, argument in enumerate(arguments[:-1])
            if argument in path_options
        )
        self.assert_redacted(result.stdout + result.stderr, *(str(path) for path in host_paths))

    def run_cli(self, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        runtime = os.environ.get("GHS_TEST_RUNTIME", "source")
        environment = self._runtime_environment(include_source_filter_repo=runtime == "source")
        if runtime == "source":
            command = [self.python_executable, "-I", "-m", "git_history_sanitize", *arguments]
        elif runtime == "wheel":
            command = self._wheel_cli(arguments)
            environment["PATH"] = os.pathsep.join([str(Path(command[0]).parent), environment["PATH"]])
        elif runtime == "container":
            command = self._container_cli(arguments)
        else:
            raise RuntimeError(f"unsupported GHS_TEST_RUNTIME: {runtime}")
        result = subprocess.run(
            command,
            check=check,
            capture_output=True,
            env=environment,
            text=True,
        )
        if runtime == "container":
            self._assert_container_result_redacted(result, arguments)
        return result

    def write_policy(
        self,
        *,
        cutoff: str | None = "2026-09-03T00:00:00+00:00",
        cutoff_commit: str | None = None,
        excluded_paths: tuple[str, ...] = (),
        prefix_message: str = "[sanitized]",
        mixed_message: str = "[sanitized]",
    ) -> Path:
        """Write a minimal deterministic v1 policy owned by this fixture."""
        if (cutoff is None) == (cutoff_commit is None):
            raise ValueError("specify exactly one cutoff value")
        history = (
            f'  cutoff: "{cutoff}"'
            if cutoff is not None
            else f"  cutoffCommit: {cutoff_commit}"
        )
        paths = "" if not excluded_paths else "paths:\n  exclude:\n" + "".join(
            f"    - {path}\n" for path in excluded_paths
        )
        policy = self.root / "policy.yml"
        policy.write_text(
            "version: 1\n"
            "history:\n"
            f"{history}\n"
            f"  prefixMessage: \"{prefix_message}\"\n"
            f"{paths}"
            "commits:\n"
            f"  mixedMessage: \"{mixed_message}\"\n"
            "refs:\n"
            "  keep:\n"
            "    - HEAD\n"
        )
        return policy

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

    def tree_with_file(self, repository: Path, path: str, content: str) -> str:
        """Create a one-file tree for a reachable object-database tamper case."""
        blob = self.add_unreachable_blob(content, repository)
        result = subprocess.run(
            [self.git_executable, "-C", str(repository), "mktree"],
            check=True,
            capture_output=True,
            env=self.environment,
            input=f"100644 blob {blob}\t{path}\n",
            text=True,
        )
        return result.stdout.strip()

    def commit_tree(
        self,
        repository: Path,
        tree: str,
        message: str,
        *parents: str,
        timestamp: str | None = None,
    ) -> str:
        """Create a deterministic commit from an existing tree for tamper tests."""
        dates = {}
        if timestamp:
            dates = {"GIT_AUTHOR_DATE": timestamp, "GIT_COMMITTER_DATE": timestamp}
        result = subprocess.run(
            [
                self.git_executable,
                "-C",
                str(repository),
                "commit-tree",
                tree,
                *(argument for parent in parents for argument in ("-p", parent)),
            ],
            check=True,
            capture_output=True,
            env=self.environment | dates,
            input=message,
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
            refs=self.refs(self.source),
            reachable_objects=self.reachable_objects(self.source),
            all_objects=self.all_objects(self.source),
            status=self.git(self.source, "status", "--porcelain=v1", "--untracked-files=all"),
            index=(self.source / ".git" / "index").read_bytes(),
            worktree=worktree,
        )

    def assert_source_snapshot(self, snapshot: SourceSnapshot) -> None:
        self.assertEqual(self.snapshot_source(), snapshot, "source repository was mutated")

    def refs(self, repository: Path) -> str:
        return self.git(repository, "for-each-ref", "--format=%(refname) %(objectname)")

    def reachable_objects(self, repository: Path) -> str:
        return self.git(repository, "rev-list", "--objects", "--all")

    def all_objects(self, repository: Path) -> str:
        return self.git(repository, "cat-file", "--batch-all-objects", "--batch-check=%(objectname)")

    def snapshot_output(self, repository: Path) -> tuple[str, str, str]:
        """Return refs plus reachable and physical object identities for a bare output."""
        return self.refs(repository), self.reachable_objects(repository), self.all_objects(repository)

    def assert_output_snapshot(
        self, repository: Path, snapshot: tuple[str, str, str]
    ) -> None:
        self.assertEqual(self.snapshot_output(repository), snapshot, "sanitized output was mutated")

    def assert_no_staging_directories(self, parent: Path) -> None:
        leftovers = sorted(path.name for path in parent.glob(".git-history-sanitize-*"))
        self.assertEqual(leftovers, [], "sanitizer staging directories remain")

    @staticmethod
    def assert_redacted(output: str, *sensitive_values: str) -> None:
        for value in sensitive_values:
            if value:
                assert value not in output, "sensitive value leaked in command output"

    def assertEqual(self, first: object, second: object, message: str = "") -> None:
        if first != second:
            raise AssertionError(message or f"{first!r} != {second!r}")
