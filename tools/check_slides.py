#!/usr/bin/env python3
"""Проверка текста слайдов ПЕРЕД сборкой презентации.

Зачем: текст ложится в рамку донора-раскладки, у которой физический предел.
Перебор виден только после сборки в Google - и тогда переписывать поздно.
На уроке 5.1 это стоило четырёх пересборок. Скрипт ловит перебор заранее.

Что проверяет:
  - слова и строки на слайд против лимита (у слайдов с фото лимит строже);
  - формат «каждое предложение с новой строки» (абзац режиссёр положит одним
    буллетом, и получится стена текста);
  - назывные обрубки без глагола («Три текста на руках.») - телеграф, от
    которого ушли решением автора 07.08.2026;
  - книжные стоп-слова («вровень», «попадание», «расплывчатое»);
  - длинные тире (в проекте запрещены);
  - ровно один акцент [[...]] в заголовке и длину заголовка;
  - поле ПРОМПТ: команда должна быть одна и короткая;
  - повторяющиеся фразы между слайдами - подсказка, где искать дубли смыслов.

Использование:
    python3 tools/check_slides.py <файл_SLIDES.txt>
    python3 tools/check_slides.py <файл> --photo 2,8,11,18
    python3 tools/check_slides.py <файл> --quiet     # только итог

Нормативы - из instructions/slide-framework.md, раздел «Размер текста под
раскладку». Это консервативные стартовые значения; свой шаблон нужно измерить.
"""

import argparse
import re
import sys
from pathlib import Path

# Лимиты по типу слайда: (слов, строк). Консервативные стартовые значения.
LIMIT_TEXT = (65, 5)     # текстовый слайд
LIMIT_PHOTO = (48, 5)    # слайд с фотографией: фото забирает половину
LIMIT_COMMAND = (35, 5)  # чистый командный слайд (только ПРОМПТ, без обвязки)
PHOTO_SOFT = 44          # 45-48 слов рядом с фото - зависит от раскладки, смотреть рендером
TITLE_MAX_CHARS = 55     # заголовок длиннее - уедет в три строки

# Книжная лексика, которую вычищали руками на уроке 5.1.
STOP_WORDS = [
    "вровень", "попадание", "расплывчат", "дословно", "означает ровно одно",
    "конвертируется", "остаётся единственное",
]

# Глагольные признаки: если в предложении нет ни одного слова с этими
# окончаниями и нет короткого глагола-связки - вероятен назывной обрубок.
VERB_ENDINGS = (
    "ть", "ться", "ет", "ёт", "ут", "ют", "ит", "ат", "ят", "ешь", "ёшь",
    "ишь", "ем", "ём", "им", "ал", "ял", "ил", "ел", "ла", "ло", "ли",
    "шь", "сь", "ся", "ай", "ей", "и", "й",
)
VERB_WORDS = {
    "есть", "нет", "будет", "было", "была", "были", "стал", "стало", "стала",
    "можно", "нужно", "надо", "хочет", "может", "даёт", "идёт", "смотри",
    "бери", "пиши", "жми", "открой", "закрой", "прогони", "дай", "поставь",
}

SLIDE_RE = re.compile(r"===SLIDE===\s*\n(.*?)(?=\n===SLIDE===|\Z)", re.S)


def parse_slides(text: str) -> list[dict]:
    """Режет файл на слайды и достаёт поля. Формат - instructions/slide-framework.md.

    Слайды разделены маркером ===SLIDE=== на отдельной строке ПЕРЕД каждым
    блоком - закрывающего маркера в формате нет (см. slide-framework.md).
    """
    out = []
    for raw in SLIDE_RE.findall(text):
        slide = {"type": "", "title": "", "body": "", "prompt": "", "visual": ""}
        field, buf = None, []
        for line in raw.split("\n"):
            if line.startswith("ТИП:"):
                slide["type"] = line[4:].strip().lower()
                field, buf = None, []
            elif line.startswith("ЗАГОЛОВОК:"):
                if field:
                    slide[field] = "\n".join(buf).strip()
                field, buf = "title", [line[10:].strip()]
            elif line.startswith("ТЕКСТ:"):
                if field:
                    slide[field] = "\n".join(buf).strip()
                field, buf = "body", [line[6:].strip()]
            elif line.startswith("ПРОМПТ:"):
                if field:
                    slide[field] = "\n".join(buf).strip()
                field, buf = "prompt", [line[7:].strip()]
            elif line.startswith("ВИЗУАЛ:"):
                if field:
                    slide[field] = "\n".join(buf).strip()
                field, buf = "visual", [line[7:].strip()]
            elif line.startswith(("ТАЙМ:", "НОМЕР_УРОКА:", "ПРИЗЫВ:")):
                if field:
                    slide[field] = "\n".join(buf).strip()
                field, buf = None, []
            elif field:
                buf.append(line)
        if field:
            slide[field] = "\n".join(buf).strip()
        out.append(slide)
    return out


def looks_nominal(sentence: str) -> bool:
    """Похоже на назывной обрубок без глагола («Три текста на руках»)."""
    words = re.findall(r"[а-яёА-ЯЁa-zA-Z]+", sentence.lower())
    if len(words) < 3:
        return False
    if any(w in VERB_WORDS for w in words):
        return False
    return not any(w.endswith(VERB_ENDINGS) and len(w) > 3 for w in words)


def limits_for(slide: dict, is_photo: bool) -> tuple[int, int, str]:
    """Лимит слайда.

    Важно: слайд, где есть И обвязка (ТЕКСТ), И команда (ПРОМПТ), режиссёр
    раскладок дробит НАДВОЕ - обвязка уходит на обычный текстовый слайд,
    промпт на командный. Поэтому обвязку меряем текстовым лимитом, а не
    командным. Командный лимит - только для слайда, где одна голая команда.
    """
    if slide["prompt"] and not slide["body"]:
        return (*LIMIT_COMMAND, "команда")
    if is_photo:
        return (*LIMIT_PHOTO, "с фото")
    return (*LIMIT_TEXT, "текст")


def check(path: Path, photo_slides: set[int], quiet: bool) -> int:
    text = path.read_text(encoding="utf-8")
    slides = parse_slides(text)
    problems: list[str] = []
    notes: list[str] = []

    seen_phrases: dict[str, int] = {}

    for i, s in enumerate(slides, 1):
        body = s["body"]
        lines = [l for l in body.split("\n") if l.strip()]
        words = len(body.split())
        max_words, max_lines, kind = limits_for(s, i in photo_slides)
        head = f"слайд {i:2d} ({kind})"

        if words > max_words:
            problems.append(f"{head}: {words} слов, лимит {max_words} - не влезет в рамку")
        elif kind == "с фото" and words > PHOTO_SOFT:
            notes.append(f"{head}: {words} слов рядом с фото - у узких раскладок обрежется, проверь рендером")
        if len(lines) > max_lines:
            problems.append(f"{head}: {len(lines)} строк, лимит {max_lines}")

        # абзац вместо построчного вывода: длинный текст в одну строку
        if len(lines) == 1 and words > 20:
            problems.append(f"{head}: текст одним абзацем - режиссёр положит его ОДНИМ буллетом, разбей по предложениям")

        # заголовок
        title = s["title"]
        if title:
            acc = title.count("[[")
            if acc != 1 and s["type"] != "титульный":
                problems.append(f"{head}: акцентов [[...]] в заголовке {acc}, нужен ровно 1")
            plain = title.replace("[[", "").replace("]]", "")
            if len(plain) > TITLE_MAX_CHARS:
                notes.append(f"{head}: заголовок {len(plain)} символов - уедет в три строки и поджмёт текст")

        # промпт: не должно быть НЕСКОЛЬКО отдельных CLI-команд подряд на
        # одном слайде (ученик не поймёт, что копировать построчно и в
        # несколько заходов - ровно так ошиблись со связкой /plugin
        # marketplace add + /plugin install). Многострочный ЖИВОЙ текст
        # запроса нейросети (естественная речь, не набор команд) - это
        # нормальный командный слайд, не блокер.
        if s["prompt"]:
            plines = [l for l in s["prompt"].split("\n") if l.strip()]
            cli_like = [l for l in plines if re.match(r"^(npx|npm|git|uipro|brew|pip3?|python3?|/\S)", l.strip())]
            if len(cli_like) > 1:
                problems.append(f"{head}: в ПРОМПТ {len(cli_like)} отдельных CLI-команд подряд - ученик копирует и вводит их по одной")
            if "===" in s["prompt"]:
                problems.append(f"{head}: в ПРОМПТ попал служебный маркер")

        # построчные проверки текста
        for line in lines:
            for sw in STOP_WORDS:
                if sw in line.lower():
                    problems.append(f"{head}: книжное слово «{sw}» - скажи это вслух, так не говорят")
            if looks_nominal(line):
                notes.append(f"{head}: похоже на назывной обрубок - «{line[:60]}»")

            # дубли фраз между слайдами
            key = " ".join(re.findall(r"[а-яёa-z]+", line.lower())[:6])
            if len(key.split()) >= 5:
                if key in seen_phrases and seen_phrases[key] != i:
                    notes.append(f"{head}: начало фразы повторяет слайд {seen_phrases[key]} - «{line[:50]}»")
                else:
                    seen_phrases[key] = i

    dashes = text.count("—")
    if dashes:
        problems.append(f"длинных тире в файле: {dashes} (в проекте запрещены, только «-»)")

    # Карта «номер в тексте -> номер в собранной презентации».
    # Слайд с обвязкой И промптом режиссёр дробит надвое, поэтому дальше по
    # презентации нумерация уезжает. Без этой карты легко передать --photo с
    # номерами из презентации и получить ложные срабатывания.
    split_at = [i for i, s in enumerate(slides, 1) if s["prompt"] and s["body"]]

    if not quiet:
        print(f"Слайдов в тексте: {len(slides)} | в презентации будет: {len(slides) + len(split_at)}")
        if split_at:
            print(f"Дробятся надвое (обвязка + команда): {split_at}")
            shift_map = []
            shift = 0
            for i in range(1, len(slides) + 1):
                if i in split_at:
                    shift_map.append(f"{i}→{i + shift}+{i + shift + 1}")
                    shift += 1
            print(f"Сдвиг нумерации: {', '.join(shift_map)}")
        if photo_slides:
            print(f"Фото на (номера ПО ТЕКСТУ): {sorted(photo_slides)}")

    if problems:
        print(f"\n❌ Блокеры ({len(problems)}):")
        for p in problems:
            print(f"   {p}")
    if notes and not quiet:
        print(f"\n⚠️  Посмотреть глазами ({len(notes)}):")
        for n in notes:
            print(f"   {n}")
    if not problems:
        print("\n✅ Лимиты и формат в норме - можно собирать.")

    return 1 if problems else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Проверка текста слайдов перед сборкой")
    ap.add_argument("file", help="файл ===SLIDE=== (обычно SLIDES.txt)")
    ap.add_argument("--photo", default="", help="номера слайдов с фото через запятую: 2,8,11")
    ap.add_argument("--quiet", action="store_true", help="только блокеры")
    args = ap.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"Файла нет: {path}")
        return 2

    photo = set()
    if args.photo.strip():
        photo = {int(x) for x in args.photo.replace(" ", "").split(",") if x}

    return check(path, photo, args.quiet)


if __name__ == "__main__":
    sys.exit(main())
