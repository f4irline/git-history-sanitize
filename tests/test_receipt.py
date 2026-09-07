import hashlib
import json
import unittest

from git_history_sanitize.receipt import Receipt, ReceiptError


class ReceiptTests(unittest.TestCase):
    def test_canonical_bytes_have_a_newline_and_round_trip(self) -> None:
        receipt = Receipt.create(
            generator_version="0.1.0",
            source_object_format="sha1",
            source_fingerprint="a" * 64,
            source_head="b" * 40,
            cutoff_commit="c" * 40,
            boundary_tree="d" * 40,
            policy_digest="e" * 64,
            sanitized_object_format="sha1",
            sanitized_root="f" * 40,
            sanitized_head="0" * 40,
        )

        encoded = receipt.to_bytes()

        self.assertTrue(encoded.endswith(b"\n"))
        self.assertEqual(Receipt.from_bytes(encoded), receipt)

    def test_rejects_duplicate_and_noncanonical_json(self) -> None:
        with self.assertRaisesRegex(ReceiptError, "malformed"):
            Receipt.from_bytes(b'{"format":"a","format":"b"}\n')
        with self.assertRaisesRegex(ReceiptError, "malformed"):
            Receipt.from_bytes(b"{}\n")

    def test_rejects_corrupt_integrity_digest(self) -> None:
        receipt = Receipt.create(
            generator_version="0.1.0", source_object_format="sha1", source_fingerprint="a" * 64,
            source_head="b" * 40, cutoff_commit="c" * 40, boundary_tree="d" * 40,
            policy_digest="e" * 64, sanitized_object_format="sha1", sanitized_root="f" * 40,
            sanitized_head="0" * 40,
        )
        payload = json.loads(receipt.to_bytes())
        payload["digest"] = "0" * 64

        with self.assertRaisesRegex(ReceiptError, "integrity"):
            Receipt.from_bytes(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode() + b"\n")

    def test_fingerprint_frames_raw_fields(self) -> None:
        fingerprint = Receipt.source_fingerprint(
            "sha1", "symref", b"refs/heads/main", "a" * 40,
            ((b"refs/heads/main", "a" * 40),),
        )
        expected = hashlib.sha256(
            b"git-history-sanitize-source-fingerprint-v1"
            + (4).to_bytes(8, "big") + b"sha1"
            + (6).to_bytes(8, "big") + b"symref"
            + (15).to_bytes(8, "big") + b"refs/heads/main"
            + (40).to_bytes(8, "big") + b"a" * 40
            + (71).to_bytes(8, "big")
            + (15).to_bytes(8, "big") + b"refs/heads/main"
            + (40).to_bytes(8, "big") + b"a" * 40
        ).hexdigest()
        self.assertEqual(fingerprint, expected)


if __name__ == "__main__":
    unittest.main()
