# BBQ-14: Canonicalize and validate excluded paths

**Branch:** `fix/BBQ-14-canonicalize-excluded-paths`
**Worktree:** `/Users/tlepola/Documents/dev/projects/personal/git-history-sanitize/.opencode/.bbq-worktrees/fix-BBQ-14-canonicalize-excluded-paths`
**Status:** In Progress
**Started:** 2026-09-12
**Last Updated:** 2026-09-12 10:16

## Overview

Reject ambiguous excluded-path policy entries and use one validated ordered value
through plan, filtering, reporting, and verification.

## Workflow Checklist

> **IMPORTANT**: This checklist ensures all workflow steps are completed, even after context compaction.
> Check off each phase as you complete it. After ANY interruption, read this section first.

### Phase 1: Implementation
- [x] Write/modify tests (TDD)
- [x] Implement changes
- [ ] Validate (lint, build, tests pass)
- [ ] Commit implementation changes — use `git-commit` skill
- [ ] Pass implementation review gate

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

- [x] Add strict policy path validation and overlap checks
- [x] Expose exclusions in plan and CLI output
- [ ] Cover policy, filtering, verification, and CLI contracts
- [ ] Document canonical excluded-path grammar

## Progress Log

### 2026-09-12 10:11

Read the ticket, research, House Rules, and relevant learnings. Created a dedicated
worktree. House Rules require strict, deterministic, redacted validation; no
exceptions are required.

### 2026-09-12 10:16

Added strict policy admission checks, order-symmetric overlap validation, and
plan reporting. TDD policy and CLI contracts now pass under the source runtime.

## Technical Notes

- Preserve exact-file versus trailing-slash directory semantics.
- Use `GitFixture` for hermetic Git and CLI integration tests.
- Reject non-UTF-8-encodable policy entries before filtering and verification.

## Testing

- [ ] Unit tests written
- [ ] Integration tests written
- [ ] Manual testing completed

## Files Changed

- `docs/progress/fix-BBQ-14-canonicalize-excluded-paths.md` - workflow tracker
- `src/git_history_sanitize/policy.py` - canonical policy path admission
- `src/git_history_sanitize/engine.py` - plan exclusion reporting
- `src/git_history_sanitize/cli.py` - human plan exclusion reporting
- `tests/test_policy.py` - canonical-path and overlap tests
- `tests/test_cli_contracts.py` - plan output contracts
