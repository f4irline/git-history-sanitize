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
        output = self.fixture.root / name
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
        self.assertIn("Unexpected refs remain", extra_ref.stderr)

        self.fixture.git(output, "branch", "-D", "unexpected-ref")
        self.fixture.add_unreachable_blob("unreachable staging secret", output)
        unreachable = self.fixture.run_cli(
            "verify", "--repository", str(output), "--policy", str(self.policy), check=False
        )
        self.assertEqual(unreachable.returncode, 2)
        self.assertIn("Unreachable objects remain after cleanup", unreachable.stderr)


if __name__ == "__main__":
    unittest.main()
