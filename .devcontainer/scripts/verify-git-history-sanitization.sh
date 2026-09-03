#!/usr/bin/env bash
# Validate a repository already rewritten by sanitize-git-history.sh.
set -euo pipefail

repository="${1:?usage: verify-git-history-sanitization.sh REPOSITORY FILTER_FILE [forbidden-string ...]}"
filter_file="${2:?usage: verify-git-history-sanitization.sh REPOSITORY FILTER_FILE [forbidden-string ...]}"
shift 2

git -C "$repository" rev-parse --is-inside-work-tree >/dev/null

while IFS= read -r path || [[ -n "$path" ]]; do
  path="${path#"${path%%[![:space:]]*}"}"
  path="${path%"${path##*[![:space:]]}"}"
  [[ -z "$path" || "$path" == \#* ]] && continue
  if git -C "$repository" log --all --format=%H -- "$path" | grep -q .; then
    echo "Sensitive path remains in reachable history: $path" >&2
    exit 1
  fi
  if git -C "$repository" rev-list --objects --all | \
      awk -v sensitive_path="$path" '
        $2 == sensitive_path { found = 1 }
        substr(sensitive_path, length(sensitive_path), 1) == "/" &&
          index($2, sensitive_path) == 1 { found = 1 }
        END { exit !found }
      '; then
    echo "Sensitive blob or tree remains reachable: $path" >&2
    exit 1
  fi
done < "$filter_file"

if git -C "$repository" for-each-ref --format='%(refname)' | grep -Evq '^refs/heads/'; then
  echo "Unexpected metadata ref remains." >&2
  exit 1
fi
if [[ -d "$repository/.git/logs" ]] && find "$repository/.git/logs" -type f -print -quit | grep -q .; then
  echo "Reflogs remain." >&2
  exit 1
fi
if [[ -e "$repository/.git/filter-repo" || -e "$repository/.git/refs/original" ]]; then
  echo "filter-repo backup metadata remains." >&2
  exit 1
fi

# After the sanitizer's GC, fsck must print no unreachable objects.
if [[ -n "$(git -C "$repository" fsck --full --unreachable --no-reflogs)" ]]; then
  echo "Unreachable objects remain after cleanup." >&2
  exit 1
fi

for forbidden in "$@"; do
  if git -C "$repository" cat-file --batch-all-objects --batch-check='%(objectname)' | \
      git -C "$repository" cat-file --batch --buffer | grep -F -- "$forbidden" >/dev/null; then
    echo "Forbidden content remains in the object database." >&2
    exit 1
  fi
done

echo "Sanitized Git repository verification passed."
