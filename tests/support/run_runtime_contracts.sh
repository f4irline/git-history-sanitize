#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  printf 'usage: %s PYTHON\n' "$0" >&2
  exit 2
fi

"$1" -m unittest -v \
  tests.test_cli_contracts \
  tests.test_cutoff_contracts \
  tests.test_end_to_end \
  tests.test_filtering_contracts \
  tests.test_output_cleanup_contracts \
  tests.test_regressions \
  tests.test_verify_contracts
