"""Git subprocess isolation contracts."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from git_history_sanitize.git import git_environment, run


class GitEnvironmentContracts(unittest.TestCase):
    def test_git_environment_forces_no_lazy_fetch_and_no_replace_objects(self) -> None:
        environment = git_environment({"GIT_NO_LAZY_FETCH": "0", "GIT_NO_REPLACE_OBJECTS": "0"})

        self.assertEqual(environment["GIT_NO_LAZY_FETCH"], "1")
        self.assertEqual(environment["GIT_NO_REPLACE_OBJECTS"], "1")

    def test_git_run_passes_no_lazy_fetch_and_no_replace_objects_to_subprocess(self) -> None:
        with patch("git_history_sanitize.git.subprocess.run") as subprocess_run:
            subprocess_run.return_value.returncode = 0
            subprocess_run.return_value.stdout = b""
            run(["--version"])

        environment = subprocess_run.call_args.kwargs["env"]
        self.assertEqual(environment["GIT_NO_LAZY_FETCH"], "1")
        self.assertEqual(environment["GIT_NO_REPLACE_OBJECTS"], "1")


if __name__ == "__main__":
    unittest.main()
