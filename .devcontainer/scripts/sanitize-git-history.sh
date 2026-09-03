#!/usr/bin/env bash
# Rewrite a disposable clone so it contains no history for configured paths.
# This script is deliberately run only in the trusted Docker build stage.
set -euo pipefail

repository="${1:?usage: sanitize-git-history.sh REPOSITORY FILTER_FILE}"
filter_file="${2:?usage: sanitize-git-history.sh REPOSITORY FILTER_FILE}"

if ! git -C "$repository" rev-parse --is-inside-work-tree >/dev/null; then
  echo "Not a Git work tree: $repository" >&2
  exit 2
fi
if [[ ! -f "$filter_file" ]]; then
  echo "Missing Git-history filter file: $filter_file" >&2
  exit 2
fi

# Directories must end in '/', while files are exact paths. Comments and blank
# lines are intentionally ignored.
python3 - "$filter_file" <<'PY'
import sys
from pathlib import PurePosixPath

for number, raw in enumerate(open(sys.argv[1], encoding="utf-8"), 1):
    path = raw.strip()
    if not path or path.startswith("#"):
        continue
    candidate = PurePosixPath(path.rstrip("/"))
    if path.startswith("/") or not path.rstrip("/") or "\\" in path or any(part == ".." for part in candidate.parts):
        raise SystemExit(f"Invalid sensitive path on line {number}: {path!r}")
PY

head_ref="$(git -C "$repository" symbolic-ref -q HEAD || true)"
if [[ -z "$head_ref" ]]; then
  echo "The trusted repository must have a symbolic HEAD." >&2
  exit 2
fi

export GIT_HISTORY_FILTER_FILE="$(cd "$(dirname "$filter_file")" && pwd)/$(basename "$filter_file")"

# A path callback alone is insufficient: this callback first sees every
# original file change, removes sensitive changes, and then changes the message
# only when that original commit was mixed. Emptying the file-change list lets
# filter-repo's pruning remove sensitive-only commits after parent rewriting.
git -C "$repository" filter-repo --force --prune-empty always --commit-callback '
import os

def configured_paths():
    paths = []
    with open(os.environ["GIT_HISTORY_FILTER_FILE"], "rb") as handle:
        for raw in handle:
            path = raw.strip()
            if path and not path.startswith(b"#"):
                paths.append(path)
    return tuple(paths)

def is_sensitive(filename):
    for path in configured_paths():
        if path.endswith(b"/"):
            if filename.startswith(path):
                return True
        elif filename == path:
            return True
    return False

original_changes = list(commit.file_changes)
sensitive_changes = [change for change in original_changes if is_sensitive(change.filename)]
if sensitive_changes:
    remaining_changes = [change for change in original_changes if not is_sensitive(change.filename)]
    if remaining_changes:
        commit.file_changes = remaining_changes
        commit.message = b"[sanitized]\n"
    else:
        commit.file_changes = []
'

# Keep only the branch checked out by the source repository. This avoids tags,
# side branches, notes, stashes, and remote tracking refs keeping old objects
# reachable. Remotes are removed rather than merely hidden.
while IFS= read -r ref; do
  [[ "$ref" == "$head_ref" ]] || git -C "$repository" update-ref -d "$ref"
done < <(git -C "$repository" for-each-ref --format='%(refname)')

while IFS= read -r remote; do
  [[ -z "$remote" ]] || git -C "$repository" remote remove "$remote"
done < <(git -C "$repository" remote)

git -C "$repository" config --local --remove-section "branch.${head_ref#refs/heads/}" 2>/dev/null || true
git -C "$repository" reflog expire --expire=now --expire-unreachable=now --all
rm -rf "$repository/.git/logs" "$repository/.git/refs/original" "$repository/.git/filter-repo"
git -C "$repository" gc --prune=now --aggressive
git -C "$repository" fsck --full --no-reflogs --unreachable
