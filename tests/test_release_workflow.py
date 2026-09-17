"""Static fail-closed release workflow contracts without a YAML dependency."""

from __future__ import annotations

import json
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

    def test_ci_selects_oci_inputs_and_runs_native_arm64_contracts(self) -> None:
        workflow = (ROOT / ".github/workflows/ci.yml").read_text()
        selector = workflow[workflow.index("oci-inputs:"):workflow.index("oci-arm64-contract:")]
        arm64 = workflow[workflow.index("oci-arm64-contract:"):workflow.index("oci-arm64-validation:")]
        gate = workflow[workflow.index("oci-arm64-validation:"):workflow.index("prototype-history:")]

        self.assertIn("schedule:", workflow)
        self.assertIn("cron: '17 4 * * 1'", workflow)
        self.assertIn("fetch-depth: 0", selector)
        self.assertIn("scripts/ci-detect-oci-inputs.sh", selector)
        self.assertIn("github.event.pull_request.base.sha", selector)
        self.assertIn("github.event.before", selector)
        self.assertIn('GITHUB_EVENT_NAME" = "schedule"', selector)
        self.assertIn('GITHUB_REF_NAME" = "main"', selector)

        self.assertIn("if: needs.oci-inputs.outputs.selected == 'true'", arm64)
        self.assertIn("runs-on: ubuntu-24.04-arm", arm64)
        self.assertIn('test "$(uname -m)" = "aarch64"', arm64)
        self.assertIn("docker/setup-buildx-action@8d2750c68a42422c14e847fe6c8ac0403b4cbd6f", arm64)
        self.assertNotIn("setup-qemu-action", arm64)
        self.assertIn('--platform linux/arm64 --load', arm64)
        self.assertIn("type=gha,scope=oci-linux-arm64", arm64)
        self.assertIn("type=gha,mode=max,scope=oci-linux-arm64", arm64)
        self.assertIn('"${OCI_TEST_IMAGE}" doctor', arm64)
        self.assertIn("docker image inspect --format '{{.Config.User}}'", arm64)
        self.assertIn('--user "$(id -u):$(id -g)"', arm64)
        self.assertIn("GHS_OCI_PLATFORM: linux/arm64", arm64)
        self.assertIn("GHS_TEST_RUNTIME: container", arm64)
        self.assertIn(
            "tests.test_output_cleanup_contracts.OutputContractTests.test_output_is_bare_and_has_no_cleanup_artifacts",
            arm64,
        )
        self.assertNotIn("--entrypoint", arm64)

        self.assertIn("name: OCI arm64 validation", gate)
        self.assertIn("if: always()", gate)
        self.assertIn("needs.oci-inputs.result", gate)
        self.assertIn("needs.oci-arm64-contract.result", gate)
        self.assertIn("selected validation", gate)

    def test_oci_documentation_preserves_caller_ownership_and_release_evidence(self) -> None:
        documents = {
            "README.md": (ROOT / "README.md").read_text(),
            "PUBLISHING_PLAN.md": (ROOT / "PUBLISHING_PLAN.md").read_text(),
            "docs/release-notes.md": (ROOT / "docs/release-notes.md").read_text(),
        }

        for name, document in documents.items():
            with self.subTest(document=name):
                self.assertIn('--user "$(id -u):$(id -g)"', document)
                self.assertIn(":ro", document)
                self.assertIn("digest-first", document)
                self.assertIn("gh attestation verify", document)

    def test_release_workflows_never_publish_trusted_diagnostics_or_receipts(self) -> None:
        for name in ("ci.yml", "release.yml", "testpypi.yml"):
            workflow = (ROOT / ".github/workflows" / name).read_text()
            with self.subTest(workflow=name):
                self.assertNotIn("--diagnostics", workflow)
                self.assertNotIn("--receipt", workflow)
                self.assertNotIn("git-history-sanitize-scope.json", workflow)

    def test_release_promotes_only_a_scanned_and_attested_digest(self) -> None:
        workflow = (ROOT / ".github/workflows/release.yml").read_text()
        image = workflow[workflow.index("publish-image:"):workflow.index("github-release:")]

        amd64 = workflow[workflow.index("build-amd64-image:"):workflow.index("validate-arm64-image:")]
        arm64 = workflow[workflow.index("validate-arm64-image:"):workflow.index("publish-image:")]

        self.assertIn("runs-on: ubuntu-24.04", amd64)
        self.assertIn("platforms: linux/amd64", amd64)
        self.assertIn("runs-on: ubuntu-24.04-arm", arm64)
        self.assertIn("platforms: linux/arm64", arm64)
        self.assertNotIn("setup-qemu-action", arm64)
        self.assertIn('test "$(uname -m)" = "aarch64"', arm64)
        self.assertIn("GHS_OCI_PLATFORM: linux/arm64", arm64)
        self.assertIn("docker image inspect --format '{{.Config.User}}'", arm64)
        self.assertIn('--user "$(id -u):$(id -g)"', arm64)
        self.assertIn("test_output_is_bare_and_has_no_cleanup_artifacts", arm64)
        for job in (amd64, arm64):
            self.assertIn("push-by-digest=true", job)
            self.assertIn("name-canonical=true", job)
            self.assertIn("SOURCE_DATE_EPOCH=${{ steps.source.outputs.date_epoch }}", job)
            self.assertIn("SOURCE_REVISION=${{ github.sha }}", job)
            self.assertIn("PACKAGE_VERSION=${{ needs.release-gate.outputs.version }}", job)

        self.assertIn("needs: [release-gate, build-amd64-image, validate-arm64-image]", image)
        self.assertIn("docker buildx imagetools create", image)
        self.assertIn("needs.build-amd64-image.outputs.digest", image)
        self.assertIn("needs.validate-arm64-image.outputs.digest", image)
        self.assertNotIn("tags: ${{ steps.metadata.outputs.tags }}", image)
        self.assertIn("image-ref: ${{ env.IMAGE_NAME }}@${{ steps.push.outputs.digest }}", image)
        self.assertIn("subject-digest: ${{ steps.push.outputs.digest }}", image)
        self.assertIn('docker buildx imagetools create --tag "$tag" "$IMAGE_NAME@$DIGEST"', image)
        self.assertLess(image.index("image-ref:"), image.index("subject-digest:"))
        self.assertLess(image.index("subject-digest:"), image.rindex("imagetools create"))

    def test_security_refresh_scans_the_pinned_container_and_tracks_exceptions(self) -> None:
        workflow = (ROOT / ".github/workflows/security-refresh.yml").read_text()
        dependabot = (ROOT / ".github/dependabot.yml").read_text()
        ignore = (ROOT / "security/trivyignore.yaml").read_text()
        process = (ROOT / "docs/security-update-process.md").read_text()

        self.assertIn("pull_request:", workflow)
        self.assertIn("schedule:", workflow)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("trivyignores: security/trivyignore.yaml", workflow)
        self.assertIn("exit-code: \"1\"", workflow)
        self.assertIn("severity: HIGH,CRITICAL", workflow)
        self.assertEqual(json.loads(ignore)["vulnerabilities"], [])
        self.assertIn("expired_at", process)
        self.assertIn("owner", process.lower())
        self.assertIn("Dependabot", process)
        self.assertIn('package-ecosystem: docker', dependabot)
        self.assertIn('package-ecosystem: github-actions', dependabot)
        self.assertIn("interval: weekly", dependabot)
        self.assertIn("branches: [main]", workflow)
        self.assertNotIn("docker push", workflow)
        self.assertNotIn("gh pr create", workflow)

    def test_workflow_actions_are_pinned_to_full_commit_shas(self) -> None:
        for path in (ROOT / ".github/workflows").glob("*.yml"):
            workflow = path.read_text()
            for action in re.findall(r"^\s*uses:\s*([^\s#]+)", workflow, re.MULTILINE):
                with self.subTest(workflow=path.name, action=action):
                    self.assertRegex(action, r"^[\w.-]+/[\w.-]+@[0-9a-f]{40}$")
