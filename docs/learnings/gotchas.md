# Gotchas

Things that might bite you. Check here before you get bitten.

---

## Pass the target platform to nested OCI fixture commands
**Ticket:** BBQ-21
**Date:** 2026-09-16

The platform matrix builds an arm64 image on an amd64 runner. Every nested
`docker run` issued by `GitFixture` must receive the matching `--platform`; if
it does not, Docker emits an architecture warning on stderr and breaks the
CLI's strict stderr contracts. Thread `GHS_OCI_PLATFORM` from CI into the
fixture command rather than weakening those contracts.

---

## Dependabot only discovers literal Docker FROM references
**Ticket:** BBQ-21
**Date:** 2026-09-16

Dependabot's Docker parser does not resolve an image stored in `ARG`. Keep the
immutable digest literal on each `FROM` line and contract-test that both stages
match `container/toolchain.lock.json`; otherwise the scheduled Docker update
entry silently creates no base-image pull request.

---

## A scheduled refresh cannot safely synthesize a reviewed OCI lock
**Ticket:** BBQ-21
**Date:** 2026-09-16

`container/toolchain.lock.json` records a digest, immutable snapshot, and exact
per-architecture package versions. A scheduled workflow must consume an
approved authoritative update source or a dedicated lock generator; it must not
invent a current snapshot, mutable base tag, or package set just to create a
pull request. Keep the refresh path reviewable and limited to declared lock
inputs.

---

## Bootstrap the CA bundle from the signed snapshot before normal TLS checks
**Ticket:** BBQ-21
**Date:** 2026-09-16

The pinned Ubuntu base cannot validate the current snapshot certificate while
fetching the newer `ca-certificates` package. Point APT at the immutable
snapshot first, temporarily disable TLS peer validation only for the pinned CA
bundle transaction, then restore normal TLS verification. APT repository
signature and package checksum verification remain enabled throughout; do not
fall back to a mutable Ubuntu index.

---

## Initialize an index before snapshotting an empty Git fixture
**Ticket:** BBQ-12
**Date:** 2026-09-14

`GitFixture.snapshot_source()` records `.git/index`, but a freshly initialized
empty repository has no index yet. For empty-source immutability contracts, run
`fixture.git(fixture.source, "read-tree", "--empty")` before taking the
snapshot; this creates the index without creating a commit or changing the
empty-source precondition.

---

## Detect bare repositories independently of the Git directory
**Ticket:** BBQ-6
**Date:** 2026-09-14

`git rev-parse --absolute-git-dir` succeeds for a bare repository, so it cannot
distinguish a bare repository from a normal repository passed as its `.git`
directory. Query `rev-parse --is-bare-repository` before deriving a worktree
root; otherwise a bare repository can treat its parent as a worktree and allow
an external `core.hooksPath` through containment checks.

---

## Stage leading-dash fixture paths explicitly
**Ticket:** BBQ-14
**Date:** 2026-09-12

`GitFixture.commit()` passes paths directly to `git add`; use
`fixture.git(fixture.source, "add", "--", *paths)` before committing fixtures
that include a leading-dash filename. This preserves the intended path test
instead of letting Git parse the filename as an option.

---

## PyPI publish directories must contain only distributions
**Ticket:** BBQ-15
**Date:** 2026-09-07

`pypa/gh-action-pypi-publish` runs metadata validation over every file in its
`packages-dir`. Keep `SHA256SUMS` and version manifests outside the directory
that contains the validated wheel and sdist, or the release fails before
publication on an unknown distribution format.

---

## GnuPG key retrieval can select an unroutable IPv6 keyserver address
**Ticket:** BBQ-5
**Date:** 2026-09-07

On this macOS runner, `keyserver.ubuntu.com` resolves to IPv6 and IPv4, but
the GnuPG dirmngr key retrieval fails with `No route to host` when it selects
IPv6. HTTPS and GitHub remain reachable over IPv4. A temporary
`dirmngr.conf` containing `disable-ipv6` makes the same fingerprint-pinned
key import succeed; use it only for the ephemeral bootstrap GnuPG home.

---

## Pinned filter-repo does not complete SHA-256 path filtering
**Ticket:** BBQ-8
**Date:** 2026-09-07

Pinned Git 2.47.0 can initialize SHA-256 fixtures, but the pinned
`git-filter-repo` 2.47.0 fails during path filtering with a fast-import crash.
Keep SHA-256 as an explicit compatibility gap; do not add a required CI matrix
cell until the pinned runtime can sanitize the fixture successfully.

---

## Strict in-process stderr contracts expose unclosed policy files
**Ticket:** BBQ-44
**Date:** 2026-09-06

`Policy.from_file` previously used `open(...).read()` without deterministically
closing the stream. In-process CLI failure injection caused the resulting
`ResourceWarning` to contaminate stderr and violate the exact diagnostic
contract. Use a context manager for policy reads; keep successful CLI stderr
strictly empty rather than filtering warnings in the harness.

---

## Writable OCI output mounts must not alias fixture inputs
**Ticket:** BBQ-44
**Date:** 2026-09-06

Mounting a fixture root read-write for outputs also makes source repositories,
policies, and Git configuration writable through alternate `/output/...`
paths, even when their canonical mounts are read-only. Keep every generated
output under a dedicated `fixture.output_dir` and mount only that directory
read-write.

---

## Apple xcrun can warn only inside the Codex Seatbelt sandbox
**Ticket:** BBQ-44
**Date:** 2026-09-06

On macOS, `xcrun` emitted `confstr() failed ... DARWIN_USER_TEMP_DIR` only under
the restricted Codex/Seatbelt execution sandbox. Setting `TMPDIR`, `TMP`,
`TEMP`, and `TEMPDIR` to fixture-owned directories did not suppress it, while
the unrestricted source contract suite passed 28/28 with empty stderr. Treat
this as runner-sandbox evidence; do not weaken product stderr assertions.

---

## Clone trust must survive the upload-pack child
**Ticket:** BBQ-44
**Date:** 2026-09-06

Put the container input exception (`/input.git`) in the read-only global Git
config: local clone transport drops command-scope configuration before
upload-pack. Source and wheel fixtures keep an empty global config.
Keep `--no-local` and never trust `*`. The earlier `/input`, `/input/.git`, and
`/output/*` exceptions belonged to the superseded worktree/root-runner setup,
not the current metadata-only mount and caller-owned outputs.

---

## Colima can retain a stale config inode after host Git updates
**Ticket:** BBQ-44
**Date:** 2026-09-06

Host `git remote add` and `git branch -D` replace repository config files.
Colima virtiofs can then expose the deleted inode to a subsequent container,
causing config reads to fail with ENOENT despite a valid host file. Tamper
remote config in place and delete refs with `update-ref -d`; keep verification
mounts read-only. This preserves the tested invalid state without changing
the sanitizer or container isolation.

---

## OCI fixture outputs must belong to the host test runner
**Ticket:** BBQ-44
**Date:** 2026-09-06

Run fixture containers with the caller's numeric UID:GID. Root-owned outputs on
Linux prevent host-side tampering and TemporaryDirectory cleanup; Colima's
ownership mapping can conceal this locally. Do not broaden permissions or
ignore cleanup failures to work around ownership.

---

## Separate mount layout from Git ownership failures
**Ticket:** BBQ-44
**Date:** 2026-09-05

The initial conclusion that Git 2.47 required a whole-worktree mount was
incorrect: ownership and trust failures obscured the actual cause. A read-only
`.git` directory mounted at `/input.git` works with the narrow input trust
exception and caller UID:GID. It avoids exposing the worktree and removes
special-case path translation. Test native Linux ownership separately from
Colima's mount behavior before adding mount-layout workarounds.

---

## Verify git-filter-repo fingerprints from the pinned source
**Ticket:** BBQ-44
**Date:** 2026-09-05

Do not assume the planned git-filter-repo fingerprint matches a package label or
source tag. The pinned upstream source in BBQ-44 emits `a40bce548d2c`; this
corrects the approved pin from `bc98e38e057b`. Keep the checker fail-closed on
any output other than the verified fingerprint.

---
