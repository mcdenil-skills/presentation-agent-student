#!/bin/bash
# Безопасно обновляет venv через общий установщик Python 3.11+.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYBIN="python3"
command -v "$PYBIN" >/dev/null 2>&1 || { echo "Не найден Python 3.11+"; exit 1; }
"$PYBIN" "$ROOT/setup.py"
