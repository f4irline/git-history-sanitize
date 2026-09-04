# Docker BuildKit integration

This directory illustrates an order-webhook API. Its `src/`, `config/`,
`package.json`, and policy are laid out as they would be in the API repository;
this example does not attempt to build or run that API.

[`build.sh`](build.sh) accepts an existing repository's `.git` directory and an
unused output location:

```bash
./build.sh /path/to/order-webhook-api/.git /path/to/build/sanitized.git
```

The Containerfile runs the published OCI image pinned to
`sha256:3ff42939fc1c3199193d9492dff0c80d53db1d073fa75a691ff293371a720ebd`.
The ordinary context excludes `.git`; BuildKit mounts the named `trusted_git`
context read-only and exports only the verified bare repository. Rebuild after
a source commit or policy change.

The BuildKit daemon, source database, policy, and build cache are trusted.
Only the exported repository is intended to leave that boundary.
