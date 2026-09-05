# BBQ-44: Build a core rewrite and verification contract test matrix

**Branch:** `test/BBQ-44-core-contract-matrix`
**Worktree:** `/Users/tlepola/Documents/dev/projects/personal/git-history-sanitize/.opencode/.bbq-worktrees/test-BBQ-44-core-contract-matrix`
**Status:** In Progress
**Started:** 2026-09-05
**Last Updated:** 2026-09-05 15:05

## Overview

Add focused, hermetic contract coverage for the supported plan, rewrite, verify,
and CLI behavior using the existing `GitFixture` harness.

## Workflow Checklist

> **IMPORTANT**: After any interruption, read this checklist first.

### Phase 1: Implementation
- [x] Write/modify tests (TDD)
- [x] Implement changes
- [x] Validate feasible local checks
- [ ] Commit implementation changes — use `git-commit` skill

### Phase 2: Learnings
- [x] Extract learnings (nothing noteworthy beyond the existing fixture pattern)
- [x] Document learnings if any — no new learning required
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

### 2026-09-05 14:18

Implementation Review Gate round 2 found that the technical plan's pinned
toolchain and source/wheel/OCI matrix remain unimplemented. It also identified
that the initial production changes consumed contracts owned by BBQ-7 and
BBQ-12. Those changes and their owner-dependent tests were reverted. The work
remains blocked pending an approved scope change or completion of the planned
matrix implementation.

### 2026-09-05 14:23

Expanded only `GitFixture` and contract tests in response to review feedback.
The settled matrix now covers bare-output cleanup, atomic failed rewrites and
staging cleanup, re-sanitization without source mutation, concise human CLI
success output, and independent verifier rejection of tampered refs, tags,
remotes, reflogs, temporary metadata, unreachable objects, reachable graph
roots, and forbidden object-database content. The source suite passes all 34
tests. No production behavior or owner-dependent BBQ-7, BBQ-8, BBQ-11, or
BBQ-12 contract was changed or added.

### 2026-09-05 14:27

Added the pinned Git bootstrap, fail-closed stdlib toolchain checker, isolated
Containerfile environments, CI source/wheel/OCI matrix, and exact local-command
documentation. Shell, Python, YAML, and whitespace checks passed. The runtime
image build compiled Git 2.47.0 after build-local GCC 15 compatibility renames,
then stopped at the required git-filter-repo fingerprint assertion: upstream
tag `v2.47.0` at the planned commit emits `a40bce548d2c`, not the planned
`bc98e38e057b`. The checker retains the planned fingerprint and the matrix is
blocked pending a corrected, approved toolchain pin.

### 2026-09-05 14:31

Implementation Review Gate round 3 returned changes required. It found that
the new runtime selectors are not yet consumed by `GitFixture`, the planned
toolchain fingerprint conflicts with the output from its pinned source, and
the deterministic checker tests plus signed-tag verification are still absent.
This is the third review round, so the workflow stops for user direction rather
than relaxing the fail-closed toolchain policy.

### 2026-09-05 15:05

Resolved the latest health-inspector findings without changing sanitizer
behavior. `GitFixture` now selects source, wheel, or container execution from
`GHS_TEST_RUNTIME`: source uses isolated module execution without `PYTHONPATH`;
wheel requires `GHS_WHEEL` and creates a fresh fixture-owned venv before using
its console script; container requires `GHS_CONTAINER_IMAGE`, invokes its OCI
entrypoint with translated fixed paths, read-only inputs, writable output, a
read-only root filesystem, no network, and a fixed environment allowlist.

The checked `git-filter-repo` fingerprint is now the verified pinned-source
output `a40bce548d2c`, correcting the approved pin while retaining exact-output
fail-closed checks. Added deterministic mocked checker tests and made CI run
them with the real checker before host runtimes. Git bootstrap now imports only
the pinned Git release key into an isolated keyring and verifies the signed tag
before checkout; CI and the image install GnuPG for that verification.

### 2026-09-05 15:15

Ran the full isolated source suite with an editable install and no `PYTHONPATH`
(42 tests), plus a built-wheel end-to-end run through the fixture-owned venv
(2 tests). Python compilation, shell syntax, YAML parsing, and whitespace
checks also passed. The complete signed bootstrap and OCI matrix remain for CI:
this host has no `gpg`, and the bootstrap correctly refuses to continue.

## Technical Notes

- House Rules loaded from the launching checkout and apply without exceptions.
- Worktree state: created at the path above; no local-only files required
  mirroring because `proto/.devcontainer/.env` is absent.
- Initial exploration confirms core focused tests can consume the existing
  hermetic fixture. Owner-dependent contracts remain fail-closed.
- Learning captured in `docs/learnings/gotchas.md`: validate a tool fingerprint
  from the exact pinned source before treating it as an approved contract.

## Testing

- [x] Focused output, verifier, and human CLI contract tests (18 tests)
- [x] Full isolated source suite (42 tests without `PYTHONPATH`)
- [x] Package build (`pip3 wheel --no-deps .`)
- [x] Isolated wheel runtime (`git-history-sanitize doctor --json`)
- [x] Container suite (24 tests via `docker buildx build --target test -f Containerfile .`)
- [x] Shell, Python, YAML, and whitespace static checks for toolchain changes
- [x] Focused deterministic runner and toolchain tests (12 tests)
- [ ] Full pinned runtime image and contract matrix (not run locally; this host
  lacks GnuPG, so the signed-tag bootstrap correctly fails closed)

## Files Changed

- `docs/progress/test-BBQ-44-core-contract-matrix.md` - workflow tracker
- `tests/support/git_fixture.py` - deterministic policy and tamper-tree helpers
- `tests/test_cutoff_contracts.py` - timestamp and preflight parity contracts
- `src/git_history_sanitize/compact.py` - shared history validation
- `src/git_history_sanitize/engine.py` - plan uses shared validation
- `src/git_history_sanitize/filtering.py` - preserve synthetic-root proof message
- `tests/test_filtering_contracts.py` - path and mixed-root contracts
- `tests/test_cli_contracts.py` - CLI JSON, human output, and expected-failure contracts
- `tests/support/git_fixture.py` - deterministic commit-tree, tamper-tree, and staging-cleanup helpers
- `tests/test_output_contracts.py` - report redaction, bare-output, cleanup, atomicity, and re-sanitize contracts
- `tests/test_verifier_contracts.py` - independent refs, tags, remotes, reflogs, metadata, unreachable-object, graph, and object-database tamper contracts
- `tests/support/toolchain.py` - exact Git and git-filter-repo output checker
- `scripts/bootstrap-test-git.sh` - pinned Git 2.47.0 bootstrap
- `Containerfile` - pinned runtime toolchain and isolated test/runtime venvs
- `.github/workflows/ci.yml` - source, wheel, and OCI contract matrix
- `README.md` - pinned toolchain prerequisites and local matrix commands
- `docs/learnings/gotchas.md` - pinned-source fingerprint mismatch gotcha
- `tests/test_toolchain.py` - deterministic exact-output checker tests
