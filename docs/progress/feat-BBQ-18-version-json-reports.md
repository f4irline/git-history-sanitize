# BBQ-18: Version JSON reports and return structured JSON errors

**Branch:** `feat/BBQ-18-version-json-reports`
**Worktree:** `/Users/tlepola/Documents/dev/projects/personal/git-history-sanitize/.opencode/.bbq-worktrees/feat-BBQ-18-version-json-reports`
**Status:** In Progress
**Started:** 2026-09-15
**Last Updated:** 2026-09-15 17:18

## Overview

Implement a versioned, redacted JSON v1 CLI contract for doctor, plan, rewrite,
and verify successes and failures, with deterministic serialization and
documented compatibility guarantees.

## Workflow Checklist

> **IMPORTANT**: This checklist ensures all workflow phases are completed after
> interruption or context compaction. Read it first before resuming.

### Phase 1: Implementation
- [x] Write/modify tests (TDD)
- [x] Implement changes
- [x] Validate (lint, build, tests pass)
- [ ] Commit implementation changes — use `git-commit` skill
- [ ] Pass implementation review gate

### Phase 2: Learnings
- [ ] Extract learnings (or note: nothing noteworthy)
- [ ] Document learnings if any — use `learnings` skill
- [ ] Commit learnings if any — use `git-commit` skill

### Phase 3: Finalize & Push (DO NOT SKIP)
- [ ] Update this progress doc to `Complete` status
- [ ] Commit progress doc update — use `git-commit` skill
- [ ] Push all commits to remote — use `git-push-remote` skill
- [ ] Create pull request — use GitHub MCP
- [ ] Move ticket to `In Review` — use Linear MCP

## Tasks

- [x] Define explicit JSON v1 serializers and safe error catalog
- [x] Route CLI JSON successes, expected failures, parser failures, and internal failures
- [x] Tag CLI-reachable failures by owning boundary and publication state
- [x] Add/update CLI contract, redaction, and failure tests
- [x] Document JSON schema v1 compatibility and stream contract

## Progress Log

### 2026-09-15 17:02

Implemented the CLI-owned reporting boundary, v1 envelope serializers, fixed
error catalog projection, parser JSON failure containment, safe unexpected
failure handling, and publication-state reporting. Focused reporting and CLI
contracts pass in the isolated source virtual environment.

### 2026-09-15 17:12

Classified source preflight failures for JSON consumers and updated all existing
JSON contract consumers to read the v1 `result` envelope. The focused source,
cutoff, CLI, and verification suite passed 58 tests. No dedicated lint or
typecheck command is configured.

### 2026-09-15 17:18

Implementation review round 1 found missing publication-state coverage and an
incorrect `git-filter-repo` failure category. Added explicit allowlisted-state
serializer tests and converted path-filtering tool failures to
`dependency.unavailable`; focused reporting and CLI contracts pass (17 tests).

### 2026-09-15 16:42

Added failing reporting-unit contracts first for the versioned envelope,
deterministic serializer, tuple conversion, surrogate escaping, omission rules,
and catalog-only error projection.

### 2026-09-15 16:36

Initialized the dedicated Herdr worktree. Read the full Linear ticket and no
additional planning comments. Applied relevant fixture, publication-state,
strict-stderr, sensitive-input, and surrogateescape learnings.

## Technical Notes

- House Rules loaded from the launching checkout and apply throughout; no
  exceptions requested or approved.
- JSON output must expose only explicitly allowlisted safe fields and fixed
  catalog metadata; raw errors and input-derived data must not be serialized.
- Worktree was created with Herdr from `origin/main`; no local-only files were
  linked or copied.

## Testing

- [ ] Unit tests written
- [ ] Integration tests written
- [ ] Manual testing completed

## Files Changed

- `docs/progress/feat-BBQ-18-version-json-reports.md` - workflow tracker
- `tests/test_reporting.py` - JSON v1 reporting unit contracts
- `src/git_history_sanitize/reporting.py` - explicit JSON v1 serializers and envelopes
- `src/git_history_sanitize/errors.py` - catalog metadata and typed error classes
- `src/git_history_sanitize/cli.py` - JSON stream/error routing and parser containment
- `src/git_history_sanitize/engine.py` - argument categories and publication state
- `src/git_history_sanitize/git.py` - dependency and source failure categories
- `src/git_history_sanitize/publication.py` - typed publication failures
- `src/git_history_sanitize/source_scope.py` - source failure category
- `src/git_history_sanitize/rewrite_analysis.py` - source analysis category
- `tests/test_cutoff_contracts.py` - v1 JSON consumer/failure contracts
- `tests/test_source_scope_contracts.py` - v1 JSON source failure contracts
- `tests/test_verify_contracts.py` - v1 JSON verification failure contract
- `tests/test_cli_contracts.py` - versioned CLI success/failure contracts
