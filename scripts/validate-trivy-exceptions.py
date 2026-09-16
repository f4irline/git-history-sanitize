#!/usr/bin/env python3
"""Fail closed on malformed, unowned, or expired Trivy exceptions."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path


REQUIRED_FIELDS = {"id", "statement", "owner", "issue", "expired_at"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--today", type=dt.date.fromisoformat, default=dt.date.today())
    arguments = parser.parse_args()
    try:
        document = json.loads(arguments.path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"invalid Trivy exceptions: {error}") from error
    exceptions = document.get("vulnerabilities") if isinstance(document, dict) else None
    if not isinstance(exceptions, list):
        raise SystemExit("invalid Trivy exceptions: vulnerabilities must be a list")
    for exception in exceptions:
        if not isinstance(exception, dict) or REQUIRED_FIELDS - exception.keys():
            raise SystemExit("invalid Trivy exception: id, statement, owner, issue, and expired_at are required")
        try:
            expiry = dt.date.fromisoformat(str(exception["expired_at"]))
        except ValueError as error:
            raise SystemExit("invalid Trivy exception: expired_at must be an ISO date") from error
        if expiry < arguments.today:
            raise SystemExit(f"expired Trivy exception: {exception['id']}")
        if expiry > arguments.today + dt.timedelta(days=30):
            raise SystemExit(f"Trivy exception expires after 30 days: {exception['id']}")


if __name__ == "__main__":
    main()
