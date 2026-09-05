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
        with self.assertRaises(AssertionError) as error:
            self.fixture.assert_redacted('{"error": "customer-secret"}', "customer-secret")
        self.assertNotIn("customer-secret", str(error.exception))

    def test_source_runner_uses_its_runtime_venv_without_pythonpath_or_host_tool(self) -> None:
        runtime_bin = str(Path(self.fixture.python_executable).parent)
        unintended_tool = self.fixture.root / "host-tools" / "git-filter-repo"
        environment = self.fixture.environment | {"PYTHONPATH": "/host/checkout/src"}
        self.fixture.environment = environment
        self.fixture.source_filter_repo_executable = str(unintended_tool)

        with patch("tests.support.git_fixture.subprocess.run") as run:
            self.fixture.run_cli("doctor")

        command = run.call_args.args[0]
        runtime_path = run.call_args.kwargs["env"]["PATH"].split(os.pathsep)
        self.assertEqual(command, [self.fixture.python_executable, "-I", "-m", "git_history_sanitize", "doctor"])
        self.assertNotIn("PYTHONPATH", run.call_args.kwargs["env"])
        self.assertIn(runtime_bin, runtime_path)
        self.assertNotIn(str(unintended_tool.parent.resolve()), runtime_path)

    def test_container_runner_requires_an_image(self) -> None:
        with patch.dict(os.environ, {"GHS_TEST_RUNTIME": "container"}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "GHS_CONTAINER_IMAGE"):
                self.fixture.run_cli("doctor")

    def test_wheel_runner_requires_a_wheel(self) -> None:
        with patch.dict(os.environ, {"GHS_TEST_RUNTIME": "wheel"}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "GHS_WHEEL"):
                self.fixture.run_cli("doctor")

    def test_wheel_runner_rejects_console_script_outside_fixture_venv(self) -> None:
        wheel = self.fixture.root / "fixture.whl"
        wheel.touch()
        launcher = self.fixture.root / "wheel-runtime" / "bin" / "git-history-sanitize"
        launcher.parent.mkdir(parents=True)
        launcher.symlink_to(self.fixture.python_executable)

        with patch.dict(os.environ, {"GHS_WHEEL": str(wheel)}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "fixture-owned wheel venv"):
                self.fixture._wheel_cli(("doctor",))

    def test_wheel_runner_installs_filter_repo_in_its_fixture_venv(self) -> None:
        wheel = self.fixture.root / "fixture.whl"
        wheel.touch()
        runtime = self.fixture.root / "wheel-runtime"
        launcher = runtime / "bin" / "git-history-sanitize"

        def install(command: list[str], **_kwargs: object) -> None:
            if "venv" in command:
                launcher.parent.mkdir(parents=True)
            else:
                launcher.touch()

        with (
            patch.dict(os.environ, {"GHS_WHEEL": str(wheel)}, clear=False),
            patch("tests.support.git_fixture.subprocess.run", side_effect=install) as run,
        ):
            self.fixture._wheel_cli(("doctor",))

        self.assertEqual(run.call_count, 2)
        install_command = run.call_args_list[1].args[0]
        self.assertEqual(install_command[:5], [str(runtime / "bin" / "python"), "-I", "-m", "pip", "install"])
        self.assertIn("git-filter-repo==2.47.0", install_command)
        self.assertIsNotNone(self.fixture.source_filter_repo_executable)
        self.assertIn(
            str(Path(self.fixture.python_executable).parent),
            run.call_args_list[1].kwargs["env"]["PATH"].split(os.pathsep),
        )

    def test_wheel_runner_resolves_filter_repo_from_the_fixture_venv(self) -> None:
        command = [str(self.fixture.root / "wheel-runtime" / "bin" / "git-history-sanitize"), "doctor"]

        with (
            patch.dict(os.environ, {"GHS_TEST_RUNTIME": "wheel"}, clear=False),
            patch.object(self.fixture, "_wheel_cli", return_value=command),
            patch("tests.support.git_fixture.subprocess.run") as run,
        ):
            self.fixture.run_cli("doctor")

        self.assertEqual(
            run.call_args.kwargs["env"]["PATH"].split(os.pathsep)[0],
            str(self.fixture.root / "wheel-runtime" / "bin"),
        )

    def test_container_runner_allows_translated_paths_in_success_output(self) -> None:
        arguments = self._container_rewrite_arguments()
        result = subprocess.CompletedProcess([], 0, "/input.git /output/output.git\n", "/policy.yml\n")

        with (
            patch.dict(os.environ, {"GHS_TEST_RUNTIME": "container", "GHS_CONTAINER_IMAGE": "fixture-image"}, clear=False),
            patch("tests.support.git_fixture.shutil.which", return_value="/usr/bin/docker"),
            patch("tests.support.git_fixture.subprocess.run", return_value=result),
        ):
            self.assertIs(self.fixture.run_cli(*arguments), result)

    def test_container_runner_rejects_host_paths_in_expected_failure_output(self) -> None:
        arguments = self._container_rewrite_arguments()
        result = subprocess.CompletedProcess([], 2, "", f"cannot read {self.fixture.global_config}\n")

        with (
            patch.dict(os.environ, {"GHS_TEST_RUNTIME": "container", "GHS_CONTAINER_IMAGE": "fixture-image"}, clear=False),
            patch("tests.support.git_fixture.shutil.which", return_value="/usr/bin/docker"),
            patch("tests.support.git_fixture.subprocess.run", return_value=result),
        ):
            with self.assertRaisesRegex(AssertionError, "sensitive value leaked in command output") as error:
                self.fixture.run_cli(*arguments, check=False)
        self.assertNotIn(str(self.fixture.global_config), str(error.exception))

    def _container_rewrite_arguments(self) -> tuple[str, ...]:
        policy = self.fixture.write_policy()
        return (
            "rewrite",
            "--source",
            str(self.fixture.source / ".git"),
            "--output",
            str(self.fixture.root / "output.git"),
            "--policy",
            str(policy),
        )

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

    def test_container_verify_maps_source_and_output_repositories_separately(self) -> None:
        policy = self.fixture.write_policy()
        output = self.fixture.root / "sanitized.git"
        output.mkdir()

        with (
            patch.dict(os.environ, {"GHS_CONTAINER_IMAGE": "fixture-image"}, clear=False),
            patch("tests.support.git_fixture.shutil.which", return_value="/usr/bin/docker"),
        ):
            source_command = self.fixture._container_cli(
                ("verify", "--repository", str(self.fixture.source / ".git"), "--policy", str(policy))
            )
            output_command = self.fixture._container_cli(
                ("verify", "--repository", str(output), "--policy", str(policy))
            )

        source_image = source_command.index("fixture-image")
        output_image = output_command.index("fixture-image")
        self.assertEqual(source_command[source_image + 1:], ["verify", "--repository", "/input.git", "--policy", "/policy.yml"])
        self.assertEqual(output_command[output_image + 1:], ["verify", "--repository", "/output/sanitized.git", "--policy", "/policy.yml"])
        output_mounts = [output_command[index + 1] for index, value in enumerate(output_command[:-1]) if value == "--mount"]
        self.assertIn(f"type=bind,src={output.parent.resolve()},dst=/output,readonly", output_mounts)
        self.assertNotIn(f"type=bind,src={output.resolve()},dst=/input.git,readonly", output_mounts)


if __name__ == "__main__":
    unittest.main()
