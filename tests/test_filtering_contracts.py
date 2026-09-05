"""Focused path-filtering and retained-metadata contracts."""

from __future__ import annotations

import unittest

from tests.support.git_fixture import GitFixture


class FilteringContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = GitFixture(self)

    def rewrite(self, policy: object, name: str = "sanitized.git") -> object:
        output = self.fixture.root / name
        self.fixture.run_cli(
            "rewrite", "--source", str(self.fixture.source / ".git"), "--output", str(output),
            "--policy", str(policy), "--json"
        )
        return output

    def test_empty_exclusions_preserve_allowed_tree_and_metadata(self) -> None:
        self.fixture.write("allowed.txt", "safe\n")
        self.fixture.commit("retained message", "allowed.txt", timestamp="2026-09-03T01:00:00+00:00")
        self.fixture.write("allowed.txt", "safe again\n")
        self.fixture.commit("later retained message", "allowed.txt", timestamp="2026-09-03T02:00:00+00:00")
        policy = self.fixture.write_policy(prefix_message="clean root")

        output = self.rewrite(policy)

        self.assertEqual(self.fixture.git(output, "show", "HEAD:allowed.txt"), "safe again")
        self.assertEqual(
            self.fixture.git(output, "log", "-1", "--format=%an%x00%ae%x00%cn%x00%ce%x00%aI%x00%cI"),
            "Fixture\x00fixture@example.invalid\x00Fixture\x00fixture@example.invalid\x002026-09-03T02:00:00Z\x002026-09-03T02:00:00Z",
        )
        self.assertEqual(self.fixture.git(output, "log", "--max-parents=0", "-1", "--format=%s"), "clean root")
        self.assertEqual(self.fixture.git(output, "rev-list", "--max-parents=0", "--count", "HEAD"), "1")

    def test_exact_file_and_directory_exclusions_remove_reachable_history(self) -> None:
        self.fixture.write("keep.txt", "safe\n")
        self.fixture.write("secret.txt", "secret\n")
        self.fixture.write("private/key.txt", "key\n")
        self.fixture.commit("mixed", "keep.txt", "secret.txt", "private/key.txt")
        secret_blob = self.fixture.git(self.fixture.source, "rev-parse", "HEAD:secret.txt")
        key_blob = self.fixture.git(self.fixture.source, "rev-parse", "HEAD:private/key.txt")
        policy = self.fixture.write_policy(excluded_paths=("secret.txt", "private/"))

        output = self.rewrite(policy)

        names = self.fixture.git(output, "ls-tree", "-r", "--name-only", "HEAD").splitlines()
        objects = self.fixture.all_objects(output)
        self.assertEqual(names, ["keep.txt"])
        self.assertNotIn(secret_blob, objects)
        self.assertNotIn(key_blob, objects)

    def test_sensitive_only_commit_is_pruned_and_mixed_message_is_replaced(self) -> None:
        self.fixture.write("keep.txt", "one\n")
        self.fixture.commit("root allowed", "keep.txt")
        self.fixture.write("keep.txt", "two\n")
        self.fixture.write("private/secret.txt", "secret\n")
        self.fixture.commit("mixed sensitive title", "keep.txt", "private/secret.txt")
        self.fixture.write("private/secret.txt", "rotated\n")
        self.fixture.commit("sensitive only title", "private/secret.txt")
        policy = self.fixture.write_policy(excluded_paths=("private/",), mixed_message="redacted")

        output = self.rewrite(policy)

        messages = self.fixture.git(output, "log", "--format=%s", "--all").splitlines()
        self.assertEqual(messages, ["redacted", "[sanitized]"])
        self.assertNotIn("sensitive only title", "\n".join(messages))


if __name__ == "__main__":
    unittest.main()
