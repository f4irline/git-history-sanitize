#!/usr/bin/env python3
"""Fail-closed local release preparation and artifact validation."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "src" / "git_history_sanitize" / "_version.py"
STABLE_VERSION = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z")


def parse_stable_version(value: str) -> str:
    if not STABLE_VERSION.fullmatch(value):
        raise ValueError("version must be stable SemVer MAJOR.MINOR.PATCH")
    return value


def parse_tag(tag: str) -> str:
    if not tag.startswith("v"):
        raise ValueError("release tag must be vMAJOR.MINOR.PATCH")
    version = tag[1:]
    if "-" in version:
        raise ValueError("prerelease tags are unsupported")
    return parse_stable_version(version)


def source_version() -> str:
    module = ast.parse(VERSION_FILE.read_text(), filename=str(VERSION_FILE))
    for node in module.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets
        ) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return parse_stable_version(node.value.value)
    raise ValueError("canonical version source is invalid")


def run(*arguments: str, cwd: Path | None = None) -> str:
    result = subprocess.run(
        arguments, cwd=cwd or ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    if result.returncode:
        raise ValueError("release validation failed")
    return result.stdout.strip()


def git(*arguments: str) -> str:
    return run("git", *arguments)


def validate_tag(tag: str, version: str) -> None:
    if parse_tag(tag) != version:
        raise ValueError("tag and source version differ")
    if git("cat-file", "-t", f"refs/tags/{tag}") != "tag":
        raise ValueError("release tag must be annotated")
    if git("rev-parse", f"{tag}^{{}}") != git("rev-parse", "HEAD"):
        raise ValueError("release tag must resolve to HEAD")


def artifact_metadata(path: Path, suffix: str) -> str:
    if suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
            if len(names) != 1:
                raise ValueError("wheel metadata is invalid")
            data = archive.read(names[0]).decode()
    else:
        with tarfile.open(path) as archive:
            names = [name for name in archive.getnames() if len(Path(name).parts) == 2 and name.endswith("/PKG-INFO")]
            if len(names) != 1:
                raise ValueError("sdist metadata is invalid")
            handle = archive.extractfile(names[0])
            if handle is None:
                raise ValueError("sdist metadata is invalid")
            data = handle.read().decode()
    for line in data.splitlines():
        if line.startswith("Version: "):
            return line.removeprefix("Version: ")
    raise ValueError("artifact metadata has no version")


def validate_artifacts(
    directory: Path, version: str, manifest_directory: Path | None = None
) -> dict[str, object]:
    expected = {
        f"git_history_sanitize-{version}-py3-none-any.whl": ".whl",
        f"git_history_sanitize-{version}.tar.gz": ".tar.gz",
    }
    artifacts = sorted(path for path in directory.iterdir() if path.is_file())
    if {path.name for path in artifacts} != set(expected):
        raise ValueError("artifact filenames are invalid")
    checksums: dict[str, str] = {}
    for path in artifacts:
        if artifact_metadata(path, expected[path.name]) != version:
            raise ValueError("artifact metadata version differs")
        checksums[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {"artifacts": checksums, "version": version}
    destination = manifest_directory or directory
    (destination / "version-manifest.json").write_text(json.dumps(manifest, sort_keys=True) + "\n")
    (destination / "SHA256SUMS").write_text(
        "".join(f"{digest}  {name}\n" for name, digest in checksums.items())
    )
    return manifest


def build_and_validate(version: str, output: Path) -> None:
    if output.exists():
        if any(output.iterdir()):
            raise ValueError("artifact output directory must be empty")
    else:
        output.mkdir(parents=True)
    distributions = output / "distributions"
    result = subprocess.run(
        [sys.executable, "-m", "build", "--no-isolation", "--outdir", str(distributions)],
        cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if result.returncode:
        raise ValueError("distribution build failed")
    validate_artifacts(distributions, version, output)


def check(tag: str | None, version: str | None, output: Path | None) -> str:
    if (tag is None) == (version is None):
        raise ValueError("specify exactly one of --tag or --version")
    candidate = parse_tag(tag) if tag else parse_stable_version(version or "")
    if source_version() != candidate:
        raise ValueError("tag and source version differ")
    if tag:
        validate_tag(tag, candidate)
    if output is None:
        with tempfile.TemporaryDirectory(prefix="git-history-sanitize-release-") as temporary:
            build_and_validate(candidate, Path(temporary))
    else:
        build_and_validate(candidate, output)
    return candidate


def tag_exists(tag: str) -> bool:
    return subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0


def run_release_tests() -> bool:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "-v",
            "tests.test_cli_contracts",
            "tests.test_receipt",
            "tests.test_release_versioning",
            "tests.test_release_workflow",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.returncode == 0


def prepare(version: str, push: bool) -> str:
    version = parse_stable_version(version)
    tag = f"v{version}"
    if git("status", "--porcelain=v1", "--untracked-files=all"):
        raise ValueError("working tree must be clean")
    if tag_exists(tag) or git("ls-remote", "--tags", "origin", f"refs/tags/{tag}"):
        raise ValueError("release tag already exists")
    original_head = git("rev-parse", "HEAD")
    original = VERSION_FILE.read_bytes()
    tag_created = False
    try:
        VERSION_FILE.write_text(f'"""Canonical package version."""\n\n__version__ = "{version}"\n')
        with tempfile.TemporaryDirectory(prefix="git-history-sanitize-release-") as temporary:
            check(None, version, Path(temporary))
        if not run_release_tests():
            raise ValueError("release tests failed")
        git("add", str(VERSION_FILE.relative_to(ROOT)))
        git("commit", "-m", f"chore(release): prepare {version}")
        git("tag", "-a", tag, "-m", f"Release {version}")
        tag_created = True
        branch = git("branch", "--show-current")
        if push:
            git("push", "origin", branch)
            git("push", "origin", tag)
        return f"release-prepare: {'pushed' if push else 'ready'} branch={branch} version={version} tag={tag}"
    except Exception:
        if tag_created:
            git("tag", "-d", tag)
        git("reset", "--mixed", original_head)
        if VERSION_FILE.read_bytes() != original:
            VERSION_FILE.write_bytes(original)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="release.py")
    commands = parser.add_subparsers(dest="command", required=True)
    check_command = commands.add_parser("check")
    group = check_command.add_mutually_exclusive_group(required=True)
    group.add_argument("--tag")
    group.add_argument("--version")
    check_command.add_argument("--output", type=Path)
    prepare_command = commands.add_parser("prepare")
    prepare_command.add_argument("version")
    prepare_command.add_argument("--push", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "check":
            print(f"version-gate: pass version={check(arguments.tag, arguments.version, arguments.output)}")
        else:
            print(prepare(arguments.version, arguments.push))
        return 0
    except ValueError as error:
        print(f"version-gate: fail {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
