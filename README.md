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
reserved for samples that use this tool.

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

## Requirements

- Python 3.11 or later
- Git 2.36 or later
- `git-filter-repo` on `PATH`

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

Verification checks the cutoff, synthetic root, configured paths, retained
refs, remotes, reflogs, backup metadata, and unreachable objects. It can print
a JSON report:

```bash
git-history-sanitize verify \
  --repository build/sanitized.git \
  --policy .git-history-sanitize.yml \
  --json
```

The report intentionally contains no source-to-output mappings or removed
commit messages.
