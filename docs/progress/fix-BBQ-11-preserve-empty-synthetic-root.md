# BBQ-11: Preserve an empty synthetic root when all content is excluded

**Branch:** `fix/BBQ-11-preserve-empty-synthetic-root`
**Worktree:** `/Users/tlepola/Documents/dev/projects/personal/git-history-sanitize/.opencode/.bbq-worktrees/fix-BBQ-11-preserve-empty-synthetic-root`
**Status:** Complete
**Started:** 2026-09-14
**Last Updated:** 2026-09-14 18:08

## Overview

Support a non-empty source whose retained `HEAD` tree is fully excluded by
preserving a deterministic, parentless synthetic root with Git's canonical
empty tree. Report the retained `HEAD` path count and retain all cleanup,
verification, and symbolic-`HEAD` guarantees.

## Workflow Checklist

> **IMPORTANT**: This checklist ensures all workflow steps are completed, even after context compaction.
> Check off each phase as you complete it. After ANY interruption, read this section first.

### Phase 1: Implementation
- [x] Write/modify tests (TDD)
- [x] Implement changes
- [x] Validate (lint, build, tests pass) — validate-changes plugin runs automatically
- [x] Commit implementation changes — use `git-commit` skill

### Phase 2: Learnings
- [x] Extract learnings (or note: nothing noteworthy)
- [x] Document learnings if any — use `learnings` skill
- [x] Commit learnings if any — use `git-commit` skill

### Phase 3: Finalize & Push (DO NOT SKIP)
- [x] Update this progress doc to "Complete" status
- [x] Commit progress doc update — use `git-commit` skill
- [x] Push all commits to remote — use `git-push-remote` skill
- [x] Create pull request — use GitHub MCP
- [x] Move ticket to "In Review" — use Linear MCP

## Tasks

- [x] Resolve the dedicated Herdr worktree and synchronize local-only files.
- [x] Read the ticket, House Rules, and relevant project learnings.
- [x] Add regression-first contracts for all-excluded histories and plan output.
- [x] Implement deterministic empty-root recovery and retained-path reporting.
- [x] Update CLI contracts and README documentation.
- [x] Run the configured validation suite and implementation review gate.

## Progress Log

### 2026-09-14 17:38

Started implementation in the resolved Herdr worktree. Read the binding House
Rules from the launching checkout and applied relevant learnings: use
`GitFixture`, preserve symbolic refs with `surrogateescape`, validate snapshot
scope only from `HEAD`, and do not add SHA-256 filtering coverage while the
pinned runtime remains unsupported. No House Rules exceptions are requested.

### 2026-09-14 17:50

Added fixture-backed regressions for single- and multi-commit sensitive-only
histories, a mixed source with an all-excluded retained history, snapshot mode,
and cutoff-commit receipt creation. The rewrite now restores a captured
synthetic root only when filtering leaves `HEAD` unresolved, preserving its
branch ref, message, metadata, and Git-generated canonical empty tree. The
stable plan contract now reports `retained_head_path_count`; README documents
the zero-path semantics. Focused source contracts pass (29 tests).

### 2026-09-14 18:03

Completed final validation: source runtime contracts (59 tests), package build,
wheel runtime contracts (59 tests), Containerfile test target (166 tests), and
container runtime contracts (59 tests) all pass. `git diff --check` and Python
bytecode compilation also pass; no lint or standalone type-check script is
configured. The first implementation review found only that this required
progress record was untracked; this revision resolves that finding before the
fresh review gate.

### 2026-09-14 18:07

The second implementation review passed after confirming the tracked progress
record and clean worktree. Recorded the v1 empty-sanitized-tree decision in
`docs/learnings/decisions.md`; it captures why recovery follows filtering
instead of weakening pruning, cleanup, or verification. No House Rules
exceptions were required.

### 2026-09-14 18:08

Finalized the implementation record. The branch contains focused implementation,
documentation, progress, and learning commits; all configured source, wheel,
and container validation passed. No lint or standalone type-check script is
configured. House Rules compliance is complete with no approved exceptions.
The next steps are branch push, PR creation, and moving BBQ-11 to In Review.

### 2026-09-14 18:08

Pushed `fix/BBQ-11-preserve-empty-synthetic-root`, opened PR #11, and moved
BBQ-11 to In Review. All workflow checklist phases are complete.

## Technical Notes

- `workflow_root`: `/Users/tlepola/Documents/dev/projects/personal/git-history-sanitize`
- `worktree_path`: `/Users/tlepola/Documents/dev/projects/personal/git-history-sanitize/.opencode/.bbq-worktrees/fix-BBQ-11-preserve-empty-synthetic-root`
- Herdr runtime is active; worktree `w6` was created from `origin/main` and
  local-file synchronization linked/copied zero entries.
- Preserve security-first filtering and cleanup. The repair must happen before
  any cleanup, bare clone, receipt root lookup, or verification resolves `HEAD`.
- Empty-root creation obtains the empty tree through `git mktree`; no
  object-format-specific object ID is hard-coded.

## Testing

- [x] Unit tests written
- [x] Integration tests written
- [x] Manual testing completed

## Files Changed

- `docs/progress/fix-BBQ-11-preserve-empty-synthetic-root.md` - workflow tracking.
- `src/git_history_sanitize/compact.py` - capture and recover synthetic-root identity.
- `src/git_history_sanitize/engine.py` - report retained HEAD paths and repair before cleanup.
- `src/git_history_sanitize/filtering.py` - share plan/filter path-rule semantics.
- `src/git_history_sanitize/git.py` - decode symbolic refs with `surrogateescape`.
- `src/git_history_sanitize/cli.py` - render retained HEAD path count.
- `tests/test_regressions.py` - all-excluded root regression coverage.
- `tests/test_filtering_contracts.py` - snapshot empty-root contract.
- `tests/test_cutoff_contracts.py` - cutoff-commit recovery/receipt contract.
- `tests/test_cli_contracts.py` - stable plan JSON and human output coverage.
- `README.md` - document valid empty sanitized-tree output and plan scope.
- `docs/learnings/decisions.md` - record the empty-sanitized-tree decision.
