#!/usr/bin/env python3
"""Настройщик presentation-agent: venv, .env, Google-авторизация, смоук-тест.

Кроссплатформенный (Mac/Windows/Linux). Идемпотентен - повторный запуск
безопасен. Вызывается из install.sh / install.ps1 или напрямую:

    python setup.py
"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from tools.installer import (  # noqa: E402
    find_python,
    venv_python_path,
    windows_shim_bat,
    write_env_from_example,
)

VENV_DIR = os.path.join(ROOT, "tools", "venv")
REQS = os.path.join(ROOT, "tools", "requirements.txt")


def _have(cmd):
    from shutil import which
    return which(cmd) is not None


def check_prereqs():
    """Проверяет git и хотя бы один поддерживаемый AI CLI."""
    ok = True
    if _have("git"):
        print("[OK] git")
    else:
        print("[ПРОБЛЕМА] git не найден - поставь git и повтори")
        ok = False
    if _have("claude") or _have("codex"):
        available = ", ".join(x for x in ("Claude Code" if _have("claude") else "", "Codex" if _have("codex") else "") if x)
        print(f"[OK] AI CLI: {available}")
    else:
        print("[ПРОБЛЕМА] не найден Codex или Claude Code CLI")
        ok = False
    return ok


def build_venv():
    """Собирает venv нужным питоном и ставит зависимости. На Windows кладёт шим."""
    py = find_python()
    if not py:
        print("[ПРОБЛЕМА] не найден Python 3.9+ - поставь Python и повтори")
        return False
    print("Python для venv:", " ".join(py))
    subprocess.run(py + ["-m", "venv", VENV_DIR], check=True)
    vpy = venv_python_path(VENV_DIR, sys.platform)
    subprocess.run([vpy, "-m", "pip", "install", "--upgrade", "pip"], check=True)
    subprocess.run([vpy, "-m", "pip", "install", "-r", REQS], check=True)
    if sys.platform.startswith("win"):
        bindir = os.path.join(VENV_DIR, "bin")
        os.makedirs(bindir, exist_ok=True)
        with open(os.path.join(bindir, "python.bat"), "w", newline="") as f:
            f.write(windows_shim_bat(VENV_DIR))
        print("[OK] Windows-шим tools/venv/bin/python.bat создан")
    print("[OK] venv собран")
    return True


def setup_env():
    created = write_env_from_example(
        os.path.join(ROOT, ".env.example"),
        os.path.join(ROOT, ".env"),
    )
    if created:
        print("[OK] .env создан из .env.example - впиши свои ключи (Pexels/OpenAI)")
    else:
        print("[OK] .env уже есть - не трогаю")


def setup_local_config():
    example = os.path.join(ROOT, "tools", "converters", "config.example.json")
    target = os.path.join(ROOT, "tools", "converters", "config.json")
    if os.path.exists(target):
        print("[OK] config.json уже есть - не трогаю")
        return
    shutil.copyfile(example, target)
    print("[OK] config.json создан из безопасного шаблона")


def google_auth():
    vpy = venv_python_path(VENV_DIR, sys.platform)
    auth = os.path.join(ROOT, "tools", "converters", "google_auth.py")
    oauth = os.path.join(ROOT, "tools", "converters", "oauth_client.json")
    if not os.path.exists(oauth):
        print("[ПРОПУСК] oauth_client.json не найден - Google Slides можно подключить позже")
        return
    subprocess.run([vpy, auth], check=False)


def smoke_test():
    vpy = venv_python_path(VENV_DIR, sys.platform)
    doctor = os.path.join(ROOT, "tools", "doctor.py")
    token = os.path.join(ROOT, "tools", "converters", "token.json")
    cmd = [vpy, doctor]
    if os.path.exists(token):
        cmd += ["--token", token]
    subprocess.run(cmd, check=False)


def main():
    print("=== Настройка presentation-agent ===\n")
    if not check_prereqs():
        print("\nСначала поставь недостающее и запусти снова.")
        return 1
    if not build_venv():
        return 1
    setup_env()
    setup_local_config()
    print("\n--- Google-авторизация ---")
    google_auth()
    print("\n--- Смоук-тест ---")
    smoke_test()
    print("\nГотово. Открой эту папку в Codex или Claude Code и начинай работать.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
