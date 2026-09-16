# BBQ-21: Make the OCI image reproducible and non-root

**Branch:** `feat/BBQ-21-reproducible-oci-image`
**Worktree:** `/Users/tlepola/Documents/dev/projects/personal/git-history-sanitize/.opencode/.bbq-worktrees/feat-BBQ-21-reproducible-oci-image`
**Status:** In Progress
**Started:** 2026-09-16
**Last Updated:** 2026-09-16 20:54

## Overview

Implement the approved OCI runtime supply-chain, non-root, release-validation,
and operator-documentation plan for reproducible multi-platform releases.

## Workflow Checklist

> **IMPORTANT**: This checklist ensures all workflow steps are completed, even after context compaction.
> Check off each phase as you complete it. After ANY interruption, read this section first.

### Phase 1: Implementation
- [x] Write/modify tests (TDD)
- [x] Implement changes
- [ ] Validate (lint, build, tests pass) — validate-changes plugin runs automatically
- [x] Commit implementation changes — use `git-commit` skill
- [ ] Pass implementation review gate

### Phase 2: Learnings
- [x] Extract learnings (or note: nothing noteworthy)
- [x] Document learnings if any — use `learnings` skill
- [x] Commit learnings if any — use `git-commit` skill

### Phase 3: Finalize & Push (DO NOT SKIP)
- [ ] Update this progress doc to "Complete" status
- [ ] Commit progress doc update — use `git-commit` skill
- [ ] Push all commits to remote — use `git-push-remote` skill
- [x] Create pull request — use GitHub MCP
- [x] Move ticket to "In Review" — use Linear MCP

## Tasks

- [x] Add locked OCI toolchain manifest, deterministic verifier, and sentinel contract.
- [x] Build a minimal, non-root OCI runtime from pinned artifacts.
- [x] Extend doctor and OCI contract coverage with fail-closed metadata checks.
- [x] Add multi-platform CI/release, SBOM/provenance, scanning, and refresh controls.
- [x] Document hardened usage and security update process.

## Progress Log

### 2026-09-16

CI reported two defects. The arm64 fixture suite omitted `--platform` on nested
Docker commands, causing Docker's architecture warning to violate strict stderr
contracts. The security refresh scan found eight HIGH CVEs in the unused
`/usr/bin/pebble` binary inherited from the Ubuntu image. `b7f5f5a` forwards
the selected platform through the fixture runner and removes that unused binary.
The locked OCI test target now passes 211 tests; local arm64 image build,
caller-UID `doctor`, and absence of the binary were verified. Push and hosted
CI confirmation remain.

### 2026-09-16

Pushed the implementation through `7940192`, then moved BBQ-21 to In Review.
The follow-up progress commit finalizes the workflow record.

### 2026-09-16

Final local quality gate passed. The locked OCI test target completed all 210
tests; the final runtime image built, `doctor --json` validated the manifest,
and its configured user is `65532:65532`. No linter or typecheck script is
configured; the locked OCI test target is the project test/build validation.

### 2026-09-16

Added weekly Dependabot review proposals for the literal, digest-pinned OCI
base and GitHub Actions. `security-refresh` now scans pull requests targeting
main that change a reviewed toolchain input, remains read-only, and cannot push
an image or create a pull request. The lock-binding contract requires the
reviewed digest on both Docker stages. An independent review found Dependabot
cannot resolve an ARG-backed `FROM`; replacing that indirection was reviewed
cleanly. The locked OCI test target passes all 210 tests.

### 2026-09-16

Committed Git compatibility patch input/output hash checks (`0140a01`) after
syntax, static-contract, and full builder validation succeeded. Committed
per-platform OCI contracts (`227892e`): CI now asserts the non-root image
account, exercises `doctor` under the caller UID:GID, and runs the existing
fixture rewrite suite (including output UID:GID assertions) for amd64 and
arm64. The locked OCI test target passes all 210 tests. Direct native source
tests remain unsuitable because the host does not use the locked Git 2.47.0
toolchain.

The remaining security-refresh requirement needs an approved authoritative
source for a new base digest and per-architecture APT snapshot/package lock.
The current repository has no lock-regeneration tool or source of truth for
those values, so the scheduled workflow cannot safely invent a mutable update.

### 2026-09-16

After opening PR #16, the Linear technical plan review surfaced unimplemented
requirements: a reviewed security-refresh PR path, per-platform runtime
contracts beyond `doctor`, and Git compatibility patch hashes. The progress
state is reopened; the PR remains open while those requirements are completed.

### 2026-09-16

Final quality gate passed: the locked OCI test target ran 210 tests successfully;
the runtime image built successfully; `doctor --json` validated the provenance
manifest; and the image ran as UID:GID `65532:65532`. No linter, typecheck, or
standalone build script is configured in `pyproject.toml`; the OCI build is the
project build validation. Native arm64 validation completed locally; amd64 is
validated by the configured GitHub Actions matrix because local QEMU GCC
emulation previously produced a compiler internal error.

### 2026-09-16

Recorded the OCI CA bootstrap constraint in `docs/learnings/gotchas.md` and
committed it separately as `5e151b4`. Final lint/build/test validation and
runtime image checks are next.

### 2026-09-16

Implementation review found and resolved missing build/lock binding, missing
live Python verification, mutable APT CA bootstrap, and unenforced Trivy
exception governance. The CA bundle is now bootstrapped from the immutable,
signed snapshot before normal TLS verification resumes; all current lock inputs
are contract-tested against the build definitions. The final OCI test target
passes all 210 tests. Review feedback that contradicted the successful native
`doctor --json` result (Python 3.14.4) was not applied.

### 2026-09-16

All 206 tests pass in the locked OCI test target. A native runtime build passed
with a non-unknown source revision, `doctor --json` verified the manifest, and
the process ran as UID:GID `65532:65532`. The release image build now passes
the tag commit timestamp, revision, and validated package version to the
manifest generator. A local emulated `linux/amd64` build hit a GCC compiler
internal error; the configured GitHub Actions matrix remains responsible for
native amd64 and arm64 validation.

### 2026-09-16

The immutable snapshot resolved on retry, allowing the runtime image to build
and run as UID:GID `65532:65532`. Expanded the Docker test stage to include
the repository so OCI, workflow, and documentation contract tests can run
inside the locked toolchain. Full OCI test-target validation is now running.

### 2026-09-16

Implementation is blocked on the selected immutable Ubuntu snapshot returning
HTTP 503 from APT during a clean rebuild. The snapshot had previously resolved
the locked packages after CA bootstrap, so no mutable-repository fallback was
accepted. OCI build validation therefore remains incomplete and no commit,
push, or pull request was created.

### 2026-09-16

Approved baseline: retain the existing base digest, generate and review the
exact per-architecture APT locks from the selected immutable snapshot, use
UID:GID `65532:65532`, and scan the final digest with Trivy at
HIGH/CRITICAL severity. Exceptions default to empty and must be scoped,
owned, reviewed, and expire within 30 days.

### 2026-09-16

Created a Herdr-managed worktree from `origin/main`; synced local files (none).
Loaded House Rules and relevant OCI learnings. No approved House Rules exceptions.

## Technical Notes

- Worktree provider: Herdr (active `HERDR_ENV=1`); workspace metadata `wG`.
- Relevant learnings require caller UID:GID for writable fixture output, narrow
  read-only mounts, the verified `a40bce548d2c` filter-repo fingerprint, and
  hermetic `GitFixture` coverage.
- The final OCI image must fail closed if its required sentinel or manifest is
  missing and must not include build-only material.

## Testing

- [x] Unit tests written
- [x] Integration tests written
- [x] Manual OCI validation completed

## Files Changed

- `Containerfile` - locked multi-stage non-root image and OCI test target.
- `container/` - pinned toolchain lock, runtime sentinel, and entrypoint.
- `src/git_history_sanitize/oci_toolchain.py` - fail-closed OCI manifest parsing.
- `src/git_history_sanitize/git.py` - doctor toolchain provenance reporting.
- `scripts/verify-container-toolchain.py` - deterministic manifest generator.
- `tests/test_oci_contracts.py` - OCI lock and runtime contracts.
- `tests/test_output_cleanup_contracts.py` - caller-owned output contract.
- `tests/test_release_workflow.py` - release, CI, scanning, and provenance contracts.
- `.github/workflows/` - CI platform matrix, release promotion, and security refresh.
- `.github/dependabot.yml` - weekly Docker and GitHub Actions review proposals.
- `docs/security-update-process.md` - image refresh and exception process.
- `README.md`, `PUBLISHING_PLAN.md`, `docs/release-notes.md` - hardened operator guidance.
- `docs/progress/feat-BBQ-21-reproducible-oci-image.md` - workflow progress tracking.
