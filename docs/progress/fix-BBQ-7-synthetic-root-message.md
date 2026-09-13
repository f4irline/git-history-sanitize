# BBQ-7: Fix synthetic-root message when the boundary commit is mixed

**Branch:** `fix/BBQ-7-synthetic-root-message`
**Worktree:** `/Users/tlepola/Documents/dev/projects/personal/git-history-sanitize/.opencode/.bbq-worktrees/fix-BBQ-7-synthetic-root-message`
**Status:** Complete
**Started:** 2026-09-13
**Last Updated:** 2026-09-13 12:40

## Overview

Preserve the configured synthetic-root message during mixed-path filtering while
retaining ordinary mixed-commit behavior and sensitive-path removal.

## Workflow Checklist

> **IMPORTANT**: This checklist ensures all workflow steps are completed, even after context compaction.
> Check off each phase as you complete it. After ANY interruption, read this section first.

### Phase 1: Implementation
- [x] Write/modify tests (TDD)
- [x] Implement changes
- [x] Validate (lint, build, tests pass)
- [x] Commit implementation changes — use `git-commit` skill
- [x] Implementation review gate passes

### Phase 2: Learnings
- [x] Extract learnings (nothing noteworthy)
- [x] Document learnings if any — no new learning
- [x] Commit learnings if any — not applicable

### Phase 3: Finalize & Push (DO NOT SKIP)
- [x] Update this progress doc to "Complete" status
- [x] Commit progress doc update — use `git-commit` skill
- [ ] Push all commits to remote — use `git-push-remote` skill
- [ ] Create pull request — use GitHub MCP
- [ ] Move ticket to "In Review" — use Linear MCP

## Tasks

- [x] Add mixed synthetic-root regression coverage for complete and snapshot modes
- [x] Preserve the root message by structural parentlessness in the callback
- [x] Validate focused and configured project checks

## Progress Log

### 2026-09-13 12:40

Finalized implementation documentation. House Rules are fully compliant: the
change retains sanitization and verification, adds no dependencies or API
surface, remains focused on history filtering, and has deterministic fixture
coverage. No exceptions were requested or used. This worktree is the resolved
Herdr worktree listed above.

### 2026-09-13 12:35

Implementation review gate passed with no blocking or important findings. The
structural parent guard follows the ticket plan and preserves verifier behavior.
Learnings evaluation found no new meaningful gotcha, pattern, decision, or
discovery beyond the ticket's already-applied `GitFixture` and SHA-256 runtime
learnings; no learning entry was added.

### 2026-09-13 12:30

Validation passed: focused filtering tests; source contracts (53 tests) plus
fixture/toolchain helpers (70 tests); build; and wheel runtime contracts (53
tests). No lint or standalone type-check script is configured. OCI contracts
are opt-in locally and were not run.

### 2026-09-13 12:15

Added complete and snapshot-mode mixed-root regressions before changing the
callback. The focused integration module passes after suppressing only the
ordinary mixed-message replacement for parentless commits; sensitive entries
continue to be removed.

### 2026-09-13 12:00

Created dedicated Herdr worktree. Reviewed ticket research, technical plan, and
relevant learnings. House Rules are loaded from the launching checkout; no
exceptions are required.

## Technical Notes

- Use `GitFixture` for hermetic CLI/repository assertions.
- Test only the supported SHA-1 filtering runtime; pinned filter-repo does not
  support the SHA-256 filtering path.
- `not commit.parents` is the stable structural synthetic-root marker; do not
  carry pre-filter object IDs through filtering.

## Testing

- [x] Unit tests written (not applicable: callback behavior requires CLI integration coverage)
- [x] Integration tests written
- [x] Manual testing completed

## Files Changed

- `docs/progress/fix-BBQ-7-synthetic-root-message.md` - workflow tracking
- `src/git_history_sanitize/filtering.py` - preserve a parentless root message
- `tests/test_filtering_contracts.py` - cover complete and snapshot mixed roots
