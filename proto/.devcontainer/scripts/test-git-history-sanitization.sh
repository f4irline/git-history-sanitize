#!/usr/bin/env bash
# Build a small history with allowed, mixed, and sensitive-only commits.
set -euo pipefail

sanitizer="${1:?usage: test-git-history-sanitization.sh SANITIZER VERIFY}"
verifier="${2:?usage: test-git-history-sanitization.sh SANITIZER VERIFY}"
fixture="$(mktemp -d)"
trap 'rm -rf "$fixture"' EXIT

git init --initial-branch=main "$fixture/repository" >/dev/null
repository="$fixture/repository"
git -C "$repository" config user.name "History test"
git -C "$repository" config user.email "history-test@example.invalid"

commit_at() {
  local timestamp="$1"
  local message="$2"
  GIT_AUTHOR_DATE="$timestamp" GIT_COMMITTER_DATE="$timestamp" \
    git -C "$repository" commit -qm "$message"
}

printf 'one\n' > "$repository/allowed.txt"
git -C "$repository" add allowed.txt
commit_at "2026-09-02T10:00:00+00:00" "Old allowed implementation details"

printf 'two\n' >> "$repository/allowed.txt"
mkdir -p "$repository/private"
printf 'customer material\n' > "$repository/private/secret.txt"
git -C "$repository" add allowed.txt private/secret.txt
commit_at "2026-09-02T11:00:00+00:00" "Old Customer Foo implementation"

printf 'three\n' >> "$repository/allowed.txt"
git -C "$repository" add allowed.txt
commit_at "2026-09-03T09:00:00+00:00" "First allowed commit"

printf 'four\n' >> "$repository/allowed.txt"
printf 'rotated material\n' >> "$repository/private/secret.txt"
git -C "$repository" add allowed.txt private/secret.txt
commit_at "2026-09-03T10:00:00+00:00" "Customer Foo secret implementation"

printf 'sensitive only\n' >> "$repository/private/secret.txt"
git -C "$repository" add private/secret.txt
commit_at "2026-09-03T11:00:00+00:00" "Rotate Foo credentials"

printf 'five\n' >> "$repository/allowed.txt"
git -C "$repository" add allowed.txt
commit_at "2026-09-03T12:00:00+00:00" "Another allowed change"

# Exercise the reported edge case explicitly: the branch tip itself is mixed.
printf 'six\n' >> "$repository/allowed.txt"
printf 'more private material\n' >> "$repository/private/secret.txt"
git -C "$repository" add allowed.txt private/secret.txt
commit_at "2026-09-03T13:00:00+00:00" "Latest commit mentions another customer secret"

printf '%s\n' private/ > "$fixture/filter.txt"
printf '%s\n' "2026-09-03T00:00:00+00:00" > "$fixture/cutoff.txt"
"$sanitizer" "$repository" "$fixture/filter.txt" "$fixture/cutoff.txt"
"$verifier" "$repository" "$fixture/filter.txt" "$fixture/cutoff.txt" \
  "Old allowed implementation details" "Old Customer Foo implementation" \
  "First allowed commit" "Customer Foo secret implementation" \
  "Rotate Foo credentials" \
  "Latest commit mentions another customer secret"

[[ "$(git -C "$repository" log --format=%s --all | sed -n '1p')" == "[sanitized]" ]]
[[ "$(git -C "$repository" log --format=%s --all | sed -n '2p')" == "Another allowed change" ]]
[[ "$(git -C "$repository" log --format=%s --all | sed -n '3p')" == "[sanitized]" ]]
[[ "$(git -C "$repository" log --format=%s --all | sed -n '4p')" == "[sanitized]" ]]
[[ "$(git -C "$repository" rev-list --count --all)" == 4 ]]
[[ "$(git -C "$repository" show HEAD:allowed.txt)" == $'one\ntwo\nthree\nfour\nfive\nsix' ]]
[[ "$(git -C "$repository" show --format= --name-only HEAD)" == "allowed.txt" ]]
[[ "$(git -C "$repository" rev-list --max-parents=0 --count HEAD)" == 1 ]]
! git -C "$repository" show HEAD:private/secret.txt >/dev/null 2>&1

echo "Cutoff, mixed, and sensitive-only commit behavior passed."
