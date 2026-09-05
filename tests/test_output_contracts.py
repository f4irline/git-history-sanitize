"""CLI reports must not disclose source-only sensitive values."""

from __future__ import annotations

import unittest

from tests.support.git_fixture import GitFixture


class OutputContractTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
