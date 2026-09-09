# BBQ-9: Correct and stream forbidden-content verification

**Branch:** `fix/BBQ-9-forbidden-content`
**Worktree:** `/Users/tlepola/Documents/dev/projects/personal/git-history-sanitize/.opencode/.bbq-worktrees/fix-BBQ-9-forbidden-content`
**Status:** In Progress
**Started:** 2026-09-09
**Last Updated:** 2026-09-09 18:47

## Overview

Implement bounded, body-only forbidden-content verification for Git objects and
bare-repository hooks, with safe file and stdin pattern inputs.

## Workflow Checklist

> **IMPORTANT**: This checklist ensures all workflow steps are completed, even after context compaction.
> Check off each phase as you complete it. After ANY interruption, read this section first.

### Phase 1: Implementation
- [x] Write/modify tests (TDD)
- [x] Implement changes
- [x] Validate (lint, build, tests pass) — validate-changes plugin runs automatically
- [x] Commit implementation changes — use `git-commit` skill

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

- [x] Load ticket research, plan, House Rules, and relevant learnings.
- [x] Create isolated worktree from `origin/main`.
- [x] Add tests for body-only streaming matching and safe CLI inputs.
- [x] Implement bounded matcher, batch parser, object/hook scanning, and inputs.
- [x] Document the verification contract and run focused quality gates.

## Progress Log

### 2026-09-09 18:33

Started work in the dedicated worktree. Loaded House Rules and applicable
learnings: use `GitFixture` for hermetic Git integration tests, preserve strict
UTF-8 only for CLI forbidden text, and keep exact redacted stderr contracts.
No House Rules exceptions are requested.

### 2026-09-09 18:38

Implemented the bounded Aho-Corasick matcher, raw-byte file/stdin record
inputs, body-only `cat-file` stream parser, and immediate regular hook scan.
Focused source tests (36), bytecode compilation, and whitespace validation
pass. Committed implementation as `3d7ac93`.

### 2026-09-09 18:41

The first implementation review found coverage and container-runtime gaps.
Added protocol, object-kind, byte, bounds, safe-hook, and input-redaction
coverage; preserved raw strict UTF-8 CLI bytes; and made fixture container
inputs mountable. Full source runtime matrix (42 tests) and focused suite (73
tests) pass with pinned Git/filter-repo checks. Committed revisions as
`c79fa42`.

### 2026-09-09 18:47

Added truncated-body and invalid-delimiter protocol tests. Built the package;
the wheel and OCI runtime matrices each passed 42 tests. Documented the
container sensitive-input fixture pattern in `docs/learnings/patterns.md`.

## Technical Notes

- Verification must search only body bytes, preserve match state within a body
  or hook file, and fail closed without leaking patterns, paths, object IDs, or
  Git stderr.
- Use only Python standard library dependencies.
- Worktree state: created; base: `origin/main`.

## Testing

- [x] Unit tests written
- [x] Integration tests written
- [x] Manual testing completed

## Files Changed

- `docs/progress/fix-BBQ-9-forbidden-content.md` - workflow tracker.
- `src/git_history_sanitize/forbidden.py` - bounded byte matcher and inputs.
- `src/git_history_sanitize/verify.py` - stream and hook scanning.
- `src/git_history_sanitize/cli.py` - safe forbidden input flags.
- `tests/test_forbidden_content.py` - matcher and scanner tests.
- `tests/test_cli_contracts.py` - file/stdin redaction contracts.
- `tests/support/git_fixture.py` - stdin-capable CLI harness.
- `tests/test_git_fixture.py` - container fixture input wiring tests.
- `src/git_history_sanitize/git.py` - public scoped Git command builder.
- `Containerfile` - dedicated forbidden-file mount directory.
- `README.md` - matching and resource contracts.
