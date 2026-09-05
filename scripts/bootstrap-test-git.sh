#!/usr/bin/env bash
set -euo pipefail

readonly git_tag="v2.47.0"
readonly git_commit="777489f9e09c8d0dd6b12f9d90de6376330577a2"
readonly git_release_key_fingerprint="4F9036B1FEE7221FC778ECEFB0B5E88696AFE6CB"
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
export GNUPGHOME="$workdir/gnupg"
export HOME="$workdir/home"
export XDG_CONFIG_HOME="$workdir/xdg-config"
export GIT_CONFIG_NOSYSTEM=1
export GIT_CONFIG_GLOBAL=/dev/null
export GIT_TEMPLATE_DIR="$workdir/templates"
mkdir -m 700 "$GNUPGHOME"
mkdir -p "$HOME" "$XDG_CONFIG_HOME" "$GIT_TEMPLATE_DIR"

if ! command -v gpg >/dev/null; then
  printf 'gpg is required to verify Git release tags\n' >&2
  exit 1
fi
gpg --batch --keyserver hkps://keys.openpgp.org --recv-keys "$git_release_key_fingerprint"
imported_fingerprint="$(gpg --batch --with-colons --fingerprint "$git_release_key_fingerprint" | awk -F: '$1 == "fpr" { print $10; exit }')"
if [[ "$imported_fingerprint" != "$git_release_key_fingerprint" ]]; then
  printf 'Git release key fingerprint did not match the pinned fingerprint\n' >&2
  exit 1
fi

git init -q "$workdir/git"
git -C "$workdir/git" \
  fetch -q --depth=1 https://github.com/git/git.git "refs/tags/$git_tag:refs/tags/$git_tag"
git -C "$workdir/git" verify-tag "$git_tag"
resolved="$(git -C "$workdir/git" rev-parse "$git_tag^{commit}")"
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
