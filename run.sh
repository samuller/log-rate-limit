#
# Script for running commonly used commands quickly, e.g. "./run.sh lint". See: "./run.sh help".
#

# Fail on first error.
set -e

help() {
    echo "You have to provide a command to run, e.g. '$0 lint'"
    commands=$(compgen -A function | tr '\n' ' ')
    echo "All commands available are: $commands"
    exit
}

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

format() {
    black log_rate_limit/ tests/
}

test() {
    # --cov-context test
    # We add "test" contexts to see how many tests cover each line of code. This helps to spot overlapping coverage
    # or a too-high "coverage density" which means that small changes to those parts of the code will require updating
    # and fixing many different tests.
    poetry run pytest --verbose --cov=log_rate_limit --cov-branch --cov-context test \
        --cov-report=term --cov-report=html --cov-fail-under=100
}

if [ "$#" -gt 1 ]; then
    echo -n "Too many args. "
    help
fi

# Run function with same name of CLI argument (default to "help").
cmd=${1:-"help"}
$cmd
