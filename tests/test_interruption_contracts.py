"""Real-signal rewrite interruption and recovery contracts."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import unittest

from git_history_sanitize.workspace import clean_workspace, list_workspaces
from tests.support.git_fixture import GitFixture


class InterruptionContractTests(unittest.TestCase):
    def test_abrupt_owner_exit_stays_active_until_inherited_child_lock_closes(self) -> None:
        fixture = GitFixture(self)
        script = """
import os
import subprocess
import sys
from git_history_sanitize.git import hold_process_lock, start_process
from git_history_sanitize.workspace import Workspace

workspace = Workspace.create(sys.argv[1])
with hold_process_lock(workspace.lock_descriptor):
    start_process(
        [sys.executable, "-c", "import time; time.sleep(1.5)"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    os._exit(0)
"""

        subprocess.run(
            [sys.executable, "-I", "-c", script, str(fixture.output_dir)],
            check=True,
            env=fixture.environment,
        )

        active = list_workspaces(fixture.output_dir)
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].state, "active")
        deadline = time.monotonic() + 5
        records = active
        while time.monotonic() < deadline:
            records = list_workspaces(fixture.output_dir)
            if records[0].state == "stale":
                break
            time.sleep(0.05)
        self.assertEqual(records[0].state, "stale")

        clean_workspace(fixture.output_dir, records[0].id)

    def test_sigterm_stops_children_and_retains_one_private_stale_workspace(self) -> None:
        fixture = GitFixture(self)
        fixture.write("large.bin", "x" * (16 * 1024 * 1024))
        fixture.commit("large source", "large.bin")
        policy = fixture.write_policy(excluded_paths=("large.bin",))
        output = fixture.output_dir / "sanitized.git"
        source_snapshot = fixture.snapshot_source()
        command = [
            fixture.python_executable,
            "-I",
            "-m",
            "git_history_sanitize",
            "rewrite",
            "--source",
            str(fixture.source / ".git"),
            "--output",
            str(output),
            "--policy",
            str(policy),
        ]
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=fixture.environment,
        )
        deadline = time.monotonic() + 10
        workspace = None
        while time.monotonic() < deadline and process.poll() is None:
            candidates = tuple(fixture.output_dir.glob(".git-history-sanitize-*"))
            if candidates and (candidates[0] / "rewrite").exists():
                workspace = candidates[0]
                break
            time.sleep(0.005)
        self.assertIsNotNone(workspace, "rewrite did not expose an active workspace")

        os.kill(process.pid, signal.SIGTERM)
        stdout, stderr = process.communicate(timeout=10)

        self.assertEqual(process.returncode, 143)
        self.assertEqual(stdout, "")
        self.assertEqual(
            stderr,
            "error: sanitization interrupted: List sanitizer workspaces under the output parent "
            "and clean the stale ID before retrying.\n",
        )
        self.assertFalse(output.exists())
        records = list_workspaces(fixture.output_dir)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].state, "interrupted")
        self.assertEqual(oct(workspace.stat().st_mode & 0o777), "0o700")
        fixture.assert_source_snapshot(source_snapshot)
        fixture.assert_redacted(stdout + stderr, str(workspace), str(fixture.source), "large source")

        clean_workspace(fixture.output_dir, records[0].id)
        self.assertFalse(workspace.exists())


if __name__ == "__main__":
    unittest.main()
