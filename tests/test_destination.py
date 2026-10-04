"""Stable reservations reject collisions before analysis and inherit into children."""

from __future__ import annotations

import os
import subprocess
import sys
import signal
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from git_history_sanitize.destination import reserve, reservation_name, validate
from git_history_sanitize.errors import DestinationError
from git_history_sanitize.git import finish_process, start_process
from git_history_sanitize.workspace import list_workspaces
from tests.support.git_fixture import GitFixture


class DestinationTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.parent = Path(temporary.name).resolve()
        self.output = self.parent / "output.git"

    def test_paths_and_collisions_fail_before_creating_reservations(self) -> None:
        (self.parent / "file").write_text("safe sentinel")
        (self.parent / "link").symlink_to("missing")
        for path in ("relative", str(self.parent) + "/./output", self.parent / "file", self.parent / "link", self.parent / "missing" / "output", self.parent / "file" / "output", self.parent / ".ghs-destination-lock-forbidden"):
            with self.subTest(path=path), self.assertRaises(DestinationError):
                validate(path, (), "Output")
        with self.assertRaises(DestinationError):
            validate(self.output, (self.parent,), "Output")
        self.assertEqual(list(self.parent.glob(".ghs-destination-lock-*")), [])

    def test_stable_private_empty_lock_is_reused_not_unlinked_or_cleaned(self) -> None:
        with reserve((self.output,), ()):
            lock = self.parent / reservation_name(self.output.name)
            inode = lock.stat().st_ino
            self.assertEqual(lock.stat().st_mode & 0o777, 0o600)
            self.assertEqual(lock.read_bytes(), b"")
            with self.assertRaises(DestinationError) as caught:
                with reserve((self.output,), ()):
                    self.fail("busy destination entered")
            self.assertEqual(caught.exception.metadata.code, "destination.busy")
            with reserve((self.parent / "independent",), ()):
                pass
        with reserve((self.output,), ()):
            self.assertEqual(lock.stat().st_ino, inode)
        self.assertEqual(list_workspaces(self.parent), ())
        self.assertTrue(lock.exists())

    def test_unsafe_lock_entries_are_not_repaired_or_removed(self) -> None:
        lock = self.parent / reservation_name(self.output.name)
        for kind in ("symlink", "fifo", "mode", "content", "hardlink"):
            with self.subTest(kind=kind):
                if kind == "symlink":
                    lock.symlink_to("missing")
                elif kind == "fifo":
                    os.mkfifo(lock, 0o600)
                else:
                    lock.touch(mode=0o600)
                    if kind == "mode":
                        lock.chmod(0o644)
                    if kind == "content":
                        lock.write_bytes(b"sentinel")
                    if kind == "hardlink":
                        os.link(lock, self.parent / "other-link")
                before = lock.lstat()
                with self.assertRaises(DestinationError) as caught:
                    with reserve((self.output,), ()):
                        pass
                self.assertEqual(caught.exception.metadata.code, "destination.reservation_unsafe")
                self.assertEqual(lock.lstat(), before)
                lock.unlink()
                if kind == "hardlink":
                    (self.parent / "other-link").unlink()

    def test_shared_receipt_alias_and_partial_failure_release(self) -> None:
        receipt = self.parent / "receipt.json"
        with reserve((receipt,), ()):
            with self.assertRaises(DestinationError):
                with reserve((self.output, receipt), ()):
                    pass
            with reserve((self.output,), ()):
                pass
        for alias in ("OUTPUT.GIT", "out\u00e9", "oute\u0301"):
            if alias == "OUTPUT.GIT":
                self.assertEqual(reservation_name(alias), reservation_name(self.output.name))
        self.assertEqual(reservation_name("out\u00e9"), reservation_name("oute\u0301"))
        with self.assertRaises(DestinationError):
            with reserve((self.output, self.output / "receipt"), ()):
                pass

    def test_close_only_release_keeps_child_reservation_alive(self) -> None:
        read_ready, write_ready = os.pipe()
        read_release, write_release = os.pipe()
        child = None
        try:
            with reserve((self.output,), ()):
                child = start_process([sys.executable, "-c", "import os,sys; os.write(int(sys.argv[1]),b'R'); os.read(int(sys.argv[2]),1)", str(write_ready), str(read_release)], pass_fds=(write_ready, read_release), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.assertEqual(os.read(read_ready, 1), b"R")
            with self.assertRaises(DestinationError):
                with reserve((self.output,), ()):
                    pass
            os.write(write_release, b"X")
            child.wait(timeout=10)
            finish_process(child)
            with reserve((self.output,), ()):
                pass
        finally:
            if child is not None and child.poll() is None:
                child.kill()
                child.wait()
                finish_process(child)
            for descriptor in (read_ready, write_ready, read_release, write_release):
                os.close(descriptor)

    def test_unsupported_lock_primitive_fails_closed(self) -> None:
        with patch("git_history_sanitize.destination.fcntl.flock", side_effect=OSError), self.assertRaises(DestinationError):
            with reserve((self.output,), ()):
                pass

    def test_wrong_owner_and_replaced_lock_fail_without_repair(self) -> None:
        lock = self.parent / reservation_name(self.output.name)
        lock.touch(mode=0o600)
        for identity in ("getuid", "getgid"):
            with patch(f"git_history_sanitize.destination.os.{identity}", return_value=-1), self.assertRaises(DestinationError) as caught:
                with reserve((self.output,), ()):
                    pass
            self.assertEqual(caught.exception.metadata.code, "destination.reservation_unsafe")
        import fcntl
        original = fcntl.flock
        def replace_during_acquisition(descriptor: int, operation: int) -> None:
            original(descriptor, operation)
            lock.unlink()
            lock.touch(mode=0o600)
        with patch("git_history_sanitize.destination.fcntl.flock", side_effect=replace_during_acquisition), self.assertRaises(DestinationError) as caught:
            with reserve((self.output,), ()):
                pass
        self.assertEqual(caught.exception.metadata.code, "destination.reservation_unsafe")

    def test_busy_output_and_shared_receipt_never_enter_analysis_or_clone(self) -> None:
        from git_history_sanitize.engine import rewrite
        from git_history_sanitize.policy import Policy

        fixture = GitFixture(self)
        fixture.write("file", "safe")
        cutoff = fixture.commit("initial", "file")
        policy = Policy.from_file(fixture.write_policy(cutoff=None, cutoff_commit=cutoff))
        receipt = fixture.receipt_dir / "receipt.json"
        output = fixture.output_dir / "output.git"
        ready_read, ready_write = os.pipe()
        release_read, release_write = os.pipe()
        script = """
import os, sys
from git_history_sanitize.engine import rewrite
from git_history_sanitize.errors import SanitizeError
from git_history_sanitize.policy import Policy
from unittest.mock import patch
def barrier(*args):
    os.write(int(sys.argv[5]), b'R')
    os.read(int(sys.argv[6]), 1)
    raise SanitizeError('barrier stopped before graph traversal')
with patch('git_history_sanitize.engine.RewriteAnalysis.create', side_effect=barrier):
    try:
        rewrite(sys.argv[1], sys.argv[2], Policy.from_file(sys.argv[3]), sys.argv[4])
    except SanitizeError:
        pass
"""
        child = subprocess.Popen([sys.executable, "-I", "-c", script, str(fixture.source), str(output), str(fixture.root / "policy.yml"), str(receipt), str(ready_write), str(release_read)], env=fixture.environment, pass_fds=(ready_write, release_read), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            import select
            self.assertTrue(select.select([ready_read], [], [], 10)[0], "writer did not reach reserved analysis barrier")
            self.assertEqual(os.read(ready_read, 1), b"R")
            for candidate, evidence in ((output, fixture.receipt_dir / "different.json"), (fixture.output_dir / "different.git", receipt)):
                with patch.dict(os.environ, fixture.environment, clear=True), patch("git_history_sanitize.engine.RewriteAnalysis.create") as analysis, patch("git_history_sanitize.git.Repository.clone_to") as clone:
                    with self.assertRaises(DestinationError) as caught:
                        rewrite(fixture.source, candidate, policy, evidence)
                    self.assertEqual(caught.exception.metadata.code, "destination.busy")
                    analysis.assert_not_called()
                    clone.assert_not_called()
            fixture.assert_no_staging_directories(fixture.output_dir)
            fixture.assert_no_staging_directories(fixture.receipt_dir)
        finally:
            os.write(release_write, b"X")
            child.communicate(timeout=10)
            for descriptor in (ready_read, ready_write, release_read, release_write):
                os.close(descriptor)

    def test_sigkill_parent_does_not_release_orphan_child_reservation(self) -> None:
        import select

        ready_read, ready_write = os.pipe()
        release_read, release_write = os.pipe()
        script = """
import os,sys
from pathlib import Path
from git_history_sanitize.destination import reserve
from git_history_sanitize.git import start_process
with reserve((Path(sys.argv[1]),), ()):
    child = start_process([sys.executable, '-c', 'import os,sys; os.write(int(sys.argv[1]),b"R"); os.read(int(sys.argv[2]),1)', sys.argv[2], sys.argv[3]], pass_fds=(int(sys.argv[2]),int(sys.argv[3])))
    child.wait()
"""
        parent = subprocess.Popen([sys.executable, "-I", "-c", script, str(self.output), str(ready_write), str(release_read)], pass_fds=(ready_write, release_read), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            self.assertTrue(select.select([ready_read], [], [], 10)[0])
            self.assertEqual(os.read(ready_read, 1), b"R")
            parent.send_signal(signal.SIGKILL)
            parent.wait(timeout=10)
            with self.assertRaises(DestinationError) as caught:
                with reserve((self.output,), ()):
                    pass
            self.assertEqual(caught.exception.metadata.code, "destination.busy")
        finally:
            os.write(release_write, b"X")
            if parent.poll() is None:
                parent.kill()
                parent.wait()
            for descriptor in (ready_read, ready_write, release_read, release_write):
                os.close(descriptor)


if __name__ == "__main__":
    unittest.main()
