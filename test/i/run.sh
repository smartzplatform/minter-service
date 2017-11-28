#!/usr/bin/env bash

BIN_DIR="$(cd $(dirname $0) && pwd)"
cd "$BIN_DIR"

python3 -m unittest *.py
