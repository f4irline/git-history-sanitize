"""Source forms, state observations, and read-only source contracts."""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from git_history_sanitize.errors import SourceError
from git_history_sanitize.git import Repository, parse_worktree_status
from tests.support.git_fixture import GitFixture


class DiscoveryUnits(unittest.TestCase):
    def test_binary_status_categories_and_malformed_records(self) -> None:
        state = parse_worktree_status(b"M  staged\0 M newline\nname\0?? \xff\0!! ignored/\0UU conflict\0")
        self.assertEqual(state, (True, True, True, True, True))
        for raw in (b"M  truncated", b"garbage\0", b"R  rename\0", b"?? \0"):
            with self.subTest(raw=raw), self.assertRaises(SourceError):
                parse_worktree_status(raw)

    def test_discovery_proves_linked_and_metadata_roots(self) -> None:
        fixture = GitFixture(self)
        fixture.write("file", "committed")
        fixture.commit("initial", "file")
        linked = fixture.root / "linked"
        fixture.git(fixture.source, "worktree", "add", "-b", "selected", str(linked))
        with patch.dict(os.environ, fixture.environment, clear=True):
            for source in (linked, linked / ".git", Path(fixture.git(linked, "rev-parse", "--absolute-git-dir"))):
                repository = Repository(source)
                self.assertEqual(repository.discovery.kind, "linked-worktree")
                self.assertEqual(repository.worktree_root(), linked)
                self.assertEqual(repository.validate_head(), "refs/heads/selected")
                self.assertEqual(repository.git_path("objects"), fixture.source / ".git" / "objects")
            moved = fixture.root / "metadata"
            fixture.git(fixture.root, "clone", "--no-local", "--bare", str(fixture.source), str(moved))
            self.assertEqual(Repository(moved).discovery.kind, "bare")

    def test_metadata_only_separate_git_dir_and_hostile_context(self) -> None:
        import shutil

        fixture = GitFixture(self)
        fixture.write("file", "safe")
        fixture.commit("initial", "file")
        metadata = fixture.root / "metadata"
        shutil.copytree(fixture.source / ".git", metadata)
        separate, external = fixture.root / "separate", fixture.root / "external-git"
        fixture.git(fixture.root, "init", "--separate-git-dir", str(external), str(separate))
        with patch.dict(os.environ, fixture.environment | {"GIT_DIR": str(metadata), "GIT_WORK_TREE": str(fixture.home), "GIT_OBJECT_DIRECTORY": str(fixture.home)}, clear=True):
            state = Repository(metadata).source_state()
            self.assertEqual(state.inspection, "unavailable")
            self.assertEqual(Repository(separate / ".git").discovery.kind, "working-tree")
            self.assertEqual(Repository(separate / ".git").worktree_root(), separate)
            self.assertEqual(Repository(fixture.source).worktree_root(), fixture.source)
            self.assertEqual(Repository(fixture.source).validate_head(), "refs/heads/main")

    def test_fsmonitor_never_executes_and_status_failure_is_not_clean(self) -> None:
        fixture = GitFixture(self)
        fixture.write("file", "safe")
        fixture.commit("initial", "file")
        marker = fixture.source / "executed"
        monitor = fixture.source / ".git" / "monitor"
        monitor.write_text(f"#!/bin/sh\ntouch '{marker}'\n")
        monitor.chmod(0o700)
        fixture.git(fixture.source, "config", "core.fsmonitor", str(monitor))
        with patch.dict(os.environ, fixture.environment, clear=True):
            repository = Repository(fixture.source)
            before = (fixture.source / ".git" / "index").read_bytes()
            self.assertEqual(repository.source_state().inspection, "inspected")
            self.assertEqual((fixture.source / ".git" / "index").read_bytes(), before)
            self.assertFalse(marker.exists())
            original = repository.run
            from git_history_sanitize.git import GitError
            def failed_status(*arguments: str, **kwargs: object) -> bytes:
                if "status" in arguments:
                    raise GitError("unsafe raw stderr")
                return original(*arguments, **kwargs)
            with patch.object(repository, "run", side_effect=failed_status), self.assertRaises(SourceError) as caught:
                repository.source_state()
            self.assertEqual(caught.exception.metadata.code, "source.state_unavailable")


class SourceDiscoveryContracts(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = GitFixture(self)
        self.fixture.write("dir/file", "committed\n")
        self.fixture.commit("initial", "dir/file")
        self.policy = self.fixture.write_policy()

    def plan(self, source: Path | None, *, cwd: Path | None = None, trusted: bool = False) -> dict:
        args = ["plan", "--policy", str(self.policy), "--json"]
        if source is not None:
            args += ["--source", str(source)]
        if trusted:
            args += ["--diagnostics=trusted"]
        result = self.fixture.run_cli(*args, check=False, cwd=cwd)
        self.assertEqual(result.stderr, "")
        return json.loads(result.stdout)

    def test_explicit_forms_have_equivalent_committed_output(self) -> None:
        fixture = self.fixture
        bare = fixture.root / "bare.git"
        linked = fixture.root / "linked"
        fixture.git(fixture.root, "clone", "--bare", "--no-local", str(fixture.source), str(bare))
        fixture.git(fixture.source, "worktree", "add", "--force", str(linked), "main")
        private = Path(fixture.git(linked, "rev-parse", "--absolute-git-dir"))
        expected = None
        for index, source in enumerate((fixture.source, fixture.source / ".git", bare, linked, linked / ".git", private)):
            with self.subTest(source_form=index):
                planned = self.plan(source, trusted=True)
                self.assertEqual(planned["status"], "success")
                self.assertEqual(planned["diagnostics"]["symbolic_retained_ref"], "refs/heads/main")
                output = fixture.output_dir / f"output-{index}.git"
                result = fixture.run_cli("rewrite", "--source", str(source), "--output", str(output), "--policy", str(self.policy), "--json")
                self.assertEqual(result.stderr, "")
                snapshot = fixture.snapshot_output(output)
                expected = snapshot if expected is None else expected
                self.assertEqual(snapshot, expected)

    def test_implicit_nested_cwd_but_explicit_subdirectory_rejected(self) -> None:
        for cwd in (self.fixture.source, self.fixture.source / "dir"):
            self.assertEqual(self.plan(None, cwd=cwd)["status"], "success")
        for source in (self.fixture.source / "dir", self.fixture.root / "missing"):
            payload = self.plan(source)
            self.assertEqual(payload["code"], "source.invalid_location")
            self.assertNotIn(str(source), json.dumps(payload))
        self.assertEqual(self.plan(None, cwd=self.fixture.home)["code"], "source.invalid_location")

    def test_dirty_state_warns_without_mutating_or_including_files(self) -> None:
        fixture = self.fixture
        fixture.write(".gitignore", "ignored\n")
        fixture.commit("ignore rule", ".gitignore")
        fixture.write("dir/file", "safe-dirty-sentinel")
        fixture.git(fixture.source, "add", "dir/file")
        fixture.write("dir/file", "safe-unstaged-sentinel")
        fixture.write("untracked", "safe-untracked-sentinel")
        fixture.write("ignored", "safe-ignored-sentinel")
        before = fixture.snapshot_source()
        payload = self.plan(fixture.source)
        state = payload["result"]["source"]["worktree"]
        self.assertEqual(state, {"inspection": "inspected", "staged": True, "unstaged": True, "untracked": True, "ignored": True, "unmerged": False})
        self.assertEqual([warning["code"] for warning in payload["result"]["warnings"]], ["source.committed_history_only", "source.working_tree_content_excluded"])
        output = fixture.output_dir / "dirty.git"
        result = fixture.run_cli("rewrite", "--source", str(fixture.source), "--output", str(output), "--policy", str(self.policy), "--json")
        self.assertEqual(result.stderr, "")
        fixture.assert_source_snapshot(before)
        self.assertEqual(fixture.git(output, "show", "HEAD:dir/file"), "committed")
        self.assertNotIn("sentinel", result.stdout)

    def test_rename_and_conflict_are_observed_without_names_or_index_writes(self) -> None:
        fixture = self.fixture
        fixture.git(fixture.source, "mv", "dir/file", "dir/renamed file")
        payload = self.plan(fixture.source)
        self.assertTrue(payload["result"]["source"]["worktree"]["staged"])
        self.assertNotIn("renamed file", json.dumps(payload))
        # Build conflict topology before its first OCI mount, independently.
        fixture = self.fixture = GitFixture(self)
        fixture.write("dir/file", "base\n")
        fixture.commit("base", "dir/file")
        self.policy = fixture.write_policy()
        fixture.git(fixture.source, "checkout", "-b", "side")
        fixture.write("dir/file", "side\n")
        fixture.commit("side", "dir/file")
        fixture.git(fixture.source, "checkout", "main")
        fixture.write("dir/file", "main\n")
        fixture.commit("main", "dir/file")
        fixture.git(fixture.source, "merge", "side", check=False)
        before = fixture.snapshot_source()
        payload = self.plan(fixture.source)
        state = payload["result"]["source"]["worktree"]
        self.assertTrue(state["unmerged"] and state["staged"] and state["unstaged"])
        fixture.assert_source_snapshot(before)

    def test_detached_and_unborn_have_fixed_actionable_diagnostics(self) -> None:
        fixture = self.fixture
        fixture.git(fixture.source, "checkout", "--detach")
        self.assertEqual(self.plan(fixture.source)["code"], "source.detached_head")
        # Preserve the HEAD inode across repeated read-only OCI mounts (BBQ-44).
        (fixture.source / ".git" / "HEAD").write_text("ref: refs/heads/empty\n")
        self.assertEqual(self.plan(fixture.source)["code"], "source.unborn_head")

    def test_snapshot_also_requires_symbolic_committed_head(self) -> None:
        self.policy = self.fixture.write_policy(cutoff=None, source_mode="snapshot")
        self.fixture.git(self.fixture.source, "checkout", "--detach")
        self.assertEqual(self.plan(self.fixture.source)["code"], "source.detached_head")

    def test_invalid_receipt_parent_fails_before_staging(self) -> None:
        fixture = self.fixture
        policy = fixture.write_policy(cutoff=None, cutoff_commit=fixture.git(fixture.source, "rev-parse", "HEAD"))
        output, receipt = fixture.output_dir / "valid.git", fixture.receipt_dir / "missing" / "receipt.json"
        result = fixture.run_cli("rewrite", "--source", str(fixture.source), "--output", str(output), "--receipt", str(receipt), "--policy", str(policy), "--json", check=False)
        self.assertEqual(json.loads(result.stdout)["code"], "destination.invalid")
        self.assertFalse(output.exists())
        self.assertEqual(list(fixture.output_dir.iterdir()), [])

    def test_linked_selected_head_and_relative_gitfile(self) -> None:
        fixture = self.fixture
        linked = fixture.root / "linked"
        fixture.git(fixture.source, "worktree", "add", "-b", "selected", str(linked))
        (linked / "dir/file").write_text("selected committed content")
        fixture.git(linked, "add", "dir/file")
        fixture.git(linked, "commit", "-qm", "selected commit")
        private = Path(fixture.git(linked, "rev-parse", "--absolute-git-dir"))
        (linked / ".git").write_text(f"gitdir: {os.path.relpath(private, linked)}\n")
        payload = self.plan(linked / ".git", trusted=True)
        self.assertEqual(payload["diagnostics"]["symbolic_retained_ref"], "refs/heads/selected")
        output = fixture.output_dir / "selected.git"
        fixture.run_cli("rewrite", "--source", str(linked / ".git"), "--output", str(output), "--policy", str(self.policy))
        self.assertEqual(fixture.git(output, "show", "HEAD:dir/file"), "selected committed content")

    def test_linked_shared_scope_markers_cannot_bypass_preflight(self) -> None:
        fixture = self.fixture
        linked = fixture.root / "linked"
        fixture.git(fixture.source, "worktree", "add", "-b", "selected", str(linked))
        common = fixture.source / ".git"
        for relative, content in (("shallow", fixture.git(fixture.source, "rev-parse", "HEAD") + "\n"), ("info/grafts", ""), ("objects/info/alternates", ""), ("objects/pack/test.promisor", "")):
            with self.subTest(marker=relative):
                marker = common / relative
                marker.parent.mkdir(exist_ok=True)
                marker.write_text(content)
                payload = self.plan(linked / ".git")
                self.assertEqual(payload["code"], "source.invalid")
                marker.unlink()

    def test_linked_shared_hooks_receipts_and_complete_snapshots(self) -> None:
        fixture = self.fixture
        hooks = fixture.source / ".git" / "hooks"
        hooks.mkdir(exist_ok=True)
        (hooks / "pre-push").write_bytes(b"#!/bin/sh\nexit 0\n")
        linked = fixture.root / "linked"
        fixture.git(fixture.source, "worktree", "add", "-b", "selected", str(linked))
        before = fixture.snapshot_source(linked)
        main_before = fixture.snapshot_source()
        self.policy = fixture.write_policy(cutoff=None, cutoff_commit=fixture.git(linked, "rev-parse", "HEAD"))
        output, receipt = fixture.output_dir / "linked.git", fixture.receipt_dir / "linked.json"
        result = fixture.run_cli("rewrite", "--source", str(linked / ".git"), "--output", str(output), "--receipt", str(receipt), "--policy", str(self.policy), "--json", "--diagnostics=trusted")
        self.assertEqual(result.stderr, "")
        self.assertEqual((output / "hooks" / "pre-push").read_bytes(), b"#!/bin/sh\nexit 0\n")
        fixture.run_cli("verify", "--repository", str(output), "--source", str(linked / ".git"), "--receipt", str(receipt), "--policy", str(self.policy))
        self.assertEqual(fixture.snapshot_source(linked), before)
        fixture.assert_source_snapshot(main_before)
        persisted = receipt.read_text() + (output / "git-history-sanitize-scope.json").read_text()
        for transient in ("worktree", "warnings", "inspection", "committed_history_only", str(linked)):
            self.assertNotIn(transient, persisted)

    def test_all_registered_roots_and_invalid_output_parents_are_protected(self) -> None:
        fixture = self.fixture
        linked, other = fixture.root / "linked", fixture.root / "other"
        fixture.git(fixture.source, "worktree", "add", "-b", "selected", str(linked))
        fixture.git(fixture.source, "worktree", "add", "-b", "other", str(other))
        private = Path(fixture.git(linked, "rev-parse", "--absolute-git-dir"))
        for root in (fixture.source, fixture.source / ".git", linked, other, private, fixture.output_dir / "missing"):
            with self.subTest(root_kind=root.name):
                result = fixture.run_cli("rewrite", "--source", str(linked), "--output", str(root / "unsafe.git"), "--policy", str(self.policy), "--json", check=False)
                self.assertEqual(json.loads(result.stdout)["code"], "destination.invalid")
                self.assertFalse((root / "unsafe.git").exists())
        self.assertEqual(list(fixture.output_dir.iterdir()), [])

    def test_broken_gitfiles_and_metadata_only_inspection(self) -> None:
        fixture = self.fixture
        broken = fixture.root / "broken"
        broken.write_text("gitdir: missing\n")
        self.assertEqual(self.plan(broken)["code"], "source.invalid_location")
        payload = self.plan(fixture.source / ".git")
        if os.environ.get("GHS_TEST_RUNTIME") == "container":
            self.assertEqual(payload["result"]["source"]["worktree"], {"inspection": "unavailable"})
            self.assertEqual(payload["result"]["warnings"][-1]["code"], "source.working_tree_not_inspected")
        else:
            self.assertEqual(payload["result"]["source"]["worktree"]["inspection"], "inspected")


if __name__ == "__main__":
    unittest.main()
