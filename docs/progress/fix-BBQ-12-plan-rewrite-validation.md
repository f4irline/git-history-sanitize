# BBQ-12: Make plan use the full rewrite validation path

**Branch:** `fix/BBQ-12-plan-rewrite-validation`
**Worktree:** `/Users/tlepola/Documents/dev/projects/personal/git-history-sanitize/.opencode/.bbq-worktrees/fix-BBQ-12-plan-rewrite-validation`
**Status:** Complete
**Started:** 2026-09-14
**Last Updated:** 2026-09-14 19:53

## Overview

Centralize source, graph, ref, and cutoff validation so `plan` and `rewrite`
share deterministic preflight facts without mutating source or creating output.

## Workflow Checklist

> **IMPORTANT**: This checklist ensures all workflow steps are completed, even after context compaction.
> Check off each phase as you complete it. After ANY interruption, read this section first.

### Phase 1: Implementation
- [x] Write/modify tests (TDD)
- [x] Implement changes
- [x] Validate (lint, build, tests pass) — validate-changes plugin runs automatically
- [x] Commit implementation changes — use `git-commit` skill
- [x] Pass implementation review gate

### Phase 2: Learnings
- [x] Extract learnings (or note: nothing noteworthy)
- [x] Document learnings if any — use `learnings` skill
- [x] Commit learnings if any — use `git-commit` skill

### Phase 3: Finalize & Push (DO NOT SKIP)
- [x] Update this progress doc to "Complete" status
- [x] Commit progress doc update — use `git-commit` skill
- [ ] Push all commits to remote — use `git-push-remote` skill
- [ ] Create pull request — use GitHub MCP
- [ ] Move ticket to "In Review" — use Linear MCP

## Tasks

- [x] Read ticket, research, technical plan, House Rules, and relevant learnings
- [x] Resolve Herdr worktree and sync local files
- [x] Add shared-analysis unit and CLI parity tests
- [x] Extract immutable source-only rewrite analysis
- [x] Use shared analysis from plan, rewrite, and compaction
- [x] Document validation parity and run final checks

## Progress Log

### 2026-09-14 19:37

Moved BBQ-12 to In Progress. Resolved Herdr worktree `w8` at the recorded path
from `origin/main` and synced local files (0 linked, 0 copied). Reviewed the
ticket's revised research/technical plan and all project learnings. No House
Rules exceptions are required.

### 2026-09-14 19:45

Added immutable `RewriteAnalysis` preflight and routed both commands plus
compaction through its single linear-history/cutoff boundary selection. Added
focused analysis tests and hermetic plan/rewrite parity contracts for merge,
detached HEAD, timestamp recrossing, unreachable cutoff, and empty-source
failures; 32 focused tests pass using the pinned source runtime.

### 2026-09-14 19:50

Committed implementation as `e5dafc4`. Full unittest discovery passed (176
tests), pinned toolchain validation passed, source runtime contracts passed (62
tests), and a wheel build succeeded. No lint or typecheck script is configured.
Independent implementation review returned `REVIEW_RESULT: PASS` with no
findings; House Rules compliance is confirmed with no exceptions.

### 2026-09-14 19:51

Evaluated learnings and documented one relevant fixture gotcha in
`docs/learnings/gotchas.md`: initialize an index with `read-tree --empty`
before snapshotting an empty `GitFixture` source. Committed it as `7b35b2a`.

### 2026-09-14 19:53

Final quality gate passed: 176 host unit tests, pinned toolchain validation, 62
source runtime contracts, wheel build, and the `Containerfile` test target. No
lint or typecheck script is configured. Implementation was completed in the
recorded Herdr worktree; House Rules compliance is complete with no exceptions.

## Technical Notes

- `GitFixture` is mandatory for hermetic CLI parity assertions.
- Snapshot analysis must remain HEAD-tree-only; do not walk inherited history.
- A filtered empty output from a non-empty source remains valid and is distinct
  from an empty source.
- Preserve existing secret-free diagnostics and symbolic-ref byte handling.
- Rewrite constructs analysis after command-argument/destination validation and
  before dependency checks or staging, preserving receipt argument precedence.
- Herdr runtime is active (`HERDR_ENV=1`); workspace metadata is `w8`.

## Blockers

None. BBQ-22's fixture dependency is complete and available.

## Testing

- [x] Unit tests written
- [x] Integration tests written
- [ ] Manual testing completed

## Files Changed

- `docs/progress/fix-BBQ-12-plan-rewrite-validation.md` - workflow tracker and compliance record
- `src/git_history_sanitize/rewrite_analysis.py` - shared read-only preflight facts
- `src/git_history_sanitize/engine.py` - consume shared plan/rewrite analysis
- `src/git_history_sanitize/compact.py` - compact from validated analysis
- `tests/test_rewrite_analysis.py` - focused analysis invariants
- `tests/test_cutoff_contracts.py` - cutoff parity and source immutability contracts
- `tests/test_source_scope_contracts.py` - merge and detached-HEAD parity contracts
- `README.md` - document preflight parity and pre-filter facts
- `docs/learnings/gotchas.md` - empty-source fixture snapshot setup
