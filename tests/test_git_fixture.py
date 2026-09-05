import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.support.git_fixture import GitFixture


class GitFixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = GitFixture(self)

    def test_commits_tags_and_snapshots_are_deterministic(self) -> None:
        self.fixture.write("allowed.txt", "one\n")
        first = self.fixture.commit("first", "allowed.txt")
        self.fixture.tag("release", "release tag")
        snapshot = self.fixture.snapshot_source()

        self.assertEqual(self.fixture.git(self.fixture.source, "log", "-1", "--format=%an"), "Fixture")
        self.assertEqual(self.fixture.git(self.fixture.source, "log", "-1", "--format=%aI"), "2026-09-03T12:00:00Z")
        self.assertEqual(self.fixture.git(self.fixture.source, "rev-parse", "release^{}"), first)
        self.fixture.assert_source_snapshot(snapshot)

    def test_hostile_global_configuration_is_active_outside_fixture_and_neutralized_inside(self) -> None:
        hostile_root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(hostile_root, ignore_errors=True))
        hostile_config = hostile_root / "gitconfig"
        hostile_config.write_text("[user]\n\tname = Hostile Host\n")
        hostile_environment = os.environ.copy()
        hostile_environment["GIT_CONFIG_NOSYSTEM"] = "1"
        hostile_environment["GIT_CONFIG_GLOBAL"] = str(hostile_config)

        outside = subprocess.run(
            [self.fixture.git_executable, "config", "--global", "user.name"],
            check=True,
            capture_output=True,
            env=hostile_environment,
            text=True,
        )

        self.assertEqual(outside.stdout.strip(), "Hostile Host")
        self.assertTrue(self.fixture.home.is_dir())
        self.assertTrue(self.fixture.xdg_config.is_dir())
        self.assertNotEqual(self.fixture.environment["HOME"], os.environ.get("HOME"))
        self.assertNotEqual(
            self.fixture.environment["GIT_CONFIG_GLOBAL"], os.environ.get("GIT_CONFIG_GLOBAL")
        )
        self.assertEqual(self.fixture.git(self.fixture.source, "config", "user.name"), "Fixture")
        self.assertEqual(self.fixture.git(self.fixture.source, "config", "--global", "user.name", check=False), "")

    def test_source_snapshot_detects_worktree_ref_index_and_object_mutation(self) -> None:
        self.fixture.write("allowed.txt", "one\n")
        self.fixture.commit("first", "allowed.txt")
        snapshot = self.fixture.snapshot_source()

        self.fixture.write("allowed.txt", "changed\n")
        with self.assertRaises(AssertionError):
            self.fixture.assert_source_snapshot(snapshot)

        self.fixture.git(self.fixture.source, "reset", "--hard")
        snapshot = self.fixture.snapshot_source()
        self.fixture.branch("unexpected")
        with self.assertRaises(AssertionError):
            self.fixture.assert_source_snapshot(snapshot)

        self.fixture.git(self.fixture.source, "branch", "-D", "unexpected")
        snapshot = self.fixture.snapshot_source()
        self.fixture.write("staged.txt", "index mutation\n")
        self.fixture.git(self.fixture.source, "add", "staged.txt")
        with self.assertRaises(AssertionError):
            self.fixture.assert_source_snapshot(snapshot)

        self.fixture.git(self.fixture.source, "reset", "--hard")
        snapshot = self.fixture.snapshot_source()
        blob = self.fixture.add_unreachable_blob("unreachable object")
        self.assertIn(blob, self.fixture.all_objects(self.fixture.source))
        with self.assertRaises(AssertionError):
            self.fixture.assert_source_snapshot(snapshot)

    def test_redaction_assertion_accepts_context_but_rejects_sensitive_values(self) -> None:
        self.fixture.assert_redacted("error: cannot read policy", "customer-secret", "private/secret.txt")
        with self.assertRaises(AssertionError):
            self.fixture.assert_redacted('{"error": "customer-secret"}', "customer-secret")


if __name__ == "__main__":
    unittest.main()
