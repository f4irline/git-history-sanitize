"""Source-only failure injection for late rewrite atomicity."""

from __future__ import annotations

import io
import os
import stat
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from git_history_sanitize.cli import main
from git_history_sanitize.errors import SanitizeError, VerificationError
from tests.support.git_fixture import GitFixture


class EngineFailureContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = GitFixture(self)
        self.secret = "late-stage-sensitive-value"
        self.sensitive_message = "late-stage customer implementation"
        self.fixture.write("private/secret.txt", self.secret)
        self.sensitive_commit = self.fixture.commit(
            self.sensitive_message, "private/secret.txt"
        )
        self.fixture.write("allowed.txt", "safe\n")
        self.fixture.commit("allowed", "allowed.txt")
        self.policy = self.fixture.write_policy(excluded_paths=("private/",))
        self.output = self.fixture.output_dir / "must-not-exist.git"
        self.source_snapshot = self.fixture.snapshot_source()

    def run_rewrite(self, *, policy: object | None = None, receipt: Path | None = None) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            patch.dict(os.environ, self.fixture.environment, clear=True),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            arguments = [
                "rewrite", "--source", str(self.fixture.source / ".git"),
                "--output", str(self.output), "--policy", str(policy or self.policy),
            ]
            if receipt is not None:
                arguments.extend(("--receipt", str(receipt)))
            status = main(arguments)
        return status, stdout.getvalue(), stderr.getvalue()

    def assert_atomic_failure(
        self, status: int, stdout: str, stderr: str, staging_root: Path
    ) -> None:
        self.assertEqual(status, 2)
        self.assertEqual(stdout, "")
        self.assertFalse(self.output.exists())
        self.assertFalse(staging_root.exists())
        self.fixture.assert_no_staging_directories(self.output.parent)
        self.fixture.assert_source_snapshot(self.source_snapshot)
        self.fixture.assert_redacted(
            stdout + stderr,
            self.secret,
            self.sensitive_message,
            self.sensitive_commit,
            str(self.fixture.source),
        )

    def test_filter_paths_failure_is_atomic_and_cleans_staging(self) -> None:
        staging_root: Path | None = None

        def fail_filter_paths(repository: object, _policy: object) -> None:
            nonlocal staging_root
            staging_root = repository.path.parent  # type: ignore[attr-defined]
            self.assertEqual(repository.path.name, "rewrite")  # type: ignore[attr-defined]
            self.assertFalse((staging_root / "sanitized.git").exists())
            raise SanitizeError("Path filtering failed; check git-filter-repo and retry")

        with patch("git_history_sanitize.engine.filter_paths", side_effect=fail_filter_paths):
            status, stdout, stderr = self.run_rewrite()

        self.assertIsNotNone(staging_root)
        assert staging_root is not None
        self.assertEqual(
            stderr,
            "error: Path filtering failed; check git-filter-repo and retry\n",
        )
        self.assert_atomic_failure(status, stdout, stderr, staging_root)

    def test_post_rewrite_verification_failure_discards_partial_bare_output(self) -> None:
        staged_bare: Path | None = None

        def fail_verify(repository: object, _policy: object) -> None:
            nonlocal staged_bare
            staged_bare = Path(repository)
            self.assertEqual(staged_bare.name, "sanitized.git")
            self.assertEqual(
                self.fixture.git(staged_bare, "rev-parse", "--is-bare-repository"),
                "true",
            )
            raise VerificationError("Post-rewrite verification failed; output was not published")

        with patch("git_history_sanitize.engine.verify", side_effect=fail_verify):
            status, stdout, stderr = self.run_rewrite()

        self.assertIsNotNone(staged_bare)
        assert staged_bare is not None
        self.assertEqual(
            stderr,
            "error: Post-rewrite verification failed; output was not published\n",
        )
        self.assert_atomic_failure(status, stdout, stderr, staged_bare.parent)

    def test_receipt_staging_is_private_adjacent_and_cleaned_after_verification_failure(self) -> None:
        receipt = self.fixture.receipt_dir / "receipt.json"
        commit_policy = self.fixture.write_policy(
            cutoff=None,
            cutoff_commit=self.fixture.git(self.fixture.source, "rev-parse", "HEAD"),
            excluded_paths=("private/",),
        )

        def fail_verify(
            _repository: object, _policy: object, *, source: object, receipt: Path
        ) -> None:
            self.assertEqual(receipt.parent, self.fixture.receipt_dir)
            self.assertNotEqual(receipt, self.fixture.receipt_dir / "receipt.json")
            self.assertEqual(stat.S_IMODE(receipt.stat().st_mode), 0o600)
            raise VerificationError("Post-rewrite verification failed; output was not published")

        with patch("git_history_sanitize.engine.verify", side_effect=fail_verify):
            status, stdout, stderr = self.run_rewrite(
                policy=commit_policy, receipt=receipt
            )

        self.assertEqual(status, 2)
        self.assertEqual(stdout, "")
        self.assertEqual(
            stderr,
            "error: Post-rewrite verification failed; output was not published\n",
        )
        self.assertFalse(self.output.exists())
        self.assertFalse(receipt.exists())
        self.assertEqual(list(self.fixture.receipt_dir.iterdir()), [])
        self.fixture.assert_no_staging_directories(self.output.parent)
        self.fixture.assert_source_snapshot(self.source_snapshot)

    def test_output_publication_failure_leaves_only_an_orphan_receipt(self) -> None:
        receipt = self.fixture.receipt_dir / "receipt.json"
        commit_policy = self.fixture.write_policy(
            cutoff=None,
            cutoff_commit=self.fixture.git(self.fixture.source, "rev-parse", "HEAD"),
            excluded_paths=("private/",),
        )
        calls: list[Path] = []

        def fail_output_publish(staged: Path, _destination: Path) -> None:
            calls.append(staged)
            if len(calls) == 2:
                raise SanitizeError("Atomic publication failed")
            os.replace(staged, receipt)

        with patch("git_history_sanitize.engine.publish", side_effect=fail_output_publish):
            status, stdout, stderr = self.run_rewrite(policy=commit_policy, receipt=receipt)

        self.assertEqual(status, 2)
        self.assertEqual(stdout, "")
        self.assertEqual(stderr, "error: Atomic publication failed\n")
        self.assertFalse(self.output.exists())
        self.assertTrue(receipt.is_file())
        self.assertEqual(len(calls), 2)
        self.fixture.assert_no_staging_directories(self.output.parent)
        self.fixture.assert_source_snapshot(self.source_snapshot)


if __name__ == "__main__":
    unittest.main()
