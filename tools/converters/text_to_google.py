#!/usr/bin/env python3
"""
Конвертер текста в Google Slides презентацию
Автор: AI-помощник для автора

Использование:
    python text_to_google.py input.txt "Название презентации"

Требования:
    1. oauth_client.json — OAuth credentials из Google Cloud Console
    2. config.json — настройки (ID шаблона, папка для сохранения)

При первом запуске откроется браузер для авторизации.
Токен сохранится в token.json — повторная авторизация не нужна.

Формат входного файла:
    ===SLIDE===
    ТИП: контент
    ЗАГОЛОВОК: Текст заголовка
    ТЕКСТ:
    - Пункт 1
    - Пункт 2
    СПИКЕР: Речь спикера (отображается на слайде!)
    ВИЗУАЛ: Описание визуала (в заметки для дизайнера)

Типы слайдов (соответствуют порядку в шаблоне):
    1. титульный — первый слайд презентации
    2. контент — обычный слайд с текстом (по умолчанию)
    3. фото — слайд с местом для фотографии
    4. чат — "напишите в чат"
    5. бонус — анонс бонуса
    6. cta — призыв к действию с QR-кодом
    7. промпт — слайд с промптом (выделенный блок для копирования)
"""

# Маппинг названий типов слайдов на индексы в шаблоне (0-based)
SLIDE_TYPE_MAP = {
    'титульный': 0,
    'title': 0,
    'контент': 1,
    'content': 1,
    'фото': 2,
    'photo': 2,
    'чат': 3,
    'chat': 3,
    'интерактив': 3,  # Alias для чата
    'бонус': 4,
    'bonus': 4,
    'cta': 5,
    'призыв': 5,
    'qr': 5,          # Alias для CTA
    'промпт': 6,
    'prompt': 6,
    'команда': 6,     # alias: команда для нейросети в уроках = выделенный блок для копирования
    'заключение': 7,  # Новый тип
    'conclusion': 7,
}

import sys
import re
import json
import time
from pathlib import Path

try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    print("❌ Не установлены библиотеки Google API")
    print("   Установите командой: pip install google-api-python-client google-auth google-auth-oauthlib")
    sys.exit(1)


# Путь к файлам конфигурации
SCRIPT_DIR = Path(__file__).parent
OAUTH_CLIENT_FILE = SCRIPT_DIR / "oauth_client.json"  # OAuth credentials (скачивается из Google Cloud)
TOKEN_FILE = SCRIPT_DIR / "token.json"  # Сохранённый токен (создаётся автоматически)


def save_credentials(credentials, token_file=TOKEN_FILE):
    """Сохраняет OAuth-токен с правами только для владельца файла."""
    token_file.write_text(credentials.to_json(), encoding="utf-8")
    try:
        token_file.chmod(0o600)
    except OSError:
        pass
CONFIG_FILE = SCRIPT_DIR / "config.json"


def load_config() -> dict:
    """Загружает конфигурацию из config.json"""
    if not CONFIG_FILE.exists():
        print(f"❌ Файл конфигурации не найден: {CONFIG_FILE}")
        print("\n📝 Создайте файл config.json с содержимым:")
        print(json.dumps({
            "template_id": "ID_ВАШЕГО_ШАБЛОНА_ИЗ_URL",
            "share_with": "your-email@gmail.com",
            "folder_id": ""
        }, ensure_ascii=False, indent=2))
        print("\n💡 Как получить template_id:")
        print("   Откройте шаблон в Google Slides")
        print("   Скопируйте ID из URL: https://docs.google.com/presentation/d/[ВОТ_ЭТОТ_ID]/edit")
        sys.exit(1)

    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_credentials():
    """
    Получает credentials для Google API через OAuth.

    При первом запуске:
    1. Откроется браузер для авторизации
    2. Войдите в свой Google аккаунт
    3. Дайте разрешение приложению
    4. Токен сохранится в token.json для будущих запусков
    """
    SCOPES = [
        'https://www.googleapis.com/auth/presentations',
        'https://www.googleapis.com/auth/documents.readonly',
        'https://www.googleapis.com/auth/drive'
    ]

    credentials = None

    # Проверяем, есть ли сохранённый токен
    if TOKEN_FILE.exists():
        try:
            credentials = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        except Exception:
            # Токен повреждён или со старым набором scopes — игнорируем, переавторизуемся
            credentials = None

    # Если токена нет или он просрочен — запускаем авторизацию
    if not credentials or not credentials.valid:
        refreshed = False
        if credentials and credentials.expired and credentials.refresh_token:
            # Пробуем обновить просроченный токен
            print("🔄 Обновляю токен авторизации...")
            try:
                credentials.refresh(Request())
                refreshed = True
            except Exception as e:
                # refresh_token отозван/истёк (invalid_grant) — удаляем мёртвый токен
                print(f"⚠️ Не удалось обновить токен ({type(e).__name__}). Запускаю авторизацию заново.")
                try:
                    TOKEN_FILE.unlink()
                except OSError:
                    pass
                credentials = None
        if not refreshed and not (credentials and credentials.valid):
            # Первичная авторизация через браузер
            if not OAUTH_CLIENT_FILE.exists():
                print(f"❌ Файл OAuth не найден: {OAUTH_CLIENT_FILE}")
                print("\n📝 Как получить oauth_client.json:")
                print("   1. Перейдите на https://console.cloud.google.com/apis/credentials")
                print("   2. Нажмите '+ Create Credentials' → 'OAuth client ID'")
                print("   3. Выберите 'Desktop app'")
                print("   4. Скачайте JSON и сохраните как oauth_client.json")
                sys.exit(1)

            print("🌐 Открываю браузер для авторизации...")
            print("   Войдите в свой Google аккаунт и дайте разрешение")

            flow = InstalledAppFlow.from_client_secrets_file(
                str(OAUTH_CLIENT_FILE), SCOPES
            )
            credentials = flow.run_local_server(port=0)
            print("✅ Авторизация успешна!")

        # Сохраняем токен для будущих запусков
        save_credentials(credentials)

    return credentials


def parse_slides(text: str) -> list[dict]:
    """Парсит текстовый файл и возвращает список слайдов."""
    slides = []

    # Разделяем по маркеру слайда
    raw_slides = re.split(r'===SLIDE===', text)

    for slide_index, raw_slide in enumerate(raw_slides):
        # отрезаем закрывающий маркер и всё, что после него: иначе ===END===
        # прилипает к последнему полю слайда и уезжает в презентацию как текст
        # (на командных слайдах последним идёт ПРОМПТ - маркер попадал прямо
        # в плашку с командой, которую ученик копирует)
        raw_slide = re.split(r'===END===', raw_slide)[0]
        raw_slide = raw_slide.strip()
        if not raw_slide:
            continue

        slide = {
            'type': 'контент',  # тип по умолчанию
            'title': '',
            'content': '',
            'speaker_notes': '',
            'visual': '',
            # Новые поля для разных типов слайдов
            'lesson_number': '',   # Для титульного слайда
            'cta': '',             # Для интерактива (чат)
            'prompt': '',          # Для слайда с промптом
            'description': '',     # Для подзаголовков
        }

        lines = raw_slide.split('\n')
        current_field = None
        current_content = []

        for line in lines:
            # Проверяем, начинается ли новое поле
            if line.startswith('ТИП:') or line.startswith('TYPE:'):
                if current_field and current_content:
                    slide[current_field] = '\n'.join(current_content).strip()
                slide_type = line.split(':', 1)[1].strip().lower()
                slide['type'] = slide_type
                current_field = None
                current_content = []
            elif line.startswith('ЗАГОЛОВОК:'):
                if current_field and current_content:
                    slide[current_field] = '\n'.join(current_content).strip()
                current_field = 'title'
                current_content = [line[10:].strip()]
            elif line.startswith('ТЕКСТ:'):
                if current_field and current_content:
                    slide[current_field] = '\n'.join(current_content).strip()
                current_field = 'content'
                current_content = [line[6:].strip()]
            elif line.startswith('СПИКЕР:'):
                if current_field and current_content:
                    slide[current_field] = '\n'.join(current_content).strip()
                current_field = 'speaker_notes'
                current_content = [line[7:].strip()]
            elif line.startswith('ВИЗУАЛ:'):
                if current_field and current_content:
                    slide[current_field] = '\n'.join(current_content).strip()
                current_field = 'visual'
                current_content = [line[7:].strip()]
            elif line.startswith('НОМЕР_УРОКА:'):
                if current_field and current_content:
                    slide[current_field] = '\n'.join(current_content).strip()
                current_field = 'lesson_number'
                current_content = [line[12:].strip()]
            elif line.startswith('ПРИЗЫВ:'):
                if current_field and current_content:
                    slide[current_field] = '\n'.join(current_content).strip()
                current_field = 'cta'
                current_content = [line[7:].strip()]
            elif line.startswith('ПРОМПТ:'):
                if current_field and current_content:
                    slide[current_field] = '\n'.join(current_content).strip()
                current_field = 'prompt'
                current_content = [line[7:].strip()]
            elif line.startswith('ОПИСАНИЕ:'):
                if current_field and current_content:
                    slide[current_field] = '\n'.join(current_content).strip()
                current_field = 'description'
                current_content = [line[9:].strip()]
            elif current_field:
                current_content.append(line)

        # Сохраняем последнее поле
        if current_field and current_content:
            slide[current_field] = '\n'.join(current_content).strip()

        # Первый слайд по умолчанию — титульный
        if len(slides) == 0 and slide['type'] == 'контент':
            slide['type'] = 'титульный'

        # Добавляем только если есть хоть что-то
        if slide['title'] or slide['content']:
            slides.append(slide)

    return slides


def copy_template(drive_service, template_id: str, title: str, folder_id: str = None) -> str:
    """Копирует шаблон и возвращает ID новой презентации"""
    body = {'name': title}
    if folder_id:
        body['parents'] = [folder_id]

    try:
        copied = drive_service.files().copy(
            fileId=template_id,
            body=body,
            supportsAllDrives=True
        ).execute()
        return copied['id']
    except HttpError as e:
        if e.resp.status == 404:
            print(f"❌ Шаблон не найден: {template_id}")
            print("   Проверьте ID шаблона в config.json")
            print("   Убедитесь, что шаблон расшарен на сервисный аккаунт")
        else:
            print(f"❌ Ошибка при копировании шаблона: {e}")
        sys.exit(1)


def share_presentation(drive_service, file_id: str, email: str):
    """Расшаривает презентацию на указанный email"""
    try:
        drive_service.permissions().create(
            fileId=file_id,
            body={
                'type': 'user',
                'role': 'writer',
                'emailAddress': email
            },
            sendNotificationEmail=False
        ).execute()
    except HttpError as e:
        print(f"⚠️ Не удалось расшарить на {email}: {e}")


def get_template_slide_ids(slides_service, presentation_id: str) -> list[str]:
    """
    Получает ID всех слайдов-шаблонов из презентации.

    Возвращает список ID слайдов в порядке их расположения в шаблоне:
    [0] — титульный
    [1] — контент
    [2] — фото
    [3] — чат
    [4] — бонус
    [5] — cta
    """
    presentation = slides_service.presentations().get(
        presentationId=presentation_id
    ).execute()

    slides = presentation.get('slides', [])
    if not slides:
        print("❌ В шаблоне нет слайдов")
        sys.exit(1)

    return [s['objectId'] for s in slides]


def duplicate_slide(slides_service, presentation_id: str, slide_id: str) -> str:
    """Дублирует слайд и возвращает ID нового слайда"""
    import uuid
    new_slide_id = f'slide_{uuid.uuid4().hex[:8]}'

    requests = [{
        'duplicateObject': {
            'objectId': slide_id,
            'objectIds': {
                slide_id: new_slide_id
            }
        }
    }]

    slides_service.presentations().batchUpdate(
        presentationId=presentation_id,
        body={'requests': requests}
    ).execute()

    return new_slide_id


def replace_text_in_slide(slides_service, presentation_id: str, replacements: dict, page_object_ids: list = None):
    """
    Заменяет плейсхолдеры на реальный текст.

    Args:
        slides_service: Google Slides API сервис
        presentation_id: ID презентации
        replacements: Словарь {плейсхолдер: новый_текст}
        page_object_ids: Список ID слайдов для замены (если None — во всей презентации)
    """
    requests = []

    for placeholder, text in replacements.items():
        request = {
            'replaceAllText': {
                'containsText': {
                    'text': placeholder,
                    'matchCase': True
                },
                'replaceText': text or ''
            }
        }
        # Если указаны конкретные слайды — ограничиваем замену только ими
        if page_object_ids:
            request['replaceAllText']['pageObjectIds'] = page_object_ids
        requests.append(request)

    if requests:
        slides_service.presentations().batchUpdate(
            presentationId=presentation_id,
            body={'requests': requests}
        ).execute()


def delete_slide(slides_service, presentation_id: str, slide_id: str):
    """Удаляет слайд из презентации"""
    requests = [{
        'deleteObject': {
            'objectId': slide_id
        }
    }]

    slides_service.presentations().batchUpdate(
        presentationId=presentation_id,
        body={'requests': requests}
    ).execute()


def move_slide_to_end(slides_service, presentation_id: str, slide_id: str, total_slides: int):
    """
    Перемещает слайд в конец презентации.

    Args:
        slides_service: Google Slides API сервис
        presentation_id: ID презентации
        slide_id: ID слайда для перемещения
        total_slides: Общее количество слайдов в презентации
    """
    requests = [{
        'updateSlidesPosition': {
            'slideObjectIds': [slide_id],
            'insertionIndex': total_slides
        }
    }]

    slides_service.presentations().batchUpdate(
        presentationId=presentation_id,
        body={'requests': requests}
    ).execute()


def add_speaker_notes(slides_service, presentation_id: str, slide_id: str, notes: str):
    """Добавляет заметки спикера к слайду"""
    if not notes:
        return

    # Получаем информацию о слайде чтобы найти notes page
    presentation = slides_service.presentations().get(
        presentationId=presentation_id
    ).execute()

    # Находим нужный слайд
    for slide in presentation.get('slides', []):
        if slide['objectId'] == slide_id:
            notes_page = slide.get('slideProperties', {}).get('notesPage', {})
            notes_shape_id = None

            # Ищем текстовый элемент в notes page
            for element in notes_page.get('pageElements', []):
                if element.get('shape', {}).get('shapeType') == 'TEXT_BOX':
                    notes_shape_id = element['objectId']
                    break

            if notes_shape_id:
                requests = [{
                    'insertText': {
                        'objectId': notes_shape_id,
                        'text': notes,
                        'insertionIndex': 0
                    }
                }]
                try:
                    slides_service.presentations().batchUpdate(
                        presentationId=presentation_id,
                        body={'requests': requests}
                    ).execute()
                except HttpError:
                    pass  # Игнорируем ошибки с заметками
            break


def fill_slide_and_duplicate(slides_service, presentation_id: str, template_slide_id: str,
                              slide_data: dict, slide_index: int) -> str:
    """
    Дублирует шаблонный слайд и заполняет его данными.

    Алгоритм:
    1. Дублируем слайд-шаблон (новый слайд содержит плейсхолдеры)
    2. Заменяем плейсхолдеры ТОЛЬКО в новом слайде (pageObjectIds)
    3. Шаблон остаётся нетронутым для следующих слайдов

    Логика контента:
    - ТЕКСТ (BULLETS) — буллеты на слайде
    - СПИКЕР — речь спикера (идёт ТОЛЬКО в заметки!)
    - ВИЗУАЛ — описание для дизайнера (идёт ТОЛЬКО в заметки!)
    - ПРОМПТ — готовый промпт для копирования (на слайде)
    - CTA — короткий призыв к действию (на слайде)
    - LESSON_NUMBER — номер урока (на слайде)

    Возвращает ID нового слайда.
    """
    # Сначала дублируем слайд (с плейсхолдерами)
    new_slide_id = duplicate_slide(slides_service, presentation_id, template_slide_id)

    # Подготавливаем данные для замены плейсхолдеров
    title = slide_data.get('title', '')
    bullets = slide_data.get('content', '')
    speaker = slide_data.get('speaker_notes', '')
    visual = slide_data.get('visual', '')
    lesson_number = slide_data.get('lesson_number', '')
    cta = slide_data.get('cta', '')
    prompt = slide_data.get('prompt', '')
    description = slide_data.get('description', '')

    # Заменяем плейсхолдеры РАЗДЕЛЬНО для каждого поля
    replacements = {
        # Базовые плейсхолдеры
        '{{ TITLE }}': title,
        '{{TITLE}}': title,

        # Для титульного слайда
        '{{ LESSON_NUMBER }}': lesson_number,
        '{{LESSON_NUMBER}}': lesson_number,

        # Для контентных слайдов (буллеты)
        '{{ BULLETS }}': bullets,
        '{{BULLETS}}': bullets,
        '{{ TEXT }}': bullets,
        '{{TEXT}}': bullets,

        # Для интерактива (чат)
        '{{ CTA }}': cta,
        '{{CTA}}': cta,

        # Для промпта
        '{{ PROMPT }}': prompt,
        '{{PROMPT}}': prompt,

        # Для бонусов/подзаголовков
        '{{ SUBTITLE }}': description,
        '{{SUBTITLE}}': description,
        '{{ DESCRIPTION }}': description,
        '{{DESCRIPTION}}': description,

        # Для заключения
        '{{ CONCLUSION }}': title,
        '{{CONCLUSION}}': title,

        # Старые плейсхолдеры (для совместимости)
        '{{ CONTENT }}': bullets,  # По умолчанию только буллеты (НЕ СПИКЕР!)
        '{{CONTENT}}': bullets,
        '{{ BODY }}': bullets,
        '{{BODY}}': bullets,
    }

    replace_text_in_slide(slides_service, presentation_id, replacements, page_object_ids=[new_slide_id])

    # Добавляем заметки спикера (СПИКЕР и ВИЗУАЛ идут только в заметки!)
    notes_parts = []
    if speaker:
        notes_parts.append(f"🎤 СПИКЕР:\n{speaker}")
    if visual:
        notes_parts.append(f"\n🎨 ВИЗУАЛ:\n{visual}")

    if notes_parts:
        notes_text = '\n\n'.join(notes_parts)
        add_speaker_notes(slides_service, presentation_id, new_slide_id, notes_text)

    return new_slide_id


def get_template_index_for_slide(slide_type: str, num_templates: int) -> int:
    """
    Возвращает индекс шаблона для данного типа слайда.

    Если тип не найден или индекс больше количества шаблонов,
    возвращает индекс 1 (контентный слайд) или 0 если шаблон один.
    """
    slide_type_lower = slide_type.lower().strip()
    template_index = SLIDE_TYPE_MAP.get(slide_type_lower, 1)

    # Если индекс больше количества шаблонов, используем контентный (1) или первый (0)
    if template_index >= num_templates:
        template_index = min(1, num_templates - 1)

    return template_index


def create_google_slides(slides_data: list[dict], title: str, design: str = None) -> str:
    """
    Создаёт презентацию в Google Slides на основе шаблона.

    Поддерживает шаблоны с несколькими типами слайдов:
    - Слайд 1: титульный
    - Слайд 2: контент
    - Слайд 3: фото
    - Слайд 4: чат
    - Слайд 5: бонус
    - Слайд 6: cta
    - Слайд 7: промпт (выделенный блок для промптов)

    Алгоритм:
    1. Копирует шаблон
    2. Для каждого слайда выбирает нужный шаблон по полю ТИП:
    3. Заполняет плейсхолдеры и дублирует
    4. Удаляет оригинальные шаблонные слайды
    5. Возвращает URL
    """
    config = load_config()
    credentials = get_credentials()

    # Выбираем шаблон по дизайну
    templates = config.get('templates', {})
    if design and design in templates:
        template_id = templates[design]
        print(f"🎨 Дизайн: {design}")
    elif design and design not in templates:
        available = ', '.join(templates.keys()) if templates else 'нет'
        print(f"❌ Дизайн \"{design}\" не найден. Доступные: {available}")
        sys.exit(1)
    else:
        template_id = config['template_id']

    # Создаём сервисы
    drive_service = build('drive', 'v3', credentials=credentials)
    slides_service = build('slides', 'v1', credentials=credentials)

    print(f"📋 Копирую шаблон...")
    presentation_id = copy_template(
        drive_service,
        template_id,
        title,
        config.get('folder_id')
    )

    print(f"🎨 Создаю {len(slides_data)} слайдов...")

    # Оценка времени
    estimated_time = len(slides_data) * 3  # 3 секунды на слайд
    estimated_min = estimated_time // 60
    estimated_sec = estimated_time % 60
    if estimated_min > 0:
        print(f"   ⏱️  Примерное время: {estimated_min} мин {estimated_sec} сек (квота Google API: 60 запросов/мин)")
    else:
        print(f"   ⏱️  Примерное время: {estimated_sec} сек (квота Google API: 60 запросов/мин)")

    # Получаем ID всех шаблонных слайдов
    template_slide_ids = get_template_slide_ids(slides_service, presentation_id)
    num_templates = len(template_slide_ids)
    print(f"   Найдено шаблонов: {num_templates}")

    created_slide_ids = []
    total = len(slides_data)
    # Текущее кол-во слайдов в презентации (начинаем с шаблонов)
    current_total_slides = num_templates

    for i, slide_data in enumerate(slides_data):
        slide_type = slide_data.get('type', 'контент')
        title_preview = slide_data['title'][:35] + '...' if len(slide_data['title']) > 35 else slide_data['title']
        print(f"   [{i + 1}/{total}] {slide_type}: {title_preview}")

        # Выбираем шаблон по типу слайда
        template_index = get_template_index_for_slide(slide_type, num_templates)
        template_to_use = template_slide_ids[template_index]

        # Заполняем и дублируем
        new_slide_id = fill_slide_and_duplicate(
            slides_service, presentation_id, template_to_use, slide_data, i
        )
        created_slide_ids.append(new_slide_id)
        current_total_slides += 1

        # Перемещаем слайд в конец презентации
        # Это нужно, т.к. разные типы шаблонов на разных позициях
        move_slide_to_end(slides_service, presentation_id, new_slide_id, current_total_slides)

        # Добавляем заметки для дизайнера (только ВИЗУАЛ, т.к. СПИКЕР уже на слайде)
        if slide_data['visual']:
            notes_text = f"🎨 ВИЗУАЛ:\n{slide_data['visual']}"
            add_speaker_notes(slides_service, presentation_id, new_slide_id, notes_text)

        # Задержка для соблюдения квоты Google API (60 запросов/мин)
        # Каждый слайд делает ~4-5 API запросов:
        # 1. Дублирование слайда
        # 2. Замена текста (batched)
        # 3. Перемещение слайда
        # 4. Добавление заметок (если есть)
        # При 60 запросов/мин = 1 запрос/сек
        # Безопасная задержка: 3 секунды на слайд (4-5 запросов за 3 сек = ~1.3-1.6 запросов/сек)
        time.sleep(3.0)

    # Слайды уже в правильном порядке благодаря обратной обработке

    # Удаляем все оригинальные шаблонные слайды
    print("🗑️  Удаляю шаблонные слайды...")
    for template_id in template_slide_ids:
        try:
            delete_slide(slides_service, presentation_id, template_id)
        except Exception:
            pass

    # Расшариваем на пользователя
    share_email = config.get('share_with')
    if share_email:
        print(f"🔗 Расшариваю на {share_email}...")
        share_presentation(drive_service, presentation_id, share_email)

    url = f"https://docs.google.com/presentation/d/{presentation_id}/edit"
    return url


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Конвертер текста в Google Slides')
    parser.add_argument('input_file', help='Текстовый файл со слайдами')
    parser.add_argument('title', nargs='?', default=None, help='Название презентации')
    parser.add_argument('-d', '--design', default=None,
                        help='Название дизайна из config.json → templates (например: default, new)')

    args = parser.parse_args()

    title = args.title or Path(args.input_file).stem

    # Читаем входной файл
    try:
        with open(args.input_file, 'r', encoding='utf-8') as f:
            text = f.read()
    except FileNotFoundError:
        print(f"❌ Файл не найден: {args.input_file}")
        sys.exit(1)

    # Парсим слайды
    slides = parse_slides(text)

    if not slides:
        print("❌ Не найдено ни одного слайда в файле")
        print("   Убедитесь, что слайды разделены маркером ===SLIDE===")
        sys.exit(1)

    print(f"\n🚀 Создание презентации \"{title}\"")
    print(f"   Найдено слайдов: {len(slides)}")

    # Создаём презентацию
    url = create_google_slides(slides, title, design=args.design)

    print(f"\n✅ Готово!")
    print(f"📍 Ссылка: {url}")
    print(f"\n📌 Теперь можно:")
    print(f"   1. Открыть презентацию по ссылке")
    print(f"   2. Проверить форматирование")
    print(f"   3. Дизайнер может доработать визуал")


if __name__ == '__main__':
    main()
