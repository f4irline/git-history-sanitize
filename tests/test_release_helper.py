"""Release-helper shell interface contracts."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "prepare-release.sh"


class ReleaseHelperTests(unittest.TestCase):
    def test_help_is_actionable_and_successful(self) -> None:
        result = subprocess.run([str(HELPER), "--help"], text=True, capture_output=True)

        self.assertEqual(result.returncode, 0)
        self.assertIn("VERSION [--push]", result.stdout)
        self.assertIn("local version commit", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_invalid_arguments_fail_without_creating_an_environment(self) -> None:
        result = subprocess.run([str(HELPER), "1.2.3", "--invalid"], text=True, capture_output=True)

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("Usage:", result.stderr)


if __name__ == "__main__":
    unittest.main()
