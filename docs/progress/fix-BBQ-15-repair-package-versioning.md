# BBQ-15: Repair package versioning and gate releases

**Branch:** `fix/BBQ-15-repair-package-versioning`
**Worktree:** `/Users/tlepola/Documents/dev/projects/personal/git-history-sanitize/.opencode/.bbq-worktrees/fix-BBQ-15-repair-package-versioning`
**Status:** Complete
**Started:** 2026-09-07
**Last Updated:** 2026-09-07

## Overview

Establish a canonical package version and fail-closed release preparation and
publication gates.

## Workflow Checklist

> **IMPORTANT**: This checklist ensures all workflow steps are completed, even after context compaction.
> Check off each phase as you complete it. After ANY interruption, read this section first.

### Phase 1: Implementation
- [x] Write/modify tests (TDD)
- [x] Implement changes
- [x] Validate (focused tests, build, and runtime contracts pass)
- [x] Commit implementation changes — `31ab99f`

### Phase 2: Learnings
- [x] Extract learnings
- [x] Document learning in `docs/learnings/gotchas.md`
- [x] Commit learning — `b430872`

### Phase 3: Finalize & Push (DO NOT SKIP)
- [x] Update this progress doc to "Complete" status
- [x] Commit progress doc update — use `git-commit` skill
- [x] Push all commits to remote — use `git-push-remote` skill
- [x] Create pull request — GitHub PR #5
- [x] Move ticket to "In Review" — Linear updated

## Tasks

- [x] Add canonical version and public CLI contract
- [x] Add release checker and release-preparation command
- [x] Gate release and TestPyPI workflows on validated artifacts
- [x] Update CI, container, release documentation, and examples
- [x] Add unit, integration, and workflow contract tests
- [x] Complete implementation review and final validation

## Progress Log

### 2026-09-07

Implemented the canonical version source, public `--version` contract,
fail-closed release utility, artifact gate, workflow dependencies, and release
documentation. Added focused version, artifact, and workflow contract tests;
focused validation passed. The health-inspector review required separating
publishable distributions from manifest files and restoring OCI checkout
permissions; both fixes and their tests are included in `31ab99f`.

### 2026-09-07

Recorded the PyPI publisher artifact-directory constraint as a gotcha in
`b430872`. No House Rules exceptions were required. Finalization is ready:
focused tests, build, source/wheel/OCI contracts, and two health-inspector
review rounds passed.

### 2026-09-07

Pushed `fix/BBQ-15-repair-package-versioning`, opened GitHub PR #5, and moved
BBQ-15 to In Review. All workflow phases are complete.

### 2026-09-07

Added a concise `scripts/prepare-release.sh VERSION [--push]` wrapper after
maintainer feedback. It creates an isolated temporary environment and delegates
all version and release safety checks to `scripts/release.py`.

### 2026-09-07

Started in dedicated worktree. Loaded House Rules with no exceptions, reviewed
the complete Linear research and technical plan, and applied relevant fixture
and stderr-contract learnings.

## Technical Notes

- Worktree state: created from `origin/main`.
- House Rules: no exceptions. The design must fail closed before registry
  mutations, retain deterministic diagnostics, and add no runtime dependency.
- Applied learning: use fixture-owned Git state and preserve empty successful
  stderr contracts.

## Testing

- [x] Unit tests written
- [x] Integration tests written
- [x] Workflow contract tests written
- [ ] Lint passed (not configured)
- [x] Build/typecheck passed (build passed; no typecheck configured)
- [x] Full test suite passed (source, wheel, and OCI runtime contracts)

## Files Changed

- `src/git_history_sanitize/_version.py` - canonical package version.
- `scripts/release.py` - fail-closed release validation and preparation.
- `.github/workflows/{release,testpypi,ci}.yml` - gated publishing contracts.
- `tests/test_release_{versioning,workflow}.py` - release gate tests.
- `scripts/prepare-release.sh` - maintainer-facing release helper.
- Package metadata, runtime, container, requirements, and release documentation.
