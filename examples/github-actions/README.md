# GitHub Actions integration

This directory illustrates a settlement-reconciliation worker. Copy its source
layout and [`.git-history-sanitize.yml`](.git-history-sanitize.yml) into a real
repository, then copy [`workflow.yml`](workflow.yml) to
`.github/workflows/sanitized-history.yml`.

The trusted producer checks out full history, invokes the published digest-
pinned sanitizer image for `plan`, `rewrite`, and `verify`, and uploads only
the sanitized repository plus its policy. The consumer has no checkout step;
it receives and verifies only that artifact.

The source checkout, producer runner, Docker daemon, logs, cache, policy, and
artifact storage are within the trusted boundary. This workflow illustrates
where sanitized history fits; it does not harden those surrounding systems.
