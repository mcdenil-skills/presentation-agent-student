# Установка

## Самый простой способ

Если вы не хотите работать с терминалом, используйте [установку одним промптом](INSTALL-WITH-AI.md). Claude Code или Codex выполнит безопасные шаги сам.

## 1. Что понадобится

- Git;
- Codex или Claude Code;
- Python 3.11+ - только если нужны инструменты обработки данных и Google Slides.

## 2. Скачать репозиторий

```bash
git clone https://github.com/mcdenil-skills/presentation-agent-student.git
cd presentation-agent-student
```

## 3. Базовая настройка агента

1. Откройте эту папку в Codex или Claude Code.
2. Напишите: «Я здесь впервые. Подготовь локальные шаблоны и проведи меня по быстрому старту из START-HERE.md».
3. Агент создаст локальные `SOUL.md`, `MEMORY.md` и базы `knowledge/` из файлов `*.example.md`. Git их игнорирует.

Для работы только с текстами этого достаточно. Полный маршрут для новичка — в [START-HERE.md](START-HERE.md).

## 4. Установить Python-инструменты

macOS или Linux:

```bash
bash install.sh
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```

Установщик создаст локальные `.env` и `tools/converters/config.json`. Эти файлы игнорируются Git.

## 5. Подключить Google Slides - по желанию

**Важно о доступе.** Конвейер умеет копировать любой указанный вами шаблон и поэтому запрашивает полный доступ к Google Drive. Google относит такой scope к restricted. Подключайте только свой OAuth-клиент; для учебной пробы лучше использовать отдельный Google-аккаунт без личных файлов. Если вам нужны только тексты, не подключайте Google вообще.

Создайте собственный Desktop OAuth client в Google Cloud и положите скачанный файл сюда:

```text
tools/converters/oauth_client.json
```

Никому не пересылайте этот файл и не добавляйте его в Git. При первом запуске авторизации появится локальный `token.json`, он тоже исключён из Git.

Затем впишите ID собственного шаблона и папки Google Drive в:

```text
tools/converters/config.json
```

## 6. Ключи для изображений - по желанию

В локальном `.env` можно указать:

- `PEXELS_API_KEY` - бесплатный поиск фотографий;
- `OPENAI_API_KEY` - платная генерация изображений.

Без этих ключей текстовая методология продолжает работать.

## Проверка

```bash
tools/venv/bin/python -m pytest tools/tests -q
```

Если Python-инструменты не нужны, начните с персонализации `SOUL.md` и баз `knowledge/`.
