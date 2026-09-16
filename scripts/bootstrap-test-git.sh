#!/usr/bin/env bash
set -euo pipefail

readonly git_tag="v2.47.0"
readonly git_commit="777489f9e09c8d0dd6b12f9d90de6376330577a2"
readonly git_release_key_fingerprint="E1F036B1FEE7221FC778ECEFB0B5E88696AFE6CB"
readonly expected_output="git version 2.47.0"
readonly reflog_before_sha256="34d293eb189b983e7ca17f9c34d458a4e448cf4e5e339c69b050b8a97ef09c9d"
readonly reflog_after_sha256="bfcc279ac0cf974007f54d20495aa39ea23f6b516fef8c43de412785e2354309"
readonly index_pack_before_sha256="068e5950e29560d9c6c5dfc901c46637a3b620f5b420b8f78c78eca3ae285194"
readonly index_pack_after_sha256="c4f7ced0081c951f5cf19946370438f40b4a0d59bb151ffbf913704e29c39d4f"

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
# The ephemeral verifier needs a reachable keyserver, not IPv6 coverage.
printf 'disable-ipv6\n' > "$GNUPGHOME/dirmngr.conf"

if ! command -v gpg >/dev/null; then
  printf 'gpg is required to verify Git release tags\n' >&2
  exit 1
fi
# keys.openpgp.org deliberately strips user IDs from some keys, which makes
# GnuPG reject the release key before the tag signature can be checked. This
# server returns the complete public certificate; its exact fingerprint below
# remains the trust anchor.
gpg --batch --keyserver hkps://keyserver.ubuntu.com --recv-keys "$git_release_key_fingerprint"
if ! gpg --batch --with-colons --list-keys | awk -F: -v expected="$git_release_key_fingerprint" '
  $1 == "fpr" && $10 == expected { found = 1 }
  END { exit !found }
'; then
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
verify_sha256() {
  local path="$1" expected="$2" actual
  actual="$(sha256sum "$path" | awk '{print $1}')"
  if [[ "$actual" != "$expected" ]]; then
    printf 'unexpected SHA-256 for %s\n' "$path" >&2
    exit 1
  fi
}
# GCC 15 reserves unreachable() and thread_local; Git 2.47.0 uses both as
# private identifiers. Rename only the build-local helpers for Ubuntu 26.04.
verify_sha256 "$workdir/git/reflog.c" "$reflog_before_sha256"
sed 's/unreachable(/reflog_unreachable(/g' "$workdir/git/reflog.c" > "$workdir/git/reflog.c.tmp"
mv "$workdir/git/reflog.c.tmp" "$workdir/git/reflog.c"
verify_sha256 "$workdir/git/reflog.c" "$reflog_after_sha256"
verify_sha256 "$workdir/git/builtin/index-pack.c" "$index_pack_before_sha256"
sed 's/thread_local/git_thread_local/g' "$workdir/git/builtin/index-pack.c" > "$workdir/git/builtin/index-pack.c.tmp"
mv "$workdir/git/builtin/index-pack.c.tmp" "$workdir/git/builtin/index-pack.c"
verify_sha256 "$workdir/git/builtin/index-pack.c" "$index_pack_after_sha256"
make -C "$workdir/git" -s prefix="$prefix" GIT_VERSION=2.47.0 NO_TCLTK=YesPlease install
actual_output="$("$prefix/bin/git" --version)"
if [[ "$actual_output" != "$expected_output" ]]; then
  printf 'built Git emitted %s; expected %s\n' "$actual_output" "$expected_output" >&2
  exit 1
fi
