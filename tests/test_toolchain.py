import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.support import toolchain


class ToolchainTests(unittest.TestCase):
    def test_bootstrap_git_commands_inherit_isolated_configuration(self) -> None:
        bootstrap = (Path(__file__).parents[1] / "scripts" / "bootstrap-test-git.sh").read_text()

        for variable in (
            'readonly git_release_key_fingerprint="4F9036B1FEE7221FC778ECEFB0B5E88696AFE6CB"',
            'export HOME="$workdir/home"',
            'export XDG_CONFIG_HOME="$workdir/xdg-config"',
            "export GIT_CONFIG_NOSYSTEM=1",
            "export GIT_CONFIG_GLOBAL=/dev/null",
            'export GIT_TEMPLATE_DIR="$workdir/templates"',
        ):
            self.assertIn(variable, bootstrap)
        for command in ("verify-tag", "rev-parse", "checkout"):
            self.assertIn(f'git -C "$workdir/git" {command}', bootstrap)
        self.assertLess(
            bootstrap.index("export GIT_CONFIG_NOSYSTEM=1"), bootstrap.index('git init -q "$workdir/git"')
        )

    def test_accepts_exact_pinned_tool_outputs(self) -> None:
        with patch(
            "tests.support.toolchain.subprocess.run",
            side_effect=[
                subprocess.CompletedProcess(("git", "--version"), 0, toolchain.GIT_OUTPUT, ""),
                subprocess.CompletedProcess(
                    ("git", "filter-repo", "--version"), 0, toolchain.FILTER_REPO_OUTPUT, ""
                ),
            ],
        ):
            toolchain.main()

    def test_rejects_missing_tool(self) -> None:
        with patch("tests.support.toolchain.subprocess.run", side_effect=FileNotFoundError):
            with self.assertRaisesRegex(SystemExit, "Git 2.47.0 is required on PATH"):
                toolchain.command_output(("git", "--version"), toolchain.GIT_OUTPUT, "Git 2.47.0")

    def test_rejects_malformed_tool_output(self) -> None:
        malformed = subprocess.CompletedProcess(("git", "--version"), 0, toolchain.GIT_OUTPUT, "warning\n")
        with patch("tests.support.toolchain.subprocess.run", return_value=malformed):
            with self.assertRaisesRegex(SystemExit, "unsupported Git 2.47.0"):
                toolchain.command_output(("git", "--version"), toolchain.GIT_OUTPUT, "Git 2.47.0")

    def test_rejects_mismatched_tool_output(self) -> None:
        mismatched = subprocess.CompletedProcess(("git", "filter-repo", "--version"), 0, "wrong\n", "")
        with patch("tests.support.toolchain.subprocess.run", return_value=mismatched):
            with self.assertRaisesRegex(SystemExit, "unsupported git-filter-repo"):
                toolchain.command_output(
                    ("git", "filter-repo", "--version"), toolchain.FILTER_REPO_OUTPUT, "git-filter-repo"
                )
