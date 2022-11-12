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
    poetry run pytest
}

if [ "$#" -gt 1 ]; then
    echo -n "Too many args. "
    help
fi

# Run function with same name of CLI argument (default to "help").
cmd=${1:-"help"}
$cmd
