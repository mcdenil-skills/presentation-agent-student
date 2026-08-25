#!/bin/bash
# Установщик presentation-agent для macOS / Linux.
# Запуск из папки проекта:  bash install.sh
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"

PY="/usr/bin/python3"
command -v "$PY" >/dev/null 2>&1 || PY="python3"
command -v "$PY" >/dev/null 2>&1 || { echo "Не найден python3 - поставь Python 3.9+"; exit 1; }

echo "Запускаю настройку через $PY ..."
"$PY" "$DIR/setup.py"
