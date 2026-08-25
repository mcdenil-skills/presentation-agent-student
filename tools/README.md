# Инструменты

Методология работает без Python. Этот каталог нужен для больших таблиц и Google Slides.

## Проверка среды

```bash
tools/venv/bin/python tools/doctor.py
tools/venv/bin/python tools/doctor.py --token tools/converters/token.json
```

## Большие таблицы

`pipeline/` умеет:

- читать CSV, XLSX и разрешённые Google Sheets;
- нормализовать строки;
- убрать технический мусор;
- разбить данные на партии;
- объединить результаты без потери адреса исходной строки.

Смысловой анализ выполняется отдельно выбранной владельцем моделью. Перед обработкой удалите персональные данные по `PRIVACY.md`.

## Проверка текста слайдов

```bash
tools/venv/bin/python tools/check_slides.py path/to/SLIDES.txt
```

Проверка ловит переполнение, служебные маркеры, несколько CLI-команд на одном слайде, повторяющиеся начала фраз и вероятные телеграфные обрубки.

## Google Slides

- `google_to_text.py` - презентация в текст и карта объектов;
- `template_inventory.py` - повторяющиеся раскладки;
- `layout_director.py` - план раскладок;
- `source_images.py` - кандидаты изображений;
- `apply_edits.py` - правки безопасной копии;
- `render_slides.py` - PNG для визуального QA;
- `text_to_google.py` - новая презентация из формата `===SLIDE===`.

Локальные файлы `oauth_client.json`, `token.json` и `config.json` игнорируются Git. Репозиторий содержит только `config.example.json`.

## Тесты

```bash
tools/venv/bin/python -m pytest tools/tests -q
```

`requirements.in` хранит прямые зависимости, а `requirements.txt` — полный фиксированный набор с SHA-256-хэшами. Перед релизом CI проверяет его через `pip-audit`; Dependabot еженедельно предлагает обновления.
