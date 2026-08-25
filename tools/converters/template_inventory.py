#!/usr/bin/env python3
"""
Инвентаризация раскладок: из старой презентации выделяет ~10-20 уникальных
раскладок и собирает палитру доноров-эталонов для наполнения новой презы.

Результат используется как основа собственной библиотеки доноров.
"""
from __future__ import annotations

import html as _html
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from google_to_text import extract_text  # переиспользуем извлечение текста

# Стандартный широкоформатный слайд (16:9) в EMU - фолбэк, если pageSize не задан
DEFAULT_PAGE_W = 9144000
DEFAULT_PAGE_H = 5143500


def _element_center(el: dict) -> tuple[float, float] | None:
    """Центр элемента в EMU: (translateX + width*scaleX/2, translateY + height*scaleY/2).
    None, если геометрии нет."""
    size = el.get("size", {})
    w = size.get("width", {}).get("magnitude", 0)
    h = size.get("height", {}).get("magnitude", 0)
    tr = el.get("transform", {})
    if not w and not tr:
        return None
    sx = tr.get("scaleX", 1) or 1
    sy = tr.get("scaleY", 1) or 1
    tx = tr.get("translateX", 0) or 0
    ty = tr.get("translateY", 0) or 0
    cx = tx + (w * sx) / 2
    cy = ty + (h * sy) / 2
    return cx, cy


def element_grid_cell(el: dict, page_w: int, page_h: int) -> tuple[str, str]:
    """Метка ячейки сетки 3x3 для элемента: (X в L/C/R, Y в T/M/B).
    Без геометрии - центр ("C","M")."""
    center = _element_center(el)
    if center is None:
        return ("C", "M")
    cx, cy = center
    xs = ["L", "C", "R"]
    ys = ["T", "M", "B"]
    gx = min(2, max(0, int(cx / page_w * 3))) if page_w else 1
    gy = min(2, max(0, int(cy / page_h * 3))) if page_h else 1
    return (xs[gx], ys[gy])


def _line_bucket(text: str) -> str:
    """Бакет по числу непустых строк текста: '1' / '2-4' / '5+'."""
    lines = len([ln for ln in text.split("\n") if ln.strip()])
    if lines <= 1:
        return "1"
    if lines <= 4:
        return "2-4"
    return "5+"


def build_layout_signature(slide: dict, page_w: int, page_h: int) -> dict:
    """Огрублённая подпись РАСКЛАДКИ слайда (форма без контента).

    Считает типы элементов, их ячейки сетки 3x3 и для текста - бакет строк.
    Картинки/таблицы/линии учитываются по типу; пустые декоративные shape
    игнорируются (нестабильны и фрагментируют кластеры).
    """
    counts = {"text": 0, "image": 0, "table": 0, "line": 0}
    text_bins, image_bins, table_dims = [], [], []

    for el in slide.get("pageElements", []):
        if "image" in el:
            counts["image"] += 1
            gx, gy = element_grid_cell(el, page_w, page_h)
            image_bins.append([gx, gy])
        elif "table" in el:
            counts["table"] += 1
            rows = el["table"].get("rows", 0)
            cols = el["table"].get("columns", 0)
            table_dims.append(f"{rows}x{cols}")
        elif "line" in el:
            counts["line"] += 1
        elif "shape" in el:
            text = extract_text(el["shape"].get("text", {}).get("textElements", []))
            if not text.strip():
                continue  # пустой декоративный shape - пропускаем
            counts["text"] += 1
            gx, gy = element_grid_cell(el, page_w, page_h)
            text_bins.append([gx, gy, _line_bucket(text)])

    return {
        "counts": counts,
        "text_bins": sorted(text_bins),
        "image_bins": sorted(image_bins),
        "table_dims": sorted(table_dims),
        "layout_id": slide.get("slideProperties", {}).get("layoutObjectId"),
    }


def signature_key(sig: dict) -> str:
    """Стабильный ключ кластеризации. layout_id НЕ включаем (доп-сигнал, может пересплитить)."""
    core = {k: v for k, v in sig.items() if k != "layout_id"}
    return json.dumps(core, sort_keys=True, ensure_ascii=False)


def text_stats(slide: dict) -> tuple[int, int]:
    """(число блоков с непустым текстом, суммарная длина текста) - для выбора донора."""
    n_blocks = 0
    total_len = 0
    for el in slide.get("pageElements", []):
        shape = el.get("shape")
        if not shape:
            continue
        text = extract_text(shape.get("text", {}).get("textElements", [])).strip()
        if text:
            n_blocks += 1
            total_len += len(text)
    return n_blocks, total_len


_CTA_WORDS = ("чат", "ссылк", "переход", "вступ", "подпиш", "регистрац", "жми", "кнопк", "qr")


def guess_archetype(sig: dict, texts: list[str]) -> str:
    """Человекочитаемое имя раскладки по сигнатуре + текстам.
    CTA опознаём семантически (ключевые слова), остальное - структурно.
    """
    blob = " ".join(texts).lower()
    if any(w in blob for w in _CTA_WORDS):
        return "CTA / призыв в чат"

    c = sig["counts"]
    if c["table"] >= 1:
        dims = sig["table_dims"][0] if sig["table_dims"] else "?"
        return f"таблица {dims}"
    if c["image"] >= 1 and c["text"] >= 1:
        return "фото+текст"
    if c["image"] >= 1 and c["text"] == 0:
        return "только фото / фон"
    if any(b[2] == "5+" for b in sig["text_bins"]):
        return "перечисление (буллеты)"
    if c["text"] == 1 and sig["text_bins"] and sig["text_bins"][0][2] == "1":
        return "обложка / заголовок"
    if c["text"] >= 2:
        return "текст (несколько блоков)"
    return "прочее"


def choose_donor(members: list[dict]) -> dict:
    """Самый «чистый» представитель кластера: максимум заполненности,
    при равенстве - наименьший номер слайда (детерминизм)."""
    return max(members, key=lambda m: (m["n_blocks"], m["text_len"], -m["number"]))


def _slide_texts(slide: dict) -> list[str]:
    """Все непустые тексты слайда (для guess_archetype)."""
    out = []
    for el in slide.get("pageElements", []):
        shape = el.get("shape")
        if not shape:
            continue
        text = extract_text(shape.get("text", {}).get("textElements", [])).strip()
        if text:
            out.append(text)
    return out


def cluster_slides(presentation: dict) -> list[dict]:
    """Группирует слайды по ключу сигнатуры. На кластер: имя архетипа, донор,
    участники (1-based номера), роли донора. Кластеры отсортированы по размеру убыв."""
    page = presentation.get("pageSize", {})
    page_w = page.get("width", {}).get("magnitude", DEFAULT_PAGE_W) or DEFAULT_PAGE_W
    page_h = page.get("height", {}).get("magnitude", DEFAULT_PAGE_H) or DEFAULT_PAGE_H

    groups: dict[str, list[dict]] = {}
    for idx, slide in enumerate(presentation.get("slides", []), start=1):
        sig = build_layout_signature(slide, page_w, page_h)
        key = signature_key(sig)
        n_blocks, text_len = text_stats(slide)
        groups.setdefault(key, []).append({
            "number": idx,
            "slide_id": slide.get("objectId"),
            "slide": slide,
            "sig": sig,
            "n_blocks": n_blocks,
            "text_len": text_len,
        })

    clusters = []
    for members in groups.values():
        donor = choose_donor(members)
        donor_slide = donor["slide"]
        clusters.append({
            "archetype_guess": guess_archetype(donor["sig"], _slide_texts(donor_slide)),
            "donor": donor["number"],
            "donor_slide_id": donor["slide_id"],
            "members": [m["number"] for m in members],
            "roles": slide_roles(donor_slide),
            "_donor_slide": donor_slide,  # для палитры/превью; в JSON не пишем
        })
    clusters.sort(key=lambda c: len(c["members"]), reverse=True)
    return clusters


def filter_clusters(clusters: list[dict], min_count: int) -> list[dict]:
    """Оставляет только повторяющиеся раскладки (>= min_count слайдов).
    Шаблон - это то, что повторяется; редкие одиночки в палитру не идут."""
    return [c for c in clusters if len(c["members"]) >= min_count]


_COMMON_RATIOS = {
    (16, 9): "16:9", (4, 3): "4:3", (3, 2): "3:2", (1, 1): "1:1",
    (9, 16): "9:16", (3, 4): "3:4", (2, 3): "2:3",
}


def ratio_label(w: float, h: float) -> str:
    """Соотношение сторон -> ближайшая типовая метка ('16:9', '1:1', ...)."""
    if not w or not h:
        return "свободное"
    target = w / h
    best, best_diff = "свободное", 1e9
    for (rw, rh), label in _COMMON_RATIOS.items():
        diff = abs(target - rw / rh)
        if diff < best_diff:
            best, best_diff = label, diff
    return best


def _first_image_ratio(slide: dict) -> "str | None":
    """Пропорция рамки первой картинки слайда (для slides-image-layer)."""
    for el in slide.get("pageElements", []):
        if "image" in el:
            size = el.get("size", {})
            w = size.get("width", {}).get("magnitude", 0)
            h = size.get("height", {}).get("magnitude", 0)
            tr = el.get("transform", {})
            w *= tr.get("scaleX", 1) or 1
            h *= tr.get("scaleY", 1) or 1
            return ratio_label(w, h)
    return None


def build_palette(clusters: list[dict], source_id: str) -> dict:
    """JSON-палитра доноров для apply_edits / slides-image-layer."""
    archetypes = []
    for c in clusters:
        entry = {
            "name": c["archetype_guess"],
            "donor": c["donor"],
            "donor_slide_id": c["donor_slide_id"],
            "roles": c["roles"],
            "members_count": len(c["members"]),
        }
        ratio = _first_image_ratio(c["_donor_slide"])
        if ratio:
            entry["ratio_of_image"] = ratio
        archetypes.append(entry)
    return {"source_id": source_id, "archetypes": archetypes}


def slide_roles(slide: dict) -> list[str]:
    """Список ролей-слотов раскладки в порядке чтения: title/body/other:N/image:N/table:N.

    Те же правила текста, что в build_slide_map (title/body уникальны, прочее -> other:N),
    плюс картинки (image:N) и таблицы (table:N).
    """
    roles = []
    other_n = image_n = table_n = 0
    used = set()
    for el in slide.get("pageElements", []):
        if "image" in el:
            roles.append(f"image:{image_n}")
            image_n += 1
        elif "table" in el:
            roles.append(f"table:{table_n}")
            table_n += 1
        elif "shape" in el:
            text = extract_text(el["shape"].get("text", {}).get("textElements", [])).strip()
            if not text:
                continue
            ph = el["shape"].get("placeholder", {}).get("type", "")
            if ph in ("TITLE", "CENTERED_TITLE") and "title" not in used:
                role = "title"
            elif ph in ("BODY", "SUBTITLE") and "body" not in used:
                role = "body"
            else:
                role = f"other:{other_n}"
                other_n += 1
            used.add(role)
            roles.append(role)
    return roles


def build_contact_sheet_html(clusters: list[dict], thumbs: dict[int, str], title: str = "") -> str:
    """HTML-страница: карточка на кластер (превью донора, имя архетипа, размер, номер донора)."""
    cards = []
    for c in clusters:
        donor = c["donor"]
        thumb = thumbs.get(donor)
        img = (f'<img src="{_html.escape(thumb)}" alt="">' if thumb
               else '<div class="noimg">нет превью</div>')
        roles = ", ".join(c["roles"])
        cards.append(f"""
        <div class="card">
          {img}
          <div class="meta">
            <div class="name">{_html.escape(c['archetype_guess'])}</div>
            <div class="sub">донор #{donor} - слайдов: {len(c['members'])}</div>
            <div class="roles">{_html.escape(roles)}</div>
          </div>
        </div>""")
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<title>Палитра раскладок: {_html.escape(title)}</title>
<style>
  body {{ font-family: sans-serif; background:#111; color:#eee; padding:24px; }}
  h1 {{ font-size:18px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:16px; }}
  .card {{ background:#1c1c1c; border:1px solid #333; border-radius:8px; overflow:hidden; }}
  .card img {{ width:100%; display:block; }}
  .noimg {{ height:140px; display:flex; align-items:center; justify-content:center; color:#777; }}
  .meta {{ padding:10px; }}
  .name {{ font-weight:bold; }}
  .sub {{ color:#9a9; font-size:13px; margin:4px 0; }}
  .roles {{ color:#789; font-size:12px; }}
</style></head>
<body>
  <h1>Палитра раскладок: {_html.escape(title)} - {len(clusters)} раскладок</h1>
  <div class="grid">{''.join(cards)}</div>
</body></html>"""


# --- сетевой слой и CLI ---
import argparse

try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    build = None  # тесты чистых функций не требуют googleapiclient
    HttpError = Exception  # фолбэк, чтобы except HttpError был валиден без библиотеки

from google_to_text import extract_presentation_id
from text_to_google import get_credentials


def read_presentation(slides_service, presentation_id: str) -> dict:
    """Читает презентацию одним вызовом get()."""
    return slides_service.presentations().get(presentationId=presentation_id).execute()


def fetch_thumbnail_url(slides_service, presentation_id: str, page_object_id: str) -> str | None:
    """Временный contentUrl превью слайда через getThumbnail. None при ошибке."""
    try:
        resp = slides_service.presentations().pages().getThumbnail(
            presentationId=presentation_id, pageObjectId=page_object_id
        ).execute()
        return resp.get("contentUrl")
    except HttpError:
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Инвентаризация раскладок: палитра доноров из старой презентации")
    parser.add_argument("presentation", help="URL или ID презентации")
    parser.add_argument("-o", "--out", default=None,
                        help="Файл палитры JSON (по умолчанию template-palette.json)")
    parser.add_argument("--html", default=None,
                        help="Файл контактного листа HTML (по умолчанию template-contact.html)")
    parser.add_argument("--no-thumbs", action="store_true",
                        help="Не тянуть превью слайдов (быстрее, без картинок в контактном листе)")
    parser.add_argument("--min-count", type=int, default=4,
                        help="Минимум повторов раскладки для палитры (по умолчанию 4; редкие одиночки прячутся)")
    args = parser.parse_args()

    if build is None:
        print("Требуется googleapiclient. Установите: pip install google-api-python-client google-auth")
        sys.exit(1)

    source_id = extract_presentation_id(args.presentation)
    credentials = get_credentials()
    slides_service = build("slides", "v1", credentials=credentials)

    print("Загружаю презентацию...")
    try:
        presentation = read_presentation(slides_service, source_id)
    except HttpError as e:
        print(f"Ошибка Google API: {e}")
        sys.exit(1)

    pres_title = presentation.get("title", "Без названия")
    total = len(presentation.get("slides", []))
    clusters = cluster_slides(presentation)
    raw_count = len(clusters)
    kept = filter_clusters(clusters, args.min_count)
    hidden = raw_count - len(kept)
    hidden_slides = sum(len(c["members"]) for c in clusters if len(c["members"]) < args.min_count)
    clusters = kept
    print(f"   {pres_title}: {total} слайдов -> {raw_count} раскладок; "
          f"в палитре {len(kept)} (повторов >= {args.min_count}), "
          f"спрятано {hidden} редких ({hidden_slides} слайдов)")

    # превью доноров
    thumbs = {}
    if not args.no_thumbs:
        print("Тяну превью доноров...")
        for c in clusters:
            url = fetch_thumbnail_url(slides_service, source_id, c["donor_slide_id"])
            if url:
                thumbs[c["donor"]] = url

    import json as _json
    out_path = args.out or "template-palette.json"
    palette = build_palette(clusters, source_id)
    Path(out_path).write_text(
        _json.dumps(palette, ensure_ascii=False, indent=2), encoding="utf-8")

    html_path = args.html or "template-contact.html"
    Path(html_path).write_text(
        build_contact_sheet_html(clusters, thumbs, title=pres_title), encoding="utf-8")

    print(f"\nГотово:\n   палитра: {out_path}\n   контактный лист: {html_path}")
    print("\nРаскладки (по убыванию частоты):")
    for c in clusters[:25]:
        print(f"   #{c['donor']:>3}  {c['archetype_guess']:<28} x{len(c['members'])}")


if __name__ == "__main__":
    main()
