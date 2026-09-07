# Discoveries

How things work in this codebase. Tribal knowledge, written down.

---

## Preserve symbolic ref bytes during verification
**Ticket:** BBQ-5
**Date:** 2026-09-07

Git permits UTF-8 branch names. Decode `symbolic-ref` and `for-each-ref` values
with UTF-8 plus `surrogateescape` in verifier checks so a valid symbolic HEAD
round-trips through subprocess calls instead of being rejected as an invariant
failure. Cover this with a valid rewritten artifact whose branch is non-ASCII.

---
