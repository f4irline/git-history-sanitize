"""CLI reports must not disclose source-only sensitive values."""

from __future__ import annotations

import unittest

from tests.support.git_fixture import GitFixture


class OutputContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = GitFixture(self)
        self.fixture.write("allowed.txt", "safe\n")
        self.fixture.commit("allowed", "allowed.txt")
        self.policy = self.fixture.write_policy()

    def rewrite(self, name: str) -> object:
        output = self.fixture.root / name
        self.fixture.run_cli(
            "rewrite",
            "--source",
            str(self.fixture.source / ".git"),
            "--output",
            str(output),
            "--policy",
            str(self.policy),
        )
        return output

    def test_successful_reports_omit_removed_source_content_and_messages(self) -> None:
        fixture = GitFixture(self)
        secret = "customer-secret-value"
        old_message = "old customer implementation"
        fixture.write("private/secret.txt", secret)
        old_commit = fixture.commit(
            old_message, "private/secret.txt", timestamp="2026-09-02T12:00:00+00:00"
        )
        fixture.write("allowed.txt", "safe\n")
        fixture.commit("retained implementation", "allowed.txt")
        policy = fixture.write_policy(excluded_paths=("private/",))
        output = fixture.root / "sanitized.git"

        plan = fixture.run_cli(
            "plan", "--source", str(fixture.source / ".git"), "--policy", str(policy), "--json"
        )
        rewrite = fixture.run_cli(
            "rewrite", "--source", str(fixture.source / ".git"), "--output", str(output),
            "--policy", str(policy), "--json"
        )
        verify = fixture.run_cli(
            "verify", "--repository", str(output), "--policy", str(policy), "--json"
        )

        for result in (plan, rewrite, verify):
            fixture.assert_redacted(result.stdout + result.stderr, secret, old_message, old_commit)

    def test_output_is_bare_and_has_no_cleanup_artifacts(self) -> None:
        output = self.rewrite("sanitized.git")

        self.assertEqual(self.fixture.git(output, "rev-parse", "--is-bare-repository"), "true")
        self.assertEqual(self.fixture.git(output, "remote"), "")
        self.assertFalse((output / "logs").exists())
        self.assertFalse((output / "refs" / "original").exists())
        self.assertFalse((output / "filter-repo").exists())
        self.assertEqual(
            self.fixture.git(output, "fsck", "--full", "--unreachable", "--no-reflogs"), ""
        )

    def test_failed_rewrite_is_atomic_and_cleans_staging(self) -> None:
        base = self.fixture.git(self.fixture.source, "rev-parse", "HEAD")
        side = self.fixture.commit_tree(self.fixture.source, "HEAD^{tree}", "side", base)
        self.fixture.write("main.txt", "main\n")
        main = self.fixture.commit("main", "main.txt")
        merge = self.fixture.commit_tree(
            self.fixture.source, "HEAD^{tree}", "merge history", main, side
        )
        self.fixture.git(self.fixture.source, "update-ref", "refs/heads/main", merge)
        source_snapshot = self.fixture.snapshot_source()
        output = self.fixture.root / "sanitized.git"

        failed = self.fixture.run_cli(
            "rewrite",
            "--source",
            str(self.fixture.source / ".git"),
            "--output",
            str(output),
            "--policy",
            str(self.policy),
            check=False,
        )

        self.assertEqual(failed.returncode, 2)
        self.assertIn("linear retained HEAD history", failed.stderr)
        self.assertFalse(output.exists())
        self.fixture.assert_no_staging_directories(self.fixture.root)
        self.fixture.assert_source_snapshot(source_snapshot)

    def test_re_sanitizing_a_bare_output_is_deterministic_and_non_mutating(self) -> None:
        first = self.rewrite("first.git")
        first_snapshot = self.fixture.snapshot_output(first)
        second = self.fixture.root / "second.git"

        self.fixture.run_cli(
            "rewrite",
            "--source",
            str(first),
            "--output",
            str(second),
            "--policy",
            str(self.policy),
        )

        self.fixture.assert_output_snapshot(first, first_snapshot)
        self.assertEqual(self.fixture.snapshot_output(second), first_snapshot)


if __name__ == "__main__":
    unittest.main()
