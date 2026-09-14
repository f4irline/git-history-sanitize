# BBQ-6: Preserve trusted repository hooks without importing runner hooks

**Branch:** `fix/BBQ-6-preserve-trusted-hooks`
**Worktree:** `/Users/tlepola/Documents/dev/projects/personal/git-history-sanitize/.opencode/.bbq-worktrees/fix-BBQ-6-preserve-trusted-hooks`
**Status:** In Progress
**Started:** 2026-09-14
**Last Updated:** 2026-09-14 22:06

## Overview

Preserve eligible trusted source hooks while preventing runner Git templates from
injecting hooks into sanitized output. Add an explicit strip policy, deterministic
reporting, portable-hook warnings, and forbidden-content verification.

## Workflow Checklist

> **IMPORTANT**: This checklist ensures all workflow steps are completed, even after
> context compaction. After any interruption, read this section first.

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

- [x] Review ticket, technical plan, House Rules, and relevant learnings
- [x] Resolve Herdr worktree and synchronize local files
- [x] Add fixture-backed hook behavior tests
- [x] Implement safe hook inventory, template isolation, and installation
- [x] Extend CLI/reporting, verification, and documentation
- [ ] Validate and complete implementation review gate

## Progress Log

### 2026-09-14 22:06

Implementation review required a correction: bare repositories must never gain a
fabricated worktree root when their Git directory is inspected. The repository
adapter now detects bare repositories explicitly; their hook paths remain bounded
to the Git directory. Added unit and CLI coverage for an out-of-bound bare
`core.hooksPath` with redacted failure behavior. The corrected full source suite
passed: 183 tests. A second implementation review is pending.

### 2026-09-14 22:02

Implemented the binary-safe trusted-hook inventory and output installer; both
internal clones now use a private empty template directory. Added default
preservation, `--strip-hooks`, custom local-path activation, deterministic report
metadata, portability warnings, and shared forbidden-content scanning. The full
source suite passed: 182 tests. No lint, build, or standalone typecheck command
is configured in `pyproject.toml`.

Committed the implementation as `2e716a7` (`feat(hooks): preserve trusted
repository hooks`).

### 2026-09-14 21:41

Rebased the ticket worktree onto the updated `origin/main` at the user's request.
The branch already matched the fetched base; uncommitted progress and TDD tests were
safely stashed and restored without conflict.

### 2026-09-14 21:39

Read the researched ticket and technical plan, House Rules, and all learning files.
Moved BBQ-6 to In Progress; Herdr created the isolated ticket worktree. No House
Rules exceptions are required. The implementation will use `GitFixture`, retain
strict stderr/redaction contracts, and keep SHA-256 filtering out of required
coverage.

## Technical Notes

- `workflow_root` remains `/Users/tlepola/Documents/dev/projects/personal/git-history-sanitize`.
- Herdr runtime is configured and active; workspace metadata is `w9`.
- The active code path is this worktree; source House Rules remain authoritative.
- Security controls: safe regular-file-only inventory, private empty clone templates,
  no hook execution, redacted report fields, and shared hook scanning for `--forbid`.

## Blockers

None. BBQ-22's `GitFixture` dependency is complete and available.

## Testing

- [x] Unit tests written
- [x] Integration tests written
- [x] Manual testing completed

## Files Changed

- `docs/progress/fix-BBQ-6-preserve-trusted-hooks.md` - workflow record
- `src/git_history_sanitize/hooks.py` - safe hook discovery and installation
- `src/git_history_sanitize/git.py` - isolated clone template and worktree lookup
- `src/git_history_sanitize/engine.py` - hook policy and rewrite reporting
- `src/git_history_sanitize/cli.py` - `--strip-hooks` and human output
- `src/git_history_sanitize/verify.py` - active-hook forbidden-content scanning
- `tests/test_hooks.py` - fixture-backed hook behavior contracts
- `tests/test_cli_contracts.py` - hook report CLI contracts
- `README.md` - trusted-hook security and portability documentation
