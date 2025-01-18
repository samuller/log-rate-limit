#!/bin/bash
# shellcheck disable=SC2034
#
# Script for running commonly used commands quickly, e.g. "./run.sh lint". See: "./run.sh help".
#

# Fail on first error.
set -e

man_help="List all commands available."
help() {
    local commands
    # Fetch all functions declared in script.
    commands=$(compgen -A function | tr '\n' ' ')

    # If column command is not available, create a no-op function to replace it and prevent errors.
    # Alternatively, install it with: apt-get install -y bsdmainutils
    if ! type column >/dev/null 2>&1
    then function column { cat - ;}
    fi

    echo "You have to provide a command to run, e.g. '$0 lint'"
    echo "All commands available are:"
    echo
    (
        for cmd in ${commands}; do
            doc_name=man_$cmd
            echo -e "  $cmd\t\t\t${!doc_name}"
        done
    ) | column -t -s$'\t'
    echo
    exit
}

man_lint="Perform lint, type and style checks on all Python code."
lint() {
    echo "flake8..."
    poetry run flake8 log_rate_limit/
    # We're not as strict about docstrings in our tests
    poetry run flake8 --extend-ignore=D tests/
    echo "mypy..."
    poetry run mypy --strict --implicit-reexport log_rate_limit/
    # No "strict" type requirements for tests.
    poetry run mypy tests/
    echo "black..."
    poetry run black --check log_rate_limit/ tests/
}

man_format="Format all Python code."
format() {
    black log_rate_limit/ tests/
}

man_test="Run tests."
test() {
    # --cov-context test
    # We add "test" contexts to see how many tests cover each line of code. This helps to spot overlapping coverage
    # or a too-high "coverage density" which means that small changes to those parts of the code will require updating
    # and fixing many different tests.
    poetry run pytest --verbose --cov=log_rate_limit --cov-branch --cov-context test \
        --cov-report=term --cov-report=html --cov-fail-under=100
    FORCE_NO_REDIS=true pytest -k test_redis_optional
    FORCE_NO_REDIS=true poetry run pytest -k test_redis_optional
}

if [ "$#" -gt 1 ]; then
    echo -n "Too many args. "
    help
fi

# Run function with same name of CLI argument (default to "help").
cmd=${1:-"help"}
$cmd
