#!/usr/bin/env bash

set -eux

run_lint() {
    local check_mode=$1
    if [ "$check_mode" = "true" ]; then
        uv run isort --check acoustid/ tests/
        uv run black --check acoustid/ tests/
    else
        uv run isort acoustid/ tests/
        uv run black acoustid/ tests/
    fi
    uv run flake8 acoustid/ tests/
    uv run mypy acoustid/ tests/
}

run_test() {
    uv run pytest -vv tests/
}

# Default values
run_tests=true
run_linting=true
check_mode=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --ci)
            check_mode=true
            shift
            ;;
        --lint)
            run_tests=false
            run_linting=true
            shift
            ;;
        --test)
            run_tests=true
            run_linting=false
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--lint] [--ci] [--test]"
            exit 1
            ;;
    esac
done

# Execute based on parsed arguments
if [ "$run_linting" = "true" ]; then
    run_lint "$check_mode"
fi

if [ "$run_tests" = "true" ]; then
    run_test
fi
