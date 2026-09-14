"""Focused path-filtering and retained-metadata contracts.

Future consumer contract: after BBQ-7 lands, retain coverage here proving every
mixed boundary root keeps ``history.prefixMessage`` while ordinary mixed
commits use ``commits.mixedMessage`` and excluded root entries remain absent.
"""

from __future__ import annotations

import unittest

from tests.support.git_fixture import GitFixture


class FilteringContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = GitFixture(self)

    def rewrite(self, policy: object, name: str = "sanitized.git") -> object:
        output = self.fixture.output_dir / name
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

    def test_canonical_special_character_rules_reach_filtering_unchanged(self) -> None:
        paths = ("secret file.txt", "日本語/秘密.txt", "-secret.txt")
        self.fixture.write("keep.txt", "safe\n")
        for path in paths:
            self.fixture.write(path, "secret\n")
        self.fixture.git(self.fixture.source, "add", "--", "keep.txt", *paths)
        self.fixture.git(self.fixture.source, "commit", "-qm", "mixed")
        policy = self.fixture.write_policy(excluded_paths=paths)

        output = self.rewrite(policy)

        self.assertEqual(
            self.fixture.git(output, "ls-tree", "-r", "--name-only", "HEAD").splitlines(),
            ["keep.txt"],
        )

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

    def test_mixed_boundary_root_keeps_distinct_prefix_and_filters_paths(self) -> None:
        self.fixture.write("keep.txt", "safe root\n")
        self.fixture.write("secret.txt", "exact secret\n")
        self.fixture.write("private/key.txt", "directory secret\n")
        self.fixture.commit(
            "mixed boundary", "keep.txt", "secret.txt", "private/key.txt",
            timestamp="2026-09-03T01:00:00+00:00",
        )
        secret_blob = self.fixture.git(self.fixture.source, "rev-parse", "HEAD:secret.txt")
        key_blob = self.fixture.git(self.fixture.source, "rev-parse", "HEAD:private/key.txt")
        self.fixture.write("keep.txt", "safe later\n")
        self.fixture.write("private/later.txt", "later secret\n")
        self.fixture.commit(
            "later mixed", "keep.txt", "private/later.txt",
            timestamp="2026-09-03T02:00:00+00:00",
        )
        policy = self.fixture.write_policy(
            excluded_paths=("secret.txt", "private/"),
            prefix_message="synthetic root",
            mixed_message="ordinary mixed",
        )

        output = self.rewrite(policy)

        root = self.fixture.git(output, "rev-list", "--max-parents=0", "HEAD")
        self.assertEqual(self.fixture.git(output, "show", "-s", "--format=%P", root), "")
        self.assertEqual(self.fixture.git(output, "show", "-s", "--format=%B", root), "synthetic root")
        self.assertEqual(
            self.fixture.git(output, "show", "-s", "--format=%an%x00%ae%x00%cn%x00%ce%x00%aI%x00%cI", root),
            "Fixture\x00fixture@example.invalid\x00Fixture\x00fixture@example.invalid\x002026-09-03T01:00:00Z\x002026-09-03T01:00:00Z",
        )
        self.assertEqual(self.fixture.git(output, "show", "HEAD:keep.txt"), "safe later")
        self.assertEqual(self.fixture.git(output, "ls-tree", "-r", "--name-only", root), "keep.txt")
        objects = self.fixture.all_objects(output)
        self.assertNotIn(secret_blob, objects)
        self.assertNotIn(key_blob, objects)
        self.assertEqual(self.fixture.git(output, "show", "-s", "--format=%B", "HEAD"), "ordinary mixed")

    def test_mixed_boundary_root_keeps_equal_prefix_and_mixed_message(self) -> None:
        self.fixture.write("keep.txt", "safe\n")
        self.fixture.write("private/secret.txt", "secret\n")
        self.fixture.commit("mixed boundary", "keep.txt", "private/secret.txt")
        policy = self.fixture.write_policy(
            excluded_paths=("private/",),
            prefix_message="same message",
            mixed_message="same message",
        )

        output = self.rewrite(policy)

        root = self.fixture.git(output, "rev-list", "--max-parents=0", "HEAD")
        self.assertEqual(self.fixture.git(output, "show", "-s", "--format=%P", root), "")
        self.assertEqual(self.fixture.git(output, "show", "-s", "--format=%B", root), "same message")
        self.assertEqual(self.fixture.git(output, "ls-tree", "-r", "--name-only", root), "keep.txt")

    def test_snapshot_mixed_root_keeps_prefix_and_filters_paths(self) -> None:
        self.fixture.write("keep.txt", "safe snapshot\n")
        self.fixture.write("secret.txt", "exact secret\n")
        self.fixture.write("private/key.txt", "directory secret\n")
        self.fixture.commit("mixed snapshot", "keep.txt", "secret.txt", "private/key.txt")
        policy = self.fixture.write_policy(
            cutoff=None,
            excluded_paths=("secret.txt", "private/"),
            prefix_message="snapshot root",
            mixed_message="ordinary mixed",
            source_mode="snapshot",
        )

        output = self.rewrite(policy)

        root = self.fixture.git(output, "rev-list", "--max-parents=0", "HEAD")
        self.assertEqual(self.fixture.git(output, "rev-list", "--count", "HEAD"), "1")
        self.assertEqual(self.fixture.git(output, "show", "-s", "--format=%P", root), "")
        self.assertEqual(self.fixture.git(output, "show", "-s", "--format=%B", root), "snapshot root")
        self.assertEqual(self.fixture.git(output, "show", "HEAD:keep.txt"), "safe snapshot")
        self.assertEqual(self.fixture.git(output, "ls-tree", "-r", "--name-only", root), "keep.txt")

    def test_snapshot_all_excluded_head_recovers_one_empty_synthetic_root(self) -> None:
        self.fixture.write("private/secret.txt", "snapshot secret\n")
        self.fixture.commit(
            "sensitive snapshot", "private/secret.txt", timestamp="2026-09-03T01:00:00+00:00"
        )
        policy = self.fixture.write_policy(
            cutoff=None,
            excluded_paths=("private/",),
            prefix_message="snapshot root",
            source_mode="snapshot",
        )

        output = self.rewrite(policy)

        self.assertEqual(self.fixture.git(output, "rev-list", "--count", "HEAD"), "1")
        self.assertEqual(self.fixture.git(output, "show", "-s", "--format=%P", "HEAD"), "")
        self.assertEqual(self.fixture.git(output, "show", "-s", "--format=%B", "HEAD"), "snapshot root")
        self.assertEqual(self.fixture.git(output, "ls-tree", "-r", "--name-only", "HEAD"), "")
        self.assertEqual(self.fixture.git(output, "symbolic-ref", "HEAD"), "refs/heads/main")
        verified = self.fixture.run_cli(
            "verify", "--repository", str(output), "--policy", str(policy)
        )
        self.assertEqual(verified.returncode, 0)
        self.assertEqual(verified.stderr, "")


if __name__ == "__main__":
    unittest.main()
