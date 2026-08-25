#!/usr/bin/env python3
"""
Редактор копии Google-презентации по JSON-плану правок.

Копирует существующую презу (сохраняя картинки/дизайн) и применяет план:
правит текст по месту, удаляет, дублирует и переставляет слайды.

Формат плана (машинный двойник edit-map.md):
    {
      "source_id": "ID исходной презы",          # опц., можно из CLI
      "title": "Название копии",                  # опц., можно из CLI
      "edit":     [ {"slide": 12, "set": {"title": "...", "image:0": {"src": "https://..."}}} ],
      "delete":   [ {"from": 440, "to": 498}, {"slide": 233} ],
      "add":      [ {"donor": 230, "after": 4, "set": {"title": "..."}} ],
      "move":     [ {"slide": 25, "after": 5} ],
      "addImage": [ {"slide": 12, "src": "https://...", "x_emu": 914400, "y_emu": 914400, "w_emu": 2743200, "h_emu": 1828800} ],
    }

Картинки: значение роли image:N в set - объект {"src": URL|путь|drive_id}; addImage - новая картинка по позиции/размеру (EMU). src доставляется через Drive на момент вставки.

Номера слайдов - в ИСХОДНОЙ нумерации копии (до мутаций), резолвятся по первой карте.
"after": N - "после слайда, который БЫЛ номером N" (по slide_id-якорю), не позиция N.

Запуск из корня проекта:
    tools/venv/bin/python tools/converters/apply_edits.py <source_id> <plan.json> ["Название"]
"""
import sys
import json
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))


def resolve_plan(plan: dict, slide_map: list, image_map: list = None) -> tuple:
    """
    Резолвит «номер + роль» из плана в конкретные object_id по карте.

    Возвращает (resolved, errors):
      resolved = {
        "edits":       [ {"object_id", "text"} ],
        "image_edits": [ {"object_id", "src"} ],
        "delete_ids":  set(slide_id),
        "adds":        [ {"donor_id", "after_anchor_id", "set"} ],
        "moves":       [ {"slide_id", "after_anchor_id"} ],
        "image_adds":  [ {"slide_id", "src", "x_emu", "y_emu", "w_emu", "h_emu"} ],
      }
      errors = [str, ...]  - человекочитаемые причины нерезолва.

    Чистая функция: в Google ничего не шлёт. Если errors не пуст -
    вызывающий код ОБЯЗАН остановиться и не применять правки.
    """
    by_number = {s['number']: s for s in slide_map}
    by_number_img = {}
    for s in (image_map or []):
        by_number_img[s['number']] = {im['role']: im['object_id'] for im in s['images']}
    errors = []

    # Сначала собираем удаляемые номера - нужны для проверки якорей add/move
    deleted_numbers = set()
    for d in plan.get('delete', []):
        if 'slide' in d:
            nums = [d['slide']]
        elif 'from' in d and 'to' in d:
            if d['from'] > d['to']:
                errors.append(f"delete: диапазон from={d['from']} > to={d['to']} (границы перепутаны)")
                continue
            nums = list(range(d['from'], d['to'] + 1))
        else:
            errors.append(f"delete: запись {d} без 'slide' или пары 'from'/'to'")
            continue
        for n in nums:
            if n not in by_number:
                errors.append(f"delete: слайда #{n} нет в презентации")
                continue
            deleted_numbers.add(n)

    edits = []
    image_edits = []
    for e in plan.get('edit', []):
        if 'slide' not in e:
            errors.append(f"edit: запись {e} без 'slide'")
            continue
        n = e['slide']
        s = by_number.get(n)
        if not s:
            errors.append(f"edit: слайда #{n} нет в презентации")
            continue
        roles = {b['role']: b['object_id'] for b in s['blocks']}
        for role, value in e.get('set', {}).items():
            if role.startswith('image:'):
                oid = by_number_img.get(n, {}).get(role)
                if not oid:
                    errors.append(
                        f"edit: на слайде #{n} нет слота картинки '{role}' "
                        f"(есть: {sorted(by_number_img.get(n, {}))})")
                    continue
                src = value.get('src') if isinstance(value, dict) else None
                if not src:
                    errors.append(f"edit: слот {role} на слайде #{n} без 'src' (ожидался объект {{'src': ...}})")
                    continue
                image_edits.append({'object_id': oid, 'src': src})
            else:
                oid = roles.get(role)
                if not oid:
                    errors.append(
                        f"edit: на слайде #{n} нет блока с ролью '{role}' "
                        f"(есть: {sorted(roles)})")
                    continue
                edits.append({'object_id': oid, 'text': value})

    delete_ids = {by_number[n]['slide_id'] for n in deleted_numbers}

    adds = []
    for a in plan.get('add', []):
        # 'at':'end' (или 'after':'end') - добавить В КОНЕЦ без якоря. Нужно для
        # сборки с нуля из эталона: все исходные слайды удаляются, якорить не на что.
        append_end = a.get('at') == 'end' or a.get('after') == 'end'
        if 'donor' not in a or (not append_end and 'after' not in a):
            errors.append(f"add: запись {a} требует 'donor' и 'after' (или 'at':'end')")
            continue
        donor = by_number.get(a['donor'])
        if not donor:
            errors.append(f"add: донор #{a['donor']} не найден")
            continue
        after_anchor_id = None
        if not append_end:
            anchor = by_number.get(a['after'])
            if not anchor:
                errors.append(f"add: якорь after #{a['after']} не найден")
                continue
            if a['after'] in deleted_numbers:
                errors.append(f"add: якорь after #{a['after']} попал в удаляемые слайды")
                continue
            after_anchor_id = anchor['slide_id']
        donor_img_roles = by_number_img.get(a['donor'], {})
        for role, value in a.get('set', {}).items():
            if role.startswith('image:'):
                if role not in donor_img_roles:
                    errors.append(f"add: у донора #{a['donor']} нет слота картинки '{role}' "
                                  f"(есть: {sorted(donor_img_roles)})")
                elif not (isinstance(value, dict) and value.get('src')):
                    errors.append(f"add: слот {role} (донор #{a['donor']}) без 'src'")
        adds.append({
            'donor_id': donor['slide_id'],
            'after_anchor_id': after_anchor_id,  # None => в конец
            'set': a.get('set', {}),
        })

    moves = []
    for m in plan.get('move', []):
        if 'slide' not in m or 'after' not in m:
            errors.append(f"move: запись {m} требует 'slide' и 'after'")
            continue
        s = by_number.get(m['slide'])
        if not s:
            errors.append(f"move: слайда #{m['slide']} нет в презентации")
            continue
        anchor = by_number.get(m['after'])
        if not anchor:
            errors.append(f"move: якорь after #{m['after']} не найден")
            continue
        if m['after'] in deleted_numbers:
            errors.append(f"move: якорь after #{m['after']} попал в удаляемые слайды")
            continue
        moves.append({'slide_id': s['slide_id'], 'after_anchor_id': anchor['slide_id']})

    image_adds = []
    for ai in plan.get('addImage', []):
        if 'slide' not in ai or 'src' not in ai:
            errors.append(f"addImage: запись {ai} требует 'slide' и 'src'")
            continue
        n = ai['slide']
        s = by_number.get(n)
        if not s:
            errors.append(f"addImage: слайда #{n} нет в презентации")
            continue
        if n in deleted_numbers:
            errors.append(f"addImage: слайд #{n} попал в удаляемые слайды")
            continue
        missing = [k for k in ('x_emu', 'y_emu', 'w_emu', 'h_emu') if k not in ai]
        if missing:
            errors.append(f"addImage на #{n}: нет полей {missing}")
            continue
        image_adds.append({
            'slide_id': s['slide_id'], 'src': ai['src'],
            'x_emu': ai['x_emu'], 'y_emu': ai['y_emu'],
            'w_emu': ai['w_emu'], 'h_emu': ai['h_emu'],
        })

    resolved = {'edits': edits, 'image_edits': image_edits, 'image_adds': image_adds,
                'delete_ids': delete_ids, 'adds': adds, 'moves': moves}
    return resolved, errors


def build_text_replace_requests(object_id: str, text: str) -> list:
    """
    Точечная замена текста в блоке по object_id: удалить всё + вставить новое.

    Адресно по object_id (НЕ replaceAllText по совпадению) - неуникальный текст
    не заденет другие блоки. Инлайн-оформление внутри блока при этом сбрасывается
    к стилю блока (заявленная граница: пёстрые блоки правим руками).

    Разметка [[...]] в тексте красит кусок в настроенный цветовой акцент:
    после insertText добавляется updateTextStyle на размеченные диапазоны - см.
    text_styling.build_text_requests_with_accent. Без [[...]] поведение прежнее.
    """
    from text_styling import build_text_requests_with_accent
    return build_text_requests_with_accent(object_id, text)


def compute_insertion_index(order: list, anchor_id: str) -> int:
    """
    insertionIndex для updateSlidesPosition, чтобы слайд встал СРАЗУ ПОСЛЕ якоря.

    order - текущий порядок slide_id ДО перемещения. Для перемещения одного слайда
    (вверх или вниз) корректный индекс = позиция якоря + 1 (доказано тестом-симулятором
    в test_apply_edits.py). Если якорь последний - вернёт len(order) (слайд в конец).
    """
    return order.index(anchor_id) + 1


def _batch(slides_service, presentation_id, requests):
    """Шлёт один batchUpdate, если есть запросы. Возвращает ответ или None."""
    if not requests:
        return None
    return slides_service.presentations().batchUpdate(
        presentationId=presentation_id, body={'requests': requests}).execute()


def _current_order(slides_service, presentation_id):
    """Текущий порядок slide_id в презентации (свежее чтение)."""
    pres = slides_service.presentations().get(presentationId=presentation_id).execute()
    return [s['objectId'] for s in pres.get('slides', [])]


def apply_resolved(slides_service, presentation_id, resolved, drive_service=None, folder_id=None):
    """
    Применяет резолвленный план к презентации в безопасном порядке.
    Возвращает счётчики для отчёта. drive_service/folder_id нужны для доставки картинок.
    """
    from google_to_text import build_slide_map
    from text_to_google import duplicate_slide
    from image_ops import (build_image_map, resolve_media, build_replace_image_request,
                           build_create_image_request)

    counts = {'edited': 0, 'deleted': 0, 'added': 0, 'moved': 0,
              'images_set': 0, 'images_added': 0}

    # 1. Правки текста существующих блоков (один батч)
    edit_reqs = []
    for e in resolved['edits']:
        edit_reqs += build_text_replace_requests(e['object_id'], e['text'])
    if edit_reqs:
        _batch(slides_service, presentation_id, edit_reqs)
        counts['edited'] = len(resolved['edits'])

    # 1b. Подмена картинок в существующих слотах (resolve_media -> replaceImage, батч)
    img_edit_reqs = []
    for ie in resolved.get('image_edits', []):
        url = resolve_media(ie['src'], drive_service, folder_id)
        img_edit_reqs.append(build_replace_image_request(ie['object_id'], url))
    if img_edit_reqs:
        _batch(slides_service, presentation_id, img_edit_reqs)
        counts['images_set'] = len(img_edit_reqs)

    # 1c. Добавление новых картинок на существующие слайды (createImage, батч)
    add_img_reqs = []
    for ia in resolved.get('image_adds', []):
        url = resolve_media(ia['src'], drive_service, folder_id)
        add_img_reqs.append(build_create_image_request(
            ia['slide_id'], url, ia['x_emu'], ia['y_emu'], ia['w_emu'], ia['h_emu']))
    if add_img_reqs:
        _batch(slides_service, presentation_id, add_img_reqs)
        counts['images_added'] = len(add_img_reqs)

    # 2. Дубли доноров - запоминаем новые slide_id + якорь + тексты
    new_slides = []
    for a in resolved['adds']:
        new_id = duplicate_slide(slides_service, presentation_id, a['donor_id'])
        new_slides.append({
            'new_id': new_id,
            'after_anchor_id': a['after_anchor_id'],
            'set': a['set'],
        })
        time.sleep(1.0)  # бережём квоту Google
    counts['added'] = len(new_slides)

    # 3. Перечитать карты один раз и вписать текст И картинки в новые слайды по ролям
    if new_slides:
        pres = slides_service.presentations().get(presentationId=presentation_id).execute()
        text_by_id = {s['slide_id']: s for s in build_slide_map(pres)}
        img_by_id = {s['slide_id']: s for s in build_image_map(pres)}
        fill_reqs = []
        for ns in new_slides:
            ts = text_by_id.get(ns['new_id'])
            text_roles = {b['role']: b['object_id'] for b in ts['blocks']} if ts else {}
            isl = img_by_id.get(ns['new_id'])
            img_roles = {im['role']: im['object_id'] for im in isl['images']} if isl else {}
            for role, value in ns['set'].items():
                if role.startswith('image:'):
                    oid = img_roles.get(role)
                    if oid:
                        url = resolve_media(value['src'], drive_service, folder_id)
                        fill_reqs.append(build_replace_image_request(oid, url))
                else:
                    oid = text_roles.get(role)
                    if oid:
                        fill_reqs += build_text_replace_requests(oid, value)
        _batch(slides_service, presentation_id, fill_reqs)

    # 4. Удаления (один батч, по slide_id - порядок не важен)
    if resolved['delete_ids']:
        del_reqs = [{'deleteObject': {'objectId': sid}} for sid in resolved['delete_ids']]
        _batch(slides_service, presentation_id, del_reqs)
        counts['deleted'] = len(resolved['delete_ids'])

    # 5. Позиционирование: moves + расстановка новых слайдов после их якорей.
    #    По одному, со свежим чтением порядка перед каждым (insertionIndex зависит
    #    от текущего расположения).
    positional = [(m['slide_id'], m['after_anchor_id']) for m in resolved['moves']]
    positional += [(ns['new_id'], ns['after_anchor_id']) for ns in new_slides]
    for slide_id, anchor_id in positional:
        order = _current_order(slides_service, presentation_id)
        if slide_id not in order:
            continue
        if anchor_id is None:
            idx = len(order)  # в конец (для add с 'at':'end')
        elif anchor_id not in order:
            continue
        else:
            idx = compute_insertion_index(order, anchor_id)
        _batch(slides_service, presentation_id, [{
            'updateSlidesPosition': {
                'slideObjectIds': [slide_id],
                'insertionIndex': idx,
            }
        }])
        counts['moved'] += 1
        time.sleep(1.0)

    return counts


def main():
    import argparse
    from googleapiclient.discovery import build
    from text_to_google import get_credentials, copy_template, load_config, share_presentation
    from google_to_text import build_slide_map, extract_presentation_id
    from image_ops import build_image_map

    parser = argparse.ArgumentParser(description='Редактор копии Google-презентации по плану правок')
    parser.add_argument('source', help='URL или ID исходной презентации')
    parser.add_argument('plan', help='JSON-файл плана правок')
    parser.add_argument('title', nargs='?', default=None, help='Название копии')
    args = parser.parse_args()

    plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
    source_id = extract_presentation_id(args.source) or plan.get('source_id')
    title = args.title or plan.get('title') or 'Копия презентации (правки)'

    creds = get_credentials()
    drive = build('drive', 'v3', credentials=creds)
    slides = build('slides', 'v1', credentials=creds)
    cfg = load_config()

    print("Копирую исходную презу (картинки и дизайн сохраняются)...")
    copy_id = copy_template(drive, source_id, title, cfg.get('folder_id'))
    print(f"   копия: {copy_id}")

    pres = slides.presentations().get(presentationId=copy_id).execute()
    slide_map = build_slide_map(pres)
    image_map = build_image_map(pres)
    print(f"   слайдов в копии: {len(slide_map)}")

    resolved, errors = resolve_plan(plan, slide_map, image_map)
    if errors:
        print("\nСТОП: план не резолвится по карте копии. Ошибки:")
        for e in errors:
            print(f"   - {e}")
        print("\nКопия создана, но правки НЕ применены. Поправь план и запусти заново.")
        print(f"Ссылка на нетронутую копию: https://docs.google.com/presentation/d/{copy_id}/edit")
        sys.exit(1)

    print("План резолвлен. Применяю правки...")
    counts = apply_resolved(slides, copy_id, resolved, drive, cfg.get('folder_id'))

    # Отчёт по факту (перечитать)
    pres2 = slides.presentations().get(presentationId=copy_id).execute()
    final_count = len(pres2.get('slides', []))

    share = cfg.get('share_with')
    if share:
        share_presentation(drive, copy_id, share)

    print("\n=== ОТЧЁТ ===")
    print(f"   изменено блоков: {counts['edited']}")
    print(f"   подменено картинок: {counts['images_set']}")
    print(f"   добавлено картинок: {counts['images_added']}")
    print(f"   удалено слайдов: {counts['deleted']}")
    print(f"   добавлено слайдов: {counts['added']}")
    print(f"   переставлено: {counts['moved']}")
    print(f"   итоговое число слайдов: {final_count}")
    print(f"\nГотово: https://docs.google.com/presentation/d/{copy_id}/edit")


if __name__ == '__main__':
    main()
