import unittest
from pathlib import Path
from unittest.mock import patch

from git_history_sanitize.errors import SanitizeError
from git_history_sanitize.publication import publish


class PublicationTests(unittest.TestCase):
    def test_linux_unknown_architecture_fails_before_selecting_a_syscall(self) -> None:
        with (
            patch("git_history_sanitize.publication.platform.system", return_value="Linux"),
            patch("git_history_sanitize.publication.platform.machine", return_value="mips64"),
            patch("git_history_sanitize.publication.ctypes.CDLL") as library,
            self.assertRaisesRegex(SanitizeError, "unsupported"),
        ):
            publish(Path("source"), Path("destination"))
        library.assert_not_called()


if __name__ == "__main__":
    unittest.main()
