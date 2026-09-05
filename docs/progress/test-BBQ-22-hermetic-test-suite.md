# BBQ-22: Build a hermetic security regression test suite

**Branch:** `test/BBQ-22-hermetic-test-suite`
**Worktree:** `/Users/tlepola/Documents/dev/projects/personal/git-history-sanitize/.opencode/.bbq-worktrees/test-BBQ-22-hermetic-test-suite`
**Status:** Complete
**Started:** 2026-09-05
**Last Updated:** 2026-09-05 07:52

## Overview

Create a standard-library-only hermetic Git test fixture and migrate the end-to-end
coverage to deterministic, isolated test processes.

## Workflow Checklist

> **IMPORTANT**: This checklist ensures all workflow steps are completed, even after
> context compaction. After any interruption, read this section first.

### Phase 1: Implementation
- [x] Write/modify tests (TDD)
- [x] Implement changes
- [x] Validate (lint not configured; tests and build pass)
- [x] Commit implementation changes — use `git-commit` skill
- [x] Implementation review gate passes

### Phase 2: Learnings
- [x] Extract learnings (or note: nothing noteworthy)
- [x] Document learnings if any — use `learnings` skill
- [x] Commit learnings if any — use `git-commit` skill

### Phase 3: Finalize & Push (DO NOT SKIP)
- [x] Update this progress doc to "Complete" status
- [ ] Commit progress doc update — use `git-commit` skill
- [ ] Push all commits to remote — use `git-push-remote` skill
- [ ] Create pull request — use GitHub MCP
- [ ] Move ticket to "In Review" — use Linear MCP

## Tasks

- [x] Load House Rules, ticket details, and workflow context.
- [x] Create dedicated ticket worktree.
- [x] Add shared hermetic Git fixture tests.
- [x] Implement the fixture and migrate end-to-end coverage.
- [ ] Run validation and implementation review.

## Progress Log

### 2026-09-05 06:46

Loaded the House Rules from the launching checkout, moved BBQ-22 to In Progress,
and created the dedicated worktree. No existing project learnings directory exists.

### 2026-09-05 07:02

Added a standard-library-only fixture with an allowlisted process environment,
deterministic repository builders, source snapshots, and redaction assertions.
Migrated the end-to-end test through the CLI plan/rewrite/verify flow and added
hostile-global-config, controlled-failure immutability, cleanup, repeatability,
and verifier-invariant regressions. `PYTHONPATH=src python3 -m unittest discover
-s tests -t . -v` passes (11 tests).

### 2026-09-05 07:10

Implementation review required stronger fixture-owned HOME/XDG setup and explicit
physical-object/ref/output snapshot coverage. Added targeted regression assertions;
validation and review will be rerun before proceeding.

### 2026-09-05 07:18

Second review requested an explicit failed `--json` CLI invocation. The controlled
failure test now checks useful error context and sensitive-value redaction in both
normal and JSON-mode output; validation and the final review are being rerun.

### 2026-09-05 07:24

The third implementation review found the current redaction assertions vacuous:
the induced existing-output error cannot contain the fixture-marked secret values.
Per the three-round review limit, implementation is paused pending direction on a
non-vacuous established error contract to exercise. No push, PR, or ticket state
change to In Review has occurred.

### 2026-09-05 07:30

The user confirmed option 1: no established error/redaction contract exists for
this version, so no redaction regression is required. Removed the vacuous
assertions while retaining the controlled-failure source-immutability regression.
This is a ticket-scope clarification, not a House Rules exception.

### 2026-09-05 07:37

Final validation passed: host unittest (11 tests), the configured Docker test
target (11 tests), and wheel build. No linter is configured. The three review
rounds resolved isolation and snapshot findings; the remaining redaction concern
was closed by the user's ticket-scope clarification.

### 2026-09-05 07:40

Documented one reusable testing pattern: future Git/CLI integration tests should
use `GitFixture` for hermetic processes and source/output comparison helpers.

### 2026-09-05 07:45

Finalized the implementation record. All feature, documentation, and learning
commits are ready to push from the dedicated worktree. The final checklist will
be updated after the remote branch, pull request, and Linear status are confirmed.

### 2026-09-05 07:48

Pushed branch `test/BBQ-22-hermetic-test-suite` through commit `78678a9`.
GitHub rejected pull-request creation with HTTP 403 (`Resource not accessible by
personal access token`), so the ticket remains In Progress and finalization is
blocked pending pull-request permission.

### 2026-09-05 07:52

Retried pull-request creation after confirming no PR exists for the branch. GitHub
again returned HTTP 403 (`Resource not accessible by personal access token`).

## Technical Notes

- House Rules: security-first isolation, predictable CLI output, no unnecessary
  dependencies, focused scope, and deterministic results.
- Worktree state: created from `origin/main`; no local-only files needed mirroring.
- No House Rules exceptions are requested.
- The fixture resolves Git/Python/filter-repo executable paths before creating its
  environment and exposes only their directories plus fixture-owned configuration.

## Testing

- [x] Unit tests written
- [x] Integration tests written
- [x] Manual testing completed

## Files Changed

- `docs/progress/test-BBQ-22-hermetic-test-suite.md` - workflow tracking.
- `docs/learnings/patterns.md` - shared hermetic Git fixture guidance.
- `tests/support/git_fixture.py` - hermetic, deterministic Git fixture.
- `tests/support/__init__.py` - support package marker.
- `tests/test_git_fixture.py` - fixture isolation and helper regression tests.
- `tests/test_end_to_end.py` - migrated CLI workflow and immutability tests.
- `tests/test_regressions.py` - cleanup, repeatability, and verifier regressions.

## Blockers

- GitHub token lacks permission to create the pull request. The branch is pushed;
  once permission is granted, create the PR and move BBQ-22 to In Review.
