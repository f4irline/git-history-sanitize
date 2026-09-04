# Devcontainer integration

This is a support-case API in the same Node/Express and Kubernetes shape as
[`proto/`](../../proto/), but it is self-contained and has no prototype
sanitizer. Its `src/`, `infra/`, package metadata, and policy are illustrative
source material, not an application this example tries to build or test.

Copy this project layout and its `.devcontainer/` integration into a real
repository. With `WORKSPACE` set to the project working tree and `TRUSTED_GIT` set to that
repository's `.git` directory, start the service:

```bash
WORKSPACE="$PWD" TRUSTED_GIT="$PWD/.git" \
  docker compose --project-directory . \
  -f .devcontainer/docker-compose.yml up --build
```

The trusted build stage uses the published digest-pinned sanitizer image. At
runtime, Compose masks `/workspace/.git`; the entrypoint installs the verified
sanitized database there. Compose mounts and network settings—not Git History
Sanitize—provide the remaining runtime isolation.
