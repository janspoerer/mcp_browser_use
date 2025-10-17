#!/usr/bin/env bash
set -euo pipefail

# Go to repo root
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT"

# Config
PKG="${PKG:-mcp_browser_use}"            # package to measure
REPORT_DIR="${REPORT_DIR:-reports/coverage}"
HTML_DIR="$REPORT_DIR/html"
XML_FILE="$REPORT_DIR/coverage.xml"
COVERAGE_DATA="$REPORT_DIR/.coverage"     # raw coverage data file
MIN_COV="${MIN_COV:-0}"                   # set e.g. MIN_COV=85 to enforce threshold
PYTHON="${PYTHON:-python}"

# Reduce traceback noise in decorator envelope during tests
export MBU_TOOL_ERRORS_TRACEBACK=0

# Ensure deps: pytest must exist
if ! "$PYTHON" -c "import pytest" >/dev/null 2>&1; then
  echo "pytest not installed in this environment." >&2
  echo "Install: pip install pytest" >&2
  exit 1
fi

# Detect pytest-cov
if "$PYTHON" -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('pytest_cov') else 1)"; then
  HAS_PYTEST_COV=1
else
  HAS_PYTEST_COV=0
fi

# Prepare output directories
rm -rf "$REPORT_DIR" .pytest_cache || true
mkdir -p "$HTML_DIR"

echo "[coverage] Running tests..."
if [[ "$HAS_PYTEST_COV" -eq 1 ]]; then
  echo "[coverage] Using pytest-cov plugin."
  # Prefer local venv pytest if available
  if [[ -x ".venv/bin/pytest" ]]; then
    PYTEST=".venv/bin/pytest"
  else
    PYTEST="pytest"
  fi

  set +e
  COVERAGE_FILE="$COVERAGE_DATA" "$PYTEST" -q \
    --maxfail=1 \
    --disable-warnings \
    --cov="$PKG" \
    --cov-branch \
    --cov-report=term-missing:skip-covered \
    --cov-report="html:$HTML_DIR" \
    --cov-report="xml:$XML_FILE" \
    ${MIN_COV:+--cov-fail-under="$MIN_COV"} \
    tests
  STATUS=$?
  set -e
  if [[ $STATUS -ne 0 ]]; then
    echo "[coverage] Tests failed or coverage threshold not met."
    echo "HTML report: $HTML_DIR/index.html"
    echo "XML report : $XML_FILE"
    exit $STATUS
  fi
else
  echo "[coverage] pytest-cov not found. Falling back to 'coverage' CLI."
  # Ensure 'coverage' package exists
  if ! "$PYTHON" -c "import coverage" >/dev/null 2>&1; then
    echo "coverage not installed. Install: pip install coverage" >&2
    exit 1
  fi

  export COVERAGE_FILE="$COVERAGE_DATA"

  # Erase previous data
  "$PYTHON" -m coverage erase

  # Run tests with coverage
  "$PYTHON" -m coverage run --branch --source="$PKG" -m pytest -q \
    --maxfail=1 --disable-warnings tests

  # Create reports
  "$PYTHON" -m coverage xml -o "$XML_FILE"
  "$PYTHON" -m coverage html -d "$HTML_DIR"
  # Fail under threshold if set
  if [[ -n "${MIN_COV:-}" ]]; then
    "$PYTHON" -m coverage report -m --fail-under="$MIN_COV"
  else
    "$PYTHON" -m coverage report -m
  fi
fi

echo
echo "[coverage] Done."
echo " - HTML report: $HTML_DIR/index.html"
echo " - XML report : $XML_FILE"
echo " - Data file  : $COVERAGE_DATA"