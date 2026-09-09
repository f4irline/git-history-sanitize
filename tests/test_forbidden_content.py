"""Bounded forbidden-content matcher and input contracts."""

from __future__ import annotations

import io
import unittest

from git_history_sanitize.forbidden import (
    INPUT_LIMIT,
    TOTAL_LIMIT,
    ForbiddenInputError,
    Matcher,
    arguments,
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
        (hooks / "nested").mkdir(parents=True)

        with self.assertRaises(VerificationError) as error:
            _forbidden(Repository(fixture.source), (b"private-marker",))

        self.assertEqual(error.exception.invariant, "content.forbidden")

    def test_arguments_reject_non_utf8_text(self) -> None:
        with self.assertRaises(ForbiddenInputError):
            arguments(("\udcff",))


if __name__ == "__main__":
    unittest.main()
