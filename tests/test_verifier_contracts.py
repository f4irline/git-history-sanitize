"""Independent verifier contracts against deliberately tampered output."""

from __future__ import annotations

import unittest

from tests.support.git_fixture import GitFixture


class VerifierContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = GitFixture(self)
        self.fixture.write("allowed.txt", "safe\n")
        self.fixture.commit("allowed", "allowed.txt")
        self.fixture.write("private/secret.txt", "secret\n")
        self.source_tip = self.fixture.commit("mixed", "private/secret.txt")
        self.policy = self.fixture.write_policy(excluded_paths=("private/",))

    def rewrite(self, name: str = "sanitized.git") -> object:
        output = self.fixture.root / name
        self.fixture.run_cli(
            "rewrite", "--source", str(self.fixture.source / ".git"), "--output", str(output),
            "--policy", str(self.policy)
        )
        return output

    def verify(self, output: object) -> object:
        return self.fixture.run_cli(
            "verify", "--repository", str(output), "--policy", str(self.policy), check=False
        )

    def test_rejects_a_reachable_pre_cutoff_commit(self) -> None:
        old = self.fixture.commit_tree(
            self.fixture.source,
            "HEAD^{tree}",
            "old",
            timestamp="2026-09-02T12:00:00+00:00",
        )
        output = self.rewrite()
        self.fixture.git(output, "fetch", str(self.fixture.source / ".git"), old)
        self.fixture.git(output, "update-ref", "refs/heads/main", old)

        result = self.verify(output)

        self.assertEqual(result.returncode, 2)
        self.assertIn("predates history.cutoff", result.stderr)

    def test_rejects_a_tampered_synthetic_root_message(self) -> None:
        output = self.rewrite()
        tampered_root = self.fixture.commit_tree(output, "HEAD^{tree}", "tampered root")
        self.fixture.git(output, "update-ref", "refs/heads/main", tampered_root)

        result = self.verify(output)

        self.assertEqual(result.returncode, 2)
        self.assertIn("Synthetic root", result.stderr)

    def test_rejects_a_configured_path_reintroduced_after_rewrite(self) -> None:
        output = self.rewrite()
        clean_head = self.fixture.git(output, "rev-parse", "HEAD")
        self.fixture.git(output, "fetch", str(self.fixture.source / ".git"), self.source_tip)
        tampered_head = self.fixture.commit_tree(
            output, f"{self.source_tip}^{{tree}}", "safe append", clean_head
        )
        self.fixture.git(output, "update-ref", "refs/heads/main", tampered_head)

        result = self.verify(output)

        self.assertEqual(result.returncode, 2)
        self.assertIn("configured path remains", result.stderr)

    def test_rejects_temporary_metadata_left_in_output(self) -> None:
        output = self.rewrite()
        (output / "filter-repo").mkdir()

        result = self.verify(output)

        self.assertEqual(result.returncode, 2)
        self.assertIn("Temporary Git metadata remains", result.stderr)


if __name__ == "__main__":
    unittest.main()
