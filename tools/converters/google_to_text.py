#!/usr/bin/env python3
"""
Извлечение текста из Google Slides в формат ===SLIDE===
Автор: AI-помощник для автора

Использование:
    python google_to_text.py "https://docs.google.com/presentation/d/ID/edit"
    python google_to_text.py ID --slides 5-15
    python google_to_text.py ID --slides 1,3,7-10 --output my_slides.txt
    python google_to_text.py ID --chunk 30

Скрипт читает Google Slides презентацию через API и сохраняет
текст каждого слайда в формате ===SLIDE===, который можно затем
отредактировать и конвертировать обратно через convert_google.sh.

Для больших презентаций (100+ слайдов) используйте --chunk N,
чтобы разбить на файлы по N слайдов — так удобнее работать
с каждой частью отдельно и не перегружать контекст.
"""

from __future__ import annotations  # аннотации-«ленивые», совместимость с Python 3.9

import sys
import re
import argparse
from pathlib import Path

# Добавляем директорию скрипта в PATH для импорта text_to_google
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    print("❌ Не установлены библиотеки Google API")
    print("   Установите командой: pip install google-api-python-client google-auth google-auth-oauthlib")
    sys.exit(1)

from text_to_google import get_credentials


def extract_presentation_id(url_or_id: str) -> str:
    """Извлекает ID презентации из URL или возвращает как есть."""
    if 'docs.google.com' in url_or_id:
        match = re.search(r'/d/([a-zA-Z0-9_-]+)', url_or_id)
        if match:
            return match.group(1)
    return url_or_id.strip()


def parse_slide_range(range_str: str) -> set[int] | None:
    """
    Парсит строку с номерами слайдов в множество (1-based).

    Примеры:
        "5-15"      → {5, 6, ..., 15}
        "1,3,7-10"  → {1, 3, 7, 8, 9, 10}
        None        → None (все слайды)
    """
    if not range_str:
        return None

    result = set()
    for part in range_str.split(','):
        part = part.strip()
        if '-' in part:
            start, end = part.split('-', 1)
            result.update(range(int(start), int(end) + 1))
        else:
            result.add(int(part))
    return result


def extract_text(text_elements: list) -> str:
    """Извлекает чистый текст из массива textElements Google Slides API."""
    parts = []
    for te in text_elements:
        text_run = te.get('textRun', {})
        content = text_run.get('content', '')
        if content:
            parts.append(content)
    return ''.join(parts).rstrip('\n')


def parse_notes(raw_notes: str) -> tuple[str, str]:
    """
    Разбирает заметки спикера на секции СПИКЕР и ВИЗУАЛ.

    text_to_google.py записывает заметки в формате:
        🎤 СПИКЕР:
        текст спикера

        🎨 ВИЗУАЛ:
        описание визуала

    Если маркеров нет — всё считается речью спикера.
    """
    speaker = ''
    visual = ''

    if '🎤 СПИКЕР:' in raw_notes or '🎨 ВИЗУАЛ:' in raw_notes:
        # Есть маркеры — разбираем
        parts = re.split(r'(?:🎤 СПИКЕР:|🎨 ВИЗУАЛ:)', raw_notes)
        markers = re.findall(r'(🎤 СПИКЕР:|🎨 ВИЗУАЛ:)', raw_notes)

        for i, marker in enumerate(markers):
            text = parts[i + 1].strip() if i + 1 < len(parts) else ''
            if '🎤' in marker:
                speaker = text
            elif '🎨' in marker:
                visual = text
    else:
        # Нет маркеров — всё как спикер
        speaker = raw_notes.strip()

    return speaker, visual


def extract_slide_data(slide: dict, slide_index: int) -> dict | None:
    """
    Извлекает данные из одного слайда Google Slides API.

    Использует placeholder.type для определения title/body:
    - TITLE, CENTERED_TITLE → заголовок
    - BODY, SUBTITLE → текст/контент
    """
    title = ''
    body_parts = []
    other_texts = []

    # Извлекаем текст из элементов слайда
    for element in slide.get('pageElements', []):
        shape = element.get('shape', {})
        if not shape:
            continue

        text_elements = shape.get('text', {}).get('textElements', [])
        if not text_elements:
            continue

        text = extract_text(text_elements)
        if not text.strip():
            continue

        # Определяем роль элемента по placeholder.type
        placeholder = shape.get('placeholder', {})
        ph_type = placeholder.get('type', '')

        if ph_type in ('TITLE', 'CENTERED_TITLE'):
            title = text.strip()
        elif ph_type in ('BODY', 'SUBTITLE'):
            body_parts.append(text.strip())
        else:
            # Элемент без placeholder — собираем отдельно
            other_texts.append(text.strip())

    # Если placeholder не нашлось — используем эвристику
    if not title and not body_parts and other_texts:
        title = other_texts[0]
        body_parts = other_texts[1:]
    elif not title and other_texts:
        # Есть body из placeholder, но нет title — берём первый other
        title = other_texts[0]
    elif title and other_texts:
        # Есть title и body, а other добавляем к body
        body_parts.extend(other_texts)

    body = '\n'.join(body_parts)

    # Пропускаем пустые слайды
    if not title and not body:
        return None

    # Извлекаем заметки спикера
    raw_notes = ''
    notes_page = slide.get('slideProperties', {}).get('notesPage', {})
    for element in notes_page.get('pageElements', []):
        shape = element.get('shape', {})
        placeholder = shape.get('placeholder', {})
        # В notes page ищем именно BODY (не slide thumbnail)
        if placeholder.get('type') == 'BODY':
            text_elements = shape.get('text', {}).get('textElements', [])
            raw_notes = extract_text(text_elements)
            break

    # Если BODY не нашёлся в notes, ищем любой TEXT_BOX
    if not raw_notes:
        for element in notes_page.get('pageElements', []):
            shape = element.get('shape', {})
            if shape.get('shapeType') == 'TEXT_BOX':
                text_elements = shape.get('text', {}).get('textElements', [])
                raw_notes = extract_text(text_elements)
                if raw_notes.strip():
                    break

    speaker, visual = parse_notes(raw_notes)

    # Определяем тип слайда
    slide_type = 'титульный' if slide_index == 0 else 'контент'

    return {
        'type': slide_type,
        'title': title,
        'content': body,
        'speaker_notes': speaker,
        'visual': visual,
    }


def build_slide_map(presentation: dict) -> list[dict]:
    """
    Строит карту слайд→object_id→текст из загруженной презентации.

    Это мост между «номер слайда + роль» (как пишет человек в плане правок)
    и object_id текстовых блоков (как требует Slides API).

    Роли уникальны в пределах слайда:
      - первый TITLE/CENTERED_TITLE  → "title"
      - первый BODY/SUBTITLE         → "body"
      - все прочие блоки и повторы    → "other:0", "other:1", ... (по порядку чтения)

    В карту попадают только shape-элементы с непустым текстом.
    Картинки, линии, таблицы не включаются - мы их не редактируем.
    """
    slides_out = []
    for idx, slide in enumerate(presentation.get('slides', []), start=1):
        blocks = []
        other_n = 0
        used = set()
        for el in slide.get('pageElements', []):
            shape = el.get('shape')
            if not shape:
                continue
            text_elements = shape.get('text', {}).get('textElements', [])
            text = extract_text(text_elements)
            if not text.strip():
                continue
            ph_type = shape.get('placeholder', {}).get('type', '')
            if ph_type in ('TITLE', 'CENTERED_TITLE') and 'title' not in used:
                role = 'title'
            elif ph_type in ('BODY', 'SUBTITLE') and 'body' not in used:
                role = 'body'
            else:
                role = f'other:{other_n}'
                other_n += 1
            used.add(role)
            blocks.append({
                'object_id': el.get('objectId'),
                'role': role,
                'text': text.strip(),
            })
        slides_out.append({
            'number': idx,
            'slide_id': slide.get('objectId'),
            'blocks': blocks,
        })
    return slides_out


def format_slide_to_text(slide_data: dict) -> str:
    """Форматирует данные слайда в текстовый блок ===SLIDE==="""
    lines = ['===SLIDE===']
    lines.append(f"ТИП: {slide_data['type']}")

    if slide_data.get('title'):
        lines.append(f"ЗАГОЛОВОК: {slide_data['title']}")

    if slide_data.get('content'):
        lines.append('ТЕКСТ:')
        lines.append(slide_data['content'])

    if slide_data.get('speaker_notes'):
        lines.append(f"СПИКЕР: {slide_data['speaker_notes']}")

    if slide_data.get('visual'):
        lines.append(f"ВИЗУАЛ: {slide_data['visual']}")

    return '\n'.join(lines)


def sanitize_filename(name: str) -> str:
    """Убирает спецсимволы из названия для использования в имени файла."""
    # Заменяем недопустимые символы на _
    sanitized = re.sub(r'[/\\:*?"<>|]', '_', name)
    # Убираем лишние пробелы
    sanitized = re.sub(r'\s+', ' ', sanitized).strip()
    return sanitized


def main():
    parser = argparse.ArgumentParser(
        description='Извлечение Google Slides в формат ===SLIDE==='
    )
    parser.add_argument('presentation',
                        help='URL или ID презентации Google Slides')
    parser.add_argument('-s', '--slides', default=None,
                        help='Номера слайдов: "5-15" или "1,3,7-10" (по умолчанию: все)')
    parser.add_argument('-o', '--output', default=None,
                        help='Имя выходного файла (по умолчанию: {название}_SLIDES.txt)')
    parser.add_argument('-c', '--chunk', type=int, default=None,
                        help='Разбить на файлы по N слайдов (например: --chunk 30)')
    parser.add_argument('--map', nargs='?', const='', default=None,
                        help='Вывести карту слайд→object_id→текст в JSON-файл (для apply_edits.py)')

    args = parser.parse_args()

    # Извлекаем ID презентации
    presentation_id = extract_presentation_id(args.presentation)

    # Парсим диапазон слайдов
    slide_range = parse_slide_range(args.slides)

    # Авторизация и API
    credentials = get_credentials()
    slides_service = build('slides', 'v1', credentials=credentials)

    # Получаем презентацию
    print(f"📥 Загружаю презентацию...")
    try:
        presentation = slides_service.presentations().get(
            presentationId=presentation_id
        ).execute()
    except HttpError as e:
        if e.resp.status == 404:
            print(f"❌ Презентация не найдена: {presentation_id}")
            print("   Проверьте ID или URL")
        elif e.resp.status == 403:
            print(f"❌ Нет доступа к презентации: {presentation_id}")
            print("   Убедитесь, что презентация расшарена на ваш аккаунт")
        else:
            print(f"❌ Ошибка Google API: {e}")
        sys.exit(1)

    pres_title = presentation.get('title', 'Без названия')
    all_slides = presentation.get('slides', [])
    total_slides = len(all_slides)

    # Режим карты: выдаём слайд→object_id→текст и выходим (для apply_edits.py)
    if args.map is not None:
        import json as _json
        slide_map = build_slide_map(presentation)
        map_path = args.map or f"{sanitize_filename(pres_title)}_MAP.json"
        Path(map_path).write_text(
            _json.dumps(slide_map, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"\nКарта сохранена: {map_path}")
        print(f"   слайдов: {len(slide_map)}")
        print("   первые слайды:")
        for s in slide_map[:5]:
            preview = (s['blocks'][0]['text'][:120] if s['blocks'] else '(пусто)')
            print(f"     #{s['number']} [{s['slide_id']}] {len(s['blocks'])} блок(ов): {preview}")
        return

    print(f"   Название: {pres_title}")
    print(f"   Слайдов: {total_slides}")

    if slide_range:
        range_desc = args.slides
        print(f"   Извлекаем: слайды {range_desc}")

    # Извлекаем данные слайдов
    extracted = []
    for i, slide in enumerate(all_slides):
        slide_number = i + 1  # 1-based

        # Фильтр по диапазону
        if slide_range and slide_number not in slide_range:
            continue

        data = extract_slide_data(slide, i)
        if data:
            extracted.append(data)

    if not extracted:
        print("❌ Не удалось извлечь ни одного слайда с текстом")
        sys.exit(1)

    # Определяем базовое имя файла
    if args.output:
        base_name = args.output
    else:
        safe_name = sanitize_filename(pres_title)
        base_name = f"{safe_name}_SLIDES.txt"

    base_path = Path(base_name)
    stem = base_path.stem
    suffix = base_path.suffix or '.txt'

    # Разбиваем на чанки или пишем всё в один файл
    if args.chunk and args.chunk > 0 and len(extracted) > args.chunk:
        # Разбивка на части
        chunks = [extracted[i:i + args.chunk] for i in range(0, len(extracted), args.chunk)]
        written_files = []

        for chunk_idx, chunk in enumerate(chunks, 1):
            chunk_file = f"{stem}_часть{chunk_idx}{suffix}"
            text_blocks = [format_slide_to_text(s) for s in chunk]
            output_text = '\n\n'.join(text_blocks) + '\n'
            Path(chunk_file).write_text(output_text, encoding='utf-8')
            written_files.append((chunk_file, len(chunk)))

        print(f"\n✅ Готово! Разбито на {len(chunks)} файлов по ~{args.chunk} слайдов:")
        for fname, count in written_files:
            print(f"   📍 {fname} ({count} слайдов)")
        print(f"\n   Всего: {len(extracted)} слайдов")
        print(f"\n📌 Теперь можно:")
        print(f"   1. Работать с каждой частью отдельно")
        print(f"   2. Конвертировать: ./convert_google.sh \"файл.txt\" \"Название\" [-d дизайн]")
    else:
        # Один файл
        text_blocks = [format_slide_to_text(s) for s in extracted]
        output_text = '\n\n'.join(text_blocks) + '\n'
        Path(base_name).write_text(output_text, encoding='utf-8')

        print(f"\n✅ Готово!")
        print(f"📍 Файл: {base_name} ({len(extracted)} слайдов)")
        if len(extracted) > 50:
            print(f"\n💡 Совет: для больших презентаций используйте --chunk N")
            print(f"   Пример: --chunk 30 разобьёт на файлы по 30 слайдов")
        print(f"\n📌 Теперь можно:")
        print(f"   1. Отредактировать текст в файле")
        print(f"   2. Конвертировать обратно: ./convert_google.sh \"{base_name}\" \"Название\" [-d дизайн]")


if __name__ == '__main__':
    main()
