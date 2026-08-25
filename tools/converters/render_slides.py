#!/usr/bin/env python3
"""
Рендер слайдов Google Slides в PNG — «глаза» агента.

Зачем: до этого инструмента агент видел только ТЕКСТ презентации, но не
оформление. Этот скрипт вытягивает каждый слайд как картинку (PNG), чтобы
агент мог открыть её через Read и проверить глазами: фото на месте,
раскладки чередуются, заголовки бело-лаймовые, ничего не вылезло за рамку.
Так визуальный контроль (раньше — глаза автора) переходит к агенту.

Использование:
    python render_slides.py "https://docs.google.com/presentation/d/ID/edit"
    python render_slides.py ID --slides 1-5,8
    python render_slides.py ID --out-dir /tmp/etalon --size LARGE

На выходе в папке:
    slide_001.png, slide_002.png, ...   — по картинке на слайд
    manifest.json                        — карта: номер -> objectId -> файл

Технически: presentations().get() даёт список слайдов, для каждого слайда
presentations().pages().getThumbnail() возвращает временный URL картинки
(живёт ~30 минут), мы сразу качаем PNG в файл. Никакого base64 в контекст —
только лёгкие per-slide PNG, которые агент читает по одному.

Переиспользует готовые кирпичики проекта:
    get_credentials        (text_to_google.py)   — OAuth-токен
    extract_presentation_id, parse_slide_range (google_to_text.py)
    read_presentation      (template_inventory.py) — один get()
Основа функции рендера — fetch_thumbnail_url из template_inventory.py,
здесь расширена параметром размера превью.
"""

from __future__ import annotations

import sys
import json
import time
import argparse
import urllib.request
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    print("❌ Не установлены библиотеки Google API")
    print("   Установите: pip install google-api-python-client google-auth google-auth-oauthlib")
    sys.exit(1)

from text_to_google import get_credentials
from google_to_text import extract_presentation_id, parse_slide_range
from template_inventory import read_presentation


def thumbnail_url(slides_service, presentation_id: str, page_object_id: str,
                  size: str = "LARGE") -> str | None:
    """
    Временный contentUrl превью одного слайда через getThumbnail.
    size: LARGE (~1600px), MEDIUM (~800px), SMALL (~200px). None при ошибке.

    Расширение fetch_thumbnail_url (template_inventory.py) — добавлен
    управляемый размер картинки, чтобы агенту хватало чёткости для проверки.
    """
    try:
        resp = slides_service.presentations().pages().getThumbnail(
            presentationId=presentation_id,
            pageObjectId=page_object_id,
            thumbnailProperties_mimeType="PNG",
            thumbnailProperties_thumbnailSize=size,
        ).execute()
        return resp.get("contentUrl")
    except TypeError:
        # Старые версии клиента не принимают thumbnailProperties_* как kwargs —
        # падаем на дефолтный размер без параметров.
        try:
            resp = slides_service.presentations().pages().getThumbnail(
                presentationId=presentation_id, pageObjectId=page_object_id
            ).execute()
            return resp.get("contentUrl")
        except HttpError:
            return None
    except HttpError:
        return None


def download_png(url: str, dest: Path) -> bool:
    """Качает PNG по временному URL сразу в файл. True при успехе."""
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            dest.write_bytes(r.read())
        return True
    except Exception as e:  # сетевые сбои не должны валить весь прогон
        print(f"   ⚠️ не скачал {dest.name}: {type(e).__name__}: {e}")
        return False


def render(presentation_id: str, out_dir: Path, slide_filter: set[int] | None,
           size: str = "LARGE", pause: float = 0.1) -> dict:
    """
    Рендерит слайды презентации в PNG. Возвращает manifest (dict).
    slide_filter — множество 1-based номеров или None (все слайды).
    """
    credentials = get_credentials()
    slides_service = build("slides", "v1", credentials=credentials)

    print("Загружаю презентацию...")
    presentation = read_presentation(slides_service, presentation_id)
    title = presentation.get("title", "Без названия")
    slides = presentation.get("slides", [])
    print(f"   {title}: {len(slides)} слайдов")

    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "presentation_id": presentation_id,
        "title": title,
        "size": size,
        "slides": [],
    }

    rendered = 0
    for idx, slide in enumerate(slides):
        number = idx + 1
        if slide_filter is not None and number not in slide_filter:
            continue
        page_id = slide.get("objectId")
        png_name = f"slide_{number:03d}.png"
        png_path = out_dir / png_name

        url = thumbnail_url(slides_service, presentation_id, page_id, size)
        ok = bool(url) and download_png(url, png_path)
        if ok:
            rendered += 1
            print(f"   ✓ слайд {number:>3} -> {png_name}")
        else:
            print(f"   ✗ слайд {number:>3} не отрендерен")

        manifest["slides"].append({
            "number": number,
            "objectId": page_id,
            "png": png_name if ok else None,
        })
        # бережём квоту getThumbnail на больших деках
        if pause:
            time.sleep(pause)

    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nГотово: {rendered}/{len(manifest['slides'])} слайдов в {out_dir}")
    print(f"   манифест: {manifest_path}")
    return manifest


def main():
    parser = argparse.ArgumentParser(
        description="Рендер слайдов Google Slides в PNG для визуального самоконтроля")
    parser.add_argument("presentation", help="URL или ID презентации")
    parser.add_argument("--slides", default=None,
                        help="Диапазон слайдов, напр. 1-5,8 (по умолчанию все)")
    parser.add_argument("--out-dir", default=None,
                        help="Папка для PNG (по умолчанию renders/<id>)")
    parser.add_argument("--size", default="LARGE", choices=["LARGE", "MEDIUM", "SMALL"],
                        help="Размер превью (по умолчанию LARGE ~1600px)")
    parser.add_argument("--pause", type=float, default=0.1,
                        help="Пауза между слайдами, сек (бережёт квоту на больших деках)")
    args = parser.parse_args()

    presentation_id = extract_presentation_id(args.presentation)
    slide_filter = parse_slide_range(args.slides)
    out_dir = Path(args.out_dir) if args.out_dir else Path("renders") / presentation_id

    render(presentation_id, out_dir, slide_filter, size=args.size, pause=args.pause)


if __name__ == "__main__":
    main()
