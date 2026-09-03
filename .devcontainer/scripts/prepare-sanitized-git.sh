#!/usr/bin/env bash
# /workspace is a host bind mount. Docker Compose mounts a tmpfs over its .git
# directory before this runs, so copying here cannot expose the host database.
set -euo pipefail

readonly source_git=/opt/sandbox-git
readonly workspace_git=/workspace/.git

mkdir -p "$workspace_git"
if [[ -n "$(find "$workspace_git" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
  echo "Refusing to replace a non-empty /workspace/.git; it must be the sandbox tmpfs." >&2
  exit 1
fi
cp -a "$source_git/." "$workspace_git/"

exec "$@"
