#!/bin/sh
set -eu

example_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
source_git=${1:?usage: run.sh SOURCE_GIT OUTPUT_GIT}
output_git=${2:?usage: run.sh SOURCE_GIT OUTPUT_GIT}
sanitize=${GIT_HISTORY_SANITIZE:-git-history-sanitize}
policy="$example_dir/.git-history-sanitize.yml"

test -d "$source_git" || {
  printf 'error: source Git directory does not exist: %s\n' "$source_git" >&2
  exit 1
}
test ! -e "$output_git" || {
  printf 'error: output already exists: %s\n' "$output_git" >&2
  exit 1
}

"$sanitize" doctor
"$sanitize" plan --source "$source_git" --policy "$policy"
"$sanitize" rewrite --source "$source_git" --output "$output_git" --policy "$policy"
"$sanitize" verify --repository "$output_git" --policy "$policy"
