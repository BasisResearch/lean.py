#!/usr/bin/env bash
# Run the test suite under macOS `leaks` or Linux `valgrind` to detect
# missing `lean_dec_ref` / `Py_DecRef` calls.
#
# Usage:
#   tests/leaks_check.sh
#
# Environment:
#   STRESS=1   — increase iteration counts (default off)
#   FILTER=... — only run tests matching this pytest -k filter

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTEST_ARGS=(-x tests/test_memory.py tests/test_marshal.py)
[[ -n "${FILTER:-}" ]] && PYTEST_ARGS+=(-k "$FILTER")

case "$(uname)" in
  Darwin)
    # `leaks` requires the process to exit cleanly. Use --atExit option.
    echo "==> Running pytest under macOS leaks(1)"
    MallocStackLogging=1 leaks --atExit -- \
      uv run pytest "${PYTEST_ARGS[@]}"
    ;;
  Linux)
    if ! command -v valgrind >/dev/null 2>&1; then
      echo "valgrind not installed; install via apt-get install valgrind" >&2
      exit 1
    fi
    echo "==> Running pytest under valgrind"
    # PYTHONMALLOC=malloc gives valgrind clean tracking of Python allocations.
    PYTHONMALLOC=malloc valgrind \
      --leak-check=full \
      --show-leak-kinds=definite \
      --suppressions="$REPO_ROOT/tests/python.supp" \
      --error-exitcode=1 \
      uv run pytest "${PYTEST_ARGS[@]}"
    ;;
  *)
    echo "Unsupported OS: $(uname)" >&2
    exit 1
    ;;
esac
