# BBQ-44: Build a core rewrite and verification contract test matrix

**Branch:** `test/BBQ-44-core-contract-matrix`
**Worktree:** `/Users/tlepola/Documents/dev/projects/personal/git-history-sanitize/.opencode/.bbq-worktrees/test-BBQ-44-core-contract-matrix`
**Status:** Complete
**Started:** 2026-09-05
**Last Updated:** 2026-09-05 15:40 EEST

## Overview

Add focused, hermetic contract coverage for the supported plan, rewrite, verify,
and CLI behavior using the existing `GitFixture` harness.

## Workflow Checklist

> **IMPORTANT**: After any interruption, read this checklist first.

### Phase 1: Implementation
- [x] Write/modify tests (TDD)
- [x] Implement changes
- [x] Validate feasible local checks
- [x] Commit implementation changes — use `git-commit` skill

### Phase 2: Learnings
- [x] Extract learnings
- [x] Document the pinned-source fingerprint gotcha
- [x] Commit learning documentation — use `git-commit` skill

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

### 2026-09-05 16:50

Implementation Review Gate passed after the source-runner isolation fix. The
documented isolated source suite passes (50 tests). The signed wheel/OCI matrix
is CI-gated and intentionally remains fail-closed locally while the pinned
signer keyserver returns no data; no security control was relaxed. The verified
tool fingerprint correction was recorded in the Linear technical plan.

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

### 2026-09-05 16:00

Resolved the remaining health-inspector findings without changing the pinned
toolchain fingerprint. Container fixture execution now maps one input repository
to `/input.git`, policy to `/policy.yml`, and the output parent to `/output`, so
the translated paths cannot shadow each other. It also mounts the fixture-owned
home, XDG configuration, global Git config, template, and hooks directories
read-only at distinct container paths, passes only translated allowlisted Git
environment values, and tests that host fixture paths never reach container CLI
arguments or environment values.

The CI and README now run `test_git_fixture`, `test_toolchain`, and
`test_policy` only in the source helper phase. Source, wheel, and OCI runs use
the same explicit fixture-backed runtime inventory. The prior `--target test`
container check validates the Containerfile's test stage, which runs the source
checkout in `/opt/test`; it does not exercise the runtime OCI entrypoint. The
runtime entrypoint is exercised only by the fixture-backed OCI contract command
when an image is available.

Bootstrap now exports an isolated HOME, XDG config, global config, and template
directory before every Git invocation, including signed-tag verification,
revision resolution, and checkout. Focused helper tests passed locally; full
pinned toolchain, wheel, and OCI checks remain blocked because this host lacks
GnuPG.

An isolated editable source validation passed all 16 source-only helper tests
and all 27 fixture-backed source runtime contracts without `PYTHONPATH`.

The OCI build then exposed a pre-existing one-character regression in the Git
release signer pin. Restored the v2.47.0 signer fingerprint ending in
`B0B5E88696AFE6CB` to `4F9036B1FEE7221FC778ECEFB0B5E88696AFE6CB`; the
git-filter-repo toolchain fingerprint remains `a40bce548d2c`.

### 2026-09-05 16:20

Retried the OCI build after restoring the signer pin. It reached the signed-key
fetch but `keys.openpgp.org` returned `No data`; the bootstrap failed closed and
the build did not continue to fetch, compile, or execute the pinned Git source.
This is an external keyserver-availability blocker for the full wheel/OCI
matrix, not a runtime-entrypoint result.

### 2026-09-05 16:35

Resolved the latest review findings in the fixture harness. The wheel console
script now resolves strictly inside the fixture-owned wheel venv before use.
OCI runtime results now redact host fixture, source, policy, output, and
configuration paths for both successful and expected-failure commands while
allowing the translated fixed container paths. `assert_redacted` now emits a
generic failure diagnostic that does not repeat the sensitive value. Focused
deterministic fixture coverage and the full feasible source suite passed.

### 2026-09-05 15:11

Resolved the latest review findings without changing production behavior. Wheel
fixtures now install `git-filter-repo==2.47.0` into their own fresh runtime venv
and prepend only that venv when resolving the tool; source-runtime access remains
explicit and wheel execution has no host-tool PATH fallback. OCI verification now
maps only the fixture source repository to `/input.git`; rewritten bare outputs
map read-only to `/output/<name>`. New contracts assert those translations,
physical object-database exclusion by source blob IDs, and author/committer
names, emails, and timestamps on a retained non-root commit.

Focused fixture and filtering contracts passed (17 tests). The isolated source
suite passed all 49 tests without `PYTHONPATH`, including the pinned Git and
git-filter-repo checker outputs. Wheel and OCI end-to-end runtime matrix commands
were not run in this update; the existing host GnuPG/keyserver blocker remains.

### 2026-09-05 15:23 EEST

Added a focused reachable `history.cutoffCommit` contract for a linear history.
It proves that plan and rewrite select the same settled boundary and history
counts, retain the boundary tree as the synthetic root, and retain the later
commit. No merge, multi-ref, or other owner-dependent cutoff behavior was added.

CI now installs `git-filter-repo==2.47.0 --no-deps` separately in the source
venv before the editable package. The Containerfile likewise installs it in the
`/opt/test` venv and puts that venv first on `PATH` when its real exact-output
checker runs, preventing the test stage from using only the runtime symlink.

The focused cutoff contracts passed (3 tests), and the full feasible isolated
source suite passed (50 tests) without `PYTHONPATH`. The installed
`git-filter-repo` reports `a40bce548d2c`; Ruby YAML parsing, shell syntax, and
`docker buildx build --check` also passed. The signed Git bootstrap remains
blocked before the full wheel/OCI runtime matrix because `keys.openpgp.org`
returns `No data` for the required release signer key.

### 2026-09-05 15:30 EEST

Renamed the runtime contract modules to
`test_output_cleanup_contracts.py` and `test_verify_contracts.py`. Updated the
runtime inventory, packaging source inventory, and this file; no runtime
behavior changed. The focused source runtime inventory passed 28 tests. Full
source discovery passed all 50 tests in the existing isolated `.venv-verify`
environment without `PYTHONPATH`.

The same full discovery in a newly created documented `.venv-source` failed
one fixture-only assertion: its expected PATH exclusion conflicts with the
documented source setup, which installs `git-filter-repo` in that source venv.
No change was made outside the requested rename scope. The external signed
wheel/OCI matrix blocker is unchanged: this host lacks GnuPG and
`keys.openpgp.org` previously returned `No data` for the required signer key.

### 2026-09-05 15:40 EEST

Resolved the source-runner `PATH` health finding. Source execution now keeps the
fixture's deterministic Python and Git directories rather than prepending the
host-resolved `git-filter-repo` directory. The focused contract proves source
execution remains `python -I -m`, removes checkout `PYTHONPATH`, retains the
shared source-vendor runtime directory, and excludes a competing host tool.

The wheel fixture contract now accepts the documented `.venv-source` layout in
which Python and `git-filter-repo` share `bin`, while retaining its assertion
that wheel installation is run through the fixture-owned venv Python. The
focused fixture suite passed all 14 tests and full documented isolated source
discovery passed all 50 tests without `PYTHONPATH`.

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
- [x] Containerfile test target (`docker buildx build --target test -f Containerfile .`;
  validates its source-checkout test stage, not the runtime OCI entrypoint)
- [x] Shell, Python, YAML, and whitespace static checks for toolchain changes
- [x] Focused deterministic runner and toolchain tests (12 tests)
- [x] Latest review-finding fixture tests (11 tests) and full feasible source
  suite (46 tests) in `.venv-verify`
- [x] Latest source-only helper phase (16 tests) and source runtime inventory
  (27 tests) in an isolated editable venv without `PYTHONPATH`
- [x] Latest fixture and filtering contracts (17 tests) and full isolated source
  suite (49 tests) without `PYTHONPATH`
- [x] Reachable cutoff-commit parity contracts (3 tests) and full isolated source
  suite (50 tests) without `PYTHONPATH`
- [x] Renamed-contract focused source runtime inventory (28 tests) and full
  isolated source discovery (50 tests) in `.venv-verify` without `PYTHONPATH`
- [x] Source-runner PATH regression coverage (14 fixture tests) and full
  documented `.venv-source` discovery (50 tests) without `PYTHONPATH`
- [x] YAML, shell, and Containerfile static checks for the source/test venv pins
- [ ] Full pinned runtime image and contract matrix (not run locally; this host
  lacks host GnuPG and the OCI retry was blocked by `keys.openpgp.org` returning
  `No data`; the signed-tag bootstrap correctly failed closed)

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
- `tests/test_output_cleanup_contracts.py` - report redaction, bare-output, cleanup, atomicity, and re-sanitize contracts
- `tests/test_verify_contracts.py` - independent refs, tags, remotes, reflogs, metadata, unreachable-object, graph, and object-database tamper contracts
- `tests/support/toolchain.py` - exact Git and git-filter-repo output checker
- `scripts/bootstrap-test-git.sh` - pinned Git 2.47.0 bootstrap
- `Containerfile` - pinned runtime toolchain and isolated test/runtime venvs
- `.github/workflows/ci.yml` - source, wheel, and OCI contract matrix
- `README.md` - pinned toolchain prerequisites and local matrix commands
- `docs/learnings/gotchas.md` - pinned-source fingerprint mismatch gotcha
- `tests/test_toolchain.py` - deterministic exact-output checker tests
- `tests/support/run_runtime_contracts.sh` - shared source/wheel/OCI runtime inventory
- `tests/support/git_fixture.py` - wheel-local filter-repo and OCI verify path translation
- `tests/test_git_fixture.py` - wheel-local tool and OCI verify mapping contracts
- `tests/test_filtering_contracts.py` - physical object and retained metadata contracts
