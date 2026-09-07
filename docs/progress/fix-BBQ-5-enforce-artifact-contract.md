# BBQ-5: Enforce the core v1 artifact contract in verify

**Branch:** `fix/BBQ-5-enforce-artifact-contract`
**Worktree:** `/Users/tlepola/Documents/dev/projects/personal/git-history-sanitize/.opencode/.bbq-worktrees/fix-BBQ-5-enforce-artifact-contract`
**Status:** In Progress
**Started:** 2026-09-07
**Last Updated:** 2026-09-07 17:10

## Overview

Implement an independent, complete v1 verification artifact contract with stable,
redacted invariant diagnostics and focused regression coverage.

## Workflow Checklist

> **IMPORTANT**: This checklist ensures all workflow steps are completed, even after context compaction.
> Check off each phase as you complete it. After ANY interruption, read this section first.

### Phase 1: Implementation
- [ ] Write/modify tests (TDD)
- [ ] Implement changes
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

- [x] Move Linear ticket to In Progress and read its research and technical plan
- [x] Prepare dedicated worktree and review applicable House Rules and learnings
- [x] Add focused contract tests and verify their expected pre-implementation failures
- [x] Implement the invariant registry and redacted CLI diagnostics
- [x] Document the v1 contract and run focused validation
- [ ] Run complete configured runtime validation
- [ ] Complete review, learnings, and finalization workflow

## Progress Log

### 2026-09-07 16:36

Started in dedicated worktree. Applied House Rules without exceptions. Reviewed
ticket research, technical plan, and relevant learnings: use `GitFixture`, retain
redacted diagnostics, use in-place fixture config tampering, and do not make the
known SHA-256 filter-repo gap a required matrix cell.

### 2026-09-07 16:45

Added an ordered direct-inspection v1 invariant registry, redacted invariant
errors, and JSON failure serialization. Focused verifier, CLI, and cutoff
contracts pass (27 tests). Full runtime matrix and documentation remain.

### 2026-09-07 16:48

Documented the invariant catalog, direct inspection model, and invariant JSON
schema in README and PLAN. Regression, verifier, CLI, and cutoff suites pass
(29 tests); source/wheel/OCI runtime checks remain for the final gate.

### 2026-09-07 17:10

The full source runtime suite passes (38 tests) with the available system Git.
The pinned Git 2.47.0 bootstrap cannot complete because its GPG keyserver has
no network route; the subsequent toolchain check correctly rejects system Git.
This is an environment blocker, not a House Rules exception. Wheel and OCI
matrix cells remain pending until the pinned toolchain can be bootstrapped.

## Technical Notes

- `verify` must inspect repositories directly and remain independent of rewrite
  helpers.
- Stable invariant failures must not expose paths, object IDs, messages, or Git
  command output.
- Worktree state: created; no local-only files required mirroring.

## Testing

- [ ] Unit tests written
- [x] Integration tests written
- [ ] Manual testing completed

## Files Changed

- `docs/progress/fix-BBQ-5-enforce-artifact-contract.md` - workflow tracking
- `src/git_history_sanitize/verify.py` - ordered independent v1 contract checks
- `src/git_history_sanitize/errors.py` - structured invariant failure metadata
- `src/git_history_sanitize/cli.py` - stable JSON invariant error serialization
- `tests/test_verify_contracts.py` - focused artifact tamper coverage
- `tests/test_cli_contracts.py` - human and JSON invariant error contracts
- `tests/test_regressions.py` - stable ref and object-database diagnostics
- `README.md` - documented v1 artifact contract and redaction behavior
- `PLAN.md` - normative invariant inspection checklist
