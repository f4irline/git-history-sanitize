"""Security regressions and owner-ticket contracts."""

import json
import unittest

from tests.support.git_fixture import GitFixture


class SecurityRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = GitFixture(self)
        self.policy = self.fixture.root / "policy.yml"
        self.policy.write_text(
            """\
version: 1
history:
  cutoff: "2026-09-03T00:00:00+00:00"
  prefixMessage: "[sanitized]"
paths:
  exclude:
    - private/
commits:
  mixedMessage: "[sanitized]"
refs:
  keep:
    - HEAD
"""
        )
        self.fixture.write("private/secret.txt", "staging secret\n")
        self.fixture.commit(
            "Old secret", "private/secret.txt", timestamp="2026-09-02T12:00:00+00:00"
        )
        self.fixture.write("allowed.txt", "safe\n")
        self.fixture.commit("Allowed", "allowed.txt")

    def rewrite(self, name: str) -> tuple[object, object]:
        output = self.fixture.output_dir / name
        result = self.fixture.run_cli(
            "rewrite",
            "--source",
            str(self.fixture.source / ".git"),
            "--output",
            str(output),
            "--policy",
            str(self.policy),
            "--json",
        )
        return output, json.loads(result.stdout)

    def test_rewrite_removes_unreachable_staging_objects_and_is_repeatable(self) -> None:
        first, first_report = self.rewrite("first.git")
        second, second_report = self.rewrite("second.git")

        self.assertEqual(
            self.fixture.git(first, "fsck", "--full", "--unreachable", "--no-reflogs"), ""
        )
        self.assertEqual(self.fixture.snapshot_output(first), self.fixture.snapshot_output(second))
        self.assertEqual(first_report, second_report)

    def test_verifier_rejects_unexpected_ref_and_unreachable_object(self) -> None:
        output, _ = self.rewrite("sanitized.git")
        self.fixture.branch("source-side-branch")
        self.fixture.git(output, "branch", "unexpected-ref")

        extra_ref = self.fixture.run_cli(
            "verify", "--repository", str(output), "--policy", str(self.policy), check=False
        )
        self.assertEqual(extra_ref.returncode, 2)
        self.assertEqual(extra_ref.stderr, "error: verification failed: refs.retained\n")

        self.fixture.git(output, "update-ref", "-d", "refs/heads/unexpected-ref")
        self.fixture.add_unreachable_blob("unreachable staging secret", output)
        unreachable = self.fixture.run_cli(
            "verify", "--repository", str(output), "--policy", str(self.policy), check=False
        )
        self.assertEqual(unreachable.returncode, 2)
        self.assertEqual(unreachable.stderr, "error: verification failed: objects.reachable-only\n")


class AllExcludedRootRegressionTests(unittest.TestCase):
    """BBQ-11: a non-empty source may sanitize to an empty tree."""

    def _rewrite(self, fixture: GitFixture, policy: object, name: str) -> object:
        output = fixture.output_dir / name
        result = fixture.run_cli(
            "rewrite",
            "--source",
            str(fixture.source / ".git"),
            "--output",
            str(output),
            "--policy",
            str(policy),
            "--json",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        return output

    def _assert_empty_root(
        self, fixture: GitFixture, output: object, *, message: str, timestamp: str, excluded: tuple[str, ...]
    ) -> None:
        self.assertEqual(fixture.git(output, "rev-list", "--count", "HEAD"), "1")
        root = fixture.git(output, "rev-parse", "HEAD")
        self.assertEqual(fixture.git(output, "show", "-s", "--format=%P", root), "")
        self.assertEqual(fixture.git(output, "show", "-s", "--format=%B", root), message)
        self.assertEqual(fixture.git(output, "rev-parse", "HEAD^{tree}"), fixture.git(output, "mktree"))
        self.assertEqual(fixture.git(output, "symbolic-ref", "HEAD"), "refs/heads/main")
        self.assertEqual(fixture.git(output, "for-each-ref", "--format=%(refname)"), "refs/heads/main")
        self.assertEqual(
            fixture.git(output, "show", "-s", "--format=%an%x00%ae%x00%cn%x00%ce%x00%aI%x00%cI", root),
            "Fixture\x00fixture@example.invalid\x00Fixture\x00fixture@example.invalid"
            f"\x00{timestamp}\x00{timestamp}",
        )
        self.assertEqual(fixture.git(output, "fsck", "--full", "--unreachable", "--no-reflogs"), "")
        self.assertFalse((output / "filter-repo").exists())
        self.assertFalse((output / "logs").exists())
        self.assertFalse((output / "refs" / "original").exists())
        verified = fixture.run_cli(
            "verify", "--repository", str(output), "--policy", str(fixture.root / "policy.yml")
        )
        self.assertEqual(verified.returncode, 0)
        self.assertEqual(verified.stderr, "")
        self.assertEqual(fixture.git(output, "ls-tree", "-r", "--name-only", "HEAD"), "")
        for blob in excluded:
            self.assertNotIn(blob, fixture.all_objects(output))

    def _assert_plan_is_empty(self, fixture: GitFixture, policy: object) -> None:
        plan = fixture.run_cli(
            "plan", "--source", str(fixture.source / ".git"), "--policy", str(policy), "--json"
        )
        self.assertEqual(plan.stderr, "")
        self.assertEqual(json.loads(plan.stdout)["retained_head_path_count"], 0)
        human = fixture.run_cli("plan", "--source", str(fixture.source / ".git"), "--policy", str(policy))
        self.assertIn("Retained HEAD paths: 0\n", human.stdout)
        self.assertEqual(human.stderr, "")

    def test_single_sensitive_root_becomes_a_deterministic_empty_root(self) -> None:
        fixture = GitFixture(self)
        fixture.write("private/secret.txt", "secret\n")
        fixture.commit("sensitive root", "private/secret.txt", timestamp="2026-09-03T01:00:00+00:00")
        secret = fixture.git(fixture.source, "rev-parse", "HEAD:private/secret.txt")
        policy = fixture.write_policy(excluded_paths=("private/",), prefix_message="empty root")

        self._assert_plan_is_empty(fixture, policy)
        first = self._rewrite(fixture, policy, "first.git")
        second = self._rewrite(fixture, policy, "second.git")

        self._assert_empty_root(
            fixture, first, message="empty root", timestamp="2026-09-03T01:00:00Z", excluded=(secret,)
        )
        self.assertEqual(fixture.snapshot_output(first), fixture.snapshot_output(second))

    def test_multiple_sensitive_only_commits_become_one_empty_root(self) -> None:
        fixture = GitFixture(self)
        fixture.write("private/secret.txt", "first secret\n")
        fixture.commit("sensitive root", "private/secret.txt", timestamp="2026-09-03T01:00:00+00:00")
        first_secret = fixture.git(fixture.source, "rev-parse", "HEAD:private/secret.txt")
        fixture.write("private/secret.txt", "second secret\n")
        fixture.commit("sensitive update", "private/secret.txt", timestamp="2026-09-03T02:00:00+00:00")
        second_secret = fixture.git(fixture.source, "rev-parse", "HEAD:private/secret.txt")
        policy = fixture.write_policy(excluded_paths=("private/",), prefix_message="empty root")

        self._assert_plan_is_empty(fixture, policy)
        output = self._rewrite(fixture, policy, "sanitized.git")

        self._assert_empty_root(
            fixture,
            output,
            message="empty root",
            timestamp="2026-09-03T01:00:00Z",
            excluded=(first_secret, second_secret),
        )

    def test_mixed_source_with_an_all_excluded_retained_history_becomes_empty(self) -> None:
        fixture = GitFixture(self)
        fixture.write("allowed.txt", "old safe content\n")
        fixture.write("private/old.txt", "old secret\n")
        fixture.commit("old mixed", "allowed.txt", "private/old.txt", timestamp="2026-09-02T23:00:00+00:00")
        fixture.write("private/secret.txt", "retained secret\n")
        fixture.git(fixture.source, "rm", "allowed.txt")
        fixture.git(
            fixture.source,
            "add",
            "private/secret.txt",
            env={"GIT_AUTHOR_DATE": "2026-09-03T01:00:00+00:00", "GIT_COMMITTER_DATE": "2026-09-03T01:00:00+00:00"},
        )
        fixture.git(
            fixture.source,
            "commit",
            "-qm",
            "retained mixed removal",
            env={"GIT_AUTHOR_DATE": "2026-09-03T01:00:00+00:00", "GIT_COMMITTER_DATE": "2026-09-03T01:00:00+00:00"},
        )
        retained_secret = fixture.git(fixture.source, "rev-parse", "HEAD:private/secret.txt")
        policy = fixture.write_policy(excluded_paths=("private/",), prefix_message="empty root")

        self._assert_plan_is_empty(fixture, policy)
        output = self._rewrite(fixture, policy, "sanitized.git")

        self._assert_empty_root(
            fixture,
            output,
            message="empty root",
            timestamp="2026-09-03T01:00:00Z",
            excluded=(retained_secret,),
        )


if __name__ == "__main__":
    unittest.main()
