#!/usr/bin/env bash

set -ex

flake8 src/main.py
pylint -E src/main.py