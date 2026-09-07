"""Independent verifier contracts against deliberately tampered output."""

from __future__ import annotations

import json
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
        output = self.fixture.output_dir / name
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
        self.assertEqual(result.stderr, "error: verification failed: root.synthetic\n")

    def test_rejects_a_tampered_synthetic_root_message(self) -> None:
        output = self.rewrite()
        tampered_root = self.fixture.commit_tree(output, "HEAD^{tree}", "tampered root")
        self.fixture.git(output, "update-ref", "refs/heads/main", tampered_root)

        result = self.verify(output)

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, "error: verification failed: root.synthetic\n")

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
        self.assertEqual(result.stderr, "error: verification failed: paths.excluded\n")

    def test_rejects_temporary_metadata_left_in_output(self) -> None:
        output = self.rewrite()
        (output / "filter-repo").mkdir()

        result = self.verify(output)

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, "error: verification failed: metadata.clean\n")

    def test_rejects_an_unexpected_tag(self) -> None:
        output = self.rewrite()
        self.fixture.git(output, "tag", "unexpected")

        result = self.verify(output)

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, "error: verification failed: refs.retained\n")

    def test_rejects_an_unexpected_branch_ref(self) -> None:
        output = self.rewrite()
        self.fixture.git(output, "branch", "unexpected")

        result = self.verify(output)

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, "error: verification failed: refs.retained\n")

    def test_rejects_a_configured_remote(self) -> None:
        output = self.rewrite()
        # Preserve the inode: Colima virtiofs can cache a stale config after
        # host Git atomically replaces it between container invocations.
        with (output / "config").open("a") as config:
            config.write(
                '[remote "origin"]\n'
                '\turl = https://example.invalid/source.git\n'
                '\tfetch = +refs/heads/*:refs/remotes/origin/*\n'
            )

        result = self.verify(output)

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, "error: verification failed: remotes.absent\n")

    def test_rejects_an_unreachable_object(self) -> None:
        output = self.rewrite()
        self.fixture.add_unreachable_blob("unreachable tamper", output)

        result = self.verify(output)

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, "error: verification failed: objects.reachable-only\n")

    def test_rejects_reflog_and_original_ref_metadata(self) -> None:
        output = self.rewrite()
        reflog = output / "logs" / "refs" / "heads"
        reflog.mkdir(parents=True)
        (reflog / "main").write_text("tampered reflog\n")

        result = self.verify(output)

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, "error: verification failed: metadata.clean\n")

        shutil.rmtree(output / "logs")
        (output / "refs" / "original").mkdir(parents=True)
        result = self.verify(output)

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, "error: verification failed: metadata.clean\n")

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
        self.assertEqual(result.stderr, "error: verification failed: graph.linear\n")

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
        self.assertEqual(result.stderr, "error: verification failed: content.forbidden\n")

    def test_rejects_a_non_linear_graph_with_one_root(self) -> None:
        output = self.rewrite()
        root = self.fixture.git(output, "rev-parse", "HEAD~0")
        first = self.fixture.commit_tree(output, "HEAD^{tree}", "first", root)
        second = self.fixture.commit_tree(output, "HEAD^{tree}", "second", root)
        merge = self.fixture.commit_tree(output, "HEAD^{tree}", "merge", first, second)
        self.fixture.git(output, "update-ref", "refs/heads/main", merge)

        result = self.verify(output)

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, "error: verification failed: graph.linear\n")

    def test_rejects_a_non_branch_symbolic_head(self) -> None:
        output = self.rewrite()
        self.fixture.git(output, "update-ref", "refs/notes/main", "HEAD")
        self.fixture.git(output, "symbolic-ref", "HEAD", "refs/notes/main")

        result = self.verify(output)

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, "error: verification failed: head.symbolic\n")

    def test_accepts_a_utf8_symbolic_branch_head(self) -> None:
        self.fixture.git(self.fixture.source, "branch", "-m", "réparation")
        output = self.rewrite()

        result = self.verify(output)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")

    def test_rejects_historical_byte_path_and_preserves_file_semantics(self) -> None:
        output = self.rewrite()
        clean_head = self.fixture.git(output, "rev-parse", "HEAD")
        self.fixture.git(output, "fetch", str(self.fixture.source / ".git"), self.source_tip)
        historical = self.fixture.commit_tree(
            output, f"{self.source_tip}^{{tree}}", "safe historical", clean_head
        )
        clean_tip = self.fixture.commit_tree(output, "HEAD^{tree}", "safe tip", historical)
        self.fixture.git(output, "update-ref", "refs/heads/main", clean_tip)

        result = self.verify(output)

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, "error: verification failed: paths.excluded\n")

    def test_rejects_incomplete_repository_markers(self) -> None:
        output = self.rewrite()
        (output / "shallow").write_text("incomplete\n")

        result = self.verify(output)

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, "error: verification failed: repository.complete\n")

    def test_commit_cutoff_proof_rejects_tampering_without_source_mutation(self) -> None:
        fixture = GitFixture(self)
        fixture.write("old.txt", "old\n")
        fixture.commit("old", "old.txt", timestamp="2026-09-02T00:00:00+00:00")
        fixture.write("boundary.txt", "safe\n")
        boundary = fixture.commit("boundary", "boundary.txt")
        policy = fixture.write_policy(cutoff=None, cutoff_commit=boundary)
        output = fixture.output_dir / "commit.git"
        receipt = fixture.receipt_dir / "receipt.json"
        snapshot = fixture.snapshot_source()
        fixture.run_cli("rewrite", "--source", str(fixture.source / ".git"), "--output", str(output), "--policy", str(policy), "--receipt", str(receipt))
        proof = json.loads(receipt.read_text())
        proof["source"]["head"] = "0" * len(proof["source"]["head"])
        receipt.write_text(json.dumps(proof, sort_keys=True, separators=(",", ":")) + "\n")

        result = fixture.run_cli("verify", "--repository", str(output), "--policy", str(policy), "--source", str(fixture.source / ".git"), "--receipt", str(receipt), "--json", check=False)

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "error: sanitization receipt integrity check failed\n")
        fixture.assert_source_snapshot(snapshot)

    def test_receipt_read_errors_are_redacted_as_missing(self) -> None:
        fixture = GitFixture(self)
        fixture.write("boundary.txt", "safe\n")
        boundary = fixture.commit("boundary", "boundary.txt")
        policy = fixture.write_policy(cutoff=None, cutoff_commit=boundary)
        output = fixture.output_dir / "commit.git"
        receipt = fixture.receipt_dir / "receipt.json"
        fixture.run_cli("rewrite", "--source", str(fixture.source / ".git"), "--output", str(output), "--policy", str(policy), "--receipt", str(receipt))

        result = fixture.run_cli("verify", "--repository", str(output), "--policy", str(policy), "--source", str(fixture.source / ".git"), "--receipt", str(fixture.receipt_dir), check=False)

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "error: sanitization receipt is missing\n")


if __name__ == "__main__":
    unittest.main()
