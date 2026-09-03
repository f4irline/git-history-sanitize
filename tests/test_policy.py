import unittest

from git_history_sanitize.errors import PolicyError
from git_history_sanitize.policy import Policy


class PolicyTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
