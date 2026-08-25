"""Кроссплатформенные помощники установщика.

Чистые функции - без скрытых побочных эффектов, тестируются напрямую.
Платформа передаётся строкой (sys.platform: 'darwin' / 'win32' / 'linux'),
чтобы поведение можно было проверить тестами на любой ОС.
"""
import os
import shutil
import subprocess
import sys


def python_candidates(platform):
    """Команды-кандидаты интерпретатора по ОС, в порядке предпочтения.

    macOS: системный /usr/bin/python3 (3.9.x) первым - brew-питоны
    (3.12/3.14) битые для этого окружения, см. tools/rebuild_venv.sh.
    """
    if platform == "darwin":
        return ["/usr/bin/python3", "python3"]
    if platform.startswith("win"):
        return ["py -3", "python"]
    return ["python3", "python"]


def venv_python_path(venv_dir, platform):
    """Путь к интерпретатору внутри venv по ОС."""
    if platform.startswith("win"):
        return os.path.join(venv_dir, "Scripts", "python.exe")
    return os.path.join(venv_dir, "bin", "python")


def windows_shim_bat(venv_dir):
    """Содержимое tools/venv/bin/python.bat для Windows.

    Форвардит на venv/Scripts/python.exe, чтобы Unix-стиль команд из
    документации (tools/venv/bin/python ...) работал и на Windows.
    """
    target = os.path.join(venv_dir, "Scripts", "python.exe")
    return '@echo off\r\n"%s" %%*\r\n' % target


def write_env_from_example(example_path, env_path):
    """Создаёт .env из .env.example, только если .env ещё нет.

    Идемпотентно: существующий .env (с личными ключами) не трогает.
    Возвращает True если создал, False если уже был.
    """
    if os.path.exists(env_path):
        return False
    shutil.copyfile(example_path, env_path)
    return True


def write_from_example(example_path, target_path):
    """Создаёт локальную рабочую копию из *.example.md.

    Существующий файл не перезаписывает. Родительскую папку создаёт сам.
    """
    if os.path.exists(target_path):
        return False
    os.makedirs(os.path.dirname(target_path) or ".", exist_ok=True)
    shutil.copyfile(example_path, target_path)
    return True


def find_python(platform=None):
    """Находит рабочий python >= 3.9 по кандидатам ОС.

    Возвращает argv-список (например ['/usr/bin/python3'] или ['py', '-3'])
    или None, если ничего подходящего не нашлось.
    """
    platform = platform or sys.platform
    for cand in python_candidates(platform):
        argv = cand.split()
        try:
            out = subprocess.run(
                argv + ["-c", "import sys;print('%d.%d' % sys.version_info[:2])"],
                capture_output=True, text=True, timeout=15,
            )
        except (FileNotFoundError, OSError, subprocess.SubprocessError):
            continue
        if out.returncode == 0 and out.stdout.strip():
            try:
                major, minor = (int(x) for x in out.stdout.strip().split("."))
            except ValueError:
                continue
            if (major, minor) >= (3, 9):
                return argv
    return None
