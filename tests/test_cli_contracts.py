"""Stable human/JSON CLI success and expected-failure contracts."""

from __future__ import annotations

import json
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import unittest
from unittest.mock import patch

from git_history_sanitize import __version__
from git_history_sanitize import cli

from tests.support.git_fixture import GitFixture


class CliContractTests(unittest.TestCase):
    def test_version_prints_the_canonical_version_only(self) -> None:
        fixture = GitFixture(self)

        result = fixture.run_cli("--version")

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, f"{__version__}\n")
        self.assertEqual(result.stderr, "")

    def setUp(self) -> None:
        self.fixture = GitFixture(self)
        self.fixture.write("allowed.txt", "safe\n")
        self.fixture.commit("allowed", "allowed.txt")
        self.policy = self.fixture.write_policy()

    def test_doctor_plan_rewrite_and_verify_emit_public_v2_json_on_success(self) -> None:
        doctor = self.fixture.run_cli("doctor", "--json")
        plan = self.fixture.run_cli("plan", "--source", str(self.fixture.source / ".git"), "--policy", str(self.policy), "--json")
        output = self.fixture.output_dir / "sanitized.git"
        rewrite = self.fixture.run_cli("rewrite", "--source", str(self.fixture.source / ".git"), "--output", str(output), "--policy", str(self.policy), "--json")
        verify = self.fixture.run_cli("verify", "--repository", str(output), "--policy", str(self.policy), "--json")

        self.assertEqual(doctor.stderr + plan.stderr + rewrite.stderr + verify.stderr, "")
        self.assertEqual(
            json.loads(doctor.stdout),
            {"command": "doctor", "report_audience": "public", "result": json.loads(doctor.stdout)["result"], "schema_version": 2, "status": "success"},
        )
        for command, document in (("plan", plan), ("rewrite", rewrite), ("verify", verify)):
            payload = json.loads(document.stdout)
            self.assertEqual(payload["schema_version"], 2)
            self.assertEqual(payload["command"], command)
            self.assertEqual(payload["report_audience"], "public")
            self.assertEqual(payload["status"], "success")
            self.assertIn("result", payload)
        self.assertEqual(
            set(json.loads(plan.stdout)["result"]),
            {"source_commits", "discarded_commits", "retained_commits_before_path_filter", "mode", "scope", "boundary_count", "included_commit_count", "included_object_count", "retained_head_path_count", "hooks"},
        )
        self.assertIn("verification", json.loads(rewrite.stdout)["result"])
        self.assertNotIn("root", json.loads(verify.stdout)["result"])

    def test_successful_human_output_is_concise_and_actionable(self) -> None:
        plan = self.fixture.run_cli(
            "plan", "--source", str(self.fixture.source / ".git"), "--policy", str(self.policy)
        )
        output = self.fixture.output_dir / "sanitized.git"
        rewrite = self.fixture.run_cli(
            "rewrite", "--source", str(self.fixture.source / ".git"), "--output", str(output),
            "--policy", str(self.policy)
        )
        verify = self.fixture.run_cli(
            "verify", "--repository", str(output), "--policy", str(self.policy)
        )

        self.assertEqual(
            plan.stdout,
            "Source commits: 1\nPre-cutoff commits: 0\nCommits before path filtering: 1\n"
            "Retained HEAD paths: 1\nScope: complete reachable history\nHooks: preserved (0)\n",
        )
        self.assertEqual(
            rewrite.stdout,
            "Commits in output: 1\nScope: complete reachable history\nHooks: preserved (0)\n",
        )
        self.assertEqual(verify.stdout, "Verification passed.\n")
        self.assertEqual(plan.stderr + rewrite.stderr + verify.stderr, "")

    def test_trusted_plan_reports_the_validated_ordered_exclusions(self) -> None:
        policy = self.fixture.write_policy(excluded_paths=("secret file.txt", "private/"))

        result = self.fixture.run_cli(
            "plan", "--source", str(self.fixture.source / ".git"), "--policy", str(policy), "--json", "--diagnostics=trusted"
        )

        self.assertEqual(json.loads(result.stdout)["diagnostics"]["excluded_paths"], ["secret file.txt", "private/"])
        self.assertEqual(result.stderr, "")

    def test_plan_counts_paths_with_the_same_exact_and_directory_rules_as_filtering(self) -> None:
        self.fixture.write("secret file.txt", "secret\n")
        self.fixture.write("private/key.txt", "secret\n")
        self.fixture.write("allowed/note.txt", "safe\n")
        self.fixture.commit("mixed", "secret file.txt", "private/key.txt", "allowed/note.txt")
        policy = self.fixture.write_policy(excluded_paths=("secret file.txt", "private/"))

        result = self.fixture.run_cli(
            "plan", "--source", str(self.fixture.source / ".git"), "--policy", str(policy), "--json"
        )

        self.assertEqual(json.loads(result.stdout)["result"]["retained_head_path_count"], 2)
        self.assertEqual(result.stderr, "")

    def test_expected_operational_failures_use_exit_two_and_actionable_stderr(self) -> None:
        failed = self.fixture.run_cli("rewrite", "--source", str(self.fixture.source / ".git"), "--output", str(self.fixture.output_dir / "exists.git"), "--policy", str(self.fixture.root / "missing.yml"), check=False)

        self.assertEqual(failed.returncode, 2)
        self.assertEqual(failed.stdout, "")
        self.assertEqual(failed.stderr, "error: invalid policy\n")

    def test_json_parser_and_internal_failures_write_one_safe_stdout_document(self) -> None:
        streams = StringIO(), StringIO()
        with redirect_stdout(streams[0]), redirect_stderr(streams[1]):
            code = cli.main(["plan", "--json"])
        parsed = json.loads(streams[0].getvalue())
        self.assertEqual(code, 2)
        self.assertEqual(streams[1].getvalue(), "")
        self.assertEqual(parsed["code"], "usage.invalid_arguments")
        self.assertEqual(parsed["stage"], "parse")
        self.assertEqual(parsed["schema_version"], 2)
        self.assertEqual(parsed["report_audience"], "public")

        streams = StringIO(), StringIO()
        with patch("git_history_sanitize.cli.ensure_dependencies", side_effect=RuntimeError("private /path")):
            with redirect_stdout(streams[0]), redirect_stderr(streams[1]):
                code = cli.main(["doctor", "--json"])
        internal = json.loads(streams[0].getvalue())
        self.assertEqual(code, 2)
        self.assertEqual(streams[1].getvalue(), "")
        self.assertEqual(internal["code"], "internal_error")
        self.assertNotIn("private", streams[0].getvalue())

    def test_diagnostics_and_legacy_schema_are_strictly_opt_in(self) -> None:
        public = self.fixture.run_cli(
            "plan", "--source", str(self.fixture.source / ".git"), "--policy", str(self.policy), "--json"
        )
        trusted = self.fixture.run_cli(
            "plan", "--source", str(self.fixture.source / ".git"), "--policy", str(self.policy),
            "--json", "--diagnostics=trusted",
        )
        invalid_diagnostics = self.fixture.run_cli(
            "plan", "--source", str(self.fixture.source / ".git"), "--policy", str(self.policy),
            "--json", "--diagnostics=shared-secret", check=False,
        )
        legacy_without_trusted = self.fixture.run_cli(
            "plan", "--source", str(self.fixture.source / ".git"), "--policy", str(self.policy),
            "--json", "--json-schema=1", check=False,
        )

        self.assertNotIn("diagnostics", json.loads(public.stdout))
        self.assertIn("diagnostics", json.loads(trusted.stdout))
        for result in (invalid_diagnostics, legacy_without_trusted):
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stderr, "")
            payload = json.loads(result.stdout)
            self.assertEqual(payload["code"], "usage.invalid_arguments")
            self.assertEqual(payload["schema_version"], 2)
            self.assertEqual(payload["report_audience"], "public")
            self.assertNotIn("shared-secret", result.stdout)

    def test_receipt_arguments_have_stable_policy_conditional_failures(self) -> None:
        commit_policy = self.fixture.write_policy(
            cutoff=None,
            cutoff_commit=self.fixture.git(self.fixture.source, "rev-parse", "HEAD"),
        )
        missing_human = self.fixture.run_cli("verify", "--repository", str(self.fixture.source / ".git"), "--policy", str(commit_policy), check=False)
        missing_json = self.fixture.run_cli("verify", "--repository", str(self.fixture.source / ".git"), "--policy", str(commit_policy), "--json", check=False)
        timestamp = self.fixture.write_policy()
        forbidden = self.fixture.run_cli("verify", "--repository", str(self.fixture.source / ".git"), "--policy", str(timestamp), "--receipt", str(self.fixture.receipt_dir / "unused.json"), check=False)

        self.assertEqual(missing_human.returncode, 2)
        self.assertEqual(missing_human.stdout, "")
        self.assertEqual(missing_human.stderr, "error: verification failed\n")
        self.assertEqual(missing_json.returncode, 2)
        self.assertEqual(missing_json.stderr, "")
        self.assertEqual(json.loads(missing_json.stdout)["code"], "verification.failed")
        self.assertEqual(forbidden.returncode, 2)
        self.assertEqual(forbidden.stdout, "")
        self.assertEqual(forbidden.stderr, "error: verification failed\n")

    def test_verify_contract_failures_have_redacted_human_and_json_diagnostics(self) -> None:
        output = self.fixture.output_dir / "sanitized.git"
        self.fixture.run_cli(
            "rewrite", "--source", str(self.fixture.source / ".git"), "--output", str(output),
            "--policy", str(self.policy),
        )
        self.fixture.git(output, "tag", "private-marker")

        human = self.fixture.run_cli(
            "verify", "--repository", str(output), "--policy", str(self.policy), check=False,
        )
        structured = self.fixture.run_cli(
            "verify", "--repository", str(output), "--policy", str(self.policy), "--json",
            check=False,
        )

        self.assertEqual(human.returncode, 2)
        self.assertEqual(human.stdout, "")
        self.assertEqual(human.stderr, "error: verification failed: refs.retained\n")
        self.assertNotIn("private-marker", human.stderr)
        self.assertEqual(structured.returncode, 2)
        self.assertEqual(structured.stderr, "")
        self.assertEqual(json.loads(structured.stdout), {
            "code": "verification.failed", "command": "verify", "invariant": "refs.retained",
            "message": "Verification did not satisfy the sanitizer contract.",
            "report_audience": "public", "schema_version": 2, "stage": "verification", "status": "error",
        })

    def test_forbidden_file_and_stdin_records_are_scanned_without_leaking_inputs(self) -> None:
        output = self.fixture.output_dir / "sanitized.git"
        self.fixture.run_cli(
            "rewrite", "--source", str(self.fixture.source / ".git"), "--output", str(output),
            "--policy", str(self.policy),
        )
        clean_head = self.fixture.git(output, "rev-parse", "HEAD")
        tree = self.fixture.tree_with_file(output, "allowed.txt", "private marker\n")
        self.fixture.git(output, "update-ref", "refs/heads/main", self.fixture.commit_tree(output, tree, "safe", clean_head))
        patterns = self.fixture.root / "private-patterns"
        patterns.write_bytes(b"private marker\n")

        file_result = self.fixture.run_cli(
            "verify", "--repository", str(output), "--policy", str(self.policy),
            "--forbid-file", str(patterns), check=False,
        )

        self.assertEqual(file_result.returncode, 2)
        self.assertEqual(file_result.stderr, "error: verification failed: content.forbidden\n")
        self.assertNotIn("private marker", file_result.stderr)
        self.assertNotIn(str(patterns), file_result.stderr)

        stdin_result = self.fixture.run_cli(
            "verify", "--repository", str(output), "--policy", str(self.policy), "--forbid-stdin",
            check=False, input_text="private marker\n",
        )

        self.assertEqual(stdin_result.returncode, 2)
        self.assertEqual(stdin_result.stderr, "error: verification failed: content.forbidden\n")
        self.assertNotIn("private marker", stdin_result.stderr)

    def test_forbidden_input_failures_redact_empty_oversize_and_paths(self) -> None:
        empty = self.fixture.root / "private-patterns"
        empty.write_bytes(b"\n")
        oversized = self.fixture.root / "oversized-patterns"
        oversized.write_bytes(b"x" * (64 * 1024 + 1))

        for arguments, secret in (
            (("--forbid", ""), None),
            (("--forbid-file", str(empty)), str(empty)),
            (("--forbid-file", str(oversized)), str(oversized)),
        ):
            with self.subTest(arguments=arguments):
                result = self.fixture.run_cli(
                    "verify", "--repository", str(self.fixture.source / ".git"),
                    "--policy", str(self.policy), *arguments, check=False,
                )
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stderr, "error: invalid forbidden-content input\n")
                if secret:
                    self.assertNotIn(secret, result.stderr)


if __name__ == "__main__":
    unittest.main()
