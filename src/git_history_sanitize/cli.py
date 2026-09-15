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
from .reporting import error_document, error_text, success_document, success_text
from .verify import verify


def _policy(path: str) -> Policy:
    return Policy.from_file(path)


class _ArgumentParser(argparse.ArgumentParser):
    """Keep JSON parser errors inside the same redacted CLI boundary."""

    json_mode = False

    def error(self, message: str) -> None:
        raise UsageError("invalid command arguments")


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
    preview.add_argument("--json-schema", type=int, choices=(1, 2))
    preview.add_argument("--diagnostics", choices=("trusted",))
    preview.add_argument("--strip-hooks", action="store_true")

    rewrite_command = subcommands.add_parser("rewrite", help="create sanitized output")
    rewrite_command.add_argument("--source", required=True)
    rewrite_command.add_argument("--output", required=True)
    rewrite_command.add_argument("--policy", required=True)
    rewrite_command.add_argument("--receipt")
    rewrite_command.add_argument("--json", action="store_true")
    rewrite_command.add_argument("--json-schema", type=int, choices=(1, 2))
    rewrite_command.add_argument("--diagnostics", choices=("trusted",))
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
    verification.add_argument("--json-schema", type=int, choices=(1, 2))
    verification.add_argument("--diagnostics", choices=("trusted",))
    return parser


def _parse(argv: list[str], json_mode: bool) -> argparse.Namespace:
    parser = _parser()
    parser.json_mode = json_mode
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for subparser in action.choices.values():
                subparser.json_mode = json_mode
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    json_mode = "--json" in values
    command = next((value for value in values if value in {"doctor", "plan", "rewrite", "verify"}), "unknown")
    try:
        arguments = _parse(values, json_mode)
        command = arguments.command
        diagnostics = getattr(arguments, "diagnostics", None) or "public"
        requested_schema = getattr(arguments, "json_schema", None) or 2
        if getattr(arguments, "json_schema", None) is not None and not arguments.json:
            raise UsageError("JSON schema requires JSON output")
        if requested_schema == 1 and diagnostics != "trusted":
            raise UsageError("legacy JSON requires trusted diagnostics")
        schema_version = requested_schema
        if command == "doctor":
            result = ensure_dependencies()
            if arguments.json:
                sys.stdout.write(success_document(command, result))
            else:
                sys.stdout.write(success_text(command, result))
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
            sys.stdout.write(success_document(command, result, diagnostics=diagnostics, schema_version=schema_version))
        else:
            sys.stdout.write(success_text(command, result, diagnostics=diagnostics))
        return 0
    except SanitizeError as error:
        if json_mode:
            sys.stdout.write(error_document(command, error, schema_version=schema_version if 'schema_version' in locals() else 2, diagnostics=diagnostics if 'diagnostics' in locals() else "public"))
        else:
            sys.stderr.write(error_text(error))
        return 2
    except Exception:
        if json_mode:
            sys.stdout.write(error_document(command, schema_version=schema_version if 'schema_version' in locals() else 2, diagnostics=diagnostics if 'diagnostics' in locals() else "public"))
        else:
            sys.stderr.write(error_text())
        return 2
