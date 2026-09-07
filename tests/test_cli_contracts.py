"""Stable human/JSON CLI success and expected-failure contracts."""

from __future__ import annotations

import json
import unittest

from tests.support.git_fixture import GitFixture


class CliContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = GitFixture(self)
        self.fixture.write("allowed.txt", "safe\n")
        self.fixture.commit("allowed", "allowed.txt")
        self.policy = self.fixture.write_policy()

    def test_plan_rewrite_and_verify_emit_parseable_json_on_success(self) -> None:
        plan = self.fixture.run_cli("plan", "--source", str(self.fixture.source / ".git"), "--policy", str(self.policy), "--json")
        output = self.fixture.output_dir / "sanitized.git"
        rewrite = self.fixture.run_cli("rewrite", "--source", str(self.fixture.source / ".git"), "--output", str(output), "--policy", str(self.policy), "--json")
        verify = self.fixture.run_cli("verify", "--repository", str(output), "--policy", str(self.policy), "--json")

        self.assertEqual(plan.stderr, "")
        self.assertEqual(set(json.loads(plan.stdout)), {"source_commits", "discarded_commits", "retained_commits_before_path_filter"})
        self.assertIn("verification", json.loads(rewrite.stdout))
        self.assertIn("root", json.loads(verify.stdout))

    def test_successful_human_output_is_concise_and_actionable(self) -> None:
        plan = self.fixture.run_cli(
            "plan", "--source", str(self.fixture.source / ".git"), "--policy", str(self.policy)
        )
        output = self.fixture.output_dir / "sanitized.git"
        rewrite = self.fixture.run_cli(
            "rewrite", "--source", str(self.fixture.source / ".git"), "--output", str(output),
            "--policy", str(self.policy)
        )
        verify = self.fixture.run_cli(
            "verify", "--repository", str(output), "--policy", str(self.policy)
        )

        self.assertEqual(
            plan.stdout,
            "Source commits: 1\nPre-cutoff commits: 0\nCommits before path filtering: 1\n",
        )
        self.assertEqual(
            rewrite.stdout,
            f"Sanitized HEAD: {self.fixture.git(output, 'rev-parse', 'HEAD')}\n"
            "Commits in output: 1\n",
        )
        self.assertEqual(verify.stdout, "Verification passed.\n")
        self.assertEqual(plan.stderr + rewrite.stderr + verify.stderr, "")

    def test_expected_operational_failures_use_exit_two_and_actionable_stderr(self) -> None:
        failed = self.fixture.run_cli("rewrite", "--source", str(self.fixture.source / ".git"), "--output", str(self.fixture.output_dir / "exists.git"), "--policy", str(self.fixture.root / "missing.yml"), check=False)

        self.assertEqual(failed.returncode, 2)
        self.assertEqual(failed.stdout, "")
        self.assertIn("Cannot read policy file", failed.stderr)

    def test_receipt_arguments_have_stable_policy_conditional_failures(self) -> None:
        commit_policy = self.fixture.write_policy(
            cutoff=None,
            cutoff_commit=self.fixture.git(self.fixture.source, "rev-parse", "HEAD"),
        )
        missing_human = self.fixture.run_cli("verify", "--repository", str(self.fixture.source / ".git"), "--policy", str(commit_policy), check=False)
        missing_json = self.fixture.run_cli("verify", "--repository", str(self.fixture.source / ".git"), "--policy", str(commit_policy), "--json", check=False)
        timestamp = self.fixture.write_policy()
        forbidden = self.fixture.run_cli("verify", "--repository", str(self.fixture.source / ".git"), "--policy", str(timestamp), "--receipt", str(self.fixture.receipt_dir / "unused.json"), check=False)

        for result in (missing_human, missing_json):
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "error: cutoffCommit verification requires --receipt and --source\n")
        self.assertEqual(forbidden.returncode, 2)
        self.assertEqual(forbidden.stdout, "")
        self.assertEqual(forbidden.stderr, "error: history.cutoff does not accept --receipt or --source\n")

    def test_verify_contract_failures_have_redacted_human_and_json_diagnostics(self) -> None:
        output = self.fixture.output_dir / "sanitized.git"
        self.fixture.run_cli(
            "rewrite", "--source", str(self.fixture.source / ".git"), "--output", str(output),
            "--policy", str(self.policy),
        )
        self.fixture.git(output, "tag", "private-marker")

        human = self.fixture.run_cli(
            "verify", "--repository", str(output), "--policy", str(self.policy), check=False,
        )
        structured = self.fixture.run_cli(
            "verify", "--repository", str(output), "--policy", str(self.policy), "--json",
            check=False,
        )

        self.assertEqual(human.returncode, 2)
        self.assertEqual(human.stdout, "")
        self.assertEqual(human.stderr, "error: verification failed: refs.retained\n")
        self.assertNotIn("private-marker", human.stderr)
        self.assertEqual(structured.returncode, 2)
        self.assertEqual(structured.stdout, "")
        self.assertEqual(
            structured.stderr,
            '{"code": "verification_failed", "invariant": "refs.retained"}\n',
        )


if __name__ == "__main__":
    unittest.main()
