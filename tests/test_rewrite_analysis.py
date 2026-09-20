"""Focused read-only rewrite analysis contracts."""

from __future__ import annotations

import unittest

from git_history_sanitize.errors import SanitizeError
from git_history_sanitize.git import Repository
from git_history_sanitize.policy import Policy
from git_history_sanitize.rewrite_analysis import RewriteAnalysis

from tests.support.git_fixture import GitFixture


class RewriteAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = GitFixture(self)

    def _analysis(self, policy: object) -> RewriteAnalysis:
        return RewriteAnalysis.create(
            Repository(self.fixture.source / ".git"), Policy.from_file(str(policy))
        )

    def test_complete_history_selects_the_inclusive_timestamp_boundary(self) -> None:
        self.fixture.write("old.txt", "old\n")
        self.fixture.commit("old", "old.txt", timestamp="2026-09-02T23:59:59+00:00")
        self.fixture.write("boundary.txt", "boundary\n")
        boundary = self.fixture.commit("boundary", "boundary.txt")

        analysis = self._analysis(self.fixture.write_policy())

        self.assertEqual(analysis.commits, (
            self.fixture.git(self.fixture.source, "rev-parse", "HEAD^"), boundary,
        ))
        self.assertEqual(analysis.boundary_index, 1)
        self.assertEqual(analysis.boundary_commit, boundary)
        self.assertEqual(analysis.discarded_commits, 1)
        self.assertEqual(analysis.retained_commits, 1)

    def test_rejects_selected_ref_without_an_eligible_timestamp_tip(self) -> None:
        self.fixture.write("old.txt", "old\n")
        self.fixture.commit("old", "old.txt", timestamp="2026-09-02T23:59:59+00:00")
        self.fixture.write("retained.txt", "retained\n")
        self.fixture.commit("retained", "retained.txt", timestamp="2026-09-03T00:00:00+00:00")
        self.fixture.write("recrossed.txt", "recrossed\n")
        self.fixture.commit("recrossed", "recrossed.txt", timestamp="2026-09-02T23:59:59+00:00")

        with self.assertRaisesRegex(SanitizeError, "selected reference has no commit eligible"):
            self._analysis(self.fixture.write_policy())

    def test_cutoff_commit_must_be_reachable_from_head(self) -> None:
        self.fixture.write("head.txt", "head\n")
        self.fixture.commit("head", "head.txt")
        self.fixture.git(self.fixture.source, "checkout", "-qb", "side")
        self.fixture.write("side.txt", "side\n")
        unreachable = self.fixture.commit("side", "side.txt")
        self.fixture.git(self.fixture.source, "checkout", "main")

        with self.assertRaisesRegex(SanitizeError, "cutoffCommit is not reachable from every selected reference"):
            self._analysis(self.fixture.write_policy(cutoff=None, cutoff_commit=unreachable))

    def test_snapshot_uses_only_head_without_walking_inherited_merges(self) -> None:
        self.fixture.write("base.txt", "base\n")
        self.fixture.commit("base", "base.txt")
        self.fixture.git(self.fixture.source, "checkout", "-qb", "side")
        self.fixture.write("side.txt", "side\n")
        self.fixture.commit("side", "side.txt")
        self.fixture.git(self.fixture.source, "checkout", "main")
        self.fixture.write("main.txt", "main\n")
        self.fixture.commit("main", "main.txt")
        head = self.fixture.merge("side", "merge side")

        analysis = self._analysis(
            self.fixture.write_policy(cutoff=None, source_mode="snapshot", prefix_message="[snapshot]")
        )

        self.assertEqual(analysis.commits, (head,))
        self.assertEqual(analysis.boundary_index, 0)
        self.assertEqual(analysis.boundary_commit, head)

    def test_analysis_requires_a_symbolic_head(self) -> None:
        self.fixture.write("tracked.txt", "safe\n")
        self.fixture.commit("tracked", "tracked.txt")
        self.fixture.git(self.fixture.source, "checkout", "--detach")

        with self.assertRaisesRegex(SanitizeError, "must have a symbolic HEAD"):
            self._analysis(self.fixture.write_policy())

    def test_selected_merge_dag_preserves_shared_ancestry_and_parent_order(self) -> None:
        self.fixture.write("base.txt", "base\n")
        base = self.fixture.commit("base", "base.txt", timestamp="2026-09-02T23:59:59+00:00")
        self.fixture.git(self.fixture.source, "checkout", "-qb", "release")
        self.fixture.write("release.txt", "release\n")
        release = self.fixture.commit("release", "release.txt")
        self.fixture.git(self.fixture.source, "checkout", "main")
        self.fixture.write("main.txt", "main\n")
        main = self.fixture.commit("main", "main.txt")
        merge = self.fixture.merge("release", "merge release")

        analysis = self._analysis(
            self.fixture.write_policy(retained_refs=("HEAD", "refs/heads/release"))
        )

        self.assertEqual(analysis.selected_refs, ("refs/heads/main", "refs/heads/release"))
        self.assertEqual(analysis.retained_source_parents[merge], (main, release))
        self.assertEqual(analysis.retained_source_parents[main], ())
        self.assertEqual(analysis.retained_source_parents[release], ())
        self.assertNotIn(base, analysis.retained_source_parents)

    def test_selected_nested_merges_preserve_each_parent_order(self) -> None:
        self.fixture.write("base.txt", "base\n")
        self.fixture.commit("base", "base.txt", timestamp="2026-09-02T23:59:59+00:00")
        self.fixture.git(self.fixture.source, "checkout", "-qb", "side")
        self.fixture.write("side.txt", "side\n")
        side = self.fixture.commit("side", "side.txt")
        self.fixture.git(self.fixture.source, "checkout", "main")
        self.fixture.write("main.txt", "main\n")
        main = self.fixture.commit("main", "main.txt")
        first_merge = self.fixture.merge("side", "merge side")
        self.fixture.git(self.fixture.source, "checkout", "-qb", "nested", main)
        self.fixture.write("nested.txt", "nested\n")
        nested = self.fixture.commit("nested", "nested.txt")
        self.fixture.git(self.fixture.source, "checkout", "main")
        second_merge = self.fixture.merge("nested", "merge nested")

        analysis = self._analysis(self.fixture.write_policy())

        self.assertEqual(analysis.retained_source_parents[first_merge], (main, side))
        self.assertEqual(analysis.retained_source_parents[second_merge], (first_merge, nested))


if __name__ == "__main__":
    unittest.main()
