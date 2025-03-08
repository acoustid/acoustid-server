#!/usr/bin/env bash

set -eux

run_lint() {
    uv run isort --check acoustid/ tests/
    uv run black --check acoustid/ tests/
    uv run flake8 acoustid/ tests/
    uv run mypy acoustid/ tests/
}

run_test() {
    uv run pytest -vv tests/
}

if [ $# -eq 0 ]; then
    run_lint
    run_test
else
    case "$1" in
        --lint)
            run_lint
            ;;
        --test)
            run_test
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--lint|--test]"
            exit 1
            ;;
    esac
fi
