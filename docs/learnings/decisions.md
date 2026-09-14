# Decisions

Technical decisions and their rationale. Know why before you change.

---

## Preserve a valid empty sanitized tree
**Ticket:** BBQ-11
**Date:** 2026-09-14

Version 1 accepts a non-empty source whose sanitized `HEAD` tree has no
retained paths. Keep `--prune-empty always`, then restore the captured
synthetic root only when filtering leaves `HEAD` unresolved. Construct its
empty tree through Git and preserve the branch ref, prefix message, and
boundary metadata so cleanup, receipt creation, and verification keep their
normal security guarantees.

---

## Report post-rename persistence uncertainty without rollback
**Ticket:** BBQ-31
**Date:** 2026-09-13

The successful native no-replace rename transfers output ownership and is the
publication linearization point. A subsequent parent-directory synchronization
failure must report whether the repository or only a receipt was published; it
must never attempt rollback or staging cleanup of the published entry.

---
