#!/bin/sh
set -eu

example_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
source_git=${1:?usage: build.sh SOURCE_GIT OUTPUT_DIRECTORY}
output_directory=${2:?usage: build.sh SOURCE_GIT OUTPUT_DIRECTORY}

test -d "$source_git" || {
  printf 'error: source Git directory does not exist: %s\n' "$source_git" >&2
  exit 1
}
test ! -e "$output_directory" || {
  printf 'error: output directory already exists: %s\n' "$output_directory" >&2
  exit 1
}

DOCKER_BUILDKIT=1 docker buildx build \
  --build-context trusted_git="$source_git" \
  --file "$example_dir/Containerfile" \
  --target export \
  --output "type=local,dest=$output_directory" \
  "$example_dir"
