"""Static fail-closed release workflow contracts without a YAML dependency."""

from __future__ import annotations

import unittest
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


class ReleaseWorkflowTests(unittest.TestCase):
    def test_release_mutations_depend_on_the_validated_artifact_gate(self) -> None:
        workflow = (ROOT / ".github/workflows/release.yml").read_text()

        self.assertIn("release-gate:", workflow)
        for job in ("publish-pypi:", "publish-image:", "github-release:"):
            start = workflow.index(job)
            following = re.search(r"^  [a-z][a-z-]+:\n", workflow[start + len(job):], re.MULTILINE)
            end = len(workflow) if following is None else start + len(job) + following.start()
            block = workflow[start:end]
            self.assertIn("release-gate", block)
        self.assertIn("type=raw,value=latest", workflow)
        self.assertIn("needs.release-gate.outputs.version", workflow)
        self.assertIn("packages-dir: release-assets/distributions/", workflow)
        self.assertIn("release-assets/distributions/* release-assets/SHA256SUMS", workflow)
        image = workflow[workflow.index("publish-image:"):workflow.index("github-release:")]
        self.assertIn("contents: read", image)

    def test_testpypi_validates_an_explicit_intended_version_before_publish(self) -> None:
        workflow = (ROOT / ".github/workflows/testpypi.yml").read_text()

        self.assertIn("version:", workflow)
        self.assertIn("scripts/release.py check", workflow)
        self.assertIn("needs: release-gate", workflow)
        self.assertIn("prototype-history:", workflow)
        self.assertIn("packages-dir: dist/distributions/", workflow)

    def test_ci_installs_the_wheel_from_the_validated_distribution_directory(self) -> None:
        workflow = (ROOT / ".github/workflows/ci.yml").read_text()

        self.assertIn('scripts/release.py check --version "$version" --output dist', workflow)
        self.assertIn('GHS_WHEEL="$(realpath dist/distributions/*.whl)"', workflow)
