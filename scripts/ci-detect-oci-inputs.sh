#!/usr/bin/env bash
# Print true when a revision range can affect OCI validation; never fail open.
set -euo pipefail

base="${1:-}"
head="${2:-}"

if ! git rev-parse --verify --quiet "${base}^{commit}" >/dev/null || \
  ! git rev-parse --verify --quiet "${head}^{commit}" >/dev/null; then
  printf 'true\n'
  exit 0
fi

if ! paths="$(git diff --name-only --no-renames "${base}" "${head}")"; then
  printf 'true\n'
  exit 0
fi

if [[ -z "${paths}" ]]; then
  printf 'false\n'
  exit 0
fi

while IFS= read -r path; do
  case "${path}" in
    Containerfile|Containerfile.dockerignore|container/*|requirements/container-runtime.txt|requirements/release-test.txt|scripts/bootstrap-test-git.sh|scripts/verify-container-toolchain.py|pyproject.toml|README.md|LICENSE|src/*|tests/support/*|tests/test_output_cleanup_contracts.py|.github/workflows/ci.yml|.github/workflows/release.yml)
      printf 'true\n'
      exit 0
      ;;
  esac
done <<< "${paths}"

printf 'false\n'
