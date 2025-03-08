#!/usr/bin/env bash

set -eux

check_requirements() {
    temp_file=$(mktemp)
    trap 'rm -f "$temp_file"' EXIT
    uv export --no-dev > "$temp_file"
    if ! diff -u requirements.txt "$temp_file"; then
        echo "requirements.txt is out of sync with pyproject.toml"
        exit 1
    fi
}

run_lint() {
    check_requirements
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
