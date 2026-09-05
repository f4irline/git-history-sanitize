import subprocess
import unittest
from unittest.mock import patch

from tests.support import toolchain


class ToolchainTests(unittest.TestCase):
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
