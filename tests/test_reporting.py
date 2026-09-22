"""Versioned public and trusted JSON reporting contracts."""

from __future__ import annotations

import json
import unittest

from git_history_sanitize.compact import CompactResult, SyntheticRootContext
from git_history_sanitize.engine import Plan, RewriteReport
from git_history_sanitize.errors import (
    DependencyError,
    InterruptionError,
    PolicyError,
    PublicationError,
    UsageError,
    VerificationError,
    WorkspaceError,
)
from git_history_sanitize.filtering import filter_paths
from git_history_sanitize.git import GitError
from git_history_sanitize.hooks import Hook, HookInventory
from git_history_sanitize.reporting import error_document, error_text, success_document, success_text
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
                    "retained_ref_count": 0,
                    "retained_branch_count": 0,
                    "retained_lightweight_tag_count": 0,
                    "retained_annotated_tag_count": 0,
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

    def test_trusted_human_verification_uses_the_identity_diagnostic_set(self) -> None:
        report = VerificationReport(
            head="a" * 40, commit_count=1, root="b" * 40,
            retained_refs=("refs/heads/main",), excluded_paths=("private/",),
            mode="complete", scope="complete", boundary_count=1,
            included_commit_count=1, included_object_count=1,
        )

        text = success_text("verify", report, diagnostics="trusted")

        self.assertIn(f"Sanitized HEAD: {'a' * 40}", text)
        self.assertIn(f"Sanitized root: {'b' * 40}", text)
        self.assertIn("Retained refs: refs/heads/main", text)
        self.assertIn("Excluded paths: private/", text)

    def test_trusted_human_plan_and_rewrite_use_the_identity_diagnostic_set(self) -> None:
        hooks = HookInventory((Hook("pre-push", b"", 0o755, ("absolute-path",)),), False)
        plan = Plan(
            source_commits=1, discarded_commits=0, retained_commits_before_path_filter=1,
            mode="complete", scope="complete", boundary_count=1, included_commit_count=1,
            included_object_count=1, retained_head_path_count=1, excluded_paths=("private/",),
            hooks=hooks, hooks_stripped=False,
        )
        verification = VerificationReport(
            head="a" * 40, commit_count=1, root="b" * 40,
            retained_refs=("refs/heads/main",), excluded_paths=("private/",),
            mode="complete", scope="complete", boundary_count=1,
            included_commit_count=1, included_object_count=1,
        )
        rewrite = RewriteReport(
            CompactResult(1, 0, "c" * 40, "b" * 40, SyntheticRootContext("refs/heads/main", b"", ())),
            verification, hooks, False,
        )

        plan_text = success_text("plan", plan, diagnostics="trusted")
        rewrite_text = success_text("rewrite", rewrite, diagnostics="trusted")

        for text in (plan_text, rewrite_text):
            self.assertIn("Excluded paths: private/", text)
            self.assertIn("Hook names: pre-push", text)
            self.assertIn("Hook warnings: absolute-path: pre-push", text)
        self.assertIn(f"Sanitized HEAD: {'a' * 40}", rewrite_text)
        self.assertIn(f"Sanitized root: {'b' * 40}", rewrite_text)
        self.assertIn("Retained refs: refs/heads/main", rewrite_text)

    def test_human_errors_include_only_fixed_catalog_remediation(self) -> None:
        self.assertEqual(
            error_text(UsageError("private command arguments")),
            "error: invalid command arguments: Run the command with --help for usage.\n",
        )

        workspace = error_text(WorkspaceError("private /path and opaque id"))
        interrupted = error_text(InterruptionError(15))
        self.assertEqual(
            workspace,
            "error: unsafe sanitizer workspace: List sanitizer workspaces under the parent "
            "and clean one validated stale ID.\n",
        )
        self.assertEqual(
            interrupted,
            "error: sanitization interrupted: List sanitizer workspaces under the output parent "
            "and clean the stale ID before retrying.\n",
        )
        self.assertNotIn("private", workspace + interrupted)

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
