#!/usr/bin/env bash
# Local development setup: installs the Python dev dependencies with uv.
set -e

cd src
uv sync --no-install-project
