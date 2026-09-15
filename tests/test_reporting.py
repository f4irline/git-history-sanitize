"""Versioned public and trusted JSON reporting contracts."""

from __future__ import annotations

import json
import unittest

from git_history_sanitize.engine import Plan
from git_history_sanitize.errors import DependencyError, PolicyError, PublicationError, VerificationError
from git_history_sanitize.filtering import filter_paths
from git_history_sanitize.git import GitError
from git_history_sanitize.hooks import HookInventory
from git_history_sanitize.reporting import error_document, success_document
from git_history_sanitize.verify import VerificationReport


class ReportingTests(unittest.TestCase):
    def test_public_v2_plan_uses_only_aggregate_fields(self) -> None:
        plan = Plan(
            source_commits=2,
            discarded_commits=1,
            retained_commits_before_path_filter=1,
            mode="complete",
            scope="complete reachable history",
            boundary_count=1,
            included_commit_count=1,
            included_object_count=2,
            retained_head_path_count=1,
            excluded_paths=("private/",),
            hooks=HookInventory((), False),
            hooks_stripped=False,
        )

        document = success_document("plan", plan)

        self.assertTrue(document.endswith("\n"))
        self.assertNotIn(": ", document)
        self.assertEqual(
            json.loads(document),
            {
                "command": "plan",
                "report_audience": "public",
                "result": {
                    "boundary_count": 1,
                    "discarded_commits": 1,
                    "hooks": {"action": "preserved", "count": 0},
                    "included_commit_count": 1,
                    "included_object_count": 2,
                    "mode": "complete",
                    "retained_commits_before_path_filter": 1,
                    "retained_head_path_count": 1,
                    "scope": "complete reachable history",
                    "source_commits": 2,
                },
                "schema_version": 2,
                "status": "success",
            },
        )

    def test_trusted_v2_contains_identity_data_only_in_diagnostics(self) -> None:
        report = VerificationReport(
            head="a" * 40,
            commit_count=1,
            root="b" * 40,
            retained_refs=("refs/heads/\udcff",),
            excluded_paths=(),
            mode="complete",
            scope="complete",
            boundary_count=1,
            included_commit_count=1,
            included_object_count=1,
        )

        payload = json.loads(success_document("verify", report, diagnostics="trusted"))

        self.assertEqual(payload["report_audience"], "trusted")
        self.assertNotIn("head", payload["result"])
        self.assertEqual(payload["diagnostics"]["head"], "a" * 40)
        self.assertEqual(payload["diagnostics"]["root"], "b" * 40)
        self.assertEqual(payload["diagnostics"]["retained_refs"], [r"refs/heads/\xff"])
        self.assertNotIn("remediation", payload)

    def test_legacy_v1_requires_explicit_trusted_serialization(self) -> None:
        plan = Plan(
            source_commits=1, discarded_commits=0, retained_commits_before_path_filter=1,
            mode="complete", scope="complete reachable history", boundary_count=1,
            included_commit_count=1, included_object_count=1, retained_head_path_count=1,
            excluded_paths=("private/",), hooks=HookInventory((), False), hooks_stripped=False,
        )

        payload = json.loads(success_document("plan", plan, diagnostics="trusted", schema_version=1))

        self.assertEqual(payload["schema_version"], 1)
        self.assertNotIn("report_audience", payload)
        self.assertEqual(payload["result"]["excluded_paths"], ["private/"])

    def test_error_document_uses_only_catalog_metadata_and_invariant(self) -> None:
        payload = json.loads(error_document("verify", VerificationError("private /path", invariant="refs.retained")))

        self.assertEqual(
            payload,
            {
                "code": "verification.failed",
                "command": "verify",
                "invariant": "refs.retained",
                "message": "Verification did not satisfy the sanitizer contract.",
                "report_audience": "public",
                "schema_version": 2,
                "stage": "verification",
                "status": "error",
            },
        )
        self.assertNotIn("private", json.dumps(payload))
        self.assertNotIn("path", json.dumps(payload))

    def test_error_document_uses_fixed_policy_metadata(self) -> None:
        payload = json.loads(error_document("plan", PolicyError("private policy value")))

        self.assertEqual(payload["code"], "policy.invalid")
        self.assertEqual(payload["stage"], "policy")
        self.assertNotIn("private", json.dumps(payload))

    def test_error_document_preserves_only_allowlisted_publication_states(self) -> None:
        for state in ("not_published", "receipt_published", "output_published"):
            with self.subTest(state=state):
                payload = json.loads(error_document("rewrite", PublicationError("private path", publication_state=state)))
                self.assertEqual(payload["code"], "publication.failed")
                self.assertEqual(payload["publication_state"], state)
                self.assertNotIn("private", json.dumps(payload))

    def test_filter_repo_failure_is_a_dependency_error(self) -> None:
        class BrokenRepository:
            def run(self, *args: object, **kwargs: object) -> None:
                raise GitError("private tool output")

        class Policy:
            excluded_paths = ("private/",)
            mixed_message = "[sanitized]"

        with self.assertRaises(DependencyError):
            filter_paths(BrokenRepository(), Policy())  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
