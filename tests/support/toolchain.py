#!/usr/bin/env python3
"""Fail closed unless the supported Git toolchain is on PATH."""

import subprocess
from collections.abc import Sequence


GIT_OUTPUT = "git version 2.47.0\n"
FILTER_REPO_OUTPUT = "bc98e38e057b\n"


def command_output(command: Sequence[str], expected: str, label: str) -> None:
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        raise SystemExit(f"{label} is required on PATH") from None
    if result.returncode != 0:
        raise SystemExit(f"{label} command failed")
    if result.stdout != expected or result.stderr:
        raise SystemExit(f"unsupported {label}; expected pinned upstream output")


def main() -> None:
    command_output(("git", "--version"), GIT_OUTPUT, "Git 2.47.0")
    command_output(("git", "filter-repo", "--version"), FILTER_REPO_OUTPUT, "git-filter-repo")
    print(GIT_OUTPUT, end="")
    print(f"git-filter-repo {FILTER_REPO_OUTPUT}", end="")


if __name__ == "__main__":
    main()
