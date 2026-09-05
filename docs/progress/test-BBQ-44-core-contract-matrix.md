# BBQ-44: Build a core rewrite and verification contract test matrix

**Branch:** `test/BBQ-44-core-contract-matrix`
**Worktree:** `/Users/tlepola/Documents/dev/projects/personal/git-history-sanitize/.opencode/.bbq-worktrees/test-BBQ-44-core-contract-matrix`
**Status:** In Progress
**Started:** 2026-09-05
**Last Updated:** 2026-09-05 11:03

## Overview

Add focused, hermetic contract coverage for the supported plan, rewrite, verify,
and CLI behavior using the existing `GitFixture` harness.

## Workflow Checklist

> **IMPORTANT**: After any interruption, read this checklist first.

### Phase 1: Implementation
- [x] Write/modify tests (TDD)
- [x] Implement changes
- [ ] Validate (lint, build, tests pass)
- [ ] Commit implementation changes — use `git-commit` skill

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

- [x] Load House Rules and ticket research
- [x] Prepare dedicated ticket worktree
- [x] Review existing relevant learnings
- [x] Add focused cutoff contract tests using `GitFixture`
- [x] Address the plan/rewrite preflight-validation parity gap
- [ ] Run full configured validation and implementation review

## Progress Log

### 2026-09-05 10:56

Created the dedicated worktree and loaded the technical plan. The existing
`GitFixture` harness and `docs/learnings/patterns.md` will be reused; no
competing Git harness will be introduced.

### 2026-09-05 11:03

Added focused cutoff contracts. They exposed that `plan` accepted a timestamp
recrossing history that `rewrite` correctly rejected. Both commands now share
the same linear-history and boundary preflight validation.

## Technical Notes

- House Rules loaded from the launching checkout and apply without exceptions.
- Worktree state: created at the path above; no local-only files required
  mirroring because `proto/.devcontainer/.env` is absent.
- Initial exploration confirms core focused tests can consume the existing
  hermetic fixture. Owner-dependent contracts remain fail-closed.

## Testing

- [ ] Focused unit/integration contract tests
- [ ] Full source suite
- [ ] Build/type/lint checks (if configured)
- [ ] Runtime/container checks (if configured)

## Files Changed

- `docs/progress/test-BBQ-44-core-contract-matrix.md` - workflow tracker
- `tests/support/git_fixture.py` - deterministic policy writer
- `tests/test_cutoff_contracts.py` - timestamp and preflight parity contracts
- `src/git_history_sanitize/compact.py` - shared history validation
- `src/git_history_sanitize/engine.py` - plan uses shared validation
