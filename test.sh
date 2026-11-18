#!/usr/bin/env bash
# Runs the same checks as CI.
set -e

cd src
uv sync --no-install-project
LOG_LEVEL=DEBUG uv run pytest -q "$@"
cd ..

pre-commit run -a
