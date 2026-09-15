# BBQ-29: Define privacy rules for reports and diagnostics

**Branch:** `feat/BBQ-29-privacy-report-diagnostics`
**Worktree:** `/Users/tlepola/Documents/dev/projects/personal/git-history-sanitize/.opencode/.bbq-worktrees/feat-BBQ-29-privacy-report-diagnostics`
**Status:** In Progress
**Started:** 2026-09-15
**Last Updated:** 2026-09-15

## Overview

Implement versioned, safe-by-default human and JSON reports, with a strictly
opt-in local trusted diagnostic view and a documented privacy contract.

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

- [x] Read ticket research, technical plan, House Rules, and relevant learnings.
- [x] Resolve Herdr worktree and sync local-only files.
- [x] Add failing public/trusted report contract tests.
- [x] Implement the safe v2 renderer and trusted diagnostics opt-in.
- [x] Route human errors through fixed safe summaries.
- [x] Update documentation and affected integration contracts.
- [x] Run focused and full quality checks.
- [ ] Pass the implementation review gate.

## Progress Log

### 2026-09-15

Started in the dedicated Herdr-managed worktree. Linear ticket moved to In
Progress. Loaded House Rules from the launching checkout; no exceptions are
approved or required. Reviewed the ticket's research/plan and relevant
learnings: preserve fixed error projections, keep sensitive fixture inputs
contained, use hermetic Git fixtures, retain strict stderr assertions, and
never roll back published output.

### 2026-09-15

Added test-first public-v2 and trusted-diagnostic contracts, observed the
expected failures, then implemented the classified reporting boundary. Public
reports now contain only aggregate data; trusted identity values are confined
to `diagnostics`; legacy v1 requires explicit trusted JSON selection. Human
success and failures now share fixed safe rendering. Focused reporting, CLI,
engine-failure, source-scope, hook, output-cleanup, verification, and
end-to-end tests pass. Full discovery (192 tests), the pinned source runtime
matrix (64 tests), and package build pass. No lint or type-check script is
configured in `pyproject.toml`.

### 2026-09-15

Implementation review identified missing persistence and release-output guards.
Added a trusted-rewrite contract proving excluded paths and hook names remain
only in transient report data and are absent from scope metadata and receipts.
Added static CI/release/TestPyPI guards against trusted diagnostics, receipts,
and scope metadata. Trusted human `rewrite` and `verify` output now use the
same fixed identity labels as trusted JSON. Internal exceptions may retain
private context for control flow, but the sole CLI rendering boundary projects
only catalog metadata and fixed invariants; no exception text is emitted.

### 2026-09-15

Second review required explicit coverage for trusted human `plan` and `rewrite`
rendering. Added unit contracts for the complete classified identity set across
all trusted human commands. Human errors now include only fixed catalog
remediation, preserving safe actionable guidance without reflecting user input.

## Technical Notes

- Default reports must be safe for shared logs and CI artifacts.
- Trusted diagnostics are exact opt-in, local-only, transient, and must never
  expose forbidden content, credentials, raw command/stderr data, or receipts.
- JSON v2 is required for public-field removal; v1 must require explicit JSON
  plus trusted diagnostics before legacy identity fields can be selected.
- House Rules: Security First, predictable deterministic CLI, no dependencies,
  focused sanitizer scope. Compliance is active; no exceptions.

## Testing

- [x] Unit tests written
- [x] Integration tests written
- [x] Manual testing completed

## Files Changed

- `docs/progress/feat-BBQ-29-privacy-report-diagnostics.md` - workflow tracker.
- `src/git_history_sanitize/reporting.py` - classified v2/legacy report and safe human renderers.
- `src/git_history_sanitize/cli.py` - trusted diagnostics and legacy-schema selection.
- `README.md` - privacy matrix, trusted-mode guidance, and v1 migration policy.
- `tests/test_reporting.py` - public/trusted serializer contracts.
- `tests/test_cli_contracts.py` - opt-in and safe output contracts.
- `tests/test_output_cleanup_contracts.py` - sensitive public-report redaction coverage.
- `tests/test_hooks.py`, `tests/test_verify_contracts.py`, `tests/test_end_to_end.py` - trusted/public consumers.
- `tests/test_engine_failure_contracts.py`, `tests/test_source_scope_contracts.py` - fixed safe human errors.
- `tests/test_diagnostics.py` - trusted diagnostic persistence boundary.
- `tests/test_release_workflow.py` - CI and release artifact privacy guard.
