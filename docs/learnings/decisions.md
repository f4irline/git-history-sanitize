# Decisions

Technical decisions and their rationale. Know why before you change.

---

## Report post-rename persistence uncertainty without rollback
**Ticket:** BBQ-31
**Date:** 2026-09-13

The successful native no-replace rename transfers output ownership and is the
publication linearization point. A subsequent parent-directory synchronization
failure must report whether the repository or only a receipt was published; it
must never attempt rollback or staging cleanup of the published entry.

---
