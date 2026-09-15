"""Trusted diagnostics must remain transient local report data."""

from __future__ import annotations

import json
import unittest

from tests.support.git_fixture import GitFixture


class DiagnosticsContracts(unittest.TestCase):
    def test_trusted_rewrite_never_persists_diagnostic_identity_data(self) -> None:
        fixture = GitFixture(self)
        excluded_path = "private-customer-data/secret.txt"
        hook_name = "trusted-preflight"
        fixture.write(excluded_path, "secret\n")
        fixture.write("allowed.txt", "safe\n")
        cutoff = fixture.commit("allowed history", "allowed.txt")
        hooks = fixture.source / ".git" / "hooks"
        hooks.mkdir()
        (hooks / hook_name).write_bytes(b"#!/bin/sh\nexit 0\n")
        policy = fixture.write_policy(cutoff=None, cutoff_commit=cutoff, excluded_paths=("private-customer-data/",))
        output = fixture.output_dir / "sanitized.git"
        receipt = fixture.receipt_dir / "receipt.json"

        result = fixture.run_cli(
            "rewrite", "--source", str(fixture.source / ".git"), "--output", str(output),
            "--policy", str(policy), "--receipt", str(receipt), "--json", "--diagnostics=trusted",
        )

        diagnostics = json.loads(result.stdout)["diagnostics"]
        self.assertIn("private-customer-data/", diagnostics["excluded_paths"])
        self.assertIn(hook_name, diagnostics["hook_names"])
        persisted = (output / "git-history-sanitize-scope.json").read_text() + receipt.read_text()
        fixture.assert_redacted(persisted, "private-customer-data", hook_name)
        self.assertFalse((output / "diagnostics").exists())


if __name__ == "__main__":
    unittest.main()
