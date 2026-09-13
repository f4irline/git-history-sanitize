# BBQ-7: Fix synthetic-root message when the boundary commit is mixed

**Branch:** `fix/BBQ-7-synthetic-root-message`
**Worktree:** `/Users/tlepola/Documents/dev/projects/personal/git-history-sanitize/.opencode/.bbq-worktrees/fix-BBQ-7-synthetic-root-message`
**Status:** In Progress
**Started:** 2026-09-13
**Last Updated:** 2026-09-13 12:15

## Overview

Preserve the configured synthetic-root message during mixed-path filtering while
retaining ordinary mixed-commit behavior and sensitive-path removal.

## Workflow Checklist

> **IMPORTANT**: This checklist ensures all workflow steps are completed, even after context compaction.
> Check off each phase as you complete it. After ANY interruption, read this section first.

### Phase 1: Implementation
- [x] Write/modify tests (TDD)
- [x] Implement changes
- [ ] Validate (lint, build, tests pass)
- [ ] Commit implementation changes — use `git-commit` skill
- [ ] Implementation review gate passes

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

- [x] Add mixed synthetic-root regression coverage for complete and snapshot modes
- [x] Preserve the root message by structural parentlessness in the callback
- [ ] Validate focused and configured project checks

## Progress Log

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

- [ ] Unit tests written
- [ ] Integration tests written
- [ ] Manual testing completed

## Files Changed

- `docs/progress/fix-BBQ-7-synthetic-root-message.md` - workflow tracking
- `src/git_history_sanitize/filtering.py` - preserve a parentless root message
- `tests/test_filtering_contracts.py` - cover complete and snapshot mixed roots
