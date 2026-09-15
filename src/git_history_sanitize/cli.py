"""Command-line interface for Git History Sanitize."""

from __future__ import annotations

import argparse
import sys

from ._version import __version__
from .engine import plan, rewrite
from .errors import SanitizeError, UsageError
from .forbidden import collect
from .git import ensure_dependencies
from .policy import Policy
from .reporting import error_document, success_document
from .verify import verify


def _policy(path: str) -> Policy:
    return Policy.from_file(path)


class _ArgumentParser(argparse.ArgumentParser):
    """Keep JSON parser errors inside the same redacted CLI boundary."""

    json_mode = False

    def error(self, message: str) -> None:
        if self.json_mode:
            raise UsageError("invalid command arguments")
        super().error(message)


def _parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(prog="git-history-sanitize")
    parser.add_argument("--version", action="version", version=__version__)
    subcommands = parser.add_subparsers(dest="command", required=True, parser_class=_ArgumentParser)

    doctor = subcommands.add_parser("doctor", help="check required Git tooling")
    doctor.add_argument("--json", action="store_true")

    preview = subcommands.add_parser("plan", help="inspect a proposed rewrite")
    preview.add_argument("--source", required=True)
    preview.add_argument("--policy", required=True)
    preview.add_argument("--json", action="store_true")
    preview.add_argument("--strip-hooks", action="store_true")

    rewrite_command = subcommands.add_parser("rewrite", help="create sanitized output")
    rewrite_command.add_argument("--source", required=True)
    rewrite_command.add_argument("--output", required=True)
    rewrite_command.add_argument("--policy", required=True)
    rewrite_command.add_argument("--receipt")
    rewrite_command.add_argument("--json", action="store_true")
    rewrite_command.add_argument("--strip-hooks", action="store_true")

    verification = subcommands.add_parser("verify", help="verify sanitized output")
    verification.add_argument("--repository", required=True)
    verification.add_argument("--policy", required=True)
    verification.add_argument("--source")
    verification.add_argument("--receipt")
    verification.add_argument("--forbid", action="append", default=[])
    verification.add_argument("--forbid-file", action="append", default=[])
    verification.add_argument("--forbid-stdin", action="store_true")
    verification.add_argument("--json", action="store_true")
    return parser


def _parse(argv: list[str], json_mode: bool) -> argparse.Namespace:
    parser = _parser()
    parser.json_mode = json_mode
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for subparser in action.choices.values():
                subparser.json_mode = json_mode
    return parser.parse_args(argv)


def _print(value: object) -> None:
    if hasattr(value, "verification"):
        print(f"Sanitized HEAD: {value.verification.head}")
        print(f"Commits in output: {value.verification.commit_count}")
        print(f"Scope: {value.verification.scope}")
        print(f"Hooks: {value.hooks_stripped and 'stripped' or 'preserved'} ({', '.join(value.hooks.names) or 'none'})")
        return
    if hasattr(value, "source_commits"):
        print(f"Source commits: {value.source_commits}")
        print(f"Pre-cutoff commits: {value.discarded_commits}")
        print(f"Commits before path filtering: {value.retained_commits_before_path_filter}")
        print(f"Retained HEAD paths: {value.retained_head_path_count}")
        print(f"Excluded paths: {', '.join(value.excluded_paths) or 'none'}")
        print(f"Scope: {value.scope}")
        print(f"Hooks: {value.hooks_stripped and 'stripped' or 'preserved'} ({', '.join(value.hooks.names) or 'none'})")
        return
    print("Verification passed.")


def main(argv: list[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    json_mode = "--json" in values
    command = next((value for value in values if value in {"doctor", "plan", "rewrite", "verify"}), "unknown")
    try:
        arguments = _parse(values, json_mode)
        command = arguments.command
        if command == "doctor":
            result = ensure_dependencies()
            if arguments.json:
                sys.stdout.write(success_document(command, result))
            else:
                print("\n".join(result.values()))
            return 0

        policy = _policy(arguments.policy)
        if command == "plan":
            result = plan(arguments.source, policy, preserve_hooks=not arguments.strip_hooks)
        elif command == "rewrite":
            result = rewrite(
                arguments.source, arguments.output, policy, arguments.receipt,
                preserve_hooks=not arguments.strip_hooks,
            )
        else:
            forbidden = collect(
                arguments.forbid,
                arguments.forbid_file,
                sys.stdin.buffer if arguments.forbid_stdin else None,
            )
            result = verify(
                arguments.repository, policy, forbidden,
                source=arguments.source, receipt=arguments.receipt,
            )
        if arguments.json:
            sys.stdout.write(success_document(command, result))
        else:
            _print(result)
        return 0
    except SanitizeError as error:
        if json_mode:
            sys.stdout.write(error_document(command, error))
        else:
            print(f"error: {error}", file=sys.stderr)
        return 2
    except Exception:
        if json_mode:
            sys.stdout.write(error_document(command))
        else:
            print("error: unexpected internal error", file=sys.stderr)
        return 2
