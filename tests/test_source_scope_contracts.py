"""Source graph preflight contracts for the three v1 scopes."""

from __future__ import annotations

import json
import unittest

from tests.support.git_fixture import GitFixture


class SourceScopeContracts(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = GitFixture(self)
        self.fixture.write("tracked.txt", "safe\n")
        self.fixture.commit("tracked", "tracked.txt")

    def _plan(self, policy: object, check: bool = False) -> object:
        return self.fixture.run_cli("plan", "--source", str(self.fixture.source / ".git"), "--policy", str(policy), "--json", check=check)

    def test_complete_mode_rejects_replace_refs_before_output(self) -> None:
        head = self.fixture.git(self.fixture.source, "rev-parse", "HEAD")
        self.fixture.git(self.fixture.source, "update-ref", "refs/replace/" + head, head)
        policy = self.fixture.write_policy()
        result = self._plan(policy)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "error: Source uses replace refs; remove replacement state before sanitizing\n")

    def test_complete_mode_rejects_alternates(self) -> None:
        alternates = self.fixture.source / ".git" / "objects" / "info" / "alternates"
        alternates.parent.mkdir(parents=True, exist_ok=True)
        alternates.write_text("/untrusted/object-store\n")
        result = self._plan(self.fixture.write_policy())
        self.assertEqual(result.returncode, 2)
        self.assertIn("repack without alternates", result.stderr)

    def test_snapshot_reports_tree_only_scope(self) -> None:
        self.fixture.write("removed.txt", "old\n")
        self.fixture.commit("old", "removed.txt")
        (self.fixture.source / "removed.txt").unlink()
        self.fixture.commit("remove", "removed.txt")
        policy = self.fixture.write_policy(cutoff=None, source_mode="snapshot", prefix_message="[snapshot]")
        result = self._plan(policy, check=True)
        report = json.loads(result.stdout)
        self.assertEqual(report["mode"], "snapshot")
        self.assertEqual(report["scope"], "HEAD tree snapshot; inherited history excluded")
        self.assertEqual(report["source_commits"], 1)
        self.assertEqual(report["included_commit_count"], 1)
        self.assertEqual(report["included_object_count"], 2)

    def test_complete_plan_counts_head_history_but_preflights_all_refs(self) -> None:
        self.fixture.git(self.fixture.source, "checkout", "-qb", "side")
        self.fixture.write("side.txt", "side\n")
        self.fixture.commit("side", "side.txt")
        self.fixture.git(self.fixture.source, "checkout", "main")

        result = self._plan(self.fixture.write_policy(), check=True)

        report = json.loads(result.stdout)
        self.assertEqual(report["source_commits"], 1)
        self.assertEqual(report["included_commit_count"], 1)

    def test_complete_mode_rejects_promisor_before_output(self) -> None:
        self.fixture.git(self.fixture.source, "config", "extensions.partialClone", "origin")

        result = self._plan(self.fixture.write_policy())

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "error: Source is partial/promisor; explicitly materialize objects before sanitizing\n")

    def test_complete_mode_rejects_grafts_before_output(self) -> None:
        grafts = self.fixture.source / ".git" / "info" / "grafts"
        grafts.parent.mkdir(parents=True, exist_ok=True)
        grafts.write_text("invalid\n")

        result = self._plan(self.fixture.write_policy())

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "error: Source uses grafts; remove graft state before sanitizing\n")

    def test_complete_mode_rejects_shallow_rewrite_before_publication(self) -> None:
        shallow = self.fixture.root / "shallow"
        self.fixture.git(
            self.fixture.root, "clone", "--depth=1", f"file://{self.fixture.source}", str(shallow)
        )
        output = self.fixture.output_dir / "complete.git"

        result = self.fixture.run_cli(
            "rewrite", "--source", str(shallow / ".git"), "--policy", str(self.fixture.write_policy()),
            "--output", str(output), check=False,
        )

        self.assertEqual(result.returncode, 2)
        self.assertFalse(output.exists())
        self.assertEqual(result.stderr, "error: Source is shallow; fetch complete history or explicitly select bounded mode\n")

    def test_snapshot_mode_rejects_missing_head_tree_object(self) -> None:
        blob = self.fixture.git(self.fixture.source, "rev-parse", "HEAD:tracked.txt")
        object_path = self.fixture.source / ".git" / "objects" / blob[:2] / blob[2:]
        object_path.unlink()
        policy = self.fixture.write_policy(cutoff=None, source_mode="snapshot", prefix_message="[snapshot]")

        result = self._plan(policy)

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "error: Source has unavailable required objects; explicitly materialize them before sanitizing\n")

    def test_bounded_mode_rewrites_a_local_shallow_head_without_publishing_shallow_state(self) -> None:
        self.fixture.write("new.txt", "safe\n")
        self.fixture.commit("new", "new.txt")
        shallow = self.fixture.root / "shallow"
        self.fixture.git(
            self.fixture.root, "clone", "--depth=1", f"file://{self.fixture.source}", str(shallow)
        )
        policy = self.fixture.write_policy(source_mode="bounded")
        output = self.fixture.output_dir / "bounded.git"
        result = self.fixture.run_cli(
            "rewrite", "--source", str(shallow / ".git"), "--policy", str(policy),
            "--output", str(output), "--json", check=True,
        )
        report = json.loads(result.stdout)
        self.assertEqual(report["verification"]["mode"], "bounded")
        self.assertEqual(self.fixture.git(output, "rev-parse", "--is-shallow-repository"), "false")
        self.assertFalse((output / "shallow").exists())

    def test_snapshot_rewrite_has_exactly_one_synthetic_root(self) -> None:
        policy = self.fixture.write_policy(cutoff=None, source_mode="snapshot", prefix_message="[snapshot]")
        output = self.fixture.output_dir / "snapshot.git"
        self.fixture.run_cli(
            "rewrite", "--source", str(self.fixture.source / ".git"), "--policy", str(policy),
            "--output", str(output), check=True,
        )
        self.assertEqual(self.fixture.git(output, "rev-list", "--max-parents=0", "--all").splitlines(), [self.fixture.git(output, "rev-parse", "HEAD")])
        self.assertEqual(self.fixture.git(output, "show", "-s", "--format=%B", "HEAD"), "[snapshot]")


if __name__ == "__main__":
    unittest.main()
