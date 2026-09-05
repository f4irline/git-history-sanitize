"""Focused plan/rewrite cutoff contracts using the hermetic Git fixture."""

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

    def _rewrite(self, policy: object, output: object, *, check: bool = True) -> object:
        return self.fixture.run_cli(
            "rewrite", "--source", str(self.source / ".git"), "--policy", str(policy),
            "--output", str(output), "--json", check=check
        )

    def test_timestamp_cutoff_is_inclusive_and_plan_matches_rewrite(self) -> None:
        self.fixture.write("old.txt", "old\n")
        self.fixture.commit("old", "old.txt", timestamp="2026-09-02T23:59:59+00:00")
        self.fixture.write("boundary.txt", "retained\n")
        self.fixture.commit("boundary", "boundary.txt", timestamp="2026-09-03T00:00:00+00:00")
        policy = self.fixture.write_policy()

        plan = json.loads(self._plan(policy).stdout)
        output = self.fixture.root / "sanitized.git"
        rewrite = json.loads(self._rewrite(policy, output).stdout)

        self.assertEqual(plan, {
            "source_commits": 2,
            "discarded_commits": 1,
            "retained_commits_before_path_filter": 1,
        })
        self.assertEqual(rewrite["history"], {"source_commits": 2, "discarded_commits": 1})
        self.assertEqual(self.fixture.git(output, "show", "HEAD:boundary.txt"), "retained")

    def test_no_timestamp_retained_commit_fails_without_publishing_output(self) -> None:
        self.fixture.write("old.txt", "old\n")
        self.fixture.commit("old", "old.txt", timestamp="2026-09-02T23:59:59+00:00")
        policy = self.fixture.write_policy()
        output = self.fixture.root / "must-not-exist.git"

        planned = self._plan(policy, check=False)
        rewritten = self._rewrite(policy, output, check=False)

        self.assertEqual(planned.returncode, 2)
        self.assertIn("No retained commit", planned.stderr)
        self.assertEqual(rewritten.returncode, 2)
        self.assertIn("No retained commit", rewritten.stderr)
        self.assertFalse(output.exists())

    def test_plan_and_rewrite_reject_timestamp_recrossing_identically(self) -> None:
        self.fixture.write("one.txt", "one\n")
        self.fixture.commit("before", "one.txt", timestamp="2026-09-02T23:00:00+00:00")
        self.fixture.write("two.txt", "two\n")
        self.fixture.commit("after", "two.txt", timestamp="2026-09-03T01:00:00+00:00")
        self.fixture.write("three.txt", "three\n")
        self.fixture.commit("recross", "three.txt", timestamp="2026-09-02T23:30:00+00:00")
        policy = self.fixture.write_policy()
        output = self.fixture.root / "must-not-exist.git"

        planned = self._plan(policy, check=False)
        rewritten = self._rewrite(policy, output, check=False)

        self.assertEqual(planned.returncode, 2)
        self.assertEqual(rewritten.returncode, 2)
        self.assertIn("cross the cutoff", planned.stderr)
        self.assertIn("cross the cutoff", rewritten.stderr)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
