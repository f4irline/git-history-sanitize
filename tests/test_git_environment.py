"""Git subprocess isolation contracts."""

from __future__ import annotations

import signal
import subprocess
import unittest
from unittest.mock import Mock, call, patch

from git_history_sanitize.errors import InterruptionError
from git_history_sanitize.git import git_environment, hold_process_lock, run


class GitEnvironmentContracts(unittest.TestCase):
    def test_git_environment_forces_no_lazy_fetch_and_no_replace_objects(self) -> None:
        environment = git_environment({"GIT_NO_LAZY_FETCH": "0", "GIT_NO_REPLACE_OBJECTS": "0"})

        self.assertEqual(environment["GIT_NO_LAZY_FETCH"], "1")
        self.assertEqual(environment["GIT_NO_REPLACE_OBJECTS"], "1")

    def test_git_run_passes_no_lazy_fetch_and_no_replace_objects_to_subprocess(self) -> None:
        process = Mock(pid=123, returncode=0)
        process.communicate.return_value = (b"", b"")
        with patch("git_history_sanitize.git.subprocess.Popen", return_value=process) as popen:
            run(["--version"])

        environment = popen.call_args.kwargs["env"]
        self.assertEqual(environment["GIT_NO_LAZY_FETCH"], "1")
        self.assertEqual(environment["GIT_NO_REPLACE_OBJECTS"], "1")
        self.assertTrue(popen.call_args.kwargs["start_new_session"])

    def test_interrupted_git_run_terminates_kills_and_reaps_the_process_group(self) -> None:
        process = Mock(pid=321, returncode=None)
        process.communicate.side_effect = InterruptionError(signal.SIGTERM)
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired("git", 1), 0]

        with (
            patch("git_history_sanitize.git.subprocess.Popen", return_value=process),
            patch("git_history_sanitize.git.os.killpg") as kill_group,
            self.assertRaises(InterruptionError),
        ):
            run(["status"])

        self.assertEqual(
            kill_group.call_args_list,
            [call(321, signal.SIGTERM), call(321, signal.SIGKILL)],
        )
        self.assertEqual(process.wait.call_count, 2)

    def test_workspace_lock_is_inherited_by_rewrite_children(self) -> None:
        process = Mock(pid=123, returncode=0)
        process.communicate.return_value = (b"", b"")

        with (
            hold_process_lock(9),
            patch("git_history_sanitize.git.subprocess.Popen", return_value=process) as popen,
        ):
            run(["status"])

        self.assertEqual(popen.call_args.kwargs["pass_fds"], (9,))


if __name__ == "__main__":
    unittest.main()
