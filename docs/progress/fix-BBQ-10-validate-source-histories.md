# BBQ-10: Validate complete and explicitly bounded source histories

**Branch:** `fix/BBQ-10-validate-source-histories`
**Worktree:** `/Users/tlepola/Documents/dev/projects/personal/git-history-sanitize/.opencode/.bbq-worktrees/fix-BBQ-10-validate-source-histories`
**Status:** In Progress
**Started:** 2026-09-10
**Last Updated:** 2026-09-10

## Overview

Implement fail-closed source scope validation for complete, bounded shallow, and snapshot sanitization modes.

## Workflow Checklist

> **IMPORTANT**: This checklist ensures all workflow steps are completed, even after context compaction.
> Check off each phase as you complete it. After ANY interruption, read this section first.

### Phase 1: Implementation
- [x] Write/modify tests (TDD)
- [x] Implement changes
- [x] Validate (source, wheel, and OCI runtime matrices pass)
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

- [x] Capture workflow root and load binding House Rules
- [x] Move Linear ticket to In Progress and review ticket research/plan/comments
- [x] Review relevant project learnings
- [x] Create dedicated ticket worktree
- [x] Add source scope policy and preflight contracts
- [x] Implement scope-aware rewrite, verification, receipt, and metadata behavior
- [x] Run complete source/wheel/OCI validation matrix

## Progress Log

### 2026-09-10

Initialized dedicated worktree. House Rules loaded from the launching checkout;
no exceptions. Reviewed ticket research, technical plan, comments, and relevant
learnings. Applied fixture isolation, OCI mount, and surrogateescape guidance.

Implemented the source-mode policy, shared no-lazy-fetch/no-replace preflight,
complete/bounded/snapshot graph validation, scope reports, canonical published
scope metadata, bounded shallow-marker cleanup, and snapshot compaction. Added
focused policy/source integration contracts and updated documentation. Receipt
v2 now binds mode and private scope evidence, while legacy v1 remains restricted
to complete-mode verification. Focused source, cutoff, receipt, and verifier
suites passed locally; the full source/wheel/OCI matrix remains to be completed.

Health-inspector follow-up corrected scope accounting: complete mode now proves
all local refs while reporting the exact `HEAD` graph that rewrite compacts, and
snapshot mode validates/counts only `HEAD` and its current tree closure. Added
pre-publication shallow/graft/promisor/missing-object contracts, legacy complete
timestamp metadata compatibility, valid v1 receipt verification, and strict
metadata rejection for snapshot and v2 receipt outputs. Full source/wheel/OCI
runtime coverage passed locally: the source, built wheel, and freshly built OCI
image each passed the 47-test runtime contract matrix. Review revisions are
pending their focused commit.

## Technical Notes

- Worktree state: created from `origin/main`; all further repository work uses this path.
- Source scope validation must fail before staging or publication and must never trigger lazy fetches.
- No House Rules exceptions are required.

## Testing

- [x] Unit tests written
- [x] Integration tests written
- [ ] Manual testing completed

## Files Changed

- `docs/progress/fix-BBQ-10-validate-source-histories.md` - workflow tracking
- `src/git_history_sanitize/source_scope.py` - shared source preflight
- `src/git_history_sanitize/scope_metadata.py` - published scope contract
- `src/git_history_sanitize/verify.py` - legacy metadata and receipt compatibility
- `tests/test_source_scope_contracts.py` - source-scope acceptance contracts
- `tests/test_verify_contracts.py` - metadata and receipt compatibility contracts
- `tests/test_receipt.py` - v1 receipt compatibility contract
- `README.md` - source-scope and legacy verification documentation
