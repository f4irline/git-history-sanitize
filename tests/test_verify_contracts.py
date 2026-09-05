"""Independent verifier contracts against deliberately tampered output."""

from __future__ import annotations

import shutil
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

    def test_rejects_an_unexpected_tag(self) -> None:
        output = self.rewrite()
        self.fixture.git(output, "tag", "unexpected")

        result = self.verify(output)

        self.assertEqual(result.returncode, 2)
        self.assertIn("Unexpected refs remain", result.stderr)

    def test_rejects_an_unexpected_branch_ref(self) -> None:
        output = self.rewrite()
        self.fixture.git(output, "branch", "unexpected")

        result = self.verify(output)

        self.assertEqual(result.returncode, 2)
        self.assertIn("Unexpected refs remain", result.stderr)

    def test_rejects_a_configured_remote(self) -> None:
        output = self.rewrite()
        self.fixture.git(output, "remote", "add", "origin", "https://example.invalid/source.git")

        result = self.verify(output)

        self.assertEqual(result.returncode, 2)
        self.assertIn("A remote remains", result.stderr)

    def test_rejects_an_unreachable_object(self) -> None:
        output = self.rewrite()
        self.fixture.add_unreachable_blob("unreachable tamper", output)

        result = self.verify(output)

        self.assertEqual(result.returncode, 2)
        self.assertIn("Unreachable objects remain after cleanup", result.stderr)

    def test_rejects_reflog_and_original_ref_metadata(self) -> None:
        output = self.rewrite()
        reflog = output / "logs" / "refs" / "heads"
        reflog.mkdir(parents=True)
        (reflog / "main").write_text("tampered reflog\n")

        result = self.verify(output)

        self.assertEqual(result.returncode, 2)
        self.assertIn("Temporary Git metadata remains", result.stderr)

        shutil.rmtree(output / "logs")
        (output / "refs" / "original").mkdir(parents=True)
        result = self.verify(output)

        self.assertEqual(result.returncode, 2)
        self.assertIn("Temporary Git metadata remains", result.stderr)

    def test_rejects_a_disconnected_root_in_the_reachable_graph(self) -> None:
        output = self.rewrite()
        clean_head = self.fixture.git(output, "rev-parse", "HEAD")
        disconnected_root = self.fixture.commit_tree(output, "HEAD^{tree}", "other root")
        merge = self.fixture.commit_tree(
            output, "HEAD^{tree}", "merge roots", clean_head, disconnected_root
        )
        self.fixture.git(output, "update-ref", "refs/heads/main", merge)

        result = self.verify(output)

        self.assertEqual(result.returncode, 2)
        self.assertIn("exactly one root", result.stderr)

    def test_rejects_forbidden_content_in_a_reachable_object(self) -> None:
        output = self.rewrite()
        clean_head = self.fixture.git(output, "rev-parse", "HEAD")
        tree = self.fixture.tree_with_file(output, "allowed.txt", "reachable secret\n")
        tampered_head = self.fixture.commit_tree(output, tree, "safe append", clean_head)
        self.fixture.git(output, "update-ref", "refs/heads/main", tampered_head)

        result = self.fixture.run_cli(
            "verify",
            "--repository",
            str(output),
            "--policy",
            str(self.policy),
            "--forbid",
            "reachable secret",
            check=False,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("Forbidden content remains in the object database", result.stderr)


if __name__ == "__main__":
    unittest.main()
