#!/usr/bin/env python3
"""
Акцент на части текста: разметка [[...]] -> покраска выбранного фрагмента.

Заголовок может делиться на основную и акцентную часть. Вместо ручной
покраски после генерации в формате ===SLIDE=== пишем:
    ЗАГОЛОВОК: Золотое правило - [[сначала план, потом стройка]]
и текст в [[...]] автоматически красится в акцентный цвет (updateTextStyle).
Стартовый цвет нейтральный; замените его на цвет собственной палитры.

Важно про индексы: Google Slides считает позиции в Unicode-символах. Для
русского текста (без эмодзи/суррогатов) это совпадает с len() Python, поэтому
индексы из чистого текста подставляются напрямую.
"""

from __future__ import annotations

import re

# Нейтральный синий по умолчанию. Владельцу нужно заменить его на цвет бренда.
ACCENT_HEX = "4285F4"

_ACCENT_RE = re.compile(r"\[\[(.+?)\]\]", re.DOTALL)


def parse_accent_markup(text: str) -> tuple[str, list[tuple[int, int]]]:
    """
    Вынимает разметку [[...]] из текста.

    Возвращает (чистый_текст_без_скобок, [(start, end), ...]) - диапазоны
    символов в ЧИСТОМ тексте, которые надо покрасить. Если разметки нет -
    исходный текст и пустой список (поведение как раньше).

    >>> parse_accent_markup("Золотое правило - [[сначала план]]")
    ('Золотое правило - сначала план', [(18, 30)])
    """
    if "[[" not in text:
        return text, []

    parts: list[str] = []
    ranges: list[tuple[int, int]] = []
    pos = 0
    idx = 0  # позиция в собираемом чистом тексте

    for m in _ACCENT_RE.finditer(text):
        before = text[pos:m.start()]
        parts.append(before)
        idx += len(before)

        inner = m.group(1)
        start = idx
        parts.append(inner)
        idx += len(inner)
        ranges.append((start, idx))

        pos = m.end()

    parts.append(text[pos:])
    return "".join(parts), ranges


def hex_to_rgb01(hex_color: str) -> tuple[float, float, float]:
    """'4285F4' или '#4285F4' -> (r, g, b) в долях 0..1 для Slides API."""
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0)


def build_accent_style_request(object_id: str, start: int, end: int,
                               hex_color: str = ACCENT_HEX) -> dict:
    """Запрос updateTextStyle: красит [start, end) в блоке в заданный цвет."""
    r, g, b = hex_to_rgb01(hex_color)
    return {
        "updateTextStyle": {
            "objectId": object_id,
            "textRange": {"type": "FIXED_RANGE", "startIndex": start, "endIndex": end},
            "style": {
                "foregroundColor": {
                    "opaqueColor": {"rgbColor": {"red": r, "green": g, "blue": b}}
                }
            },
            "fields": "foregroundColor",
        }
    }


def build_text_requests_with_accent(object_id: str, text: str,
                                    hex_color: str = ACCENT_HEX) -> list:
    """
    Полный набор запросов на замену текста с акцентом: удалить всё -> вставить
    чистый текст -> покрасить размеченные [[...]] куски (в этом порядке, в одном
    батче, чтобы updateTextStyle видел уже вставленный текст).
    """
    clean, ranges = parse_accent_markup(text)
    reqs = [
        {"deleteText": {"objectId": object_id, "textRange": {"type": "ALL"}}},
        {"insertText": {"objectId": object_id, "insertionIndex": 0, "text": clean}},
    ]
    for start, end in ranges:
        reqs.append(build_accent_style_request(object_id, start, end, hex_color))
    return reqs


if __name__ == "__main__":
    # быстрый самотест разбора
    samples = [
        "Золотое правило - [[сначала план, потом стройка]]",
        "[[Прототип работает]] - кнопки нажимаются",
        "Без акцента вообще",
        "Два [[куска]] в одной [[строке]]",
    ]
    for s in samples:
        clean, ranges = parse_accent_markup(s)
        print(repr(s))
        print("  ->", repr(clean), ranges)
        for st, en in ranges:
            print("     красим:", repr(clean[st:en]))
