## Install

```bash
pipx install git-history-sanitize=={{VERSION}}
```

## OCI image

```text
ghcr.io/f4irline/git-history-sanitize@{{IMAGE_DIGEST}}
```

Requires Python 3.11 or later, Git 2.36 or later, and `git-filter-repo` for the
PyPI installation. The OCI image bundles those runtime dependencies.

## Version correction

The immutable `v0.1.1` release incorrectly shipped package artifacts marked
`0.1.0`. This validated release corrects that discrepancy without rewriting
historical tags or artifacts.
