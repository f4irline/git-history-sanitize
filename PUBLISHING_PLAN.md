# Publishing plan

## Objective

Publish Git History Sanitize as a local-first open-source command-line product
that teams can use in a trusted build step before exposing a sanitized Git
database to another system.

The production installation path is an OCI image. A PyPI package is also
published for local developer and conventional CI usage. Neither distribution
uploads a customer's source repository, policy, or sanitized output anywhere.

## Release channels

### Primary: OCI image on GHCR

Publish the existing `Containerfile` as a public multi-platform image at:

```text
ghcr.io/f4irline/git-history-sanitize
```

Document digest-pinned use as the recommended production integration:

```bash
docker run --rm \
  -v "$PWD/.git:/input.git:ro" \
  -v "$PWD/policy.yml:/policy.yml:ro" \
  -v "$PWD/build:/output" \
  ghcr.io/f4irline/git-history-sanitize@sha256:<digest> \
  rewrite --source /input.git --output /output/sanitized.git --policy /policy.yml
```

Publish immutable semantic-version tags (`v1.0.0` and `1.0.0`) and a moving
`latest` tag. Release documentation must recommend the digest, with the version
tag offered only for convenience.

The image remains the preferred installation because it supplies the supported
Git, Python, and `git-filter-repo` runtime together.

### Secondary: PyPI CLI package

Publish the current universal Python package under the final chosen PyPI name.
Users install a pinned version with:

```bash
pipx install git-history-sanitize==<version>
```

The PyPI documentation must state that Git and `git-filter-repo` are runtime
requirements and direct users to `git-history-sanitize doctor`. Do not promise
a one-command pipx setup until the required `git filter-repo` executable is
confirmed to be discoverable in the supported pipx environments.

If that experience is not acceptable, make the dependency self-contained in a
later release before changing the installation claim. The OCI image remains the
reliable path in the meantime.

### Source releases

Attach the source distribution, wheel, checksums, and concise release notes to
every GitHub Release. This lets organizations mirror or build the tool within
their own package and registry infrastructure.

## Before the first release

1. The permanent public repository is `f4irline/git-history-sanitize`; this
   checkout's `origin` is configured for that location.
2. Confirm that the intended PyPI project name is available. If
   `git-history-sanitize` is unavailable, choose a distinctive replacement
   before making public references to it.
3. Update `pyproject.toml` with the final version, maintainer `f4irline`, and
   project URLs for `https://github.com/f4irline/git-history-sanitize` and
   `https://github.com/f4irline/git-history-sanitize/issues`.
4. Verify the package can build a source distribution and wheel with
   `python -m build`. This adds packaging output only; it does not introduce a
   new test suite.
5. Add a short installation section to the root README that leads with the
   GHCR image and separately documents the Python prerequisites.
6. Add an Apache-compatible license notice only if future dependencies require
   one. The current MIT license remains the product license.
7. Create the PyPI Trusted Publisher configuration before merging the release
   workflow. It should identify GitHub owner `f4irline`, repository
   `git-history-sanitize`, workflow `release.yml`, and the protected `pypi`
   environment.
8. Do one `v0.1.0` rehearsal through TestPyPI and GHCR before the first public
   release tag. Treat it as a release-pipeline validation, not as an additional
   product test suite.

## GitHub Actions workflows

Workflows live in `.github/workflows/`. Pin every third-party action to a full
commit SHA and give each job the smallest permissions it needs.

### `ci.yml`: existing validation on pushes and pull requests

Triggers:

- pushes to the default branch;
- pull requests targeting the default branch.

Jobs:

1. Check out the repository with full history where the prototype history test
   needs it.
2. Run the root package test command already used manually:

   ```bash
   docker buildx build --target test -f Containerfile .
   ```

3. Run the prototype history fixture already used manually:

   ```bash
   cd proto
   docker buildx build \
     --target git-history-test \
     --build-context trusted_git=../.git \
     -f .devcontainer/Dockerfile.devcontainer .
   ```

4. Build Python distribution artifacts with `python -m build` and upload them
   as a short-lived CI artifact for the release workflow or inspection.

This workflow adds no new tests. It simply automates the two container test
commands already exercised manually and confirms the distributable package can
be built.

### `release.yml`: tagged publication

Trigger only when a tag matching `v*` is pushed. The workflow must not publish
from ordinary branch pushes.

Stages:

1. **Validate**

   Re-run the same two container commands from `ci.yml`; release publication is
   blocked if either fails.

2. **Build distributions**

   Build the wheel and source distribution once, calculate SHA-256 checksums,
   and upload the artifacts between jobs without rebuilding them.

3. **Publish PyPI**

   Download the verified artifacts and publish them through PyPI Trusted
   Publishing. Configure this job with:

   ```yaml
   environment: pypi
   permissions:
     id-token: write
   ```

   No PyPI API token is stored in GitHub.

4. **Build and publish the image**

   Build the root `Containerfile` for `linux/amd64` and `linux/arm64`, push it
   to GHCR, and apply the immutable version tags plus `latest`. Configure this
   job with:

   ```yaml
   permissions:
     contents: read
     packages: write
     attestations: write
     id-token: write
   ```

   Generate build provenance for the published image and preserve its returned
   digest in the release notes.

5. **Create GitHub Release**

   Create a release for the tag, attach the wheel, source distribution, and
   checksum file, and include:

   - the package version;
   - the image name and immutable digest;
   - the minimum Git and Python requirements;
   - the exact PyPI and OCI installation commands;
   - a concise list of user-visible changes.

The release workflow needs `contents: write` only in the GitHub Release job;
do not grant it to validation, PyPI, or image jobs.

### `testpypi.yml`: manual rehearsal

Use a manually dispatched workflow to build the distribution and publish it to
TestPyPI using a separate `testpypi` environment and Trusted Publisher
configuration. It follows the same validation and build steps as `release.yml`
but never creates a GitHub Release, pushes a container tag, or publishes to
production PyPI.

## Versioning and release operation

Use semantic versioning:

- `0.x` while the policy format and supported repository structures are still
  evolving;
- `1.0.0` when the policy schema, CLI commands, output contract, and failure
  behavior are ready to be treated as stable;
- a new major version for incompatible policy or output changes.

The policy's own `version` field remains the compatibility mechanism for policy
files. A release must not silently reinterpret an older policy version.

Release procedure:

1. Update the package version and release notes.
2. Run the same root and prototype container builds locally if desired.
3. Merge the release preparation change.
4. Create and push the signed `v<version>` tag.
5. Watch `release.yml`; verify the PyPI version, the GHCR digest, and the
   GitHub Release assets.
6. Install the PyPI package and run the digest-pinned image once against a
   disposable fixture before announcing the release.

## Consumer documentation

The README should have a short "Choose an installation" section:

| Situation | Recommended route |
| --- | --- |
| CI, Docker, devcontainer, or sandbox integration | Digest-pinned GHCR image |
| Developer workstation with supported prerequisites | Pinned PyPI package |
| Air-gapped or internally mirrored environment | Source distribution or mirrored OCI image |

Every integration guide should use this flow:

```text
trusted source Git + checked-in policy
                 |
                 v
       plan / rewrite / verify
                 |
                 v
      sanitized bare Git output only
                 |
                 v
       sandbox or other consumer
```

State plainly that the original repository and its build runner are part of the
trusted boundary. Git History Sanitize produces and verifies a restricted Git
database; it does not isolate a runner, container daemon, network, credentials,
logs, cache, or artifact store.

## Operator prerequisites

Before implementation, provide or create:

1. **GitHub ownership — resolved**: the public repository and this checkout's
   `origin` are `f4irline/git-history-sanitize`.
2. **PyPI ownership — outstanding**: create or identify a verified PyPI account
   for `f4irline`, confirm the final intended project name, and create a
   TestPyPI account for rehearsal releases.
3. **GitHub environments — outstanding**: create `pypi` and `testpypi`.
   Configure `pypi` so only `f4irline` can approve a tagged production release.
4. **GHCR decision — resolved**: publish a public image at
   `ghcr.io/f4irline/git-history-sanitize`. No separate registry account is
   needed because GHCR uses the GitHub owner and workflow token.
5. **Maintainer information — resolved**: use `f4irline` in package metadata
   and `https://github.com/f4irline/git-history-sanitize/issues` as the issue
   tracker.
6. **Release authority — resolved**: restrict version-tag pushes and production
   environment approvals to `f4irline`.

No long-lived publishing credentials need to be supplied to GitHub when using
PyPI Trusted Publishing and GHCR's workflow token. Do not place a PyPI token,
registry password, or customer policy in repository secrets.

## Done criteria

Publishing is complete when a tag produces all of the following without manual
artifact upload:

- a passing CI run using the existing root and prototype container commands;
- a wheel and source distribution on PyPI;
- a multi-platform GHCR image with a documented digest;
- a GitHub Release containing checksums and the Python artifacts;
- provenance attached to the published image;
- copy-paste installation instructions verified against the released artifacts.
