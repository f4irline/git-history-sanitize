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

printf 'one\n' > "$repository/allowed.txt"
git -C "$repository" add allowed.txt
git -C "$repository" commit -qm "Allowed change"

printf 'two\n' >> "$repository/allowed.txt"
mkdir -p "$repository/private"
printf 'customer material\n' > "$repository/private/secret.txt"
git -C "$repository" add allowed.txt private/secret.txt
git -C "$repository" commit -qm "Customer Foo secret implementation"

printf 'rotated material\n' >> "$repository/private/secret.txt"
git -C "$repository" add private/secret.txt
git -C "$repository" commit -qm "Rotate Foo credentials"

printf 'three\n' >> "$repository/allowed.txt"
git -C "$repository" add allowed.txt
git -C "$repository" commit -qm "Another allowed change"

# Exercise the reported edge case explicitly: the branch tip itself is mixed.
printf 'four\n' >> "$repository/allowed.txt"
printf 'more private material\n' >> "$repository/private/secret.txt"
git -C "$repository" add allowed.txt private/secret.txt
git -C "$repository" commit -qm "Latest commit mentions another customer secret"

printf '%s\n' private/ > "$fixture/filter.txt"
"$sanitizer" "$repository" "$fixture/filter.txt"
"$verifier" "$repository" "$fixture/filter.txt" \
  "Customer Foo secret implementation" "Rotate Foo credentials" \
  "Latest commit mentions another customer secret"

[[ "$(git -C "$repository" log --format=%s --all | sed -n '1p')" == "[sanitized]" ]]
[[ "$(git -C "$repository" log --format=%s --all | sed -n '2p')" == "Another allowed change" ]]
[[ "$(git -C "$repository" log --format=%s --all | sed -n '3p')" == "[sanitized]" ]]
[[ "$(git -C "$repository" log --format=%s --all | sed -n '4p')" == "Allowed change" ]]
[[ "$(git -C "$repository" rev-list --count --all)" == 4 ]]
[[ "$(git -C "$repository" show HEAD:allowed.txt)" == $'one\ntwo\nthree\nfour' ]]
[[ "$(git -C "$repository" show --format= --name-only HEAD)" == "allowed.txt" ]]
! git -C "$repository" show HEAD:private/secret.txt >/dev/null 2>&1

echo "Mixed and sensitive-only commit behavior passed."
