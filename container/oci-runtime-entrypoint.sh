#!/bin/sh
set -eu

readonly sentinel=/usr/local/etc/git-history-sanitize/oci-manifest-required
readonly manifest=/usr/local/share/git-history-sanitize/toolchain-manifest.json

if [ ! -r "$sentinel" ] || [ ! -r "$manifest" ]; then
  printf '%s\n' 'required OCI toolchain manifest is unavailable' >&2
  exit 126
fi

exec /opt/runtime/bin/python -m git_history_sanitize "$@"
