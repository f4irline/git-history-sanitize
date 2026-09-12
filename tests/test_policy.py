import re
import unittest

from git_history_sanitize.errors import PolicyError
from git_history_sanitize.policy import Policy


class PolicyTests(unittest.TestCase):
    @staticmethod
    def policy_with_paths(*paths: str) -> str:
        entries = "".join(f"    - {path}\n" for path in paths)
        return (
            "version: 1\n"
            "history:\n"
            "  cutoffCommit: deadbeef\n"
            "paths:\n"
            "  exclude:\n"
            f"{entries}"
        )

    def test_parses_timestamp_policy(self) -> None:
        policy = Policy.from_text(
            """
version: 1
history:
  cutoff: "2026-09-03T00:00:00+03:00"
paths:
  exclude:
    - secret.json
    - private/
commits:
  mixedMessage: "[sanitized]"
refs:
  keep:
    - HEAD
"""
        )

        self.assertEqual(policy.history.cutoff_epoch, 1788382800)
        self.assertEqual(policy.excluded_paths, ("secret.json", "private/"))

    def test_rejects_ambiguous_cutoff(self) -> None:
        with self.assertRaisesRegex(PolicyError, "exactly one"):
            Policy.from_text(
                """
version: 1
history:
  cutoff: "2026-09-03T00:00:00+00:00"
  cutoffCommit: "deadbeef"
"""
            )

    def test_rejects_boolean_policy_version(self) -> None:
        with self.assertRaisesRegex(PolicyError, "version 1"):
            Policy.from_text("version: true\nhistory:\n  cutoff: 2026-09-03T00:00:00+00:00\n")

    def test_rejects_parent_path(self) -> None:
        with self.assertRaisesRegex(PolicyError, "Invalid excluded path"):
            Policy.from_text(
                """
version: 1
history:
  cutoffCommit: "deadbeef"
paths:
  exclude:
    - ../secret
"""
            )

    def test_accepts_canonical_exact_and_directory_paths(self) -> None:
        paths = ("secret file.txt", "日本語/秘密", ".env", "-private", "private/")

        policy = Policy.from_text(self.policy_with_paths(*paths))

        self.assertEqual(policy.excluded_paths, paths)

    def test_rejects_noncanonical_excluded_paths_with_entry_and_reason(self) -> None:
        invalid_paths = (
            ('""', "", "empty"),
            (".", ".", "dot segment"),
            ("./secret", "./secret", "dot segment"),
            ("secret/./key", "secret/./key", "dot segment"),
            ("../secret", "../secret", "parent traversal"),
            ("secret/../key", "secret/../key", "parent traversal"),
            ("/secret", "/secret", "absolute"),
            (r"secret\\key", r"secret\\key", "backslash"),
            ("secret//key", "secret//key", "empty segment"),
            ("private//", "private//", "empty segment"),
            ('"secret\\x00key"', "secret\x00key", "NUL"),
            ('"\\ud800"', "\ud800", "UTF-8"),
        )

        for path, entry, reason in invalid_paths:
            with self.subTest(path=path), self.assertRaisesRegex(
                PolicyError, f"{reason}.*{re.escape(repr(entry))}"
            ):
                Policy.from_text(self.policy_with_paths(path))

    def test_rejects_duplicate_and_directory_descendant_rules_in_any_order(self) -> None:
        cases = (
            (("private/", "private/"), "duplicate"),
            (("private/", "private/key.txt"), "overlap"),
            (("private/key.txt", "private/"), "overlap"),
            (("private/", "private/nested/"), "overlap"),
            (("private/nested/", "private/"), "overlap"),
        )

        for paths, reason in cases:
            with self.subTest(paths=paths), self.assertRaisesRegex(PolicyError, reason):
                Policy.from_text(self.policy_with_paths(*paths))

    def test_preserves_exact_file_and_directory_distinction(self) -> None:
        policy = Policy.from_text(self.policy_with_paths("private", "private/"))

        self.assertEqual(policy.excluded_paths, ("private", "private/"))

    def test_source_mode_defaults_to_complete(self) -> None:
        policy = Policy.from_text("version: 1\nhistory:\n  cutoff: 2026-09-03T00:00:00+00:00\n")
        self.assertEqual(policy.source.mode, "complete")

    def test_snapshot_rejects_cutoff(self) -> None:
        with self.assertRaisesRegex(PolicyError, "does not accept"):
            Policy.from_text("version: 1\nsource:\n  mode: snapshot\nhistory:\n  cutoff: 2026-09-03T00:00:00+00:00\n  prefixMessage: '[snapshot]'\n")

    def test_rejects_unknown_source_mode(self) -> None:
        with self.assertRaisesRegex(PolicyError, "source.mode"):
            Policy.from_text("version: 1\nsource:\n  mode: remote\nhistory:\n  cutoff: 2026-09-03T00:00:00+00:00\n")


if __name__ == "__main__":
    unittest.main()
