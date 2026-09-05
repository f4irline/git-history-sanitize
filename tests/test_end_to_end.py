import json
import unittest

from tests.support.git_fixture import GitFixture


class EndToEndTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = GitFixture(self)
        self.root = self.fixture.root
        self.source = self.fixture.source

    def commit(self, timestamp: str, message: str, *paths: str) -> None:
        self.fixture.commit(message, *paths, timestamp=timestamp)

    def write_policy(self) -> None:
        (self.root / "policy.yml").write_text(
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
        self.fixture.git(
            self.source,
            "tag",
            "-a",
            "private-release",
            "-m",
            "Annotated tag secret message",
        )
        self.fixture.branch("unwanted-side-branch", "HEAD~1")

        source_snapshot = self.fixture.snapshot_source()
        self.write_policy()
        policy = self.root / "policy.yml"
        planned = self.fixture.run_cli(
            "plan", "--source", str(self.source / ".git"), "--policy", str(policy), "--json"
        )
        proposed = json.loads(planned.stdout)
        self.assertEqual(proposed["source_commits"], 7)
        self.assertEqual(proposed["discarded_commits"], 2)

        output = self.root / "sanitized.git"
        rewritten = self.fixture.run_cli(
            "rewrite",
            "--source",
            str(self.source / ".git"),
            "--output",
            str(output),
            "--policy",
            str(policy),
            "--json",
        )
        report = json.loads(rewritten.stdout)

        self.assertTrue(output.is_dir())
        self.fixture.assert_source_snapshot(source_snapshot)
        self.assertEqual(report["verification"]["commit_count"], 4)
        self.assertEqual(
            self.fixture.git(output, "log", "--format=%s", "--all").splitlines(),
            ["[sanitized]", "Another allowed change", "[sanitized]", "[sanitized]"],
        )
        self.assertEqual(
            self.fixture.git(output, "show", "HEAD:allowed.txt"),
            "one\ntwo\nthree\nfour\nfive\nsix",
        )
        self.assertNotIn("private/secret.txt", self.fixture.git(output, "ls-tree", "-r", "--name-only", "HEAD"))
        self.assertEqual(self.fixture.git(output, "remote"), "")
        self.assertEqual(self.fixture.git(output, "for-each-ref", "--format=%(refname)"), "refs/heads/main")
        output_snapshot = self.fixture.snapshot_output(output)

        verified = self.fixture.run_cli(
            "verify",
            "--repository",
            str(output),
            "--policy",
            str(policy),
            "--json",
            "--forbid",
            "Old allowed implementation",
            "--forbid",
            "Old customer implementation",
            "--forbid",
            "First allowed commit",
            "--forbid",
            "Customer Foo secret implementation",
            "--forbid",
            "Rotate Foo credentials",
            "--forbid",
            "Latest customer secret",
            "--forbid",
            "Annotated tag secret message",
        )
        self.assertEqual(json.loads(verified.stdout)["root"], report["verification"]["root"])
        self.fixture.assert_output_snapshot(output, output_snapshot)

        # The tool accepts its own bare output as a future read-only source.
        second_output = self.root / "sanitized-again.git"
        second_rewrite = self.fixture.run_cli(
            "rewrite",
            "--source",
            str(output),
            "--output",
            str(second_output),
            "--policy",
            str(policy),
            "--json",
        )
        self.assertEqual(json.loads(second_rewrite.stdout)["verification"]["commit_count"], 4)
        self.assertEqual(
            self.fixture.git(second_output, "show", "HEAD:allowed.txt"),
            "one\ntwo\nthree\nfour\nfive\nsix",
        )

    def test_failed_cli_rewrite_does_not_mutate_the_source(self) -> None:
        self.fixture.write("allowed.txt", "one\n")
        self.commit("2026-09-03T12:00:00+00:00", "Allowed", "allowed.txt")
        self.write_policy()
        source_snapshot = self.fixture.snapshot_source()
        output = self.root / "already-exists.git"
        output.mkdir()

        failed = self.fixture.run_cli(
            "rewrite",
            "--source",
            str(self.source / ".git"),
            "--output",
            str(output),
            "--policy",
            str(self.root / "policy.yml"),
            check=False,
        )

        self.assertEqual(failed.returncode, 2)
        self.assertIn("Output path already exists", failed.stderr)
        self.fixture.assert_redacted(failed.stderr, "customer-secret", "private/secret.txt")
        self.fixture.assert_source_snapshot(source_snapshot)


if __name__ == "__main__":
    unittest.main()
