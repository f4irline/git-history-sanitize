import unittest
import tempfile
import errno
import threading
from pathlib import Path
from unittest.mock import patch

from git_history_sanitize.errors import SanitizeError
from git_history_sanitize.publication import publication_error, publish, sync_published_parent


class PublicationTests(unittest.TestCase):
    def test_publication_error_categories_are_actionable_and_redacted(self) -> None:
        cases = {
            errno.EEXIST: "Publication destination already exists",
            errno.EACCES: "Publication failed: permission denied",
            errno.EPERM: "Publication failed: permission denied",
            errno.ENOSPC: "Publication failed: insufficient storage",
            errno.ENOTDIR: "Publication failed: destination or parent has an incompatible type",
            errno.EXDEV: "Publication failed: source and destination must share a filesystem",
        }

        for native_errno, expected in cases.items():
            with self.subTest(native_errno=native_errno):
                error = publication_error(native_errno)
                self.assertEqual(str(error), expected)
                self.assertNotIn("/private/source", str(error))
                self.assertNotIn("/private/destination", str(error))

    def test_parent_sync_failure_reports_already_published_output(self) -> None:
        with (
            patch("git_history_sanitize.publication.os.open", return_value=3),
            patch("git_history_sanitize.publication.os.fsync", side_effect=OSError(errno.EIO, "I/O")),
            patch("git_history_sanitize.publication.os.close"),
            self.assertRaisesRegex(
                SanitizeError,
                "Output was published but parent-directory durability could not be confirmed",
            ),
        ):
            sync_published_parent(Path("/private/output"))

    def test_unsupported_parent_sync_reports_atomic_visibility_only(self) -> None:
        with (
            patch("git_history_sanitize.publication.os.open", return_value=3),
            patch("git_history_sanitize.publication.os.fsync", side_effect=OSError(errno.EINVAL, "unsupported")),
            patch("git_history_sanitize.publication.os.close"),
        ):
            self.assertFalse(sync_published_parent(Path("/private/output")))

    def test_linux_unknown_architecture_fails_before_selecting_a_syscall(self) -> None:
        with (
            patch("git_history_sanitize.publication.platform.system", return_value="Linux"),
            patch("git_history_sanitize.publication.platform.machine", return_value="mips64"),
            patch("git_history_sanitize.publication.ctypes.CDLL") as library,
            self.assertRaisesRegex(SanitizeError, "unsupported"),
        ):
            publish(Path("source"), Path("destination"))
        library.assert_not_called()

    def test_native_publish_preserves_an_existing_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = directory / "source"
            destination = directory / "destination"
            source.write_bytes(b"new")
            destination.write_bytes(b"original")

            with self.assertRaisesRegex(SanitizeError, "already exists"):
                publish(source, destination)

            self.assertEqual(destination.read_bytes(), b"original")
            self.assertEqual(source.read_bytes(), b"new")

    def test_competing_publishers_have_one_winner_without_clobbering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            destination = directory / "destination"
            first = directory / "first"
            second = directory / "second"
            first.write_bytes(b"first")
            second.write_bytes(b"second")
            start = threading.Barrier(2)
            results: list[str] = []

            def attempt(source: Path) -> None:
                start.wait()
                try:
                    publish(source, destination)
                    results.append("published")
                except SanitizeError as error:
                    results.append(str(error))

            threads = [threading.Thread(target=attempt, args=(source,)) for source in (first, second)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            self.assertEqual(results.count("published"), 1)
            self.assertEqual(results.count("Publication destination already exists"), 1)
            self.assertIn(destination.read_bytes(), {b"first", b"second"})


if __name__ == "__main__":
    unittest.main()
