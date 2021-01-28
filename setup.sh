#!/usr/bin/env bash

[ -d env ] && rm -rf env

python3 -m venv env
source env/bin/activate
pip install -r requirements.txt