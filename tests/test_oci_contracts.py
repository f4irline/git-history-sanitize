"""Fail-closed OCI toolchain and image-structure contracts."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from git_history_sanitize.oci_toolchain import ToolchainManifestError, load_manifest, load_required_manifest


ROOT = Path(__file__).resolve().parents[1]


class OciContractsTests(unittest.TestCase):
    def test_reviewed_lock_has_immutable_platform_toolchain_records(self) -> None:
        lock = json.loads((ROOT / "container/toolchain.lock.json").read_text())

        self.assertEqual(lock["schema_version"], 1)
        self.assertTrue(lock["base_image"].startswith("ubuntu@sha256:"))
        self.assertTrue(lock["apt_snapshot"]["url"].startswith("https://snapshot.ubuntu.com/"))
        self.assertRegex(lock["git"]["commit"], r"^[0-9a-f]{40}$")
        self.assertEqual(lock["git_filter_repo"]["fingerprint"], "a40bce548d2c")
        self.assertRegex(lock["git_filter_repo"]["artifact_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(set(lock["platforms"]), {"amd64", "arm64"})
        for architecture, record in lock["platforms"].items():
            with self.subTest(architecture=architecture):
                self.assertRegex(record["python_version"], r"^\d+\.\d+\.\d+$")
                self.assertTrue(all("=" in item for item in record["runtime_apt"] + record["build_apt"]))

    def test_build_inputs_are_bound_to_the_reviewed_lock(self) -> None:
        lock = json.loads((ROOT / "container/toolchain.lock.json").read_text())
        containerfile = (ROOT / "Containerfile").read_text()
        bootstrap = (ROOT / "scripts/bootstrap-test-git.sh").read_text()
        requirements = (ROOT / "requirements/container-runtime.txt").read_text()

        self.assertIn(lock["base_image"], containerfile)
        self.assertIn(lock["apt_snapshot"]["url"], containerfile)
        for record in lock["platforms"].values():
            for package in record["runtime_apt"] + record["build_apt"]:
                with self.subTest(package=package):
                    self.assertIn(package, containerfile)
        for value in lock["git"].values():
            if isinstance(value, str):
                self.assertIn(value, bootstrap)
        for patch in lock["git"]["patches"].values():
            self.assertIn(patch["before_sha256"], bootstrap)
            self.assertIn(patch["after_sha256"], bootstrap)
        self.assertIn(lock["git_filter_repo"]["version"], requirements)
        self.assertIn(lock["git_filter_repo"]["artifact_sha256"], requirements)

    def test_manifest_loader_rejects_a_missing_required_value(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "toolchain-manifest.json"
            manifest.write_text('{"schema_version":1}')

            with self.assertRaisesRegex(ToolchainManifestError, "required OCI toolchain manifest"):
                load_manifest(manifest)

    def test_required_sentinel_resolves_only_its_declared_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "toolchain-manifest.json"
            manifest.write_text(json.dumps({
                "schema_version": 1, "git": "git version 2.47.0",
                "git_filter_repo": "a40bce548d2c", "lock_sha256": "a" * 64,
                "package_version": "0.1.2", "python": "3.12.3", "source_revision": "b" * 40,
            }))
            sentinel = root / "oci-manifest-required"
            sentinel.write_text(json.dumps({"schema_version": 1, "manifest": str(manifest)}))

            self.assertEqual(load_required_manifest(sentinel), load_manifest(manifest))

    def test_runtime_is_non_root_and_requires_the_manifest_sentinel(self) -> None:
        containerfile = (ROOT / "Containerfile").read_text()
        entrypoint = (ROOT / "container/oci-runtime-entrypoint.sh").read_text()

        self.assertIn("USER 65532:65532", containerfile)
        self.assertIn("--require-hashes", containerfile)
        self.assertIn("COPY --from=builder", containerfile)
        self.assertIn("Acquire::Retries=20", containerfile)
        self.assertIn("oci-runtime-entrypoint.sh", containerfile)
        self.assertIn("oci-manifest-required", containerfile)
        self.assertIn("toolchain-manifest.json", entrypoint)
        self.assertIn("exec /opt/runtime/bin/python -m git_history_sanitize", entrypoint)

    def test_container_switches_to_the_snapshot_before_installing_ca_certificates(self) -> None:
        containerfile = (ROOT / "Containerfile").read_text()

        self.assertLess(containerfile.index("sed -i"), containerfile.index("apt-get"))

    def test_manifest_generator_checks_the_live_python_version(self) -> None:
        generator = (ROOT / "scripts/verify-container-toolchain.py").read_text()

        self.assertIn("platform.python_version()", generator)

    def test_trivy_exceptions_reject_expired_records(self) -> None:
        validator = ROOT / "scripts/validate-trivy-exceptions.py"
        with tempfile.TemporaryDirectory() as directory:
            exceptions = Path(directory) / "exceptions.yaml"
            exceptions.write_text(json.dumps({"vulnerabilities": [{
                "id": "CVE-2026-0001",
                "statement": "fixture",
                "owner": "security@example.invalid",
                "issue": "BBQ-21",
                "expired_at": "2026-09-15",
            }]}))

            completed = subprocess.run(
                [sys.executable, validator, "--today", "2026-09-16", exceptions],
                capture_output=True,
                check=False,
                text=True,
            )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("expired", completed.stderr)


if __name__ == "__main__":
    unittest.main()
