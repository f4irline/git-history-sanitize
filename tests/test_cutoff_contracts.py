"""Focused plan/rewrite cutoff contracts using the hermetic Git fixture.

Future consumer contracts:

* After BBQ-8 lands, retain valid, missing, malformed, mismatched, and tampered
  cutoffCommit proof cases, including exact human and JSON diagnostics.
* After BBQ-12 lands, retain plan/rewrite parity for every deterministic source
  and policy rejection, plus equal source and boundary counts on success.
"""

from __future__ import annotations

import json
import unittest

from tests.support.git_fixture import GitFixture


class CutoffContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = GitFixture(self)
        self.source = self.fixture.source

    def _plan(self, policy: object, *, check: bool = True) -> object:
        return self.fixture.run_cli(
            "plan", "--source", str(self.source / ".git"), "--policy", str(policy), "--json", check=check
        )

    def _rewrite(self, policy: object, output: object, *, receipt: object | None = None, check: bool = True) -> object:
        arguments = [
            "rewrite", "--source", str(self.source / ".git"), "--policy", str(policy),
            "--output", str(output), "--json",
        ]
        if receipt is not None:
            arguments.extend(("--receipt", str(receipt)))
        return self.fixture.run_cli(*arguments, check=check)

    def test_timestamp_cutoff_is_inclusive_and_plan_matches_rewrite(self) -> None:
        self.fixture.write("old.txt", "old\n")
        self.fixture.commit("old", "old.txt", timestamp="2026-09-02T23:59:59+00:00")
        self.fixture.write("boundary.txt", "retained\n")
        self.fixture.commit("boundary", "boundary.txt", timestamp="2026-09-03T00:00:00+00:00")
        policy = self.fixture.write_policy()

        plan = json.loads(self._plan(policy).stdout)
        output = self.fixture.output_dir / "sanitized.git"
        rewrite = json.loads(self._rewrite(policy, output).stdout)

        self.assertEqual(plan, {
            "source_commits": 2,
            "discarded_commits": 1,
            "retained_commits_before_path_filter": 1,
        })
        self.assertEqual(rewrite["history"], {"source_commits": 2, "discarded_commits": 1})
        self.assertEqual(self.fixture.git(output, "show", "HEAD:boundary.txt"), "retained")

    def test_reachable_cutoff_commit_selects_the_same_boundary_for_plan_and_rewrite(self) -> None:
        self.fixture.write("old.txt", "old\n")
        self.fixture.commit("old", "old.txt", timestamp="2026-09-02T23:59:59+00:00")
        self.fixture.write("boundary.txt", "boundary\n")
        boundary = self.fixture.commit("boundary", "boundary.txt")
        self.fixture.write("retained.txt", "retained\n")
        self.fixture.commit("retained", "retained.txt")
        policy = self.fixture.write_policy(cutoff=None, cutoff_commit=boundary)

        plan = json.loads(self._plan(policy).stdout)
        output = self.fixture.output_dir / "sanitized.git"
        receipt = self.fixture.receipt_dir / "receipt.json"
        rewrite = json.loads(self._rewrite(policy, output, receipt=receipt).stdout)

        self.assertEqual(plan, {
            "source_commits": 3,
            "discarded_commits": 1,
            "retained_commits_before_path_filter": 2,
        })
        self.assertEqual(rewrite["history"], {
            "source_commits": plan["source_commits"],
            "discarded_commits": plan["discarded_commits"],
        })
        self.assertEqual(self.fixture.git(output, "show", "HEAD^:boundary.txt"), "boundary")
        self.assertEqual(self.fixture.git(output, "show", "HEAD:retained.txt"), "retained")
        verified = self.fixture.run_cli("verify", "--repository", str(output), "--policy", str(policy), "--source", str(self.source / ".git"), "--receipt", str(receipt))
        self.assertEqual(verified.stderr, "")

    def test_commit_cutoff_requires_a_full_receipt_and_full_lowercase_oid(self) -> None:
        self.fixture.write("boundary.txt", "boundary\n")
        boundary = self.fixture.commit("boundary", "boundary.txt")
        policy = self.fixture.write_policy(cutoff=None, cutoff_commit=boundary[:12])
        output = self.fixture.output_dir / "missing.git"

        planned = self._plan(policy, check=False)
        rewritten = self._rewrite(policy, output, check=False)

        self.assertEqual(planned.returncode, 2)
        self.assertEqual(rewritten.returncode, 2)
        self.assertEqual(rewritten.stdout, "")
        self.assertEqual(rewritten.stderr, "error: cutoffCommit rewrite requires --receipt\n")
        self.assertFalse(output.exists())

    def test_annotated_tag_oid_is_not_a_commit_cutoff(self) -> None:
        self.fixture.write("boundary.txt", "boundary\n")
        self.fixture.commit("boundary", "boundary.txt")
        tag = self.fixture.tag("boundary", "boundary tag")
        tag_oid = self.fixture.git(self.source, "rev-parse", "boundary")
        self.assertNotEqual(tag, tag_oid)
        policy = self.fixture.write_policy(cutoff=None, cutoff_commit=tag_oid)

        result = self._plan(policy, check=False)

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "error: history.cutoffCommit must resolve to a commit\n")

    def test_no_timestamp_retained_commit_fails_without_publishing_output(self) -> None:
        self.fixture.write("old.txt", "old\n")
        self.fixture.commit("old", "old.txt", timestamp="2026-09-02T23:59:59+00:00")
        policy = self.fixture.write_policy()
        output = self.fixture.output_dir / "must-not-exist.git"

        planned = self._plan(policy, check=False)
        rewritten = self._rewrite(policy, output, check=False)

        self.assertEqual(planned.returncode, 2)
        self.assertIn("No retained commit", planned.stderr)
        self.assertEqual(rewritten.returncode, 2)
        self.assertIn("No retained commit", rewritten.stderr)
        self.assertFalse(output.exists())

if __name__ == "__main__":
    unittest.main()
