# Git History Sanitize: implementation plan

## Goal

Build a focused, open-source tool that creates a standalone sanitized Git
repository from an existing repository and a versioned policy.

The tool is responsible for Git-history rewriting and verification only. It
does not provide containers, filesystem masking, network isolation, agent
configuration, or runtime sandboxing.

## User experience

```bash
# Preview the rewrite without creating output.
git-history-sanitize plan \
  --source .git \
  --policy .git-history-sanitize.yml

# Produce a new, standalone Git database.
git-history-sanitize rewrite \
  --source .git \
  --output build/sanitized.git \
  --policy .git-history-sanitize.yml

# Independently verify the result.
git-history-sanitize verify \
  --repository build/sanitized.git \
  --policy .git-history-sanitize.yml
```

The source repository is read-only by default. Output is written to a temporary
location, verified, and moved to the requested destination only after all
checks pass.

## Policy

```yaml
version: 1

history:
  cutoff: "2026-09-03T00:00:00+03:00"
  # A commit boundary should also be supported:
  # cutoffCommit: "abc123..."
  prefixMessage: "[sanitized]"

paths:
  exclude:
    - secret.json
    - infra/

commits:
  mixedMessage: "[sanitized]"

refs:
  keep:
    - HEAD
```

Rules must be explicit and deterministic:

- Timestamps use RFC 3339 and require a timezone.
- The cutoff comparison uses committer timestamps.
- Commits at the cutoff are retained.
- Directory exclusions end in `/`; file exclusions are exact paths.
- Unknown policy fields and unsupported repository structures fail closed.

## Rewrite pipeline

1. Validate the policy, Git version, `git-filter-repo` version, source, and
   output locations.
2. Create a private disposable clone without checking out the working tree.
3. Resolve and retain only the configured refs.
4. Find the cutoff boundary.
5. Collapse the pre-cutoff history into a parentless synthetic commit whose
   tree matches the first allowed commit and whose message is
   `[sanitized]`.
6. Recreate the remaining graph while preserving allowed trees, commit
   messages, authors, committers, and timestamps.
7. Run sensitive-path filtering over the shortened graph with
   `git filter-repo`.
8. For each original retained commit:
   - keep allowed-only commits normally;
   - keep allowed changes from mixed commits but replace their messages;
   - remove sensitive-only commits when they become empty.
9. Remove remotes, unwanted refs, tags, notes, stashes, reflogs,
   `refs/original`, replace refs, filter-repo mappings, and temporary
   metadata.
10. Repack and garbage-collect with immediate pruning.
11. Run the independent verifier.
12. Atomically publish the sanitized Git database.

The original object database and intermediate repository must never be copied
into the output.

## Components

```text
src/git_history_sanitize/
├── cli.py
├── policy.py
├── repository.py
├── cutoff.py
├── filtering.py
├── cleanup.py
├── verification.py
└── reporting.py

tests/
├── fixtures/
├── test_policy.py
├── test_cutoff.py
├── test_paths.py
├── test_mixed_commits.py
├── test_refs.py
├── test_cleanup.py
└── test_end_to_end.py
```

The implementation should use the `git-filter-repo` callback API for path and
mixed-message filtering. Git subprocess calls should be centralized, avoid
shell interpolation, capture failures, and redact sensitive output.

## Verification contract

Verification must fail unless all of the following hold:

- No reachable commit predates the cutoff.
- The synthetic boundary is a root commit with the configured message.
- Configured paths are absent from reachable history.
- Sensitive blobs and trees are absent from `git rev-list --objects --all`.
- Only configured refs remain.
- No remotes, remote-tracking refs, notes, stashes, replace refs, backup refs,
  or reflogs remain.
- No filter-repo mapping or temporary metadata remains.
- `git fsck --full --unreachable --no-reflogs` reports no unreachable
  objects.
- Mixed commits preserve allowed changes and use the replacement message.
- Sensitive-only commits disappear.
- Normal `log`, `diff`, `show`, `status`, and `blame` operations work
  when the output is paired with a working tree.

The verifier should support human-readable output and a stable JSON report for
CI. Reports must not contain removed commit IDs, messages, object contents, or
source-to-output mappings.

## Test strategy

Start with the fixture behavior proven in the prototype:

- pre-cutoff allowed and mixed commits;
- a first post-cutoff commit that becomes the synthetic root;
- post-cutoff allowed, mixed, and sensitive-only commits;
- a mixed commit at the branch tip;
- forbidden strings in old and mixed commit messages;
- extra branches, tags, notes, stashes, remotes, and reflogs;
- unreachable objects followed by cleanup;
- filenames containing spaces and non-ASCII characters.

Then add:

- merge commits and multi-parent DAG reconstruction;
- multiple retained refs with shared ancestry;
- non-monotonic and malformed timestamps;
- annotated and signed tags;
- signed commits and unusual commit encodings;
- Git LFS pointers, submodules, worktrees, replace refs, and alternates;
- shallow and partial repositories, which should initially fail closed;
- large histories for performance and memory regression testing.

Every security regression should have a fixture that proves both reachability
and physical object cleanup.

## Distribution

Publish:

- a Python package installable with `pipx`;
- a versioned OCI image containing pinned Git and `git-filter-repo` versions;
- checksummed release archives;
- an SBOM and signed release artifacts.

Docker, BuildKit, CI, and devcontainer examples belong in an
`examples/` directory. They demonstrate how to pass a source `.git` and
consume the sanitized output, but remain outside the product's security and
runtime responsibilities.

## Milestones

### M1: Extract the prototype — implemented

- [x] Create the Python package and CLI.
- [x] Define and validate policy version 1.
- [x] Port cutoff compaction, path filtering, cleanup, and verification.
- [x] Preserve the current linear-history fail-closed behavior.
- [x] Add fixture and end-to-end tests.

### M2: Production Git graph support

- Reconstruct merge commits and shared DAG ancestry.
- Support explicit retained refs.
- Add cutoff-by-commit.
- Preserve supported metadata exactly and explicitly strip unsupported
  signatures.
- Add property-based and adversarial tests.

### M3: Release and integration

- Publish packages and the OCI image.
- Add Docker/BuildKit and CI examples.
- Produce JSON verification reports.
- Add reproducible builds, SBOMs, signing, and release automation.

### M4: Security readiness

- Document the threat model and trust boundaries.
- Test final artifacts and image layers for original objects.
- Benchmark large repositories.
- Commission an external security review.
- Stabilize the policy and report schemas for a 1.0 release.

## Initial non-goals

- Runtime sandbox creation or orchestration.
- Working-tree file masking.
- Network or process isolation.
- Secret detection based on file contents.
- Mutating or force-pushing the source repository.
- Hosting sanitized repositories.

## Open decisions

- Whether cutoff-by-commit should take precedence when both cutoff forms are
  present.
- Whether path names in reports are considered sensitive.
- Supported Git and `git-filter-repo` version ranges.
- Behavior for histories whose timestamps cross the cutoff multiple times.
- Whether the first stable release must support merges or may fail closed.
