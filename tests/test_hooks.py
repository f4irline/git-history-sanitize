"""Trusted hook preservation and runner-template isolation contracts."""

from __future__ import annotations

import json
import shutil
import stat
import unittest

from git_history_sanitize.git import Repository
from git_history_sanitize.hooks import HookError, discover

from tests.support.git_fixture import GitFixture


class HookContractsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = GitFixture(self)
        self.fixture.write("allowed.txt", "safe\n")
        self.fixture.commit("allowed", "allowed.txt")
        self.policy = self.fixture.write_policy()

    def _rewrite(self, *arguments: str):
        output = self.fixture.output_dir / "sanitized.git"
        result = self.fixture.run_cli(
            "rewrite", "--source", str(self.fixture.source / ".git"), "--output", str(output),
            "--policy", str(self.policy), *arguments,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        return output, result

    def test_preserves_executable_standard_hooks_and_ignores_samples(self) -> None:
        hooks = self.fixture.source / ".git" / "hooks"
        hooks.mkdir()
        hook = hooks / "pre-commit"
        hook.write_bytes(b"#!/bin/sh\nexit 0\n")
        hook.chmod(0o751)
        (hooks / "pre-commit.sample").write_bytes(b"template-only\n")
        source = self.fixture.snapshot_source()

        output, result = self._rewrite("--json")

        preserved = output / "hooks" / "pre-commit"
        self.assertEqual(preserved.read_bytes(), hook.read_bytes())
        self.assertEqual(
            stat.S_IMODE(preserved.stat().st_mode) & 0o111,
            stat.S_IMODE(hook.stat().st_mode) & 0o111,
        )
        self.assertFalse((output / "hooks" / "pre-commit.sample").exists())
        self.assertEqual(json.loads(result.stdout)["result"]["hooks"]["names"], ["pre-commit"])
        self.fixture.assert_source_snapshot(source)

    def test_preserves_local_custom_hooks_path_in_output_configuration(self) -> None:
        custom = self.fixture.source / ".git" / "trusted-hooks"
        custom.mkdir()
        (custom / "post-commit").write_bytes(b"#!/bin/sh\necho safe\n")
        self.fixture.git(self.fixture.source, "config", "--local", "core.hooksPath", "trusted-hooks")

        output, _ = self._rewrite()

        self.assertEqual((output / "hooks" / "post-commit").read_bytes(), b"#!/bin/sh\necho safe\n")
        self.assertEqual(self.fixture.git(output, "config", "--local", "--get", "core.hooksPath"), "hooks")

    def test_preserves_worktree_local_hooks_path_and_reports_portability_warning(self) -> None:
        custom = self.fixture.source / ".trusted-hooks"
        custom.mkdir()
        (custom / "pre-push").write_bytes(b"#!/usr/bin/env sh\nexec /opt/tools/check\n")
        self.fixture.git(self.fixture.source, "config", "--local", "core.hooksPath", ".trusted-hooks")

        plan = self.fixture.run_cli(
            "plan", "--source", str(self.fixture.source / ".git"), "--policy", str(self.policy), "--json"
        )
        output, rewrite = self._rewrite("--json")

        for result in (plan, rewrite):
            hooks = json.loads(result.stdout)["result"]["hooks"]
            self.assertEqual(hooks["warnings"], {
                "absolute-path": ["pre-push"], "absolute-shebang": ["pre-push"],
            })
            self.assertNotIn("/opt/tools/check", result.stdout)
        self.assertTrue((output / "hooks" / "pre-push").is_file())

    def test_runner_template_hooks_never_enter_output(self) -> None:
        template_hook = self.fixture.template_dir / "hooks" / "post-checkout"
        template_hook.parent.mkdir()
        template_hook.write_bytes(b"runner-private\n")
        hooks = self.fixture.source / ".git" / "hooks"
        hooks.mkdir()
        (hooks / "pre-commit").write_bytes(b"source-safe\n")

        output, _ = self._rewrite()

        self.assertTrue((output / "hooks" / "pre-commit").is_file())
        self.assertFalse((output / "hooks" / "post-checkout").exists())

    def test_strip_hooks_excludes_source_hooks_and_reports_selection(self) -> None:
        hooks = self.fixture.source / ".git" / "hooks"
        hooks.mkdir()
        (hooks / "pre-commit").write_bytes(b"source-safe\n")

        output, result = self._rewrite("--strip-hooks", "--json")

        self.assertFalse((output / "hooks" / "pre-commit").exists())
        self.assertEqual(json.loads(result.stdout)["result"]["hooks"], {
            "action": "stripped", "count": 1, "names": ["pre-commit"], "warnings": {},
        })

    def test_bare_source_rejects_hooks_path_outside_its_git_directory(self) -> None:
        bare = self.fixture.root / "source.git"
        self.fixture.git(self.fixture.root, "clone", "--bare", str(self.fixture.source / ".git"), str(bare))
        outside = self.fixture.root / "foreign-hooks"
        outside.mkdir()
        (outside / "pre-push").write_bytes(b"outside-private\n")
        self.fixture.git(bare, "config", "--local", "core.hooksPath", "../foreign-hooks")
        with self.assertRaises(HookError) as error:
            discover(Repository(bare))
        self.assertIn("core.hooksPath", str(error.exception))
        self.assertNotIn("foreign-hooks", str(error.exception))

        output = self.fixture.root.parent / f"{self.fixture.root.name}-sanitized.git"
        self.addCleanup(shutil.rmtree, output, ignore_errors=True)
        result = self.fixture.run_cli(
            "rewrite", "--source", str(bare), "--output", str(output), "--policy", str(self.policy),
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("core.hooksPath", result.stderr)
        self.assertNotIn("foreign-hooks", result.stderr)
        self.assertFalse(output.exists())

    def test_forbidden_content_checks_preserved_active_hooks_but_not_samples(self) -> None:
        hooks = self.fixture.source / ".git" / "hooks"
        hooks.mkdir()
        (hooks / "pre-commit").write_bytes(b"private-marker\n")
        (hooks / "pre-commit.sample").write_bytes(b"ignored-marker\n")
        output, _ = self._rewrite()

        active = self.fixture.run_cli(
            "verify", "--repository", str(output), "--policy", str(self.policy),
            "--forbid", "private-marker", check=False,
        )
        sample = self.fixture.run_cli(
            "verify", "--repository", str(output), "--policy", str(self.policy),
            "--forbid", "ignored-marker",
        )

        self.assertEqual(active.returncode, 2)
        self.assertEqual(active.stderr, "error: verification failed: content.forbidden\n")
        self.assertEqual(sample.returncode, 0, sample.stderr)


if __name__ == "__main__":
    unittest.main()
