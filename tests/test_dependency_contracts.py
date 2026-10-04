"""Hermetic dependency provenance, parsing, and redacted CLI boundaries."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

from git_history_sanitize import cli
from git_history_sanitize.errors import DependencyError, SourceError, VerificationError
from git_history_sanitize.filtering import filter_paths
from git_history_sanitize.git import Repository, ensure_dependencies, run
from git_history_sanitize.reporting import error_document, error_text, success_text
from git_history_sanitize.verify import _object_body_chunks


class DependencyContracts(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        sentinel_patch = patch("git_history_sanitize.git.OCI_MANIFEST_SENTINEL", self.root / "absent-sentinel")
        sentinel_patch.start()
        self.addCleanup(sentinel_patch.stop)
        self.bin = self.root / "bin"
        self.exec_path = self.root / "exec"
        self.bin.mkdir()
        self.exec_path.mkdir()
        self.environment = {
            "PATH": str(self.bin), "HOME": str(self.root),
            "GIT_EXEC_PATH": str(self.exec_path), "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
        }
        self.git = self.bin / "git"
        self.helper = self.exec_path / "git-filter-repo"
        self.write_git()
        self.write_executable(self.helper, "import sys\nsys.stdout.buffer.write(b'a40bce548d2c\\n')")
        self.write_executable(self.bin / "git-filter-repo", "raise RuntimeError('decoy must not execute')")

    def write_executable(self, path: Path, body: str) -> None:
        path.write_text(f"#!{sys.executable}\n{body}\n")
        path.chmod(0o755)

    def write_git(self, version: bytes = b"git version 2.47.0\n", status: int = 0) -> None:
        self.write_executable(self.git, f"""
import os, sys
args = sys.argv[1:]
if args == ['--version']:
    sys.stdout.buffer.write({version!r})
    sys.stderr.write('private process diagnostic')
    sys.exit({status})
if args == ['--exec-path']:
    print(os.environ['GIT_EXEC_PATH'])
    sys.exit(0)
if 'filter-repo' in args:
    assert os.environ['GIT_NO_LAZY_FETCH'] == '1'
    assert os.environ['GIT_NO_REPLACE_OBJECTS'] == '1'
    remaining = args[args.index('filter-repo') + 1:]
    if remaining != ['--version']:
        from pathlib import Path
        Path(os.environ['HOME'], 'rewrite-route').write_text(' '.join(remaining[:4]))
        sys.exit(0)
    helper = os.path.join(os.environ['GIT_EXEC_PATH'], 'git-filter-repo')
    os.execv(helper, [helper, *remaining])
sys.exit(0)
""")

    def check_records(self, statuses: tuple[str, str] = ("pass", "pass")) -> list[dict[str, str | None]]:
        return [
            {"name": "git", "executable_path": str(self.git), "detected_version": "2.47.0",
             "required_range": ">=2.36", "status": statuses[0]},
            {"name": "git-filter-repo", "executable_path": str(self.helper), "detected_version": "a40bce548d2c",
             "required_range": "a40bce548d2c (2.47.0)", "status": statuses[1]},
        ]

    def test_supported_tools_and_rewrite_use_git_subcommand_not_decoy(self) -> None:
        result = ensure_dependencies(self.environment)
        self.assertEqual(result, {"git": "git version 2.47.0", "git_filter_repo": "a40bce548d2c", "checks": self.check_records()})
        repository = object.__new__(Repository)
        repository.path, repository.git_dir, repository._bare = self.root, self.root, True
        policy = Mock(included_paths=None, excluded_paths=("private/",), mixed_message="[sanitized]")
        with patch.dict(os.environ, self.environment, clear=True):
            from git_history_sanitize.git import Discovery
            repository.discovery = Discovery("bare", repository.git_dir, repository.git_dir, None, repository.git_dir)
            filter_paths(repository, policy)
        self.assertEqual((self.root / "rewrite-route").read_text(), "--force --prune-empty always --commit-callback")
        self.assertEqual(success_text("doctor", result),
                         f"git: pass; executable={self.git}; detected=2.47.0; required=>=2.36\n"
                         f"git-filter-repo: pass; executable={self.helper}; detected=a40bce548d2c; required=a40bce548d2c (2.47.0)\n")

    def test_cli_success_has_exact_additive_json_contract(self) -> None:
        streams = StringIO(), StringIO()
        with patch.dict(os.environ, self.environment, clear=True), redirect_stdout(streams[0]), redirect_stderr(streams[1]):
            code = cli.main(["doctor", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(streams[1].getvalue(), "")
        self.assertEqual(json.loads(streams[0].getvalue()), {
            "command": "doctor", "report_audience": "public", "schema_version": 2, "status": "success",
            "result": {"git": "git version 2.47.0", "git_filter_repo": "a40bce548d2c", "checks": self.check_records()},
        })

    def test_versions_are_strict_bounded_and_fail_closed(self) -> None:
        for output, status, code, detected in (
            (b"git version 2.35.9\n", 0, "unsupported", "2.35.9"),
            (b"private process diagnostic\n", 0, "invalid_output", None),
            (b"git version 2.47.0\nprivate\n", 0, "invalid_output", None),
            (b"\xff", 0, "invalid_output", None),
            (b"x" * 300, 0, "invalid_output", None),
            (b"git version 2.47.0\n", 7, "execution_failed", None),
        ):
            with self.subTest(code=code, output=output):
                self.write_git(output, status)
                with self.assertRaises(DependencyError) as raised:
                    ensure_dependencies(self.environment)
                self.assertEqual(raised.exception.metadata.code, f"dependency.{code}")
                payload = json.loads(error_document("doctor", raised.exception))
                self.assertEqual(payload["checks"][0]["detected_version"], detected)
                self.assertEqual([item["status"] for item in payload["checks"]], ["fail", "pass"])
                self.assertNotIn("private process diagnostic", json.dumps(payload) + error_text(raised.exception))

    def test_helper_nonzero_malformed_and_non_utf8_output_are_typed(self) -> None:
        for body, code in (
            ("import sys; print('private process diagnostic'); sys.exit(7)", "execution_failed"),
            ("print('private process diagnostic')", "invalid_output"),
            ("import sys; sys.stdout.buffer.write(b'\\xff')", "invalid_output"),
            ("print('a40bce548d2c\\nprivate process diagnostic')", "invalid_output"),
        ):
            with self.subTest(code=code):
                self.write_executable(self.helper, body)
                with self.assertRaises(DependencyError) as raised:
                    ensure_dependencies(self.environment)
                payload = json.loads(error_document("doctor", raised.exception))
                self.assertEqual(payload["code"], f"dependency.{code}")
                self.assertEqual([check["status"] for check in payload["checks"]], ["pass", "fail"])
                self.assertIsNone(payload["checks"][1]["detected_version"])
                self.assertNotIn("private process diagnostic", json.dumps(payload))

    def test_probe_timeout_is_bounded_and_reaped(self) -> None:
        self.write_executable(self.helper, "import time; time.sleep(60)")
        with patch("git_history_sanitize.git._DEPENDENCY_TIMEOUT", 1.0):
            with self.assertRaises(DependencyError) as raised:
                ensure_dependencies(self.environment)
        self.assertEqual(raised.exception.metadata.code, "dependency.execution_failed")
        from git_history_sanitize.git import _ACTIVE_PROCESSES
        self.assertFalse(_ACTIVE_PROCESSES)

    def test_supported_vendor_git_versions_preserve_legacy_value(self) -> None:
        for value in ("git version 2.36.0", "git version 2.54.0 (Apple Git-157)", "git version 2.47.0.windows.1"):
            with self.subTest(value=value):
                self.write_git((value + "\n").encode())
                self.assertEqual(ensure_dependencies(self.environment)["git"], value)

    def test_missing_non_executable_and_wrong_fingerprint(self) -> None:
        (self.bin / "git-filter-repo").unlink()
        for name, code in (("git", "missing"), ("git-filter-repo", "missing"),
                           ("git-filter-repo", "not_executable"), ("git", "not_executable"),
                           ("git-filter-repo", "unsupported")):
            with self.subTest(name=name, code=code):
                path = self.git if name == "git" else self.helper
                original = path.read_text()
                if code == "missing":
                    path.unlink()
                elif code == "not_executable":
                    path.chmod(0o644)
                else:
                    self.write_executable(path, "print('0123456789ab')")
                with self.assertRaises(DependencyError) as raised:
                    ensure_dependencies(self.environment)
                self.assertEqual(raised.exception.metadata.code, f"dependency.{code}")
                self.assertEqual(len(raised.exception.checks), 2)
                self.write_executable(path, original.split('\n', 1)[1])

    def test_cli_failure_has_exact_safe_error_envelope_and_human_checks(self) -> None:
        self.write_git(b"private process diagnostic", 9)
        for json_mode in (False, True):
            streams = StringIO(), StringIO()
            with patch.dict(os.environ, self.environment, clear=True), redirect_stdout(streams[0]), redirect_stderr(streams[1]):
                code = cli.main(["doctor", *(["--json"] if json_mode else [])])
            self.assertEqual(code, 2)
            output = streams[0 if json_mode else 1].getvalue()
            self.assertEqual(streams[1 if json_mode else 0].getvalue(), "")
            self.assertNotIn("private process diagnostic", output)
            self.assertNotIn("Traceback", output)
            if json_mode:
                payload = json.loads(output)
                self.assertEqual(set(payload), {"command", "report_audience", "schema_version", "status", "code", "stage", "message", "remediation", "checks"})
                self.assertEqual(payload["code"], "dependency.execution_failed")
                self.assertEqual(payload["stage"], "dependency")
                self.assertEqual(payload["checks"][1], self.check_records()[1])
            else:
                self.assertIn("git: fail;", output)
                self.assertIn("README.md", output)

    def test_oci_attestation_retains_fields_and_classifies_failures(self) -> None:
        sentinel, manifest = self.root / "sentinel", self.root / "manifest"
        sentinel.write_text(json.dumps({"schema_version": 1, "manifest": str(manifest)}))
        declaration = {"schema_version": 1, "git": "git version 2.47.0", "git_filter_repo": "a40bce548d2c",
                       "python": "3.12.3", "lock_sha256": "a" * 64, "package_version": "0.1.2", "source_revision": "b" * 40}
        manifest.write_text(json.dumps(declaration))
        with patch("git_history_sanitize.git.OCI_MANIFEST_SENTINEL", sentinel), patch("git_history_sanitize.git.platform.python_version", return_value="3.12.3"):
            result = ensure_dependencies(self.environment)
            self.assertEqual(result, {"git": declaration["git"], "git_filter_repo": declaration["git_filter_repo"],
                                     "checks": self.check_records(), "python": "3.12.3", "manifest_sha256": "a" * 64,
                                     "package_version": "0.1.2", "source_revision": "b" * 40})
            for content in (b"\xff", b"[]", b'{"schema_version":1}', json.dumps(declaration | {"git": "git version 2.48.0"}).encode()):
                manifest.write_bytes(content)
                with self.assertRaises(DependencyError) as raised:
                    ensure_dependencies(self.environment)
                self.assertEqual(raised.exception.metadata.code, "dependency.oci_mismatch")
                self.assertEqual(json.loads(error_document("doctor", raised.exception))["checks"], self.check_records())
                self.assertNotIn("checks", json.loads(error_document("rewrite", raised.exception)))

    def test_expected_startup_and_stream_failures_are_typed(self) -> None:
        with patch("git_history_sanitize.git.start_process", side_effect=PermissionError("private")):
            with self.assertRaises(DependencyError) as raised:
                ensure_dependencies(self.environment)
            self.assertEqual(raised.exception.metadata.code, "dependency.startup_failed")
        process = Mock(returncode=0)
        process.communicate.side_effect = OSError("private")
        process.poll.return_value = 0
        with patch("git_history_sanitize.git.start_process", return_value=process):
            with self.assertRaises(SourceError):
                run(["status"], environment=self.environment)
        repository = Mock()
        repository.object_format.return_value = "sha1"
        for failure in (PermissionError("private"), subprocess.SubprocessError("private")):
            with patch("git_history_sanitize.verify.start_process", side_effect=failure):
                with self.assertRaises(VerificationError):
                    list(_object_body_chunks(repository))

    def test_filesystem_and_oci_sentinel_errors_are_not_internal(self) -> None:
        with patch("git_history_sanitize.git.os.stat", side_effect=PermissionError("private process diagnostic")):
            with self.assertRaises(DependencyError) as raised:
                ensure_dependencies(self.environment)
        self.assertEqual(raised.exception.metadata.code, "dependency.startup_failed")
        sentinel = self.root / "sentinel"
        with patch("git_history_sanitize.git.OCI_MANIFEST_SENTINEL", sentinel), patch.object(Path, "lstat", side_effect=PermissionError("private process diagnostic")):
            with self.assertRaises(DependencyError) as raised:
                ensure_dependencies(self.environment)
        self.assertEqual(raised.exception.metadata.code, "dependency.oci_mismatch")
        with patch.object(Path, "resolve", side_effect=PermissionError("private process diagnostic")):
            with self.assertRaises(SourceError):
                Repository(self.root)


if __name__ == "__main__":
    unittest.main()
