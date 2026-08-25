"""Предпроверка движка. Запуск: tools/venv/bin/python tools/doctor.py [--token PATH] [--file PATH]"""
import sys, os, argparse


def check(name, ok, hint=""):
    print(("[OK] " if ok else "[ПРОБЛЕМА] ") + name + ("" if ok else f"  -> {hint}"))
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token")
    ap.add_argument("--file")
    a = ap.parse_args()
    ok = True
    try:
        import openpyxl, charset_normalizer, rapidfuzz, googleapiclient  # noqa
        ok &= check("Библиотеки движка установлены", True)
    except Exception as e:
        ok &= check("Библиотеки движка", False, f"пересобери venv: ./tools/rebuild_venv.sh ({e})")
    if a.token:
        exists = os.path.exists(a.token)
        ok &= check(f"Токен {a.token}", exists, "нет токена - нужна авторизация Google")
        if exists:
            try:
                from google.oauth2.credentials import Credentials
                c = Credentials.from_authorized_user_file(a.token)
                ok &= check("Scope drive у токена", "drive" in " ".join(c.scopes or []),
                            "нет scope drive - Sheets не выгрузить")
            except Exception as e:
                ok &= check("Токен читается", False, str(e))
    if a.file:
        ok &= check(f"Файл {a.file} доступен", os.path.exists(a.file), "проверь путь")
    print("\nИТОГ:", "всё готово" if ok else "есть проблемы - см. выше")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
