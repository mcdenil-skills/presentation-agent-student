#!/bin/bash
# Конвертер текста в Google Slides (вендорная копия в проекте presentation-agent)
# Использование: ./convert_google.sh input.txt "Название презентации" [-d дизайн]
# Примеры:
#   ./convert_google.sh slides.txt "Вебинар"              # дизайн по умолчанию
#   ./convert_google.sh slides.txt "Вебинар" -d new       # новый дизайн
#
# ОТЛИЧИЕ от версии в скилле: здесь python берётся из движкового venv проекта
# (tools/venv/, на уровень выше папки converters), а не из converters/venv/.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Запускаем через интерпретатор движкового venv проекта (tools/venv/)
"$SCRIPT_DIR/../venv/bin/python" "$SCRIPT_DIR/text_to_google.py" "$@"
