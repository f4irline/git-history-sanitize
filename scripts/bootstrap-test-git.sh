#!/usr/bin/env bash
set -euo pipefail

readonly git_tag="v2.47.0"
readonly git_commit="777489f9e09c8d0dd6b12f9d90de6376330577a2"
readonly expected_output="git version 2.47.0"

if [[ $# -ne 1 ]]; then
  printf 'usage: %s PREFIX\n' "$0" >&2
  exit 2
fi

prefix="$1"
mkdir -p "$prefix"
prefix="$(cd "$prefix" && pwd)"
workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null git init -q "$workdir/git"
GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null git -C "$workdir/git" \
  fetch -q --depth=1 https://github.com/git/git.git "refs/tags/$git_tag"
resolved="$(git -C "$workdir/git" rev-parse FETCH_HEAD^{commit})"
if [[ "$resolved" != "$git_commit" ]]; then
  printf 'Git tag %s resolved to %s, expected %s\n' "$git_tag" "$resolved" "$git_commit" >&2
  exit 1
fi

git -C "$workdir/git" checkout -q --detach "$git_commit"
# GCC 15 reserves unreachable() and thread_local; Git 2.47.0 uses both as
# private identifiers. Rename only the build-local helpers for Ubuntu 26.04.
sed 's/unreachable(/reflog_unreachable(/g' "$workdir/git/reflog.c" > "$workdir/git/reflog.c.tmp"
mv "$workdir/git/reflog.c.tmp" "$workdir/git/reflog.c"
sed 's/thread_local/git_thread_local/g' "$workdir/git/builtin/index-pack.c" > "$workdir/git/builtin/index-pack.c.tmp"
mv "$workdir/git/builtin/index-pack.c.tmp" "$workdir/git/builtin/index-pack.c"
make -C "$workdir/git" -s prefix="$prefix" NO_TCLTK=YesPlease install
if [[ "$("$prefix/bin/git" --version)" != "$expected_output" ]]; then
  printf 'built Git did not emit %s\n' "$expected_output" >&2
  exit 1
fi
