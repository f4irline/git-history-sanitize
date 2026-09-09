"""Bounded forbidden-content matcher and input contracts."""

from __future__ import annotations

import io
import unittest
from unittest.mock import patch

from git_history_sanitize.forbidden import (
    CHUNK_SIZE,
    INPUT_LIMIT,
    TOTAL_LIMIT,
    ForbiddenInputError,
    Matcher,
    arguments,
    collect,
    read_records,
)
from git_history_sanitize.git import Repository
from git_history_sanitize.verify import _forbidden, _scan_hooks, _scan_object_bodies
from git_history_sanitize.errors import VerificationError

from tests.support.git_fixture import GitFixture


class ForbiddenContentTests(unittest.TestCase):
    def test_matcher_finds_a_pattern_split_across_chunks(self) -> None:
        matcher = Matcher((b"private-marker",))

        self.assertFalse(matcher.feed(b"private-"))
        self.assertTrue(matcher.feed(b"marker"))

    def test_matcher_does_not_match_across_separate_bodies(self) -> None:
        matcher = Matcher((b"private-marker",))

        self.assertFalse(matcher.feed(b"private-"))
        matcher.reset()
        self.assertFalse(matcher.feed(b"marker"))

    def test_raw_newline_records_preserve_non_utf8_bytes(self) -> None:
        self.assertEqual(read_records(io.BytesIO(b"one\ntwo\xff\n")), (b"one", b"two\xff"))

    def test_arguments_preserve_nfd_utf8_bytes_without_normalizing(self) -> None:
        nfd = "e\u0301"

        self.assertEqual(arguments((nfd,)), (nfd.encode("utf-8"),))
        self.assertNotEqual(arguments((nfd,)), ("\u00e9".encode("utf-8"),))

    def test_inputs_reject_empty_records_and_aggregate_across_sources(self) -> None:
        with self.assertRaises(ForbiddenInputError):
            arguments(("",))
        with self.assertRaises(ForbiddenInputError):
            read_records(io.BytesIO(b"\n"))
        with self.assertRaises(ForbiddenInputError):
            collect(
                (f"{index:02x}" + "a" * (INPUT_LIMIT - 2) for index in range(TOTAL_LIMIT // INPUT_LIMIT)),
                (),
                io.BytesIO(b"b"),
            )

    def test_raw_records_reject_an_oversized_record(self) -> None:
        with self.assertRaises(ForbiddenInputError):
            read_records(io.BytesIO(b"x" * (INPUT_LIMIT + 1)))

    def test_raw_records_reject_an_aggregate_over_the_limit(self) -> None:
        records = (b"a" * INPUT_LIMIT + b"\n") * (TOTAL_LIMIT // INPUT_LIMIT + 1)

        with self.assertRaises(ForbiddenInputError):
            read_records(io.BytesIO(records))

    def test_object_scanner_searches_bodies_not_batch_headers(self) -> None:
        fixture = GitFixture(self)
        fixture.write("safe.txt", "safe\n")
        fixture.commit("safe", "safe.txt")

        _scan_object_bodies(Repository(fixture.source), Matcher((b"blob",)))

    def test_object_scanner_matches_blob_commit_tree_and_annotated_tag_bodies(self) -> None:
        fixture = GitFixture(self)
        fixture.write("marker-blob", "safe\n")
        fixture.commit("marker-commit", "marker-blob")
        fixture.tag("release", "marker-tag")

        for pattern in (b"marker-blob", b"marker-commit", b"marker-tag"):
            with self.subTest(pattern=pattern), self.assertRaises(VerificationError) as error:
                _forbidden(Repository(fixture.source), (pattern,))
            self.assertEqual(error.exception.invariant, "content.forbidden")

    def test_object_scanner_matches_binary_unicode_and_multiple_patterns(self) -> None:
        fixture = GitFixture(self)
        fixture.add_unreachable_blob(b"\x00safe\xff\xc3\xa9\x00")

        with self.assertRaises(VerificationError) as error:
            _forbidden(Repository(fixture.source), (b"absent", b"\xff\xc3\xa9"))
        self.assertEqual(error.exception.invariant, "content.forbidden")

    def test_object_scanner_matches_across_chunks_but_not_objects(self) -> None:
        fixture = GitFixture(self)
        marker = b"private-marker"
        fixture.add_unreachable_blob(b"x" * (CHUNK_SIZE * 3 - len(marker) // 2) + marker)

        class RecordingMatcher(Matcher):
            def __init__(self) -> None:
                super().__init__((marker,))
                self.sizes: list[int] = []

            def feed(self, data: bytes) -> bool:
                self.sizes.append(len(data))
                return super().feed(data)

        matcher = RecordingMatcher()
        with self.assertRaises(VerificationError):
            _scan_object_bodies(Repository(fixture.source), matcher)
        self.assertGreaterEqual(len(matcher.sizes), 2)
        self.assertLessEqual(max(matcher.sizes), CHUNK_SIZE)

        fixture = GitFixture(self)
        fixture.add_unreachable_blob(b"private-")
        fixture.add_unreachable_blob(b"marker")
        _scan_object_bodies(Repository(fixture.source), Matcher((marker,)))

    def test_object_scanner_rejects_malformed_cat_file_protocol(self) -> None:
        class Process:
            stdout = io.BytesIO(b"not a cat-file header\n")

            def wait(self) -> int:
                return 0

            def poll(self) -> int:
                return 0

            def terminate(self) -> None:
                raise AssertionError("unexpected terminate")

        fixture = GitFixture(self)
        repository = Repository(fixture.source)
        with (
            patch.object(repository, "object_format", return_value="sha1"),
            patch("git_history_sanitize.verify.subprocess.Popen", return_value=Process()),
        ):
            with self.assertRaises(VerificationError) as error:
                _forbidden(repository, (b"marker",))
        self.assertEqual(error.exception.invariant, "content.forbidden")

    def test_object_scanner_rejects_truncated_declared_cat_file_body(self) -> None:
        class Process:
            stdout = io.BytesIO(b"0" * 40 + b" blob 4\nabc")

            def wait(self) -> int:
                return 0

            def poll(self) -> int:
                return 0

            def terminate(self) -> None:
                raise AssertionError("unexpected terminate")

        fixture = GitFixture(self)
        repository = Repository(fixture.source)
        with (
            patch.object(repository, "object_format", return_value="sha1"),
            patch("git_history_sanitize.verify.subprocess.Popen", return_value=Process()),
        ):
            with self.assertRaises(VerificationError) as error:
                _forbidden(repository, (b"marker",))
        self.assertEqual(error.exception.invariant, "content.forbidden")

    def test_object_scanner_rejects_invalid_cat_file_body_delimiter(self) -> None:
        class Process:
            stdout = io.BytesIO(b"0" * 40 + b" blob 3\nabc!")

            def wait(self) -> int:
                return 0

            def poll(self) -> int:
                return 0

            def terminate(self) -> None:
                raise AssertionError("unexpected terminate")

        fixture = GitFixture(self)
        repository = Repository(fixture.source)
        with (
            patch.object(repository, "object_format", return_value="sha1"),
            patch("git_history_sanitize.verify.subprocess.Popen", return_value=Process()),
        ):
            with self.assertRaises(VerificationError) as error:
                _forbidden(repository, (b"marker",))
        self.assertEqual(error.exception.invariant, "content.forbidden")

    def test_hook_scanner_checks_immediate_regular_files(self) -> None:
        fixture = GitFixture(self)
        hook = fixture.source / ".git" / "hooks" / "post-commit"
        hook.parent.mkdir()
        hook.write_bytes(b"private-marker\n")

        with self.assertRaises(VerificationError) as error:
            _scan_hooks(Repository(fixture.source), Matcher((b"private-marker",)))
        self.assertEqual(error.exception.invariant, "content.forbidden")

    def test_hook_scanner_rejects_nonregular_entries(self) -> None:
        fixture = GitFixture(self)
        hooks = fixture.source / ".git" / "hooks"
        hooks.mkdir()
        (hooks / "nested").mkdir(parents=True)

        with self.assertRaises(VerificationError) as error:
            _forbidden(Repository(fixture.source), (b"private-marker",))

        self.assertEqual(error.exception.invariant, "content.forbidden")

    def test_hook_scanner_rejects_symlinks(self) -> None:
        fixture = GitFixture(self)
        hooks = fixture.source / ".git" / "hooks"
        hooks.mkdir()
        target = fixture.root / "hook-target"
        target.write_bytes(b"safe\n")
        (hooks / "post-commit").symlink_to(target)

        with self.assertRaises(VerificationError) as error:
            _forbidden(Repository(fixture.source), (b"private-marker",))
        self.assertEqual(error.exception.invariant, "content.forbidden")

    def test_arguments_reject_non_utf8_text(self) -> None:
        with self.assertRaises(ForbiddenInputError):
            arguments(("\udcff",))


if __name__ == "__main__":
    unittest.main()
