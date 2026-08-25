import os
import pytest
from tools.pipeline.load_table import detect_csv_dialect, load_csv, load_xlsx, preview_columns

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def test_unknown_csv_column_raises():
    path = os.path.join(FIX, "sample_semicolon.csv")
    with pytest.raises(ValueError):
        load_csv(path, text_col="НетТакого")


def test_unknown_xlsx_column_raises():
    path = os.path.join(FIX, "sample_two_sheets.xlsx")
    with pytest.raises(ValueError):
        load_xlsx(path, text_col="НетТакого")


def test_detect_semicolon():
    path = os.path.join(FIX, "sample_semicolon.csv")
    enc, delim = detect_csv_dialect(path)
    assert delim == ";"


def test_load_csv_column():
    path = os.path.join(FIX, "sample_semicolon.csv")
    rows = load_csv(path, text_col="Комментарий")
    texts = [r["текст"] for r in rows]
    assert "дорого для меня сейчас" in texts
    assert len(rows) == 3


def test_load_csv_extracts_author():
    # Колонка "Имя" входит в AUTHOR_COLUMNS -> поле "автор" должно извлечься.
    path = os.path.join(FIX, "sample_semicolon.csv")
    rows = load_csv(path, text_col="Комментарий")
    by_text = {r["текст"]: r["автор"] for r in rows}
    assert by_text["дорого для меня сейчас"] == "Аня"
    assert by_text["клиенты уходят к конкурентам"] == "Ваня"


def test_load_xlsx_all_sheets():
    path = os.path.join(FIX, "sample_two_sheets.xlsx")
    rows = load_xlsx(path, text_col="Текст")
    sheets = {r["лист"] for r in rows}
    assert sheets == {"Лист1", "Лист2"}   # КРИТИЧНО: оба листа
    assert len(rows) == 2


def test_preview_shows_columns():
    path = os.path.join(FIX, "sample_semicolon.csv")
    prev = preview_columns(path)
    assert "Комментарий" in prev["columns"]
    assert len(prev["sample_rows"]) >= 1
