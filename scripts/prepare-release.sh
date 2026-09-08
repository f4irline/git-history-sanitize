#!/usr/bin/env bash
# Prepare a validated release commit and annotated tag without host dependencies.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/prepare-release.sh VERSION [--push]

Creates a temporary virtual environment, installs the reviewed release tooling,
and runs the fail-closed release preparation command. By default it creates a
local version commit and annotated tag only. Pass --push to push them after all
validation succeeds.
EOF
}

if [[ $# -lt 1 || $# -gt 2 || ${1:-} == "--help" || ${1:-} == "-h" ]]; then
  usage
  [[ ${1:-} == "--help" || ${1:-} == "-h" ]] && exit 0
  exit 2
fi

version=$1
push=${2:-}
if [[ -n "$push" && "$push" != "--push" ]]; then
  usage >&2
  exit 2
fi

root=$(git rev-parse --show-toplevel)
cd "$root"
environment=$(mktemp -d "${TMPDIR:-/tmp}/git-history-sanitize-release.XXXXXX")
trap 'rm -rf "$environment"' EXIT

python3 -m venv "$environment"
"$environment/bin/python" -m pip install --quiet \
  --requirement requirements/release-test.txt --editable . git-filter-repo==2.47.0

arguments=(scripts/release.py prepare "$version")
if [[ "$push" == "--push" ]]; then
  arguments+=(--push)
fi
"$environment/bin/python" "${arguments[@]}"
