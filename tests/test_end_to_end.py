import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from git_history_sanitize.engine import plan, rewrite
from git_history_sanitize.policy import Policy
from git_history_sanitize.verify import verify


def git(path: Path, *arguments: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), *arguments],
        check=True,
        env=env,
        stdout=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


class EndToEndTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        subprocess.run(["git", "init", "--initial-branch=main", str(self.source)], check=True)
        git(self.source, "config", "user.name", "Fixture")
        git(self.source, "config", "user.email", "fixture@example.invalid")

    def commit(self, timestamp: str, message: str, *paths: str) -> None:
        git(self.source, "add", *paths)
        environment = os.environ.copy()
        environment["GIT_AUTHOR_DATE"] = timestamp
        environment["GIT_COMMITTER_DATE"] = timestamp
        git(self.source, "commit", "-qm", message, env=environment)

    def policy(self) -> Policy:
        return Policy.from_text(
            """
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

    def test_rewrite_preserves_allowed_state_without_source_mutation(self) -> None:
        (self.source / "allowed.txt").write_text("one\n")
        self.commit("2026-09-02T10:00:00+00:00", "Old allowed implementation", "allowed.txt")

        (self.source / "allowed.txt").write_text("one\ntwo\n")
        (self.source / "private").mkdir()
        (self.source / "private" / "secret.txt").write_text("customer material\n")
        self.commit(
            "2026-09-02T11:00:00+00:00",
            "Old customer implementation",
            "allowed.txt",
            "private/secret.txt",
        )

        (self.source / "allowed.txt").write_text("one\ntwo\nthree\n")
        self.commit("2026-09-03T09:00:00+00:00", "First allowed commit", "allowed.txt")

        (self.source / "allowed.txt").write_text("one\ntwo\nthree\nfour\n")
        (self.source / "private" / "secret.txt").write_text("rotated material\n")
        self.commit(
            "2026-09-03T10:00:00+00:00",
            "Customer Foo secret implementation",
            "allowed.txt",
            "private/secret.txt",
        )

        (self.source / "private" / "secret.txt").write_text("sensitive only\n")
        self.commit("2026-09-03T11:00:00+00:00", "Rotate Foo credentials", "private/secret.txt")

        (self.source / "allowed.txt").write_text("one\ntwo\nthree\nfour\nfive\n")
        self.commit("2026-09-03T12:00:00+00:00", "Another allowed change", "allowed.txt")

        (self.source / "allowed.txt").write_text(
            "one\ntwo\nthree\nfour\nfive\nsix\n"
        )
        (self.source / "private" / "secret.txt").write_text("more private material\n")
        self.commit(
            "2026-09-03T13:00:00+00:00",
            "Latest customer secret",
            "allowed.txt",
            "private/secret.txt",
        )
        git(
            self.source,
            "tag",
            "-a",
            "private-release",
            "-m",
            "Annotated tag secret message",
        )
        git(self.source, "branch", "unwanted-side-branch", "HEAD~1")

        source_head = git(self.source, "rev-parse", "HEAD")
        policy = self.policy()
        proposed = plan(self.source / ".git", policy)
        self.assertEqual(proposed.source_commits, 7)
        self.assertEqual(proposed.discarded_commits, 2)

        output = self.root / "sanitized.git"
        report = rewrite(self.source / ".git", output, policy)

        self.assertTrue(output.is_dir())
        self.assertEqual(git(self.source, "rev-parse", "HEAD"), source_head)
        self.assertEqual(report.verification.commit_count, 4)
        self.assertEqual(
            git(output, "log", "--format=%s", "--all").splitlines(),
            ["[sanitized]", "Another allowed change", "[sanitized]", "[sanitized]"],
        )
        self.assertEqual(
            git(output, "show", "HEAD:allowed.txt"),
            "one\ntwo\nthree\nfour\nfive\nsix",
        )
        self.assertNotIn("private/secret.txt", git(output, "ls-tree", "-r", "--name-only", "HEAD"))
        self.assertEqual(git(output, "remote"), "")
        self.assertEqual(git(output, "for-each-ref", "--format=%(refname)"), "refs/heads/main")

        verified = verify(
            output,
            policy,
            (
                "Old allowed implementation",
                "Old customer implementation",
                "First allowed commit",
                "Customer Foo secret implementation",
                "Rotate Foo credentials",
                "Latest customer secret",
                "Annotated tag secret message",
            ),
        )
        self.assertEqual(verified.root, report.verification.root)

        # The tool accepts its own bare output as a future read-only source.
        second_output = self.root / "sanitized-again.git"
        second_report = rewrite(output, second_output, policy)
        self.assertEqual(second_report.verification.commit_count, 4)
        self.assertEqual(
            git(second_output, "show", "HEAD:allowed.txt"),
            "one\ntwo\nthree\nfour\nfive\nsix",
        )


if __name__ == "__main__":
    unittest.main()
