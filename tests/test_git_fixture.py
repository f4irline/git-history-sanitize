import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_source_runner_uses_isolated_installed_module_without_pythonpath(self) -> None:
        environment = self.fixture.environment | {"PYTHONPATH": "/host/checkout/src"}
        self.fixture.environment = environment

        with patch("tests.support.git_fixture.subprocess.run") as run:
            self.fixture.run_cli("doctor")

        command = run.call_args.args[0]
        self.assertEqual(command, [self.fixture.python_executable, "-I", "-m", "git_history_sanitize", "doctor"])
        self.assertNotIn("PYTHONPATH", run.call_args.kwargs["env"])

    def test_container_runner_requires_an_image(self) -> None:
        with patch.dict(os.environ, {"GHS_TEST_RUNTIME": "container"}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "GHS_CONTAINER_IMAGE"):
                self.fixture.run_cli("doctor")

    def test_wheel_runner_requires_a_wheel(self) -> None:
        with patch.dict(os.environ, {"GHS_TEST_RUNTIME": "wheel"}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "GHS_WHEEL"):
                self.fixture.run_cli("doctor")

    def test_container_runner_translates_fixture_paths_and_uses_allowlisted_environment(self) -> None:
        policy = self.fixture.write_policy()
        output = self.fixture.root / "output.git"
        arguments = (
            "rewrite",
            "--source",
            str(self.fixture.source / ".git"),
            "--output",
            str(output),
            "--policy",
            str(policy),
        )

        with (
            patch.dict(os.environ, {"GHS_CONTAINER_IMAGE": "fixture-image"}, clear=False),
            patch("tests.support.git_fixture.shutil.which", return_value="/usr/bin/docker"),
        ):
            command = self.fixture._container_cli(arguments)

        image_index = command.index("fixture-image")
        self.assertEqual(
            command[image_index + 1:],
            [
                "rewrite",
                "--source",
                "/input.git",
                "--output",
                "/output/output.git",
                "--policy",
                "/policy.yml",
            ],
        )
        self.assertNotIn(str(self.fixture.root), command[image_index + 1:])
        mounts = [command[index + 1] for index, value in enumerate(command[:-1]) if value == "--mount"]
        self.assertIn(
            f"type=bind,src={(self.fixture.source / '.git').resolve()},dst=/input.git,readonly",
            mounts,
        )
        self.assertIn(f"type=bind,src={policy.resolve()},dst=/policy.yml,readonly", mounts)
        self.assertIn(f"type=bind,src={output.parent.resolve()},dst=/output", mounts)
        for host_path, container_path in (
            (self.fixture.home, "/home/fixture"),
            (self.fixture.xdg_config, "/xdg-config"),
            (self.fixture.global_config, "/gitconfig"),
            (self.fixture.template_dir, "/templates"),
            (self.fixture.hooks_dir, "/hooks"),
        ):
            self.assertIn(f"type=bind,src={host_path},dst={container_path},readonly", mounts)
        destinations = [mount.split(",dst=", 1)[1].split(",", 1)[0] for mount in mounts]
        self.assertEqual(len(destinations), len(set(destinations)))
        self.assertIn("--read-only", command)
        self.assertIn("--network=none", command)
        self.assertEqual(
            {command[index + 1] for index, value in enumerate(command[:-1]) if value == "--env"},
            {
                "HOME=/home/fixture",
                "XDG_CONFIG_HOME=/xdg-config",
                "LC_ALL=C",
                "LANG=C",
                "TZ=UTC",
                "GIT_CONFIG_NOSYSTEM=1",
                "GIT_CONFIG_GLOBAL=/gitconfig",
                "GIT_TEMPLATE_DIR=/templates",
                "GIT_AUTHOR_NAME=Fixture",
                "GIT_AUTHOR_EMAIL=fixture@example.invalid",
                "GIT_COMMITTER_NAME=Fixture",
                "GIT_COMMITTER_EMAIL=fixture@example.invalid",
                "GIT_AUTHOR_DATE=2026-09-03T12:00:00+00:00",
                "GIT_COMMITTER_DATE=2026-09-03T12:00:00+00:00",
                "GIT_CONFIG_COUNT=4",
                "GIT_CONFIG_KEY_0=commit.gpgsign",
                "GIT_CONFIG_VALUE_0=false",
                "GIT_CONFIG_KEY_1=tag.gpgSign",
                "GIT_CONFIG_VALUE_1=false",
                "GIT_CONFIG_KEY_2=credential.helper",
                "GIT_CONFIG_VALUE_2=",
                "GIT_CONFIG_KEY_3=core.hooksPath",
                "GIT_CONFIG_VALUE_3=/hooks",
            },
        )
        self.assertFalse(
            any(str(self.fixture.root) in value for value in command[image_index + 1:] if value)
        )


if __name__ == "__main__":
    unittest.main()
