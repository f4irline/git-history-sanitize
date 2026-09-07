# Git History Sanitize

Git History Sanitize creates a new, standalone Git database from an existing
repository according to a declarative policy. It is a history-rewriting and
verification tool, not a container or runtime sandbox.

It never mutates the source repository. Rewrites happen in a disposable clone,
the completed bare repository is independently verified, and it is atomically
moved to the requested output path only after verification succeeds.

The original sandbox-specific prototype is preserved in
[`proto/`](proto/). It demonstrates one possible consumer of a sanitized Git
database, but is not part of this tool. The separate `examples/` namespace is
for runnable samples that use published Git History Sanitize artifacts. Start
with the [`examples/` index](examples/README.md) for CLI, BuildKit, GitHub
Actions, and proto-style devcontainer integrations.

## Choose an installation

| Situation | Recommended route |
| --- | --- |
| CI, Docker, devcontainer, or sandbox integration | Digest-pinned GHCR image |
| Developer workstation with supported prerequisites | Pinned PyPI package |
| Air-gapped or internally mirrored environment | Source distribution or mirrored OCI image |

### Production OCI image

The public image is the recommended production installation because it bundles
the supported Git, Python, and `git-filter-repo` runtime. Pin the published
digest rather than a mutable tag:

```bash
docker run --rm \
  -v "$PWD/.git:/input.git:ro" \
  -v "$PWD/policy.yml:/policy.yml:ro" \
  -v "$PWD/build:/output" \
  ghcr.io/f4irline/git-history-sanitize@sha256:<published-digest> \
  rewrite --source /input.git --output /output/sanitized.git --policy /policy.yml
```

### PyPI command-line package

Install a pinned release with `pipx`:

```bash
pipx install git-history-sanitize==<version>
git-history-sanitize doctor
```

The PyPI package requires Git 2.36 or later and `git-filter-repo` on `PATH`.
Use `doctor` to confirm the installed tools before processing a repository. The
OCI image is the supported alternative when supplying those prerequisites on a
workstation or runner is inconvenient.

## Releases

`src/git_history_sanitize/_version.py` is the only package-version source.
Maintainers prepare stable releases locally with Python 3.11+, Git, and the
reviewed build closure:

```bash
python3 -m pip install --requirement requirements/release-test.txt --editable .
python3 scripts/release.py prepare 0.1.2
python3 scripts/release.py prepare 0.1.2 --push
```

The default command creates only a local version commit and annotated
`v0.1.2` tag after source, artifact, and focused-test checks pass. `--push` is
an explicit opt-in and runs only after that gate and tag succeed. It never
publishes registries. Release tags accept stable strict SemVer only; prerelease
tags are deliberately rejected so they cannot move `latest`.

## Requirements

- Python 3.11 or later
- Git 2.36 or later
- `git-filter-repo` on `PATH`

## Contract-Test Toolchain

The supported contract-test toolchain is Git `2.47.0`, built from signed
upstream tag `v2.47.0` at commit
`777489f9e09c8d0dd6b12f9d90de6376330577a2`, and upstream
`git-filter-repo` `2.47.0`, at commit
`6f79afc8c90c592a3052e6cc53c2ca8907515bca`. The latter reports the
upstream-defined source-content fingerprint `a40bce548d2c` from
`git filter-repo --version`; this fingerprint, rather than package metadata,
is the required check. This corrects the approved pin after verification against
the pinned upstream source; the checker remains fail-closed on any other output.

Source and wheel contract tests require build prerequisites for Git, Python
with `venv`, `git-filter-repo==2.47.0`, and the exact-pinned
`requirements/release-test.txt` closure. OCI tests also
require Docker Buildx. Bootstrap the private Git prefix before every host test
mode; this prevents test runs from falling back to the system Git:

```bash
scripts/bootstrap-test-git.sh "$PWD/.toolchain/git-2.47.0"
export PATH="$PWD/.toolchain/git-2.47.0/bin:$PATH"
```

Run the source-only fixture/toolchain helpers, then the fixture-backed runtime
contracts without `PYTHONPATH`:

```bash
python3 -m venv .venv-source
.venv-source/bin/python -m pip install --no-deps -e . git-filter-repo==2.47.0
PATH="$PWD/.venv-source/bin:$PATH" env -u PYTHONPATH .venv-source/bin/python -m unittest -v tests.test_git_fixture tests.test_toolchain tests.test_policy
PATH="$PWD/.venv-source/bin:$PATH" env -u PYTHONPATH .venv-source/bin/python tests/support/toolchain.py
PATH="$PWD/.venv-source/bin:$PATH" env -u PYTHONPATH GHS_TEST_RUNTIME=source tests/support/run_runtime_contracts.sh .venv-source/bin/python
```

Build and run the wheel mode without `PYTHONPATH`:

```bash
python3 -m pip install build==1.3.0
python3 -m build
python3 -m venv .venv-wheel
.venv-wheel/bin/python -m pip install --no-deps dist/*.whl git-filter-repo==2.47.0
PATH="$PWD/.venv-wheel/bin:$PATH" env -u PYTHONPATH .venv-wheel/bin/python tests/support/toolchain.py
PATH="$PWD/.venv-source/bin:$PATH" env -u PYTHONPATH GHS_TEST_RUNTIME=wheel GHS_WHEEL="$(realpath dist/*.whl)" tests/support/run_runtime_contracts.sh .venv-source/bin/python
```

OCI coverage is opt-in locally and mandatory in CI:

```bash
docker buildx build --load -t git-history-sanitize:local -f Containerfile .
docker run --rm --entrypoint python3 -v "$PWD/tests/support/toolchain.py:/toolchain.py:ro" git-history-sanitize:local /toolchain.py
PATH="$PWD/.venv-source/bin:$PATH" env -u PYTHONPATH GHS_TEST_RUNTIME=container GHS_CONTAINER_IMAGE=git-history-sanitize:local tests/support/run_runtime_contracts.sh .venv-source/bin/python
```

Fixtures use safe markers for sensitive values. Failure diagnostics and test
assertions must not print source secrets or host-only fixture paths.

For development from a checkout:

```bash
pipx install .
```

## Policy

```yaml
version: 1

history:
  cutoff: "2026-09-03T00:00:00+03:00"
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

The policy parser intentionally accepts a restricted, security-auditable YAML
subset: mappings, indented mappings, scalar values, and `-` lists. Strings may
be quoted. Timestamps must be RFC 3339 values with explicit timezones.

Use either `history.cutoff` or `history.cutoffCommit`. A cutoff timestamp is
compared with committer timestamps; the cutoff commit itself is retained.
`cutoffCommit` must be a lowercase, full storage-format commit OID reachable
from source HEAD; abbreviations, refs, expressions, and uppercase values fail.

## Usage

```bash
git-history-sanitize doctor

git-history-sanitize plan \
  --source .git \
  --policy .git-history-sanitize.yml

git-history-sanitize rewrite \
  --source .git \
  --output build/sanitized.git \
  --policy .git-history-sanitize.yml

git-history-sanitize verify \
  --repository build/sanitized.git \
  --policy .git-history-sanitize.yml
```

The commands above are timestamp-cutoff commands. A commit cutoff requires a
private receipt outside both the source and output trees, then verification
against the original source and exact original policy bytes:

```bash
git-history-sanitize rewrite --source /trusted/source/.git \
  --output /artifacts/sanitized.git --receipt /private/receipts/sanitized.json \
  --policy /trusted/policy.yml
git-history-sanitize verify --repository /artifacts/sanitized.git \
  --source /trusted/source/.git --receipt /private/receipts/sanitized.json \
  --policy /trusted/policy.yml
```

`rewrite` always creates a parentless synthetic root with the configured
prefix message. It retains the tree at the first allowed commit, removes
pre-cutoff commits, then filters sensitive paths from the shortened history.
Mixed commits retain allowed file changes but have their messages replaced.
Sensitive-only commits are pruned when they become empty.

The first release supports a single linear retained branch. Merge histories,
non-monotonic cutoff timestamps, and unsupported refs fail closed instead of
producing an ambiguous rewrite.

## Container image

Build the OCI image:

```bash
docker buildx build --load -t git-history-sanitize:local -f Containerfile .
```

Use it with a read-only Git input and writable output directory:

```bash
docker run --rm \
  -v "$PWD/.git:/input.git:ro" \
  -v "$PWD/.git-history-sanitize.yml:/policy.yml:ro" \
  -v "$PWD/build:/output" \
  git-history-sanitize:local rewrite \
    --source /input.git \
    --output /output/sanitized.git \
    --policy /policy.yml
```

Run the isolated package tests with:

```bash
docker buildx build --target test -f Containerfile .
```

## Verification

Verification independently inspects the completed output repository. The v1
artifact contract requires a linear retained `HEAD` graph, a parentless
synthetic root with the configured prefix message and cutoff eligibility, one
symbolic `refs/heads/*` ref, no excluded path in any retained tree, no remotes,
no shallow/partial/promisor/alternate object state, no reflogs or backup
metadata, and no unreachable objects. `--forbid` additionally scans the full
object database.

Each contract failure uses a stable, redacted invariant identifier:
`graph.linear`, `root.synthetic`, `head.symbolic`, `refs.retained`,
`paths.excluded`, `remotes.absent`, `repository.complete`, `metadata.clean`,
`objects.reachable-only`, or `content.forbidden`. Human output names only that
identifier. With `--json`, a contract failure writes exactly
`{"code": "verification_failed", "invariant": "<identifier>"}` to stderr,
leaves stdout empty, and exits 2. It never includes paths, object IDs, commit
messages, Git command output, or object contents.

Successful verification can print a JSON report:

```bash
git-history-sanitize verify \
  --repository build/sanitized.git \
  --policy .git-history-sanitize.yml \
  --json
```

The report intentionally contains no source-to-output mappings or removed
commit messages.

For `cutoffCommit`, Receipt v1 is private trusted evidence. It binds the exact
raw policy bytes, source object format, source HEAD and complete ref map,
boundary commit/tree, and sanitized root/HEAD. It contains source identifiers,
so keep it owner-readable only and do not publish it with the sanitized Git
database. The receipt digest detects corruption but is not a signature; trusted
distribution or signing/key management is outside this tool's scope. A
sanitized output without its private receipt and original source is not
cutoff-proven, and verification fails closed.
