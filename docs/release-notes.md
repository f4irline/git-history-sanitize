## Install

```bash
pipx install git-history-sanitize=={{VERSION}}
```

## OCI image

```text
ghcr.io/f4irline/git-history-sanitize@{{IMAGE_DIGEST}}
```

Requires Python 3.11 or later, Git 2.36 or later, and `git-filter-repo` for the
PyPI installation. The OCI image bundles those runtime dependencies. This
digest is the digest-first release identity; version and `latest` tags are
convenience references only.

## OCI execution

Run the image as the caller's numeric UID/GID so the writable output remains
host-owned. Keep the source Git database and policy read-only:

```bash
docker run --rm \
  --user "$(id -u):$(id -g)" \
  -v "$PWD/.git:/input.git:ro" \
  -v "$PWD/policy.yml:/policy.yml:ro" \
  -v "$PWD/build:/output" \
  ghcr.io/f4irline/git-history-sanitize@{{IMAGE_DIGEST}} \
  rewrite --source /input.git --output /output/sanitized.git --policy /policy.yml
```

## Supply-chain evidence

The GitHub Release includes wheel/source checksums and the image's GitHub build
provenance. Verify the attestation for the exact digest before use:

```bash
gh attestation verify "oci://ghcr.io/f4irline/git-history-sanitize@{{IMAGE_DIGEST}}" \
  --owner f4irline --bundle-from-oci
```

## Version correction

The immutable `v0.1.1` release incorrectly shipped package artifacts marked
`0.1.0`. This validated release corrects that discrepancy without rewriting
historical tags or artifacts.
