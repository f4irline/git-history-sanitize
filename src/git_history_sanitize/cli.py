"""Command-line interface for Git History Sanitize."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from .engine import plan, rewrite
from .errors import SanitizeError
from .git import ensure_dependencies
from .policy import Policy
from .verify import verify


def _policy(path: str) -> Policy:
    return Policy.from_file(path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="git-history-sanitize")
    subcommands = parser.add_subparsers(dest="command", required=True)

    doctor = subcommands.add_parser("doctor", help="check required Git tooling")
    doctor.add_argument("--json", action="store_true")

    preview = subcommands.add_parser("plan", help="inspect a proposed rewrite")
    preview.add_argument("--source", required=True)
    preview.add_argument("--policy", required=True)
    preview.add_argument("--json", action="store_true")

    rewrite_command = subcommands.add_parser("rewrite", help="create sanitized output")
    rewrite_command.add_argument("--source", required=True)
    rewrite_command.add_argument("--output", required=True)
    rewrite_command.add_argument("--policy", required=True)
    rewrite_command.add_argument("--json", action="store_true")

    verification = subcommands.add_parser("verify", help="verify sanitized output")
    verification.add_argument("--repository", required=True)
    verification.add_argument("--policy", required=True)
    verification.add_argument("--forbid", action="append", default=[])
    verification.add_argument("--json", action="store_true")
    return parser


def _print(value: object, as_json: bool) -> None:
    if as_json:
        if hasattr(value, "to_dict"):
            print(json.dumps(value.to_dict(), sort_keys=True))
        elif hasattr(value, "to_json"):
            print(value.to_json())
        else:
            print(json.dumps(asdict(value), sort_keys=True))
        return
    if hasattr(value, "verification"):
        print(f"Sanitized HEAD: {value.verification.head}")
        print(f"Commits in output: {value.verification.commit_count}")
        return
    if hasattr(value, "source_commits"):
        print(f"Source commits: {value.source_commits}")
        print(f"Pre-cutoff commits: {value.discarded_commits}")
        print(f"Commits before path filtering: {value.retained_commits_before_path_filter}")
        return
    print("Verification passed.")


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "doctor":
            result = ensure_dependencies()
            print(json.dumps(result, sort_keys=True) if arguments.json else "\n".join(result.values()))
            return 0
        policy = _policy(arguments.policy)
        if arguments.command == "plan":
            _print(plan(arguments.source, policy), arguments.json)
        elif arguments.command == "rewrite":
            _print(rewrite(arguments.source, arguments.output, policy), arguments.json)
        elif arguments.command == "verify":
            _print(
                verify(arguments.repository, policy, tuple(arguments.forbid)),
                arguments.json,
            )
        return 0
    except SanitizeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
