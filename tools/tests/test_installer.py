import os
from tools.installer import (
    python_candidates,
    venv_python_path,
    windows_shim_bat,
    write_env_from_example,
    write_from_example,
)


def test_python_candidates_macos_prefers_system():
    # macOS: системный /usr/bin/python3 первым - brew-питоны битые для этого окружения
    assert python_candidates("darwin")[0] == "/usr/bin/python3"


def test_python_candidates_windows():
    assert python_candidates("win32") == ["py -3", "python"]


def test_python_candidates_linux():
    assert python_candidates("linux") == ["python3", "python"]


def test_venv_python_path_unix():
    assert venv_python_path("/p/venv", "darwin").endswith(os.path.join("bin", "python"))


def test_venv_python_path_windows():
    assert venv_python_path("C:/p/venv", "win32").endswith(os.path.join("Scripts", "python.exe"))


def test_windows_shim_points_to_scripts():
    bat = windows_shim_bat("C:/p/venv")
    assert "Scripts" in bat and "python.exe" in bat
    assert bat.startswith("@echo off")


def test_write_env_creates_when_missing(tmp_path):
    ex = tmp_path / ".env.example"
    ex.write_text("PEXELS_API_KEY=\n")
    env = tmp_path / ".env"
    assert write_env_from_example(str(ex), str(env)) is True
    assert env.read_text() == "PEXELS_API_KEY=\n"


def test_write_env_idempotent_does_not_overwrite(tmp_path):
    ex = tmp_path / ".env.example"
    ex.write_text("A=\n")
    env = tmp_path / ".env"
    env.write_text("A=secret\n")
    assert write_env_from_example(str(ex), str(env)) is False
    assert env.read_text() == "A=secret\n"  # личные ключи не затёрли


def test_write_from_example_creates_parent_and_preserves_existing(tmp_path):
    example = tmp_path / "templates" / "SOUL.example.md"
    example.parent.mkdir()
    example.write_text("шаблон\n")
    target = tmp_path / "workspace" / "SOUL.md"

    assert write_from_example(str(example), str(target)) is True
    assert target.read_text() == "шаблон\n"

    target.write_text("личные данные\n")
    assert write_from_example(str(example), str(target)) is False
    assert target.read_text() == "личные данные\n"


def test_google_auth_module_has_main():
    import importlib
    mod = importlib.import_module("google_auth")  # из tools/converters (conftest кладёт в путь)
    assert hasattr(mod, "main")
