#!/bin/bash
# Пересборка venv движка. ВАЖНО: только /usr/bin/python3 (3.9.6 CommandLineTools).
# brew-питоны (3.12/3.14) битые для этого окружения - НЕ использовать.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
PYBIN="/usr/bin/python3"
echo "Python: $($PYBIN --version)"
rm -rf "$DIR/venv"
"$PYBIN" -m venv "$DIR/venv"
"$DIR/venv/bin/python" -m pip install --upgrade pip
"$DIR/venv/bin/python" -m pip install -r "$DIR/requirements.txt"
echo "OK: venv пересобран в $DIR/venv"
