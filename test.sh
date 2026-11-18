#!/usr/bin/env bash
# Runs the same checks as CI. Run it from anywhere.
set -e

cd "$(dirname "$0")/src"
uv sync --locked --no-install-project
LOG_LEVEL=DEBUG uv run --locked pytest -q "$@"
cd ..

pre-commit run -a
