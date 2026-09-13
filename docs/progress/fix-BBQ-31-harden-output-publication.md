# BBQ-31: Harden atomic output publication

**Branch:** `fix/BBQ-31-harden-output-publication`
**Worktree:** `/Users/tlepola/Documents/dev/projects/personal/git-history-sanitize/.opencode/.bbq-worktrees/fix-BBQ-31-harden-output-publication`
**Status:** In Progress
**Started:** 2026-09-13
**Last Updated:** 2026-09-13

## Overview

Harden no-replace publication of verified sanitized repositories with explicit
permissions, error categories, durability handling, ownership-aware cleanup,
and documented semantics.

## Workflow Checklist

> **IMPORTANT**: After any interruption, read this checklist first.

### Phase 1: Implementation
- [x] Write/modify tests (TDD)
- [x] Implement changes
- [x] Validate (lint, build, tests pass)
- [x] Commit implementation changes — use `git-commit` skill
- [x] Implementation Review Gate passes

### Phase 2: Learnings
- [ ] Extract learnings (or note: nothing noteworthy)
- [ ] Document learnings if any — use `learnings` skill
- [ ] Commit learnings if any — use `git-commit` skill

### Phase 3: Finalize & Push (DO NOT SKIP)
- [ ] Update this progress doc to "Complete" status
- [ ] Commit progress doc update — use `git-commit` skill
- [ ] Push all commits to remote — use `git-push-remote` skill
- [ ] Create pull request — use GitHub MCP
- [ ] Move ticket to "In Review" — use Linear MCP

## Tasks

- [x] Add failing publication and rewrite durability contract tests
- [x] Implement typed publication, persistence, permissions, and cleanup protocol
- [x] Document publication and durability guarantees
- [x] Run focused and configured validation suites
- [x] Pass implementation review gate

## Progress Log

### 2026-09-13

Created dedicated worktree from `origin/main`, loaded House Rules from the
launching checkout, moved BBQ-31 to In Progress, and reviewed ticket research,
technical plan, and relevant fixture/redaction learnings. No House Rules
exceptions are requested.

### 2026-09-13

Added and observed failing contracts for native error categories and post-rename
durability reporting. Implemented deterministic staged synchronization,
no-replace errno mapping, private modes, dangling-symlink rejection, explicit
publication ownership, and post-publication parent persistence reporting.
Focused publication and failure-contract tests pass under the pinned toolchain.

### 2026-09-13

Validation passed: all 153 source tests, 50 source runtime contracts, 50 wheel
runtime contracts, and 50 OCI runtime contracts. No lint or separate typecheck
configuration exists in this Python project; `git diff --check` is clean.

### 2026-09-13

Implementation review required two revisions. Added a fixture-backed concurrent
CLI rewrite contract and corrected receipt-parent durability diagnostics so they
state that only the receipt was published. The final validation matrix will be
rerun after these revisions.

### 2026-09-13

Added pre-publication synchronization-failure and permissive-umask mode
contracts in response to the second review. All 157 source tests now pass;
source, rebuilt wheel, and rebuilt OCI runtime contracts each passed (50 tests).
The final review found no code or behavioral issue. Its documentation
cleanliness finding is resolved by this commit.

## Technical Notes

- Native no-replace rename remains the sole publication linearization point.
- Relevant learnings require `GitFixture` for integration coverage, exact
  redacted diagnostics, and dedicated caller-owned OCI output mounts.
- Worktree state: created. All implementation actions use this worktree.
- House Rules compliance: Security First (no-replace, private modes, redacted
  errors); Predictable CLI (stable errors and published-state diagnostics);
  Minimal Dependencies (standard library only); Focused Scope and Deterministic
  Results (native publication linearization point). No exceptions.

## Testing

- [x] Unit tests written
- [x] Integration tests written
- [x] Source contracts run
- [x] Wheel contracts run
- [x] OCI contracts run

## Files Changed

- `src/git_history_sanitize/publication.py` - publication, modes, and durability primitives
- `src/git_history_sanitize/engine.py` - verified output publication protocol
- `tests/test_publication.py` - no-replace race, error, and durability unit contracts
- `tests/test_engine_failure_contracts.py` - destination and post-publication contracts
- `README.md` - atomic visibility and durability semantics
