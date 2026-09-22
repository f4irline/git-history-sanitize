"""Private sanitizer workspace ownership and cleanup contracts."""

from __future__ import annotations

import json
import os
import stat
import tempfile
import threading
import unittest
from unittest.mock import patch
from pathlib import Path

from git_history_sanitize.errors import InterruptionError, UsageError, WorkspaceError
from git_history_sanitize.workspace import Workspace, clean_workspace, list_workspaces


class WorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.parent = Path(self.temporary.name).resolve()

    def test_workspace_is_private_owned_and_removed_after_success(self) -> None:
        previous_umask = os.umask(0)
        try:
            with Workspace.create(self.parent) as workspace:
                manifest = workspace.path / "ownership.json"
                lock = workspace.path / "lock"
                payload = json.loads(manifest.read_text(encoding="ascii"))

                self.assertEqual(stat.S_IMODE(workspace.path.stat().st_mode), 0o700)
                self.assertEqual(stat.S_IMODE(manifest.stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE(lock.stat().st_mode), 0o600)
                self.assertEqual(payload["id"], workspace.id)
                self.assertEqual(payload["uid"], os.getuid())
                self.assertEqual(payload["gid"], os.getgid())
                self.assertNotIn(str(self.parent), manifest.read_text(encoding="ascii"))
                self.assertEqual(list_workspaces(self.parent)[0].state, "active")
        finally:
            os.umask(previous_umask)

        self.assertFalse(workspace.path.exists())
        self.assertEqual(list_workspaces(self.parent), ())

    def test_interruption_retains_recognizable_stale_workspace_until_explicit_cleanup(self) -> None:
        workspace_path: Path | None = None
        workspace_id = ""

        with self.assertRaises(InterruptionError):
            with Workspace.create(self.parent) as workspace:
                workspace_path = workspace.path
                workspace_id = workspace.id
                raise InterruptionError(15)

        assert workspace_path is not None
        self.assertTrue(workspace_path.is_dir())
        self.assertEqual(stat.S_IMODE(workspace_path.stat().st_mode), 0o700)
        self.assertEqual(list_workspaces(self.parent)[0].state, "interrupted")

        cleaned = clean_workspace(self.parent, workspace_id)

        self.assertEqual(cleaned.id, workspace_id)
        self.assertFalse(workspace_path.exists())

    def test_cleanup_refuses_active_ambiguous_and_broad_targets(self) -> None:
        with Workspace.create(self.parent) as workspace:
            with self.assertRaises(WorkspaceError):
                clean_workspace(self.parent, workspace.id)

        ambiguous = self.parent / (".git-history-sanitize-" + "a" * 32)
        ambiguous.mkdir(mode=0o700)
        self.assertEqual(list_workspaces(self.parent)[0].state, "ambiguous")
        with self.assertRaises(WorkspaceError):
            clean_workspace(self.parent, "a" * 32)
        with self.assertRaises(UsageError):
            clean_workspace(self.parent, "*")
        self.assertTrue(ambiguous.is_dir())

    def test_cleanup_refuses_symlinked_workspace_without_following_it(self) -> None:
        outside = self.parent / "outside"
        outside.mkdir()
        marker = outside / "keep"
        marker.write_text("keep", encoding="ascii")
        workspace_id = "b" * 32
        (self.parent / f".git-history-sanitize-{workspace_id}").symlink_to(outside)

        records = list_workspaces(self.parent)

        self.assertEqual(records[0].state, "ambiguous")
        with self.assertRaises(WorkspaceError):
            clean_workspace(self.parent, workspace_id)
        self.assertEqual(marker.read_text(encoding="ascii"), "keep")

    def test_cleanup_refuses_symlinked_parent_and_published_lookalike(self) -> None:
        linked_parent = self.parent.parent / f"{self.parent.name}-link"
        linked_parent.symlink_to(self.parent, target_is_directory=True)
        self.addCleanup(linked_parent.unlink)
        with self.assertRaises(WorkspaceError):
            list_workspaces(linked_parent)

        workspace_id = "c" * 32
        published = self.parent / f".git-history-sanitize-{workspace_id}"
        published.mkdir(mode=0o700)
        (published / "HEAD").write_text("ref: refs/heads/main\n", encoding="ascii")
        with self.assertRaises(WorkspaceError):
            clean_workspace(self.parent, workspace_id)
        self.assertEqual(
            (published / "HEAD").read_text(encoding="ascii"),
            "ref: refs/heads/main\n",
        )

    def test_cleanup_unlinks_nested_symlinks_without_following_them(self) -> None:
        outside = self.parent / "outside"
        outside.mkdir()
        marker = outside / "keep"
        marker.write_text("keep", encoding="ascii")
        with self.assertRaises(InterruptionError):
            with Workspace.create(self.parent) as workspace:
                workspace_id = workspace.id
                raise InterruptionError(2)
        (workspace.path / "nested-link").symlink_to(outside, target_is_directory=True)

        clean_workspace(self.parent, workspace_id)

        self.assertEqual(marker.read_text(encoding="ascii"), "keep")

    def test_malformed_or_wrong_mode_metadata_is_ambiguous_and_retained(self) -> None:
        with self.assertRaises(InterruptionError):
            with Workspace.create(self.parent) as workspace:
                workspace_id = workspace.id
                raise InterruptionError(2)
        manifest = workspace.path / "ownership.json"
        manifest.write_text("{}", encoding="ascii")
        manifest.chmod(0o644)

        self.assertEqual(list_workspaces(self.parent)[0].state, "ambiguous")
        with self.assertRaises(WorkspaceError):
            clean_workspace(self.parent, workspace_id)
        self.assertTrue(workspace.path.is_dir())

    def test_disk_full_during_manifest_creation_removes_partial_workspace(self) -> None:
        with patch(
            "git_history_sanitize.workspace._write_file",
            side_effect=OSError(28, "private filesystem detail"),
        ):
            with self.assertRaises(WorkspaceError):
                Workspace.create(self.parent)

        self.assertEqual(list(self.parent.iterdir()), [])

    def test_signal_during_manifest_creation_preserves_signal_exit_semantics(self) -> None:
        with patch(
            "git_history_sanitize.workspace._write_file",
            side_effect=InterruptionError(15),
        ):
            with self.assertRaises(InterruptionError) as raised:
                Workspace.create(self.parent)

        self.assertEqual(raised.exception.signum, 15)
        self.assertEqual(list(self.parent.iterdir()), [])

    def test_only_one_concurrent_cleaner_can_remove_a_stale_workspace(self) -> None:
        with self.assertRaises(InterruptionError):
            with Workspace.create(self.parent) as workspace:
                workspace_id = workspace.id
                raise InterruptionError(2)
        barrier = threading.Barrier(2)
        results: list[str] = []

        def clean() -> None:
            barrier.wait()
            try:
                clean_workspace(self.parent, workspace_id)
                results.append("cleaned")
            except WorkspaceError:
                results.append("refused")

        threads = [threading.Thread(target=clean) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(sorted(results), ["cleaned", "refused"])


if __name__ == "__main__":
    unittest.main()
