#!/usr/bin/env python3
"""
Движок постановки картинок в Google Slides: подмена картинки в рамку дизайнера
(replaceImage) и добавление новой (createImage), плюс доставка файла в Drive,
чтобы у Google был публичный URL на момент вставки.

Модуль используется редактором копии и слоем изображений.
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from template_inventory import ratio_label  # переиспользуем метку пропорции


def build_image_map(presentation: dict) -> list[dict]:
    """Карта слотов картинок по слайдам: image:N -> object_id + пропорция рамки + размеры.

    Параллельна build_slide_map (та намеренно картинки НЕ включает - там только текст).
    В карту идут только элементы-картинки (ключ 'image' в pageElement).
    """
    out = []
    for idx, slide in enumerate(presentation.get("slides", []), start=1):
        images = []
        n = 0
        for el in slide.get("pageElements", []):
            if "image" not in el:
                continue
            size = el.get("size", {})
            w = size.get("width", {}).get("magnitude", 0)
            h = size.get("height", {}).get("magnitude", 0)
            tr = el.get("transform", {})
            w_eff = w * (tr.get("scaleX", 1) or 1)
            h_eff = h * (tr.get("scaleY", 1) or 1)
            images.append({
                "object_id": el.get("objectId"),
                "role": f"image:{n}",
                "ratio": ratio_label(w_eff, h_eff),
                "w_emu": w_eff,
                "h_emu": h_eff,
            })
            n += 1
        out.append({"number": idx, "slide_id": slide.get("objectId"), "images": images})
    return out


def build_replace_image_request(image_object_id: str, url: str, method: str = "CENTER_CROP") -> dict:
    """Запрос replaceImage: меняет содержимое картинки, сохраняя рамку/позицию/кадрирование.
    method: CENTER_CROP (заполнить рамку, обрезав лишнее) или CENTER_INSIDE (вписать целиком)."""
    return {
        "replaceImage": {
            "imageObjectId": image_object_id,
            "url": url,
            "imageReplaceMethod": method,
        }
    }


def build_create_image_request(page_object_id: str, url: str,
                               x_emu: float, y_emu: float, w_emu: float, h_emu: float) -> dict:
    """Запрос createImage: вставляет новую картинку на слайд по позиции/размеру (EMU)."""
    return {
        "createImage": {
            "url": url,
            "elementProperties": {
                "pageObjectId": page_object_id,
                "size": {
                    "width": {"magnitude": w_emu, "unit": "EMU"},
                    "height": {"magnitude": h_emu, "unit": "EMU"},
                },
                "transform": {
                    "scaleX": 1, "scaleY": 1,
                    "translateX": x_emu, "translateY": y_emu,
                    "unit": "EMU",
                },
            },
        }
    }


def drive_public_url(file_id: str) -> str:
    """Прямой URL скачивания файла Drive (Google Slides умеет тянуть его на вставке картинки)."""
    return f"https://drive.google.com/uc?export=download&id={file_id}"


def resolve_media_kind(src: str) -> str:
    """Классифицирует источник картинки: 'url' (http/https), 'local' (путь/файл с расширением), 'drive_id'."""
    if src.startswith("http://") or src.startswith("https://"):
        return "url"
    if "/" in src or src.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
        return "local"
    return "drive_id"


def upload_to_drive_public(drive_service, file_path: str, folder_id: str = None) -> str:
    """Заливает локальный файл в Drive, делает доступным 'по ссылке', возвращает file_id.
    После replaceImage/createImage Google копирует пиксели внутрь презы - временный файл можно удалить.

    Локальная заливка изредка рвётся BrokenPipeError на первой же попытке
    (обрыв соединения, не ошибка API) - retry с паузой почти всегда лечит."""
    import time
    from googleapiclient.http import MediaFileUpload

    meta = {"name": Path(file_path).name}
    if folder_id:
        meta["parents"] = [folder_id]

    last_err = None
    for attempt in range(3):
        try:
            media = MediaFileUpload(file_path, resumable=False)
            created = drive_service.files().create(body=meta, media_body=media, fields="id").execute()
            file_id = created["id"]
            drive_service.permissions().create(
                fileId=file_id, body={"role": "reader", "type": "anyone"}).execute()
            return file_id
        except (BrokenPipeError, ConnectionError, OSError) as e:
            last_err = e
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
    raise last_err


def resolve_media(src: str, drive_service=None, folder_id: str = None) -> str:
    """Превращает источник картинки в URL, который Google Slides сможет вытянуть на вставке.
    http(s) -> как есть; drive id -> публичный URL; локальный путь -> заливка в Drive + публичный URL."""
    kind = resolve_media_kind(src)
    if kind == "url":
        return src
    if kind == "drive_id":
        return drive_public_url(src)
    file_id = upload_to_drive_public(drive_service, src, folder_id)
    return drive_public_url(file_id)


def replace_image(slides_service, presentation_id: str, image_object_id: str,
                  url: str, method: str = "CENTER_CROP"):
    """Подменяет картинку по object_id, сохраняя рамку. Один batchUpdate."""
    slides_service.presentations().batchUpdate(
        presentationId=presentation_id,
        body={"requests": [build_replace_image_request(image_object_id, url, method)]},
    ).execute()


def create_image(slides_service, presentation_id: str, page_object_id: str,
                 url: str, x_emu: float, y_emu: float, w_emu: float, h_emu: float):
    """Вставляет новую картинку на слайд. Один batchUpdate."""
    slides_service.presentations().batchUpdate(
        presentationId=presentation_id,
        body={"requests": [build_create_image_request(page_object_id, url, x_emu, y_emu, w_emu, h_emu)]},
    ).execute()
