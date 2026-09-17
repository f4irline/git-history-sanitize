"""Contracts for conservative OCI-sensitive CI input detection."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SELECTOR = ROOT / "scripts/ci-detect-oci-inputs.sh"


class OciInputSelectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repository = Path(self.temp_dir.name)
        self.git("init", "--initial-branch=main")
        self.git("config", "user.name", "CI test")
        self.git("config", "user.email", "ci@example.invalid")
        self.commit("docs/notes.md")
        self.base = self.git("rev-parse", "HEAD").stdout.strip()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def git(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ("git", *arguments), cwd=self.repository, check=True, text=True, capture_output=True
        )

    def commit(self, path: str) -> str:
        target = self.repository / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"{path}\n")
        self.git("add", "--", path)
        self.git("commit", "-m", path)
        return self.git("rev-parse", "HEAD").stdout.strip()

    def selected(self, base: str, head: str) -> str:
        return subprocess.run(
            (str(SELECTOR), base, head), cwd=self.repository, check=True, text=True, capture_output=True
        ).stdout.strip()

    def test_selects_all_oci_sensitive_path_classes(self) -> None:
        for path in (
            "Containerfile",
            "Containerfile.dockerignore",
            "container/toolchain.lock.json",
            "requirements/container-runtime.txt",
            "requirements/release-test.txt",
            "scripts/bootstrap-test-git.sh",
            "scripts/verify-container-toolchain.py",
            "pyproject.toml",
            "README.md",
            "LICENSE",
            "src/git_history_sanitize/cli.py",
            "tests/support/toolchain.py",
            "tests/test_output_cleanup_contracts.py",
            ".github/workflows/ci.yml",
            ".github/workflows/release.yml",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.selected(self.base, self.commit(path)), "true")

    def test_skips_unrelated_paths(self) -> None:
        self.assertEqual(self.selected(self.base, self.commit("docs/architecture.md")), "false")

    def test_selects_deleted_oci_input(self) -> None:
        sensitive_head = self.commit("container/temporary-input")
        (self.repository / "container/temporary-input").unlink()
        self.git("add", "--all")
        self.git("commit", "-m", "delete container input")
        self.assertEqual(self.selected(sensitive_head, self.git("rev-parse", "HEAD").stdout.strip()), "true")

    def test_fails_closed_when_the_range_cannot_be_resolved(self) -> None:
        self.assertEqual(self.selected("missing-base", "missing-head"), "true")
