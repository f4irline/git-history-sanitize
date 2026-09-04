#!/bin/sh
set -eu

workspace=/workspace
git_dir="$workspace/.git"

test -d /opt/sanitized.git
mkdir -p "$git_dir"
cp -a /opt/sanitized.git/. "$git_dir/"
git --git-dir="$git_dir" config core.bare false
git --git-dir="$git_dir" config core.worktree "$workspace"
git -C "$workspace" fsck --full --no-reflogs >/dev/null

exec "$@"
