#!/usr/bin/env python3
"""Отдельная точка Google-авторизации.

Переиспользует логику конвертера (text_to_google.get_credentials), чтобы не
дублировать OAuth-поток и набор scopes. Запускается установщиком.

Запуск: tools/venv/bin/python tools/converters/google_auth.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from text_to_google import get_credentials  # noqa: E402


def main():
    print("Открываю браузер для Google-авторизации.")
    print("Войди в СВОЙ Google-аккаунт. Появится экран")
    print("'Google не проверил это приложение' - нажми 'Дополнительно' ->")
    print("'Перейти (небезопасно)'. Это нормально: приложение твоей команды.")
    creds = get_credentials()
    if creds and creds.valid:
        print("OK: Google-авторизация готова, токен сохранён.")
        return 0
    print("ПРОБЛЕМА: авторизация не завершена. Запусти установщик снова.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
