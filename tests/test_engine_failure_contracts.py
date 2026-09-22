"""Source-only failure injection for late rewrite atomicity."""

from __future__ import annotations

import io
import os
import stat
import signal
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from git_history_sanitize.cli import main
from git_history_sanitize.engine import _destination
from git_history_sanitize.errors import InterruptionError, SanitizeError, VerificationError
from git_history_sanitize.workspace import clean_workspace, list_workspaces
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
            "error: sanitization failed\n",
        )
        self.assert_atomic_failure(status, stdout, stderr, staging_root)

    def test_interruption_retains_private_owned_workspace_with_redacted_recovery(self) -> None:
        staging_root: Path | None = None

        def interrupt(repository: object, _policy: object) -> None:
            nonlocal staging_root
            staging_root = repository.path.parent  # type: ignore[attr-defined]
            self.assertEqual(stat.S_IMODE(staging_root.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE((staging_root / "ownership.json").stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE((staging_root / "lock").stat().st_mode), 0o600)
            raise InterruptionError(signal.SIGTERM)

        with patch("git_history_sanitize.engine.filter_paths", side_effect=interrupt):
            status, stdout, stderr = self.run_rewrite()

        self.assertEqual(status, 143)
        self.assertEqual(stdout, "")
        self.assertEqual(
            stderr,
            "error: sanitization interrupted: List sanitizer workspaces under the output parent "
            "and clean the stale ID before retrying.\n",
        )
        self.assertIsNotNone(staging_root)
        assert staging_root is not None
        self.assertTrue(staging_root.is_dir())
        records = list_workspaces(self.output.parent)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].state, "interrupted")
        self.assertNotIn(str(staging_root), stderr)
        self.assertFalse(self.output.exists())
        self.fixture.assert_source_snapshot(self.source_snapshot)

        clean_workspace(self.output.parent, records[0].id)
        self.assertFalse(staging_root.exists())

    def test_staged_sync_failure_is_atomic_and_reports_an_actionable_error(self) -> None:
        with (
            patch("git_history_sanitize.engine.verify", return_value=object()),
            patch(
                "git_history_sanitize.engine.sync_staged_tree",
                side_effect=SanitizeError("Staged output synchronization failed before publication"),
            ),
        ):
            status, stdout, stderr = self.run_rewrite()

        self.assertEqual(
            stderr,
            "error: sanitization failed\n",
        )
        self.assert_atomic_failure(status, stdout, stderr, self.output.parent / ".unused")

    def test_output_and_receipt_modes_ignore_a_permissive_umask(self) -> None:
        fixture = GitFixture(self)
        fixture.write("allowed.txt", "safe\n")
        cutoff = fixture.commit("allowed", "allowed.txt")
        policy = fixture.write_policy(cutoff=None, cutoff_commit=cutoff)
        output = fixture.output_dir / "sanitized.git"
        receipt = fixture.receipt_dir / "receipt.json"
        previous_umask = os.umask(0)
        try:
            result = fixture.run_cli(
                "rewrite",
                "--source",
                str(fixture.source / ".git"),
                "--output",
                str(output),
                "--policy",
                str(policy),
                "--receipt",
                str(receipt),
            )
        finally:
            os.umask(previous_umask)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(receipt.stat().st_mode), 0o600)

    def test_existing_destination_types_are_rejected_without_following_symlinks(self) -> None:
        protected: tuple[Path, ...] = ()
        entries = {
            "file": lambda path: path.write_text("existing"),
            "empty-directory": lambda path: path.mkdir(),
            "nonempty-directory": lambda path: (path.mkdir(), (path / "child").write_text("existing")),
            "symlink": lambda path: path.symlink_to(self.fixture.root / "missing-target"),
        }

        for name, create in entries.items():
            with self.subTest(name=name):
                destination = self.fixture.output_dir / name
                create(destination)
                with self.assertRaisesRegex(SanitizeError, "Output path"):
                    _destination(destination, protected, "Output")

    def test_competing_cli_rewrites_publish_one_verified_output(self) -> None:
        fixture = GitFixture(self)
        fixture.write("allowed.txt", "safe\n")
        fixture.commit("allowed", "allowed.txt")
        policy = fixture.write_policy()
        output = fixture.output_dir / "concurrent.git"
        source_snapshot = fixture.snapshot_source()
        start = threading.Barrier(2)
        results: list[object] = []

        def rewrite() -> None:
            start.wait()
            results.append(
                self.fixture.run_cli(
                    "rewrite",
                    "--source",
                    str(fixture.source / ".git"),
                    "--output",
                    str(output),
                    "--policy",
                    str(policy),
                    check=False,
                )
            )

        threads = [threading.Thread(target=rewrite) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        successful = [result for result in results if result.returncode == 0]  # type: ignore[attr-defined]
        failed = [result for result in results if result.returncode == 2]  # type: ignore[attr-defined]
        self.assertEqual(len(successful), 1)
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0].stdout, "")
        self.assertEqual(failed[0].stderr, "error: sanitized output publication failed\n")
        fixture.assert_redacted(failed[0].stderr, str(fixture.root))
        self.assertEqual(fixture.git(output, "rev-parse", "--is-bare-repository"), "true")
        fixture.assert_no_staging_directories(output.parent)
        fixture.assert_source_snapshot(source_snapshot)

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
            "error: verification failed\n",
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
            self.assertEqual(receipt.parent.parent, self.fixture.receipt_dir)
            self.assertTrue(receipt.parent.name.startswith(".git-history-sanitize-"))
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
            "error: verification failed\n",
        )
        self.assertFalse(self.output.exists())
        self.assertFalse(receipt.exists())
        self.assertEqual(list(self.fixture.receipt_dir.iterdir()), [])
        self.fixture.assert_no_staging_directories(self.output.parent)
        self.fixture.assert_source_snapshot(self.source_snapshot)

    def test_receipt_interruption_retains_matching_owned_workspaces_on_both_filesystems(self) -> None:
        receipt = self.fixture.receipt_dir / "receipt.json"
        commit_policy = self.fixture.write_policy(
            cutoff=None,
            cutoff_commit=self.fixture.git(self.fixture.source, "rev-parse", "HEAD"),
            excluded_paths=("private/",),
        )

        with patch(
            "git_history_sanitize.engine.verify",
            side_effect=InterruptionError(signal.SIGINT),
        ):
            status, stdout, stderr = self.run_rewrite(policy=commit_policy, receipt=receipt)

        output_records = list_workspaces(self.output.parent)
        receipt_records = list_workspaces(receipt.parent)
        self.assertEqual(status, 130)
        self.assertEqual(stdout, "")
        self.assertIn("sanitization interrupted", stderr)
        self.assertEqual(len(output_records), 1)
        self.assertEqual(len(receipt_records), 1)
        self.assertEqual(output_records[0].id, receipt_records[0].id)
        self.assertEqual(output_records[0].state, "interrupted")
        self.assertEqual(receipt_records[0].state, "interrupted")
        self.assertEqual(receipt_records[0].role, "receipt")
        self.assertFalse(self.output.exists())
        self.assertFalse(receipt.exists())

        clean_workspace(self.output.parent, output_records[0].id)
        clean_workspace(receipt.parent, receipt_records[0].id)
        self.assertEqual(list(self.output.parent.iterdir()), [])
        self.assertEqual(list(receipt.parent.iterdir()), [])

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
        self.assertEqual(stderr, "error: sanitization failed\n")
        self.assertFalse(self.output.exists())
        self.assertTrue(receipt.is_file())
        self.assertEqual(len(calls), 2)
        self.fixture.assert_no_staging_directories(self.output.parent)
        self.fixture.assert_source_snapshot(self.source_snapshot)

    def test_post_publication_durability_failure_keeps_complete_output(self) -> None:
        def fail_output_parent_sync(path: Path) -> bool:
            if path == self.output.parent:
                raise SanitizeError(
                    "Output was published but parent-directory durability could not be confirmed"
                )
            return True

        with (
            patch("git_history_sanitize.engine.verify", return_value=object()),
            patch("git_history_sanitize.engine.sync_published_parent", side_effect=fail_output_parent_sync),
        ):
            status, stdout, stderr = self.run_rewrite()

        self.assertEqual(status, 2)
        self.assertEqual(stdout, "")
        self.assertEqual(
            stderr,
            "error: sanitization failed\n",
        )
        self.assertTrue(self.output.is_dir())
        self.assertEqual(self.fixture.git(self.output, "rev-parse", "--is-bare-repository"), "true")
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o700)
        self.fixture.assert_no_staging_directories(self.output.parent)
        self.fixture.assert_source_snapshot(self.source_snapshot)

    def test_receipt_durability_failure_does_not_claim_output_was_published(self) -> None:
        receipt = self.fixture.receipt_dir / "receipt.json"
        commit_policy = self.fixture.write_policy(
            cutoff=None,
            cutoff_commit=self.fixture.git(self.fixture.source, "rev-parse", "HEAD"),
            excluded_paths=("private/",),
        )

        def fail_receipt_parent_sync(path: Path, failure: str) -> bool:
            self.assertEqual(path, receipt.parent)
            self.assertEqual(
                failure,
                "Receipt was published but output was not; "
                "parent-directory durability could not be confirmed",
            )
            raise SanitizeError(
                "Receipt was published but output was not; "
                "parent-directory durability could not be confirmed"
            )

        with (
            patch("git_history_sanitize.engine.verify", return_value=object()),
            patch("git_history_sanitize.engine.sync_published_parent", side_effect=fail_receipt_parent_sync),
        ):
            status, stdout, stderr = self.run_rewrite(policy=commit_policy, receipt=receipt)

        self.assertEqual(status, 2)
        self.assertEqual(stdout, "")
        self.assertEqual(
            stderr,
            "error: sanitization failed\n",
        )
        self.assertTrue(receipt.is_file())
        self.assertFalse(self.output.exists())
        self.fixture.assert_no_staging_directories(self.output.parent)


if __name__ == "__main__":
    unittest.main()
