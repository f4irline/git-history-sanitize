"""Private Receipt v1 evidence and source identity bindings."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable

from .errors import SanitizeError

_FORMAT = "git-history-sanitize-receipt"
_VERSION = 1
_WIDTHS = {"sha1": 40, "sha256": 64}


class ReceiptError(SanitizeError):
    """A redacted Receipt v1 validation failure."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReceiptError("sanitization receipt is malformed")
        result[key] = value
    return result


def _framed(value: bytes) -> bytes:
    return len(value).to_bytes(8, "big") + value


def _oid(value: object, object_format: str) -> bool:
    return (
        isinstance(value, str)
        and len(value) == _WIDTHS[object_format]
        and all(character in "0123456789abcdef" for character in value)
    )


@dataclass(frozen=True)
class Receipt:
    payload: dict[str, Any]

    @classmethod
    def create(
        cls,
        *,
        generator_version: str,
        source_object_format: str,
        source_fingerprint: str,
        source_head: str,
        cutoff_commit: str,
        boundary_tree: str,
        policy_digest: str,
        sanitized_object_format: str,
        sanitized_root: str,
        sanitized_head: str,
    ) -> "Receipt":
        value: dict[str, Any] = {
            "format": _FORMAT,
            "version": _VERSION,
            "generator": {"name": "git-history-sanitize", "version": generator_version},
            "source": {
                "object_format": source_object_format,
                "repository_fingerprint": source_fingerprint,
                "head": source_head,
                "cutoff_commit": cutoff_commit,
                "boundary_tree": boundary_tree,
            },
            "policy": {"sha256": policy_digest},
            "sanitized": {
                "object_format": sanitized_object_format,
                "root": sanitized_root,
                "head": sanitized_head,
            },
        }
        value["digest"] = hashlib.sha256(_canonical(value)).hexdigest()
        return cls._validate(value, verify_digest=True)

    @staticmethod
    def source_fingerprint(
        object_format: str,
        head_kind: str,
        head_ref: bytes,
        head: str,
        refs: Iterable[tuple[bytes, str]],
    ) -> str:
        ref_map = b"".join(_framed(name) + _framed(oid.encode("ascii")) for name, oid in refs)
        content = b"git-history-sanitize-source-fingerprint-v1" + b"".join(
            _framed(value)
            for value in (object_format.encode("ascii"), head_kind.encode("ascii"), head_ref, head.encode("ascii"), ref_map)
        )
        return hashlib.sha256(content).hexdigest()

    @classmethod
    def from_bytes(cls, data: bytes) -> "Receipt":
        if data.startswith(b"\xef\xbb\xbf"):
            raise ReceiptError("sanitization receipt is malformed")
        try:
            decoded = data.decode("utf-8")
            value = json.loads(decoded, object_pairs_hook=_object)
        except (UnicodeDecodeError, json.JSONDecodeError, ReceiptError) as error:
            if isinstance(error, ReceiptError):
                raise
            raise ReceiptError("sanitization receipt is malformed") from error
        receipt = cls._validate(value, verify_digest=True)
        if data != receipt.to_bytes():
            raise ReceiptError("sanitization receipt is malformed")
        return receipt

    @classmethod
    def _validate(cls, value: object, *, verify_digest: bool) -> "Receipt":
        if not isinstance(value, dict) or set(value) != {"format", "version", "generator", "source", "policy", "sanitized", "digest"}:
            raise ReceiptError("sanitization receipt is malformed")
        generator, source, policy, sanitized = (value[name] for name in ("generator", "source", "policy", "sanitized"))
        if value["format"] != _FORMAT or type(value["version"]) is not int or value["version"] != _VERSION:
            raise ReceiptError("sanitization receipt is malformed")
        if not isinstance(generator, dict) or set(generator) != {"name", "version"} or generator["name"] != "git-history-sanitize" or not isinstance(generator["version"], str):
            raise ReceiptError("sanitization receipt is malformed")
        if not isinstance(source, dict) or set(source) != {"object_format", "repository_fingerprint", "head", "cutoff_commit", "boundary_tree"}:
            raise ReceiptError("sanitization receipt is malformed")
        if not isinstance(sanitized, dict) or set(sanitized) != {"object_format", "root", "head"}:
            raise ReceiptError("sanitization receipt is malformed")
        if not isinstance(policy, dict) or set(policy) != {"sha256"}:
            raise ReceiptError("sanitization receipt is malformed")
        for binding in (source, sanitized):
            if binding["object_format"] not in _WIDTHS:
                raise ReceiptError("sanitization receipt is malformed")
        if not all(_oid(source[name], source["object_format"]) for name in ("head", "cutoff_commit", "boundary_tree")):
            raise ReceiptError("sanitization receipt is malformed")
        if not all(_oid(sanitized[name], sanitized["object_format"]) for name in ("root", "head")):
            raise ReceiptError("sanitization receipt is malformed")
        if not all(isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value) for value in (source["repository_fingerprint"], policy["sha256"], value["digest"])):
            raise ReceiptError("sanitization receipt is malformed")
        if verify_digest:
            payload = dict(value)
            digest = payload.pop("digest")
            if hashlib.sha256(_canonical(payload)).hexdigest() != digest:
                raise ReceiptError("sanitization receipt integrity check failed")
        return cls(value)

    def to_bytes(self) -> bytes:
        return _canonical(self.payload) + b"\n"
