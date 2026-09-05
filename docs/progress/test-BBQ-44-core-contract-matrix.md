# BBQ-44: Build a core rewrite and verification contract test matrix

**Branch:** `test/BBQ-44-core-contract-matrix`
**Worktree:** `/Users/tlepola/Documents/dev/projects/personal/git-history-sanitize/.opencode/.bbq-worktrees/test-BBQ-44-core-contract-matrix`
**Status:** Complete
**Started:** 2026-09-05
**Last Updated:** 2026-09-05 14:10

## Overview

Add focused, hermetic contract coverage for the supported plan, rewrite, verify,
and CLI behavior using the existing `GitFixture` harness.

## Workflow Checklist

> **IMPORTANT**: After any interruption, read this checklist first.

### Phase 1: Implementation
- [x] Write/modify tests (TDD)
- [x] Implement changes
- [x] Validate (lint, build, tests pass)
- [ ] Commit implementation changes — use `git-commit` skill

### Phase 2: Learnings
- [x] Extract learnings (nothing noteworthy beyond the existing fixture pattern)
- [x] Document learnings if any — no new learning required
- [ ] Commit learnings if any — use `git-commit` skill

### Phase 3: Finalize & Push (DO NOT SKIP)
- [x] Update this progress doc to "Complete" status
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
- [x] Add output-redaction and verifier tamper contract tests using `GitFixture`
- [x] Run full configured validation and implementation review

## Progress Log

### 2026-09-05 10:56

Created the dedicated worktree and loaded the technical plan. The existing
`GitFixture` harness and `docs/learnings/patterns.md` will be reused; no
competing Git harness will be introduced.

### 2026-09-05 11:03

Added focused cutoff contracts. They exposed that `plan` accepted a timestamp
recrossing history that `rewrite` correctly rejected. Both commands now share
the same linear-history and boundary preflight validation.

### 2026-09-05 11:09

Added focused filtering and CLI contracts. The mixed synthetic-root contract
revealed a verifier-breaking message replacement; path filtering now preserves
the configured root message while still redacting later mixed commits.

### 2026-09-05 11:12

The editable-install source suite passed (19 tests). Implementation Review Gate
round 1 returned changes required: the planned output/verification contract
modules and cross-runtime toolchain, container, CI, and README artifacts are
still outstanding. Phase 1 is intentionally not complete.

### 2026-09-05 14:10

Added `GitFixture`-based report-redaction coverage and verifier tamper contracts
for pre-cutoff commits, synthetic-root messages, reintroduced excluded paths,
and leftover filter-repo metadata. Source-path and container suites pass with
24 tests each; an isolated wheel installation also completed `doctor --json`.
The existing CI, Containerfile, and README already define and document these
runtime paths, so no speculative runner or policy change was added.

## Technical Notes

- House Rules loaded from the launching checkout and apply without exceptions.
- Worktree state: created at the path above; no local-only files required
  mirroring because `proto/.devcontainer/.env` is absent.
- Initial exploration confirms core focused tests can consume the existing
  hermetic fixture. Owner-dependent contracts remain fail-closed.

## Testing

- [x] Focused output and verifier contract tests (5 tests)
- [x] Full source suite (24 tests via `PYTHONPATH=src`)
- [x] Package build (`pip3 wheel --no-deps .`)
- [x] Isolated wheel runtime (`git-history-sanitize doctor --json`)
- [x] Container suite (24 tests via `docker buildx build --target test -f Containerfile .`)

## Files Changed

- `docs/progress/test-BBQ-44-core-contract-matrix.md` - workflow tracker
- `tests/support/git_fixture.py` - deterministic policy writer
- `tests/test_cutoff_contracts.py` - timestamp and preflight parity contracts
- `src/git_history_sanitize/compact.py` - shared history validation
- `src/git_history_sanitize/engine.py` - plan uses shared validation
- `src/git_history_sanitize/filtering.py` - preserve synthetic-root proof message
- `tests/test_filtering_contracts.py` - path and mixed-root contracts
- `tests/test_cli_contracts.py` - CLI JSON and expected-failure contracts
- `tests/support/git_fixture.py` - deterministic commit-tree helper for tamper cases
- `tests/test_output_contracts.py` - report redaction contract
- `tests/test_verifier_contracts.py` - verifier tamper contracts
