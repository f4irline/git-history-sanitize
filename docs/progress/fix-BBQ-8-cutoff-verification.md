# BBQ-8: Make cutoffCommit independently verifiable

**Branch:** `fix/BBQ-8-cutoff-verification`
**Worktree:** `/Users/tlepola/Documents/dev/projects/personal/git-history-sanitize/.opencode/.bbq-worktrees/fix-BBQ-8-cutoff-verification`
**Status:** In Progress
**Started:** 2026-09-07
**Last Updated:** 2026-09-07 12:20

## Overview

Implement private Receipt v1 evidence for `history.cutoffCommit`, source-backed
verification, strict cutoff identity resolution, atomic no-clobber publication,
and the accompanying contract tests, documentation, and CI coverage.

## Workflow Checklist

> **IMPORTANT**: This checklist ensures all workflow steps are completed, even after context compaction.
> Check off each phase as you complete it. After ANY interruption, read this section first.

### Phase 1: Implementation
- [x] Write/modify tests (TDD)
- [x] Implement changes
- [x] Validate (lint, build, tests pass) — validate-changes plugin runs automatically
- [x] Commit implementation changes — use `git-commit` skill

### Phase 2: Learnings
- [x] Extract learnings (or note: nothing noteworthy)
- [x] Document learnings if any — use `learnings` skill
- [x] Commit learnings if any — use `git-commit` skill

### Phase 3: Finalize & Push (DO NOT SKIP)
- [x] Update this progress doc to "Complete" status
- [ ] Commit progress doc update — use `git-commit` skill
- [x] Push all commits to remote — use `git-push-remote` skill
- [x] Create pull request — use GitHub MCP
- [x] Move ticket to "In Review" — use Linear MCP

## Tasks

- [x] Add strict receipt and source-identity primitives with tests.
- [x] Integrate receipt lifecycle and atomic publication into rewrite/verify.
- [x] Extend CLI, fixtures, runtime contracts, documentation, and CI.
- [x] Run the feasible required validation matrix and implementation review.

## Progress Log

### 2026-09-07 10:14

Loaded House Rules from the launching checkout, moved BBQ-8 to In Progress,
reviewed its research/technical plan and relevant learnings, and created this
dedicated worktree. No House Rules exceptions are requested.

## Technical Notes

- Apply the `GitFixture` hermetic integration pattern and exact stderr contracts.
- Receipt evidence is private: diagnostics and reports must not disclose source
  paths, OIDs, refs, trees, or receipt contents.
- Only dedicated OCI output/receipt mounts may be writable.

## Blockers

None. BBQ-22 is complete; its stale formal blocking relation does not prevent
implementation.

### 2026-09-07 10:28

Completed Receipt v1 with canonical private evidence, raw-byte policy binding,
strict commit resolution, source fingerprinting, staged source verification,
and native no-replace publication. The pinned Git 2.47.0 baseline passed 57
tests; the expanded source suite passed 63 tests. Committed implementation as
`7b96a42`.

### 2026-09-07 10:32

Validated the pinned source suite (63 tests), toolchain fingerprint, and wheel
runtime contracts (30 tests). SHA-256 repository initialization works, but the
pinned `git-filter-repo` crashes during path filtering; this remains a recorded
compatibility gap rather than a weakened or misleading CI claim.

### 2026-09-07 10:46

Started health-review remediation. Added focused TDD coverage for unsupported
Linux architectures, publication failure after receipt publication, receipt
read errors, policy boolean versions, annotated tag cutoffs, and policy-
conditional CLI failures. The focused pinned suite passes, but Phase 1 remains
in progress until an independent review of these fixes passes.

### 2026-09-07 11:13

Addressed the remaining Receipt v1 review findings with strict integer version
typing and a real macOS native no-replace preservation contract. Added
`tests.test_publication` to the CI source-unit inventory. Focused pinned tests
pass; Phase 1 remains in progress pending independent review.

### 2026-09-07 11:15

Independent implementation review passed on round three. The pinned source-unit
suite passed 60 tests and the source runtime contracts passed 33 tests. The
wheel runtime contracts previously passed 30 tests. No lint or static typecheck
script is configured. House Rules are compliant with no approved exceptions.

### 2026-09-07 11:16

Pushed `fix/BBQ-8-cutoff-verification`, created PR #3, and moved BBQ-8 to In Review.

### 2026-09-07 12:17

Resumed remediation for the OCI receipt publication failure. Receipt staging must
remain in its destination parent so the native no-replace rename stays on one
mount; implementation and validation are in progress.

### 2026-09-07 12:20

Stage receipts with a mode of `0600` in the receipt destination parent, then
remove the temporary entry on every post-creation failure path. The rebuilt OCI
cutoff contracts passed 5 tests; the source runtime and source-only matrices
passed 72 tests. Status remains In Progress while the remediation commit is
awaiting normal review.

## Testing

- [x] Unit tests written
- [x] Integration tests written
- [x] Manual testing completed

## Files Changed

- `docs/progress/fix-BBQ-8-cutoff-verification.md` - workflow tracking.
- `src/git_history_sanitize/receipt.py` - Receipt v1 parsing, serialization, and source fingerprint.
- `src/git_history_sanitize/engine.py` - adjacent private receipt staging and cleanup.
- `src/git_history_sanitize/publication.py` - native atomic no-replace publication.
- `README.md`, `PLAN.md`, `PUBLISHING_PLAN.md` - Receipt v1 operating contract.
- `.github/workflows/ci.yml` - Receipt unit coverage in the pinned matrix.
- `tests/test_publication.py` - native no-replace publication contracts.
- `tests/test_receipt.py`, `tests/test_cutoff_contracts.py`, `tests/test_verify_contracts.py` - Receipt v1 and source-backed verification contracts.
- `tests/test_engine_failure_contracts.py` - receipt staging failure contract.
