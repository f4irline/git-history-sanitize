# BBQ-14: Canonicalize and validate excluded paths

**Branch:** `fix/BBQ-14-canonicalize-excluded-paths`
**Worktree:** `/Users/tlepola/Documents/dev/projects/personal/git-history-sanitize/.opencode/.bbq-worktrees/fix-BBQ-14-canonicalize-excluded-paths`
**Status:** In Progress
**Started:** 2026-09-12
**Last Updated:** 2026-09-12 10:28

## Overview

Reject ambiguous excluded-path policy entries and use one validated ordered value
through plan, filtering, reporting, and verification.

## Workflow Checklist

> **IMPORTANT**: This checklist ensures all workflow steps are completed, even after context compaction.
> Check off each phase as you complete it. After ANY interruption, read this section first.

### Phase 1: Implementation
- [x] Write/modify tests (TDD)
- [x] Implement changes
- [x] Validate (lint, build, tests pass)
- [x] Commit implementation changes — use `git-commit` skill
- [x] Pass implementation review gate

### Phase 2: Learnings
- [x] Extract learnings (documented fixture leading-dash staging gotcha)
- [x] Document learnings if any — use `learnings` skill
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
- [x] Cover policy, filtering, verification, and CLI contracts
- [x] Document canonical excluded-path grammar

## Progress Log

### 2026-09-12 10:11

Read the ticket, research, House Rules, and relevant learnings. Created a dedicated
worktree. House Rules require strict, deterministic, redacted validation; no
exceptions are required.

### 2026-09-12 10:16

Added strict policy admission checks, order-symmetric overlap validation, and
plan reporting. TDD policy and CLI contracts now pass under the source runtime.

### 2026-09-12 10:19

Added fixture-backed filtering coverage for spaces, Unicode, and leading-dash
rules, plan report coverage, and user-facing canonical-path documentation.

### 2026-09-12 10:21

Validation passed: 146 source-runtime tests with pinned Git 2.47.0 and
git-filter-repo 2.47.0, plus `uv build`. No lint or type-check command is
configured in this repository.

### 2026-09-12 10:24

Implementation review required exact-file verification coverage. Added a
fixture-backed plan/rewrite/verify contract for an exact-file rule alongside a
directory rule; the reintroduced exact file fails with `paths.excluded`.

### 2026-09-12 10:28

Implementation review passed on the second round after exact-file verification
coverage was added. Documented the leading-dash fixture staging gotcha.

## Technical Notes

- Preserve exact-file versus trailing-slash directory semantics.
- Use `GitFixture` for hermetic Git and CLI integration tests.
- Reject non-UTF-8-encodable policy entries before filtering and verification.

## Testing

- [x] Unit tests written
- [x] Integration tests written
- [x] Manual testing completed

## Files Changed

- `docs/progress/fix-BBQ-14-canonicalize-excluded-paths.md` - workflow tracker
- `src/git_history_sanitize/policy.py` - canonical policy path admission
- `src/git_history_sanitize/engine.py` - plan exclusion reporting
- `src/git_history_sanitize/cli.py` - human plan exclusion reporting
- `tests/test_policy.py` - canonical-path and overlap tests
- `tests/test_cli_contracts.py` - plan output contracts
- `tests/test_filtering_contracts.py` - special-character filtering contract
- `tests/test_verify_contracts.py` - exact-file plan and verifier contract
- `README.md` - excluded-path grammar and plan reporting documentation
- `docs/learnings/gotchas.md` - fixture leading-dash staging gotcha
