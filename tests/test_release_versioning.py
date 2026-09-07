"""Release version gate contracts."""

from __future__ import annotations

import importlib.util
import tarfile
import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from tests.support.git_fixture import GitFixture


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("release", ROOT / "scripts" / "release.py")
assert SPEC and SPEC.loader
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


class ReleaseVersioningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = GitFixture(self)
        self.version_file = self.fixture.write(
            "src/git_history_sanitize/_version.py", '__version__ = "0.0.1"\n'
        )
        self.fixture.commit("initial", "src/git_history_sanitize/_version.py")
        self.root = release.ROOT
        self.release_version_file = release.VERSION_FILE
        release.ROOT = self.fixture.source
        release.VERSION_FILE = self.version_file
        self.addCleanup(setattr, release, "ROOT", self.root)
        self.addCleanup(setattr, release, "VERSION_FILE", self.release_version_file)

    def test_supported_versions_are_strict_stable_semver(self) -> None:
        self.assertEqual(release.parse_stable_version("1.2.3"), "1.2.3")
        for version in ("01.2.3", "1.02.3", "1.2.03", "1.2", "v1.2.3"):
            with self.assertRaisesRegex(ValueError, "stable SemVer"):
                release.parse_stable_version(version)

    def test_prerelease_is_rejected_with_a_stable_message(self) -> None:
        with self.assertRaisesRegex(ValueError, "prerelease tags are unsupported"):
            release.parse_tag("v1.2.3-rc.1")

    def test_tag_requires_the_v_prefix(self) -> None:
        self.assertEqual(release.parse_tag("v1.2.3"), "1.2.3")
        with self.assertRaisesRegex(ValueError, "release tag must be vMAJOR.MINOR.PATCH"):
            release.parse_tag("1.2.3")

    def test_artifact_validator_requires_matching_names_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self._write_artifacts(directory, "1.2.3")

            manifest = release.validate_artifacts(directory, "1.2.3")

            self.assertEqual(manifest["version"], "1.2.3")
            self.assertEqual(len(manifest["artifacts"]), 2)
            self.assertTrue((directory / "SHA256SUMS").is_file())
            self.assertTrue((directory / "version-manifest.json").is_file())

    def test_artifact_validator_rejects_invalid_filenames(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self._write_artifacts(directory, "1.2.3")
            (directory / "unexpected.txt").write_text("not a distribution\n")

            with self.assertRaisesRegex(ValueError, "artifact filenames are invalid"):
                release.validate_artifacts(directory, "1.2.3")

    def test_artifact_validator_rejects_mismatched_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self._write_artifacts(directory, "1.2.3", wheel_version="1.2.4")

            with self.assertRaisesRegex(ValueError, "artifact metadata version differs"):
                release.validate_artifacts(directory, "1.2.3")

    def test_tag_gate_requires_an_annotated_tag_at_head(self) -> None:
        self.fixture.tag("v1.2.3", "release")
        with patch.object(release, "git", side_effect=self._git):
            release.validate_tag("v1.2.3", "1.2.3")

        self.fixture.git(self.fixture.source, "tag", "v1.2.4")
        with patch.object(release, "git", side_effect=self._git):
            with self.assertRaisesRegex(ValueError, "annotated"):
                release.validate_tag("v1.2.4", "1.2.4")

    def test_tag_gate_rejects_a_tag_that_differs_from_the_source_version(self) -> None:
        self.fixture.tag("v1.2.3", "release")

        with self.assertRaisesRegex(ValueError, "tag and source version differ"):
            release.validate_tag("v1.2.3", "1.2.4")

    def test_prepare_rejects_dirty_and_duplicate_local_or_remote_tags(self) -> None:
        self.fixture.write("dirty.txt", "dirty\n")
        with patch.object(release, "git", side_effect=self._git):
            with self.assertRaisesRegex(ValueError, "working tree must be clean"):
                release.prepare("1.2.3", push=False)

        self.fixture.git(self.fixture.source, "clean", "-fd")
        self.fixture.tag("v1.2.3", "release")
        with patch.object(release, "git", side_effect=self._git):
            with self.assertRaisesRegex(ValueError, "release tag already exists"):
                release.prepare("1.2.3", push=False)

        self.fixture.git(self.fixture.source, "tag", "-d", "v1.2.3")
        with patch.object(release, "tag_exists", return_value=False), patch.object(
            release, "git", side_effect=lambda *args: "remote-tag" if args[0] == "ls-remote" else self._git(*args)
        ):
            with self.assertRaisesRegex(ValueError, "release tag already exists"):
                release.prepare("1.2.3", push=False)

    def test_prepare_default_does_not_push_and_explicit_push_follows_tag_creation(self) -> None:
        calls: list[tuple[str, ...]] = []

        def git(*arguments: str) -> str:
            calls.append(arguments)
            if arguments[0] in {"ls-remote", "push"}:
                return ""
            return self._git(*arguments)

        with self._prepared(git):
            release.prepare("1.2.3", push=False)
        self.assertFalse(any(call[0] == "push" for call in calls))

        self.fixture.git(self.fixture.source, "tag", "-d", "v1.2.3")
        self.fixture.git(self.fixture.source, "reset", "--hard", "HEAD~1")
        calls.clear()
        with self._prepared(git):
            release.prepare("1.2.3", push=True)
        tag_index = calls.index(("tag", "-a", "v1.2.3", "-m", "Release 1.2.3"))
        self.assertTrue(all(index > tag_index for index, call in enumerate(calls) if call[0] == "push"))

    def test_prepare_rolls_back_local_commit_tag_and_index_on_commit_tag_or_push_failure(self) -> None:
        for failure in (("commit", "-m"), ("tag", "-a"), ("push", "origin")):
            with self.subTest(failure=failure):
                original_head = self.fixture.git(self.fixture.source, "rev-parse", "HEAD")

                def git(*arguments: str) -> str:
                    if arguments[:2] == failure:
                        raise ValueError("release mutation failed")
                    if arguments[0] == "ls-remote":
                        return ""
                    return self._git(*arguments)

                with self._prepared(git):
                    with self.assertRaisesRegex(ValueError, "release mutation failed"):
                        release.prepare("1.2.3", push=failure[0] == "push")

                self.assertEqual(self.fixture.git(self.fixture.source, "rev-parse", "HEAD"), original_head)
                self.assertEqual(self.fixture.git(self.fixture.source, "status", "--porcelain=v1"), "")
                self.assertEqual(self.fixture.git(self.fixture.source, "tag", "-l", "v1.2.3"), "")

    def _prepared(self, git: object):
        return patch.multiple(
            release,
            git=git,
            tag_exists=lambda _: False,
            check=lambda *_: "1.2.3",
            run_release_tests=lambda: True,
        )

    def _write_artifacts(self, directory: Path, version: str, wheel_version: str | None = None) -> None:
        wheel = directory / f"git_history_sanitize-{version}-py3-none-any.whl"
        with zipfile.ZipFile(wheel, "w") as archive:
            archive.writestr(
                f"git_history_sanitize-{version}.dist-info/METADATA",
                f"Metadata-Version: 2.1\nVersion: {wheel_version or version}\n",
            )
        sdist = directory / f"git_history_sanitize-{version}.tar.gz"
        with tarfile.open(sdist, "w:gz") as archive:
            payload = f"Metadata-Version: 2.1\nVersion: {version}\n".encode()
            info = tarfile.TarInfo(f"git_history_sanitize-{version}/PKG-INFO")
            info.size = len(payload)
            archive.addfile(info, BytesIO(payload))

    def _git(self, *arguments: str) -> str:
        return self.fixture.git(self.fixture.source, *arguments)
