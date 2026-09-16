# Git History Sanitize

Git History Sanitize creates a new, standalone Git database from an existing
repository according to a declarative policy. It is a history-rewriting and
verification tool, not a container or runtime sandbox.

It never mutates the source repository. Rewrites happen in a disposable clone,
the completed bare repository is independently verified, and it is atomically
moved to the requested output path only after verification succeeds.

### Output publication and durability

`rewrite` never replaces an existing output entry. The successful native
no-replace rename is the output publication point: before it, no output is
visible; after it, the output is the fully verified bare repository. Existing
files, symlinks (including dangling symlinks), and directories are rejected and
are never replaced implicitly. Concurrent rewrites targeting the same output
therefore have one winner; every other writer fails without modifying the
winner.

The staging directory and published repository root use mode `0700`; generated
receipts use mode `0600`, independently of the caller's umask. The staged
repository is synchronized before publication. After a successful rename, the
tool synchronizes its parent directory where the platform/filesystem supports
directory synchronization. If that post-publication persistence step fails, the
command returns an error stating that the complete output is already published;
it does not attempt an unsafe rollback. Where directory synchronization is not
supported, the tool guarantees atomic visibility but does not claim a
power-loss-durable directory entry.

For `cutoffCommit`, the private receipt is published before the repository so a
published repository is never exposed without its required evidence. The two
paths are separate filesystem entries and cannot be one transaction: a receipt
may remain as a private orphan if repository publication subsequently fails. A
receipt-parent persistence failure is reported as receipt-only publication; it
never claims that the repository output was published.

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
the supported Git, Python, and `git-filter-repo` runtime. Use the published
digest as the digest-first release identity rather than a mutable tag. Run with
the caller's numeric UID and GID so the writable output remains host-owned;
source and policy mounts remain read-only:

```bash
docker run --rm \
  --user "$(id -u):$(id -g)" \
  -v "$PWD/.git:/input.git:ro" \
  -v "$PWD/policy.yml:/policy.yml:ro" \
  -v "$PWD/build:/output" \
  ghcr.io/f4irline/git-history-sanitize@sha256:<published-digest> \
  rewrite --source /input.git --output /output/sanitized.git --policy /policy.yml
```

Verify the published digest's GitHub build provenance before using it in a
trusted build step:

```bash
gh attestation verify "oci://ghcr.io/f4irline/git-history-sanitize@sha256:<published-digest>" \
  --owner f4irline --bundle-from-oci
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
scripts/prepare-release.sh 0.1.2
scripts/prepare-release.sh 0.1.2 --push
```

The helper creates an isolated temporary environment with the reviewed release
tooling. The default command creates only a local version commit and annotated
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
PATH="$PWD/.venv-source/bin:$PATH" env -u PYTHONPATH .venv-source/bin/python -m unittest -v tests.test_git_fixture tests.test_toolchain tests.test_policy tests.test_forbidden_content tests.test_cli_contracts
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

source:
  mode: complete

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

### Excluded paths

Each `paths.exclude` entry is a canonical, repository-relative POSIX path. An
exact-file rule has no trailing slash (`secret.json`); a directory rule ends in
one slash (`infra/`) and removes every descendant. These two forms remain
distinct, so `name` and `name/` may both be configured.

Entries must be non-empty and UTF-8 encodable, use only `/` separators, and
contain non-empty segments other than `.` and `..`. Spaces, Unicode,
dot-prefixed names, and leading dashes are valid. The parser rejects absolute
paths, backslashes, NUL bytes, current-directory and parent-traversal forms,
duplicate separators, repeated trailing slashes, duplicate rules, and a rule
that is already covered by a configured directory. Errors identify only the
escaped policy entry and its reason; they never inspect repository contents.

`plan` reports its ordered `excluded_paths` value in JSON and its exclusions in
human output. It also reports `retained_head_path_count` in JSON and `Retained
HEAD paths` in human output: this is the number of paths in the source `HEAD`
tree that remain after applying the validated exclusions. A value of `0` is a
valid non-empty-source result; it does not describe historical content outside
the source `HEAD` tree. The same validated tuple is used for planning,
filtering, and verification.

### Trusted hooks

`plan` and `rewrite` preserve active, non-`*.sample` hooks from the source
repository by default. Hooks are trusted executable metadata outside history
path filtering: consumers of the sanitized repository may read or execute
them. Sanitization never executes hooks and does not install a hook runtime or
pre-commit environment. Pass `--strip-hooks` to either command to inspect or
create output without carrying source hooks forward; reports identify the
preserved or stripped names and portability-warning categories, never contents
or source paths.

Only regular, non-symlinked hooks from the standard hooks directory or a
repository-local `core.hooksPath` contained by the source worktree or Git
directory are eligible. A supported custom location is copied to the output
Git directory's `hooks` directory and activated there with output-local
`core.hooksPath=hooks`. This activation applies to the produced bare repository;
ordinary downstream clones do not inherit it. Hooks containing an absolute
shebang or path receive a deterministic portability warning because the
sanitizer cannot recreate source-machine dependencies.

Every internal clone uses a private empty Git template directory, so hooks from
the sanitizer runner's templates cannot enter the output.

### Source scope

`source.mode` defaults to `complete`. Complete mode proves the local object
closure for every source ref and rejects shallow, partial/promisor, graft,
replacement, and alternate-object state before output staging. Fetch complete
history, explicitly materialize required objects, remove graft/replace state,
or repack without alternates before retrying.

`plan` runs the same deterministic source, reference, graph, and cutoff
preflight that rewrite runs before staging output, then reports the same `HEAD`
graph that rewrite compacts. It neither mutates the source nor creates output.
Its source, boundary, and `retained_head_path_count` values are known
pre-filter facts; path filtering can still prune commits, so plan does not
predict the final sanitized history shape. In complete mode, the all-ref
closure check is preflight evidence only: side refs cannot inflate the reported
source or included counts.

`bounded` is an explicit shallow-clone mode. It only covers the local `HEAD`
graph up to its declared shallow roots; it never fetches or claims coverage of
older history. Every object inside that graph must already be local. The output
is made complete after the bounded graph is compacted, while its published
scope metadata retains the bounded coverage statement.

`snapshot` creates one parentless synthetic commit from the current `HEAD`
tree. It requires an explicit `history.prefixMessage`, accepts neither cutoff
field nor receipt, and does not inspect or include inherited commits. It may be
used with shallow or partial sources only when the complete `HEAD` tree closure
is already local. All modes reject grafts, replace refs, and alternates and set
Git's no-lazy-fetch protection for every Git command.

## Usage

```bash
git-history-sanitize doctor

git-history-sanitize plan \
  --source .git \
  --policy .git-history-sanitize.yml \
  --strip-hooks # optional: omit to preserve trusted hooks

git-history-sanitize rewrite \
  --source .git \
  --output build/sanitized.git \
  --policy .git-history-sanitize.yml

git-history-sanitize verify \
  --repository build/sanitized.git \
  --policy .git-history-sanitize.yml \
  --forbid 'private marker' \
  --forbid-file /private/forbidden-records \
  --forbid-stdin < /private/more-forbidden-records
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
Sensitive-only commits are pruned when they become empty. If filtering removes
every retained path from a non-empty source, the result remains a valid,
one-commit bare repository: the synthetic root keeps its configured message
and deterministic boundary metadata, points at Git's canonical empty tree, and
retains its symbolic branch `HEAD`. This is distinct from an empty source,
which remains invalid.

The first release supports a single linear retained branch. Merge histories,
non-monotonic cutoff timestamps, and unsupported refs fail closed instead of
producing an ambiguous rewrite.

## Container image

Build the OCI image:

```bash
docker buildx build --load -t git-history-sanitize:local -f Containerfile .
```

Use it with the caller UID/GID, read-only Git and policy inputs, and a writable
output directory:

```bash
docker run --rm \
  --user "$(id -u):$(id -g)" \
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
metadata, and no unreachable objects. `--forbid`, `--forbid-file`, and
`--forbid-stdin` additionally scan object bodies and active eligible hooks,
including an output-local custom `core.hooksPath`; inactive `*.sample` hooks are
ignored. `--forbid` accepts strict UTF-8 text; files and stdin are raw
newline-delimited byte records. Inputs are limited to 64 KiB per record and
1 MiB in aggregate. Object and hook bodies are streamed in 64 KiB chunks, and
patterns never match across object or hook-file boundaries.

Each contract failure uses a stable, redacted invariant identifier:
`graph.linear`, `root.synthetic`, `head.symbolic`, `refs.retained`,
`paths.excluded`, `remotes.absent`, `repository.complete`, `metadata.clean`,
`objects.reachable-only`, or `content.forbidden`. Human output names only that
identifier.

## Reporting privacy and JSON schema v2

`doctor`, `plan`, `rewrite`, and `verify` write deterministic, compact,
ASCII-safe reports. The default human and JSON reports are safe for shared logs
and CI artifacts: they use only fixed protocol metadata and aggregate operation
data. JSON writes one document plus one newline to stdout, nothing to stderr,
and exits `0` on success or `2` on failure.

| Classification | Default public report | `--diagnostics=trusted` local report | Never emitted |
| --- | --- | --- | --- |
| Fixed protocol/status | schema version, audience, command, status, fixed catalog metadata, invariant, publication state | same | — |
| Aggregate operation data | mode, scope, commit/path/object/boundary counts, hook action/count, dependency availability/version | same | — |
| Repository/policy identity | — | excluded paths, retained refs, sanitized head/root IDs, hook names/warning associations | receipt bindings, source ref fingerprints, policy digests |
| Sensitive values | — | — | forbidden values or matches, removed messages, object/hook bodies, raw policy values, credentials, raw subprocess stderr, command arguments |

Public v2 success envelopes have a stable `(schema_version, report_audience)`
contract:

```json
{"command":"plan","report_audience":"public","result":{},"schema_version":2,"status":"success"}
```

Every v2 error envelope also carries `report_audience`. It contains only the
fixed error catalog (`code`, `stage`, `message`, optional fixed `remediation`),
errors use the same catalog and optional invariant rather than exception text.
The renderer never serializes an exception message, filesystem path, source or
output object ID, receipt data, subprocess stderr, command arguments, removed
content, or credentials by default.

Trusted diagnostics are an exact, explicit local opt-in for `plan`, `rewrite`,
and `verify`:

```bash
git-history-sanitize verify \
  --repository build/sanitized.git \
  --policy .git-history-sanitize.yml \
  --json --diagnostics=trusted
```

Trusted v2 uses `"report_audience":"trusted"` and puts identity-bearing
values only in a top-level `diagnostics` object. It is for local investigation:
never redirect it to CI logs, artifacts, release notes, progress updates, or
`$GITHUB_OUTPUT`. It never changes the sanitized Git database, scope metadata,
or private receipt, and it still excludes every never-emitted value in the
table. Trusted human output presents that same identity set with fixed labels
and deterministic ordering.

`--json` defaults to public v2. JSON v1 remains a temporary migration path for
`plan`, `rewrite`, and `verify` only, and can be selected only with all three
flags: `--json --diagnostics=trusted --json-schema=1`. This makes legacy
identity-bearing output a deliberate local choice rather than a silent shared
default. Migrate consumers to public v2 aggregate fields; v1 will be removed
only in a future major contract change. Within a documented
`(schema_version, report_audience)` pair, fields are additive-only; changing a
field's type or meaning requires a new version and migration note.

Report tuples are ordered JSON arrays, unavailable optional values are omitted,
and object keys are sorted deterministically. Valid UTF-8 text is retained;
surrogateescaped bytes become literal `\\xHH` text after literal backslashes
are doubled, keeping both cases unambiguous.

Successful verification can print a public JSON report:

```bash
git-history-sanitize verify \
  --repository build/sanitized.git \
  --policy .git-history-sanitize.yml \
  --json
```

Public output intentionally contains no source-to-output mappings, paths,
refs, object IDs, hook names, or removed commit messages.

New outputs include canonical `git-history-sanitize-scope.json` at the bare
repository root. It contains only the mode, non-sensitive coverage wording,
boundary count, and included commit/object counts; verification rejects missing
or tampered scope metadata, except for legacy complete-mode artifacts. A
timestamp-cutoff complete artifact without this newer metadata remains
verifiable; its report uses zero scope counts to explicitly mean that legacy
source-scope evidence is unavailable. Missing metadata remains a hard failure
for bounded and snapshot outputs and for complete `cutoffCommit` outputs with a
v2 receipt.

For `cutoffCommit`, Receipt v2 is private trusted evidence. It binds the exact
raw policy bytes, source object format, source HEAD and complete ref map,
boundary commit/tree, mode, private scope fingerprint, and sanitized root/HEAD.
Receipt v1 remains verification-only compatibility for legacy complete-mode
artifacts; it cannot prove bounded or snapshot output. A receipt contains source identifiers,
so keep it owner-readable only and do not publish it with the sanitized Git
database. The receipt digest detects corruption but is not a signature; trusted
distribution or signing/key management is outside this tool's scope. A
sanitized output without its private receipt and original source is not
cutoff-proven, and verification fails closed.
